"""@Alanbix in the public chat: prompt layers and answer length."""
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import models
from app.ia_public_chat import asker_matches_block, build_public_system_prompt
from app.clock import utcnow


def test_public_prompt_has_public_rules_and_asker_card(db_session):
    player = db_session.query(models.User).filter(models.User.username == "Player1").first()
    player.team_name = "Les Rapides"
    db_session.commit()

    prompt, lang = build_public_system_prompt(db_session, models, player)

    assert lang == "fr"
    assert "RÈGLES DU CHAT PUBLIC" in prompt
    # The private assistant's rules (alerts, notifications, blocking) do not apply here
    assert "RÈGLES DE FONCTIONNEMENT" not in prompt
    assert '"Player1"' in prompt and "Les Rapides" in prompt
    assert "aucun match à venir pour Player1" in prompt


def test_asker_matches_block_lists_a_few_pending_matches(db_session):
    player = db_session.query(models.User).filter(models.User.username == "Player1").first()
    pending = [{"tournament": f"Cup {i}", "round": "WB Round 1", "opponent": "Player2", "status": "À venir"} for i in range(4)]
    pending[0]["opponent"] = "À déterminer (BYE)"
    data = json.dumps({"player": "Player1", "pending_matches": pending})
    with patch("app.ia_tools._tool_get_my_matches", return_value=data):
        block = asker_matches_block(db_session, models, player, "en")

    lines = block.splitlines()
    assert lines[0] == "- Upcoming matches of Player1:"
    assert lines[1] == "  - Cup 0, WB Round 1, opponent to be decided"
    assert lines[2] == "  - Cup 1, WB Round 1, against Player2"
    assert len(lines) == 4  # title + 3 matches


@pytest.mark.asyncio
async def test_public_answer_length_is_capped_below_the_context():
    from app.ia_queue import IAQueueManager, QueueEntry, PUBLIC_CHAT_MAX_ANSWER_TOKENS

    entry = QueueEntry(
        priority=10, created_at=time.time(), user_id=0, username="Alanbix", task_type="public_chat",
        payload={"ollama_host": "http://gpu1:11434", "model": "m", "messages": [{"role": "user", "content": "?"}],
                 "context_window": 32768},
    )
    res = MagicMock(status_code=200)
    res.json.return_value = {"message": {"content": "ok"}}
    client = AsyncMock()
    client.post = AsyncMock(return_value=res)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        await IAQueueManager()._process_public_chat(entry, entry.payload)

    options = client.post.call_args.kwargs["json"]["options"]
    assert options["num_predict"] == PUBLIC_CHAT_MAX_ANSWER_TOKENS
    assert options["num_ctx"] == 32768


def _msg(db, user=None, content="", minutes_ago=0, is_bot=False, reply_to=None, deleted=False):
    import datetime as dt
    m = models.PublicChatMessage(
        user_id=user.id if user else None, sender_name="Alanbix" if is_bot else None, is_bot=is_bot,
        content=content, reply_to_id=reply_to.id if reply_to else None, is_deleted=deleted,
        created_at=utcnow() - dt.timedelta(minutes=minutes_ago),
    )
    db.add(m)
    db.commit()
    return m


def test_thread_shows_speakers_replies_and_the_older_message_answered(db_session):
    from app.ia_public_chat import build_thread_message
    p1, p2, p3 = (db_session.query(models.User).filter(models.User.username == f"Player{i}").first() for i in (1, 2, 3))
    old = _msg(db_session, p2, "Qui veut un 1v1 sur Quake ?", minutes_ago=50)
    _msg(db_session, p3, "trop vieux, hors fenêtre", minutes_ago=45)
    _msg(db_session, p3, "message supprimé", minutes_ago=10, deleted=True)
    _msg(db_session, p3, "Moi je suis chaud", minutes_ago=5)
    _msg(db_session, None, "Je note, ça va saigner !", minutes_ago=4, is_bot=True)
    trigger = _msg(db_session, p1, "@Alanbix il a raison ou pas ?", reply_to=old)

    text = build_thread_message(db_session, models, trigger, "fr")

    assert "Qui veut un 1v1 sur Quake ?" in text  # older, but the asked message replies to it
    assert "hors fenêtre" not in text and "supprimé" not in text
    assert "Player3: Moi je suis chaud" in text
    assert "Alanbix (toi): Je note" in text
    lines = text.splitlines()
    assert lines[-2] == "Message auquel tu réponds, de Player1 :"
    assert lines[-1].endswith("Player1 (en réponse à Player2 « Qui veut un 1v1 sur Quake ? »): @Alanbix il a raison ou pas ?")
    # Oldest first, the asked message only once
    assert text.index("Quake") < text.index("chaud") < text.index("Je note")
    assert text.count("il a raison") == 1


def test_answering_an_alanbix_message_calls_alanbix(client, db_session):
    import app.routers.public_chat as pc
    bot = _msg(db_session, None, "Prêts pour la finale ?", is_bot=True)
    pc._last_ai_reply_time = 0
    with patch.object(pc, "_process_alanbix_public_reply", AsyncMock()) as reply:
        res = client.post("/public-chat/messages", json={"content": "Carrément !", "reply_to_id": bot.id})
    assert res.status_code == 200, res.text
    reply.assert_called_once()
    assert reply.call_args.args[0] == res.json()["id"]


def test_busy_alanbix_tells_the_sender_when_to_retry(client):
    import app.routers.public_chat as pc
    pc._last_ai_reply_time = time.time() - 5
    with patch.object(pc, "_process_alanbix_public_reply", AsyncMock()) as reply:
        res = client.post("/public-chat/messages", json={"content": "@Alanbix t'es là ?"})
    assert res.status_code == 200, res.text
    reply.assert_not_called()
    notice = res.json()["alanbix_notice"]
    assert notice["state"] == "busy" and 1 <= notice["retry_after"] <= 10


def test_alanbix_turned_off_tells_the_sender(client):
    import app.routers.public_chat as pc
    pc._last_ai_reply_time = 0
    real_config = pc.get_public_chat_config
    with patch.object(pc, "get_public_chat_config", side_effect=lambda db: {**real_config(db), "ai_mention_enabled": False}), \
         patch.object(pc, "_process_alanbix_public_reply", AsyncMock()) as reply:
        res = client.post("/public-chat/messages", json={"content": "@Alanbix coucou"})
    reply.assert_not_called()
    assert res.json()["alanbix_notice"] == {"state": "disabled"}


def test_plain_message_has_no_alanbix_notice(client):
    res = client.post("/public-chat/messages", json={"content": "Salut tout le monde"})
    assert "alanbix_notice" not in res.json()


async def _fail_twice(db_session, monkeypatch, instance, result):
    """Two failed @Alanbix calls in a row; returns the public lines posted and the admins' alerts."""
    import app.routers.public_chat as pc
    import app.ia_public_unavailable as down
    monkeypatch.setattr(down, "_last_alert", 0.0)
    monkeypatch.setattr(down, "_failures", 0)
    asker = db_session.query(models.User).first()
    admin = models.User(username="OrgaTest", is_admin=True)
    db_session.add(admin)
    db_session.commit()
    session = MagicMock()
    session.__enter__.return_value = db_session
    entry = MagicMock()
    entry.result_stream.get = AsyncMock(return_value=result)
    with patch("app.database.SessionLocal", return_value=session), \
         patch("app.routers.ia.pick_instance", AsyncMock(return_value=instance)), \
         patch("app.ia_queue.queue_manager.enqueue", AsyncMock(return_value=(entry, 1))), \
         patch.object(pc.ws_manager, "broadcast", AsyncMock()), \
         patch.object(pc.ws_manager, "send_to_user", AsyncMock()) as send:
        for text in ("@Alanbix quel match ?", "@Alanbix et maintenant ?"):
            trigger = _msg(db_session, asker, text)
            await pc._process_alanbix_public_reply(trigger.id, asker.id)
    lines = db_session.query(models.PublicChatMessage).filter(models.PublicChatMessage.is_bot == True).all()  # noqa: E712
    alerts = db_session.query(models.Notification).filter(models.Notification.user_id == admin.id).all()
    return lines, alerts, send


@pytest.mark.asyncio
async def test_alanbix_without_ai_instance_says_so_publicly_and_alerts_once(db_session, monkeypatch):
    """User's request (2026-11-10): a light-hearted public line, and an admin alert now and then, not each time."""
    from app.routers.awards import get_i18n_dict
    lines, alerts, send = await _fail_twice(db_session, monkeypatch, None, None)
    fr = get_i18n_dict("fr")
    variants = {fr[f"public_chat_alanbix_down_{i}"] for i in range(1, 6)}
    assert len(lines) == 2 and all(m.content in variants and m.reply_to_id for m in lines)
    assert len(alerts) == 1 and alerts[0].metadata_json["i18n"]["body"] == "notif_public_ai_down_no_instance"
    assert not any(c.args[1].get("type") == "public_chat_alanbix_notice" for c in send.await_args_list)


@pytest.mark.asyncio
async def test_missing_model_alert_names_the_model(db_session, monkeypatch):
    instance = {"url": "http://gpu1:11434", "model": "gemma4:e4b"}
    result = {"done": True, "error": True, "result": "model 'gemma4:e4b' not found", "code": "model_missing"}
    with patch("app.ia_public_chat.knowledge_block", AsyncMock(return_value="")):
        lines, alerts, _ = await _fail_twice(db_session, monkeypatch, instance, result)
    assert len(lines) == 2 and len(alerts) == 1
    assert alerts[0].metadata_json["i18n"]["body"] == "notif_public_ai_down_model_missing"
    assert "gemma4:e4b" in alerts[0].content


def test_admin_alert_waits_and_then_counts_the_failures(monkeypatch):
    import app.ia_public_unavailable as down
    monkeypatch.setattr(down, "_last_alert", 0.0)
    monkeypatch.setattr(down, "_failures", 0)
    t0 = 10_000.0
    assert down.should_alert(t0) == 1
    assert down.should_alert(t0 + 60) == 0 and down.should_alert(t0 + 120) == 0
    assert down.should_alert(t0 + down.ADMIN_ALERT_EVERY + 1) == 3


def test_public_tools_only_read_public_data():
    from app.ia_public_chat import PUBLIC_TOOL_NAMES, public_tools
    from app.ia_tools import TOOL_DEFINITIONS
    names = {t["function"]["name"] for t in public_tools({})}
    assert names == PUBLIC_TOOL_NAMES  # every allowed name exists
    known = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    for private in ("get_notifications", "announce_to_all", "send_notification_to_player", "call_admin",
                    "block_user_from_ia", "suggest_rag_entry", "ping_host", "scan_local_network"):
        assert private in known and private not in names
    assert public_tools({"tool_calling_mode": "disabled"}) == []


@pytest.mark.asyncio
async def test_public_answer_runs_a_tool_for_the_asker():
    from app.ia_queue import IAQueueManager, QueueEntry
    from app.ia_public_chat import public_tools

    tools = public_tools({})
    entry = QueueEntry(
        priority=10, created_at=time.time(), user_id=0, username="Alanbix", task_type="public_chat",
        payload={"ollama_host": "http://gpu1:11434", "model": "m", "context_window": 16384, "asker_id": 5,
                 "tools": tools, "messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "quel match ?"}]},
    )
    call = MagicMock(status_code=200)
    call.json.return_value = {"message": {"content": "", "tool_calls": [{"function": {"name": "get_my_matches", "arguments": {}}}]}}
    answer = MagicMock(status_code=200)
    answer.json.return_value = {"message": {"content": "Tu joues contre Player2 en WB Round 1."}}
    client = AsyncMock()
    client.post = AsyncMock(side_effect=[call, answer])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client), \
         patch("app.ia_tools.execute_tool", AsyncMock(return_value='{"pending_matches": []}')) as run:
        await IAQueueManager()._process_public_chat(entry, entry.payload)

    run.assert_called_once_with("get_my_matches", {}, user_id=5, conversation_id=0)
    assert client.post.call_count == 2  # the round without tool call is the answer, no extra request
    first = client.post.call_args_list[0].kwargs["json"]
    assert first["tools"] == tools and first["messages"][1]["content"].startswith("You can look up")
    result = await entry.result_stream.get()
    assert result["result"] == "Tu joues contre Player2 en WB Round 1."


def test_team_roster_gives_each_member_seat(db_session):
    from app.ia_tools import _tool_get_team_roster
    t = models.Tournament(name="BF4", status="RUNNING", config={"use_teams": True})
    db_session.add(t)
    db_session.add(models.RoomMap(name="Main Room", layout={"tables": [{"id": "T3", "label": "Fond de salle"}], "seats": []}))
    db_session.commit()
    team = models.TournamentTeam(tournament_id=t.id, name="Bouzeux")
    db_session.add(team)
    db_session.commit()
    p1, p2 = (db_session.query(models.User).filter(models.User.username == f"Player{i}").first() for i in (1, 2))
    p1.seat_id, p2.seat_id = "T3_S7", None
    db_session.add_all([models.TournamentTeamMember(team_id=team.id, user_id=p.id) for p in (p1, p2)])
    db_session.commit()

    data = json.loads(_tool_get_team_roster(db_session, models, {"team_name": "bouzeux"}))

    members = data["tournament_teams"][0]["members"]
    assert {"username": "Player1", "seat": "Fond de salle, place 7"} in members
    assert {"username": "Player2", "seat": "Non assigné"} in members


def test_player_blocked_from_the_ai_cannot_call_alanbix(client, db_session):
    from app.auth import get_current_user
    from app.main import app
    player = models.User(username="blockedone", hashed_password="x", ia_blocked=True)
    db_session.add(player)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: player
    res = client.post("/public-chat/messages", json={"content": "@Alanbix salut"})
    assert res.json()["alanbix_notice"] == {"state": "blocked"}
