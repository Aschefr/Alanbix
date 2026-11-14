"""@Alanbix is told who the players named in a public chat question are, with their block status today."""
import datetime as dt

from app import models
from app.clock import utcnow
from app.ia_named_players import named_players, named_players_block, set_ia_blocked
from app.ia_public_chat import build_public_system_prompt


def _user(db, name):
    return db.query(models.User).filter(models.User.username == name).first()


def _add(db, name, **fields):
    user = models.User(username=name, hashed_password="x", **fields)
    db.add(user)
    db.commit()
    return user


def test_named_player_is_found_whatever_the_case_and_not_inside_a_word(db_session):
    asker = _user(db_session, "Player1")
    _add(db_session, "Zorglub")
    assert [u.username for u in named_players(db_session, models, "@Alanbix ça te dirait que zorglub revienne ?", asker)] == ["Zorglub"]
    assert named_players(db_session, models, "@Alanbix les zorglubiens arrivent", asker) == []
    # The asker and usernames too short to tell from a word are left out
    _add(db_session, "le")
    assert named_players(db_session, models, "@Alanbix le Player1 c'est moi", asker) == []


def test_no_card_without_a_named_player(db_session):
    asker = _user(db_session, "Player1")
    assert named_players_block(db_session, models, "@Alanbix tu aimes quoi comme musique ?", asker, "fr") == ""
    prompt, _ = build_public_system_prompt(db_session, models, asker, "@Alanbix une recette de crêpes ?")
    assert "Joueurs nommés" not in prompt


def test_plain_player_is_just_a_registered_player(db_session):
    asker = _user(db_session, "Player1")
    block = named_players_block(db_session, models, "@Alanbix tu connais Player2 ?", asker, "fr")
    assert "- Player2 : joueur inscrit à cette LAN." in block
    assert "pas des personnages" in block and "bloqué" not in block.split("\n")[1]


def test_blocked_then_unblocked_player_is_up_to_date(db_session):
    asker = _user(db_session, "Player1")
    zorg = _add(db_session, "Zorglub")
    question = "@Alanbix ça te dirait que Zorglub revienne te parler ?"

    set_ia_blocked(zorg, True)
    zorg.public_chat_muted_until = utcnow() + dt.timedelta(hours=3)
    db_session.commit()
    line = named_players_block(db_session, models, question, asker, "fr").split("\n")[1]
    assert "toujours bloqué" in line and "muet dans le chat public jusqu'au" in line

    set_ia_blocked(zorg, False)
    zorg.public_chat_muted_until = None
    db_session.commit()
    line = named_players_block(db_session, models, question, asker, "fr").split("\n")[1]
    assert "débloqué par un administrateur le" in line and "toujours bloqué" not in line and "muet" not in line

    set_ia_blocked(zorg, True)   # blocked again: the old lifting no longer counts
    db_session.commit()
    assert zorg.ia_unblocked_at is None
    assert "toujours bloqué" in named_players_block(db_session, models, question, asker, "fr")


def test_block_older_than_the_date_column_is_read_from_its_notification(db_session):
    asker = _user(db_session, "Player1")
    zorg = _add(db_session, "Zorglub")
    db_session.add(models.Notification(
        user_id=zorg.id, type="system", title="t", content="c",
        metadata_json={"i18n": {"title": "notif_ia_blocked_title"}},
        created_at=dt.datetime(2026, 11, 12, 18, 0)))
    db_session.commit()
    line = named_players_block(db_session, models, "@Alanbix et Zorglub ?", asker, "fr").split("\n")[1]
    assert line == "- Zorglub : joueur inscrit à cette LAN ; bloqué de l'assistant le 12/11 19:00, débloqué depuis par un administrateur."

    zorg.ia_blocked = True   # still blocked, from before the column existed
    db_session.commit()
    assert "depuis le 12/11 19:00, toujours bloqué" in named_players_block(db_session, models, "@Alanbix et Zorglub ?", asker, "fr")


def test_the_reason_of_a_block_is_never_given(db_session):
    asker = _user(db_session, "Player1")
    zorg = _add(db_session, "Zorglub")
    set_ia_blocked(zorg, True)
    db_session.add(models.Notification(user_id=zorg.id, type="system", title="t",
                                       content="Raison : insultes répétées",
                                       metadata_json={"i18n": {"title": "notif_ia_blocked_title"}}))
    db_session.commit()
    for lang in ("fr", "en", "es"):
        block = named_players_block(db_session, models, "@Alanbix Zorglub ?", asker, lang)
        assert "insultes" not in block and "Zorglub" in block


def test_card_reaches_the_public_prompt(db_session):
    asker = _user(db_session, "Player1")
    prompt, _ = build_public_system_prompt(db_session, models, asker, "@Alanbix Player2 est là ?")
    assert "Joueurs nommés dans le message" in prompt and "- Player2 :" in prompt


def test_him_in_the_next_message_keeps_the_card(db_session):
    """ "tu ne te rappelles pas de tes conversations avec lui ?" names nobody: the card of the player named
    in the asker's previous message is still given (Veille, 12th round)."""
    from app.ia_named_players import asker_earlier_text
    asker = _user(db_session, "Player1")
    _add(db_session, "Zorglub")
    for text in ("@Alanbix ça te dirait que Zorglub revienne te parler ?", "@Alanbix tu ne te rappelles pas de lui ?"):
        msg = models.PublicChatMessage(user_id=asker.id, content=text, is_deleted=False, created_at=utcnow())
        db_session.add(msg)
        db_session.commit()
    earlier = asker_earlier_text(db_session, models, msg)
    assert "Zorglub" in earlier and "rappelles" not in earlier
    prompt, _ = build_public_system_prompt(db_session, models, asker, msg.content, earlier)
    assert "- Zorglub :" in prompt


def test_public_rules_say_his_memory_is_the_thread():
    """Asked about talks he cannot see, he answered "Bien sûr que je m'en souviens !" 10 times in 10
    (Veille, 13th round: 0/10 -> 8/10 honest with this rule)."""
    from app.ia_public_chat import PUBLIC_RULES
    assert "Ta mémoire, c'est le fil ci-dessous et rien d'autre" in PUBLIC_RULES["fr"]
    assert "Your memory is the thread below and nothing else" in PUBLIC_RULES["en"]
    assert "Tu memoria es el hilo de abajo y nada más" in PUBLIC_RULES["es"]
