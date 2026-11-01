"""@Alanbix in the public chat: prompt layers and answer length."""
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import models
from app.ia_public_chat import asker_matches_block, build_public_system_prompt


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
        created_at=dt.datetime.utcnow() - dt.timedelta(minutes=minutes_ago),
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
