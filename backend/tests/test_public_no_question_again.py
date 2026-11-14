"""@Alanbix does not ask the same player a question in two answers in a row in the public chat."""
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import models
from app.clock import utcnow
from app.ia_public_chat import NO_QUESTION_AGAIN, no_question_again


def _user(db, name):
    return db.query(models.User).filter(models.User.username == name).first()


def _say(db, content, user=None, reply_to=None, minutes_ago=0, is_bot=False):
    msg = models.PublicChatMessage(
        user_id=user.id if user else None, sender_name=None if user else "Alanbix", is_bot=is_bot,
        content=content, reply_to_id=reply_to.id if reply_to else None, is_deleted=False,
        created_at=utcnow() - dt.timedelta(minutes=minutes_ago))
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _alanbix(db, content, reply_to, minutes_ago=0):
    return _say(db, content, reply_to=reply_to, minutes_ago=minutes_ago, is_bot=True)


def test_line_added_when_last_answer_to_this_player_asked_a_question(db_session):
    p1 = _user(db_session, "Player1")
    first = _say(db_session, "@Alanbix j'ai eu mon permis !", p1, minutes_ago=3)
    _alanbix(db_session, "Bravo ! Tu vas rouler où en premier ?", first, minutes_ago=2)
    trigger = _say(db_session, "@Alanbix à la mer je pense", p1)
    assert no_question_again(db_session, models, trigger, "fr") == NO_QUESTION_AGAIN["fr"]
    assert no_question_again(db_session, models, trigger, "en") == NO_QUESTION_AGAIN["en"]


def test_no_line_when_last_answer_had_no_question(db_session):
    p1 = _user(db_session, "Player1")
    first = _say(db_session, "@Alanbix j'ai eu mon permis !", p1, minutes_ago=5)
    _alanbix(db_session, "Tu veux fêter ça ?", first, minutes_ago=4)
    second = _say(db_session, "@Alanbix oui ce soir", p1, minutes_ago=3)
    _alanbix(db_session, "Grave mérité, profite bien.", second, minutes_ago=2)
    trigger = _say(db_session, "@Alanbix merci !", p1)
    # Only the latest answer to this player counts
    assert no_question_again(db_session, models, trigger, "fr") == ""


def test_only_answers_to_the_same_player_count(db_session):
    p1, p2 = _user(db_session, "Player1"), _user(db_session, "Player2")
    other = _say(db_session, "@Alanbix je suis crevé", p2, minutes_ago=2)
    _alanbix(db_session, "Grosse nuit ? Tu as dormi combien ?", other, minutes_ago=1)
    trigger = _say(db_session, "@Alanbix j'ai fini mon déménagement", p1)
    assert no_question_again(db_session, models, trigger, "fr") == ""


def test_no_line_without_a_previous_answer_or_after_the_thread_window(db_session):
    p1 = _user(db_session, "Player1")
    trigger = _say(db_session, "@Alanbix salut", p1)
    assert no_question_again(db_session, models, trigger, "fr") == ""

    old = _say(db_session, "@Alanbix ça va ?", p1, minutes_ago=50)
    _alanbix(db_session, "Oui et toi ?", old, minutes_ago=49)   # outside the 30 min thread
    later = _say(db_session, "@Alanbix je suis de retour", p1)
    assert no_question_again(db_session, models, later, "fr") == ""


def test_deleted_answer_is_ignored(db_session):
    p1 = _user(db_session, "Player1")
    first = _say(db_session, "@Alanbix hello", p1, minutes_ago=2)
    answer = _alanbix(db_session, "Hello, quoi de neuf ?", first, minutes_ago=1)
    answer.is_deleted = True
    db_session.commit()
    trigger = _say(db_session, "@Alanbix rien de spécial", p1)
    assert no_question_again(db_session, models, trigger, "fr") == ""


def test_line_translated_in_every_language():
    assert set(NO_QUESTION_AGAIN) == {"fr", "en", "es"}
    assert all("?" not in line for line in NO_QUESTION_AGAIN.values())


@pytest.mark.asyncio
async def test_line_reaches_the_model_at_the_end_of_the_system_prompt(db_session):
    import app.routers.public_chat as pc
    p1 = _user(db_session, "Player1")
    first = _say(db_session, "@Alanbix j'ai eu mon permis !", p1, minutes_ago=2)
    _alanbix(db_session, "Bravo ! Tu vas rouler où en premier ?", first, minutes_ago=1)
    trigger = _say(db_session, "@Alanbix à la mer", p1)
    session = MagicMock()
    session.__enter__.return_value = db_session
    entry = MagicMock()
    entry.result_stream.get = AsyncMock(return_value={"done": True, "error": True, "result": "stop"})
    with patch("app.database.SessionLocal", return_value=session), \
         patch("app.routers.ia.pick_instance", AsyncMock(return_value={"url": "http://gpu1:11434", "model": "m"})), \
         patch("app.ia_public_chat.knowledge_block", AsyncMock(return_value="")), \
         patch("app.ia_queue.queue_manager.enqueue", AsyncMock(return_value=(entry, 1))) as enqueue, \
         patch.object(pc.ws_manager, "broadcast", AsyncMock()), \
         patch.object(pc.ws_manager, "send_to_user", AsyncMock()):
        await pc._process_alanbix_public_reply(trigger.id, p1.id)
    system = enqueue.await_args.args[0].payload["messages"][0]["content"]
    assert system.endswith(NO_QUESTION_AGAIN["fr"])
