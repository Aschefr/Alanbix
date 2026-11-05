"""The admins' alert when the AI cannot write the closing messages of a tournament."""
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy.orm import sessionmaker
from app import models
from app.routers.tournament_ai_messages import _generate_tournament_notifications


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,title,body", [
    ("en", "AI failure — Night Cup", "Generating the personalised messages failed."),
    ("fr", "Échec IA — Night Cup", "La génération de messages personnalisés a échoué."),
])
async def test_ai_failure_is_stored_in_the_language_of_the_lan(db_session, lang, title, body):
    db_session.add(models.SystemConfig(key="lan_default_language", value=lang))
    db_session.commit()
    sessions = sessionmaker(bind=db_session.get_bind())

    with patch("app.database.SessionLocal", sessions), \
            patch("app.routers.ia.pick_instance", AsyncMock(side_effect=RuntimeError("boom"))):
        await _generate_tournament_notifications(7, "Night Cup", "Game", [], [], False)

    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    db_session.expire_all()
    notif = db_session.query(models.Notification).filter(models.Notification.user_id == admin.id).one()
    assert notif.title == f"⚠️ {title}"
    assert notif.content == f"{body}\nRuntimeError: boom"
    # What the app needs to show it in each admin's own language
    assert notif.metadata_json["tournament_name"] == "Night Cup"
    assert notif.metadata_json["error_detail"] == "RuntimeError: boom"
    assert notif.metadata_json["error"] is True
