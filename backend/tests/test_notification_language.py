"""Notifications written by the server: stored in the LAN's language, with what the app needs
to show them in each reader's language (data.i18n, read by frontend/src/lib/notifText.js)."""
import json
import pytest
from app import models
from app.ia_tools import _tool_block_user_from_ia, _tool_announce_to_all
from app.routers.notifications import localized_text


def _set_lan_language(db_session, lang):
    db_session.add(models.SystemConfig(key="lan_default_language", value=lang))
    db_session.commit()


@pytest.mark.parametrize("lang,title", [
    ("en", "📣 Admin call, help requested"),
    ("es", "📣 Llamada al admin, ayuda solicitada"),
    ("fr", "📣 Appel admin, aide demandée"),
    ("de", "📣 Appel admin, aide demandée"),  # a language without the key falls back to French
])
def test_text_follows_the_lan_language(db_session, lang, title):
    _set_lan_language(db_session, lang)
    got_title, body, meta = localized_text(db_session, "notif_admin_call_title", "notif_admin_call_body",
                                           {"username": "Zephyr", "question": "Où est le Wi-Fi ?"}, icon="📣")
    assert got_title == title
    assert "Zephyr" in body and "Où est le Wi-Fi ?" in body
    assert meta == {"i18n": {"title": "notif_admin_call_title", "body": "notif_admin_call_body", "icon": "📣",
                             "params": {"username": "Zephyr", "question": "Où est le Wi-Fi ?"}}}


def test_someone_s_own_message_is_kept_as_written(db_session):
    _set_lan_language(db_session, "en")
    title, body, meta = localized_text(db_session, "notif_admin_reply_title", params={"admin": "Orbit"},
                                       icon="🛡️", body="Salut, on regarde ça")
    assert title == "🛡️ Message from Orbit"
    assert body == "Salut, on regarde ça"
    assert "body" not in meta["i18n"]


def test_blocked_player_and_admins_get_translatable_notices(db_session):
    _set_lan_language(db_session, "en")
    player = db_session.query(models.User).filter(models.User.username == "Player3").first()
    json.loads(_tool_block_user_from_ia(db_session, models, {"reason": "Insultes répétées."}, player.id))

    mine = db_session.query(models.Notification).filter(models.Notification.user_id == player.id).one()
    assert mine.title == "AI assistant access blocked"
    assert mine.content.endswith(": Insultes répétées.")  # no doubled full stop
    assert mine.metadata_json["i18n"]["body"] == "notif_ia_blocked_body"

    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    theirs = db_session.query(models.Notification).filter(models.Notification.user_id == admin.id).one()
    assert theirs.title == "Player blocked from the AI assistant"
    assert theirs.metadata_json["i18n"]["params"] == {"username": "Player3", "reason": "Insultes répétées"}


def test_announcement_title_is_translatable_and_text_untouched(db_session):
    _set_lan_language(db_session, "es")
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    _tool_announce_to_all(db_session, models, {"content": "Pizza dans 10 minutes"}, admin.id)
    notif = db_session.query(models.Notification).filter(models.Notification.user_id == admin.id).one()
    assert notif.title == "📢 Anuncio general"
    assert notif.content == "Pizza dans 10 minutes"
    assert notif.metadata_json["i18n"] == {"title": "notif_announcement_title", "icon": "📢", "params": {}}


def test_test_notification(client, db_session):
    _set_lan_language(db_session, "en")
    assert client.post("/notifications/test").status_code == 200
    notif = db_session.query(models.Notification).order_by(models.Notification.id.desc()).first()
    assert notif.title == "🔔 Alanbix test"
    assert notif.content == "Your mobile notifications work perfectly!"
    assert notif.metadata_json["is_test"] is True
    assert notif.metadata_json["i18n"]["body"] == "notif_test_body"
