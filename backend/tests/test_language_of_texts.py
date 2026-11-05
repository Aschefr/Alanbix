"""Texts the server writes follow the language asked for, or the language of the LAN."""
import pytest
from app import models
from app.routers.tournament_notify import _notify_match_ready


@pytest.mark.parametrize("lang,title", [
    ("en", "King of the LAN"),
    ("es", "Rey de la LAN"),
    ("fr", "Roi de la LAN"),
    ("unknown", "Roi de la LAN"),
])
def test_admin_awards_use_the_requested_language(client, lang, title):
    res = client.get(f"/admin/awards?lang={lang}")
    assert res.status_code == 200
    premier = next(a for a in res.json() if a["key"] == "premier")
    assert premier["default_title"] == title


@pytest.fixture
def duel(db_session):
    a = models.User(username="notif_lang_a", hashed_password="x")
    b = models.User(username="notif_lang_b", hashed_password="x")
    tournament = models.Tournament(name="Night Cup", status="RUNNING")
    db_session.add_all([a, b, tournament])
    db_session.commit()
    return a, b, tournament


def _set_lan_language(db_session, lang):
    row = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    if row:
        row.value = lang
    else:
        db_session.add(models.SystemConfig(key="lan_default_language", value=lang))
    db_session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,title,body", [
    ("en", "Match ready!", "Your match against notif_lang_b is ready in Night Cup."),
    ("fr", "Match prêt !", "Votre match contre notif_lang_b est prêt dans Night Cup."),
])
async def test_match_ready_is_stored_in_the_language_of_the_lan(db_session, duel, lang, title, body):
    a, b, tournament = duel
    _set_lan_language(db_session, lang)

    await _notify_match_ready(db_session, tournament, {"p": [a.id, b.id], "score": [0, 0], "id": {"s": 1, "r": 1, "m": 1}})

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == a.id).one()
    assert notif.title == f"⚔️ {title}"
    assert notif.content == body
    # What the app needs to show it in each player's own language
    assert notif.metadata_json["opponent"] == "notif_lang_b"
    assert notif.metadata_json["tournament_name"] == "Night Cup"
