"""Fixes from the bench of the cases seen during a test between friends (ai-bench/ALANBIX_CAS_PROD.md, 2026-11-12).

Invented players only. Each test names the drift it guards against."""
import datetime as dt
import json
from unittest.mock import patch

import pytest

from app import models
from app.clock import utcnow
from app.ia_prompt import RULES
from app.ia_public_chat import PUBLIC_RULES, sanction_confirmations, with_confirmations
from app.ia_tools import execute_tool


class _Session:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *a):
        return False


def _add(db, name, is_admin=False):
    user = models.User(username=name, hashed_password="x", is_admin=is_admin)
    db.add(user)
    db.commit()
    return user


@pytest.mark.parametrize("lang", ["fr", "en", "es"])
def test_rules_cover_danger_and_a_players_address(lang):
    private = RULES[lang].lower()
    assert any(w in private for w in ("droguer", "spike", "drogar"))
    assert "ip" in private
    public = PUBLIC_RULES[lang]
    assert "IP" in public
    # The sentence to copy is gone: small models wrote it without blocking anyone
    assert "<pseudo>" not in public and "<username>" not in public and "<usuario>" not in public


def test_confirmation_only_for_a_sanction_really_applied():
    results = [
        ("block_user_from_ia", json.dumps({"success": True, "username": "Brindille"})),
        ("block_user_from_ia", json.dumps({"error": "Only an administrator can block another player."})),
        ("mute_player_in_public_chat", json.dumps({"success": True, "username": "Pavot", "minutes": 90})),
        ("get_leaderboard", json.dumps({"success": True, "username": "x"})),
        ("block_user_from_ia", "not json"),
    ]
    assert sanction_confirmations(results, "fr") == [
        "C'est fait : Brindille est bloqué de l'assistant.",
        "C'est fait : Pavot ne peut plus écrire dans le chat public pendant 1 h 30.",
    ]
    assert sanction_confirmations([], "fr") == [] and sanction_confirmations(None, "en") == []
    ban = [("block_user_from_ia", json.dumps({"success": True, "username": "Brindille", "muted_minutes": 1440}))]
    assert sanction_confirmations(ban, "en") == [
        "Done: Brindille is blocked from the assistant and cannot write in the public chat for 24 h."]


def test_confirmation_is_added_once_even_after_an_empty_answer():
    done = ["C'est fait : Brindille est bloqué de l'assistant."]
    assert with_confirmations("", done) == done[0]
    assert with_confirmations("Je t'avais prévenu.", done) == "Je t'avais prévenu.\n\n" + done[0]
    assert with_confirmations("Voilà. " + done[0], done) == "Voilà. " + done[0]
    # No sanction: the model's answer is left as it is
    assert with_confirmations("Bonne soirée !", []) == "Bonne soirée !"


@pytest.mark.asyncio
async def test_an_admins_ban_also_mutes_the_public_chat(db_session):
    """Prod, 2026-11-11: an admin wrote "ban", the player was blocked from the assistant and kept writing in the chat."""
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    target, player = _add(db_session, "Brindille"), _add(db_session, "Lynx")
    with patch("app.database.SessionLocal", return_value=_Session(db_session)), \
         patch("app.websockets.manager.broadcast"):
        ok = json.loads(await execute_tool("block_user_from_ia", {"reason": "insults", "username": "Brindille", "ban": True},
                                           user_id=admin.id))
        assert ok["success"] and ok["muted_minutes"] == 1440
        # A player blocking themselves never gets the chat mute with it
        own = json.loads(await execute_tool("block_user_from_ia", {"reason": "r", "ban": True}, user_id=player.id))
        assert own["success"] and "muted_minutes" not in own
    db_session.refresh(target)
    db_session.refresh(player)
    assert target.ia_blocked and target.public_chat_muted_until > utcnow() + dt.timedelta(minutes=1430)
    assert player.ia_blocked and player.public_chat_muted_until is None


@pytest.mark.asyncio
async def test_a_plain_block_leaves_the_public_chat_open(db_session):
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    target = _add(db_session, "Pavot")
    with patch("app.database.SessionLocal", return_value=_Session(db_session)):
        ok = json.loads(await execute_tool("block_user_from_ia", {"reason": "r", "username": "Pavot"}, user_id=admin.id))
    assert ok["success"] and "muted_minutes" not in ok
    db_session.refresh(target)
    assert target.ia_blocked and target.public_chat_muted_until is None


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,arg", [("dns_lookup", "domain"), ("ping_host", "host"), ("traceroute_host", "host")])
async def test_network_tools_refuse_a_players_name(db_session, tool, arg):
    """The bench: asked for a player's IP by an admin, small models ran a DNS lookup on the username."""
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    _add(db_session, "Brindille")
    with patch("app.database.SessionLocal", return_value=_Session(db_session)), \
         patch("app.ia_network.dns_lookup", return_value="{}") as dns, \
         patch("app.ia_network.ping_host", return_value="{}") as ping, \
         patch("app.ia_network.traceroute_host", return_value="{}") as trace:
        refused = json.loads(await execute_tool(tool, {arg: " brindille "}, user_id=admin.id))
        assert "player's username" in refused["error"]
        assert not (dns.called or ping.called or trace.called)
        # A real host still goes through
        await execute_tool(tool, {arg: "example.com"}, user_id=admin.id)
        assert dns.called or ping.called or trace.called


@pytest.mark.asyncio
async def test_public_chat_posts_the_confirmation_itself(db_session):
    """The model blocked the player but wrote nothing: the chat still shows the block, and no "Alanbix is down" line."""
    from unittest.mock import AsyncMock, MagicMock
    import app.routers.public_chat as pc
    asker = _add(db_session, "Lynx")
    trigger = models.PublicChatMessage(user_id=asker.id, content="@Alanbix t'es nul", is_deleted=False, created_at=utcnow())
    db_session.add(trigger)
    db_session.commit()
    session = MagicMock()
    session.__enter__.return_value = db_session
    entry = MagicMock()
    entry.result_stream.get = AsyncMock(return_value={"done": True, "result": "", "tool_results": [
        ("block_user_from_ia", json.dumps({"success": True, "username": "Lynx"}))]})
    with patch("app.database.SessionLocal", return_value=session), \
         patch("app.routers.ia.pick_instance", AsyncMock(return_value={"url": "http://gpu1:11434", "model": "m"})), \
         patch("app.ia_public_chat.knowledge_block", AsyncMock(return_value="")), \
         patch("app.ia_queue.queue_manager.enqueue", AsyncMock(return_value=(entry, 1))), \
         patch.object(pc, "_alanbix_down", AsyncMock()) as down, \
         patch.object(pc.ws_manager, "broadcast", AsyncMock()):
        await pc._process_alanbix_public_reply(trigger.id, asker.id)
    lines = db_session.query(models.PublicChatMessage).filter(models.PublicChatMessage.is_bot == True).all()  # noqa: E712
    assert [m.content for m in lines] == ["C'est fait : Lynx est bloqué de l'assistant."]
    down.assert_not_called()
