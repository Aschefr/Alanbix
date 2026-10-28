import pytest
import datetime
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app import models, database, auth
from app.websockets import manager as ws_manager
from app.routers.notifications import notify_user


@pytest.fixture
def test_user(db_session):
    user = models.User(username="test_notif_user", hashed_password="dummy_password")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def peer_user(db_session):
    peer = models.User(username="peer_notif_user", hashed_password="dummy_password")
    db_session.add(peer)
    db_session.commit()
    db_session.refresh(peer)
    return peer


@pytest.mark.asyncio
async def test_notify_user_creates_record_and_emits_push(db_session, test_user):
    """Verify that notify_user creates a Notification row and emits targeted push event."""
    mock_ws = AsyncMock()
    await ws_manager.connect(mock_ws)
    await ws_manager.register_user(mock_ws, test_user.id)
    mock_ws.send_json.reset_mock()

    try:
        notif = await notify_user(
            db=db_session,
            user_id=test_user.id,
            category="match_ready",
            title="⚔️ Match prêt !",
            body="Votre match contre Rival est prêt.",
            link="/dashboard/tournaments/1",
            data={"tournament_id": 1}
        )

        assert notif.id is not None
        assert notif.category == "match_ready"
        assert notif.link == "/dashboard/tournaments/1"

        # Verify targeted push event was sent to user's socket
        calls = [c[0][0] for c in mock_ws.send_json.call_args_list]
        push_calls = [c for c in calls if c.get("type") == "push"]
        assert len(push_calls) == 1
        assert push_calls[0]["category"] == "match_ready"
        assert push_calls[0]["title"] == "⚔️ Match prêt !"
        assert push_calls[0]["link"] == "/dashboard/tournaments/1"
    finally:
        await ws_manager.disconnect(mock_ws)


@pytest.mark.asyncio
async def test_device_registration_and_token_auth(db_session, client):
    """Verify companion device registration returns dev_ token valid for auth."""
    # 1. Register device via API (user is admin via client fixture)
    res = client.post(
        "/api/devices",
        json={"platform": "android", "name": "Pixel 8 Pro"}
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "registered"
    assert data["token"].startswith("dev_")
    device_token = data["token"]

    admin_user = db_session.query(models.User).filter(models.User.username == "admin").first()

    # 2. Verify get_user_id_from_token and get_current_user resolve this device token
    resolved_uid = auth.get_user_id_from_token(device_token, db=db_session)
    assert resolved_uid == admin_user.id
    resolved_user = await auth.get_current_user(db=db_session, token=device_token)
    assert resolved_user.id == admin_user.id

    # 3. List devices
    list_res = client.get("/api/devices/me")
    assert list_res.status_code == 200
    devices = list_res.json()
    assert len(devices) >= 1
    assert any(d["name"] == "Pixel 8 Pro" for d in devices)

    # 4. Revoke device
    device_id = data["id"]
    del_res = client.delete(f"/api/devices/{device_id}")
    assert del_res.status_code == 200

    # 5. Token is no longer valid
    assert auth.get_user_id_from_token(device_token, db=db_session) is None


@pytest.mark.asyncio
async def test_get_missed_events(db_session, client):
    """Verify that GET /notifications/missed returns notifications and unread PMs chronologically."""
    admin_user = db_session.query(models.User).filter(models.User.username == "admin").first()
    player1 = db_session.query(models.User).filter(models.User.username == "Player1").first()

    now = datetime.datetime.utcnow()
    past = now - datetime.timedelta(minutes=10)

    # 1. Add a notification for admin
    notif = models.Notification(
        user_id=admin_user.id,
        type="match_ready",
        category="match_ready",
        title="⚔️ Match 1",
        content="Pret a jouer",
        link="/dashboard/tournaments/1",
        created_at=now
    )
    db_session.add(notif)

    # 2. Add an unread private message from player1 to admin
    pm = models.PrivateMessage(
        sender_id=player1.id,
        receiver_id=admin_user.id,
        content="Salut tu es dispo ?",
        created_at=now,
        is_read=False
    )
    db_session.add(pm)
    db_session.commit()

    # Query missed events since past
    res = client.get(f"/notifications/missed?since={past.isoformat()}")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 2
    categories = [e["category"] for e in body["events"]]
    assert "match_ready" in categories
    assert "private_message" in categories


@pytest.mark.asyncio
async def test_send_test_notification_endpoint(db_session, client):
    """Verify POST /notifications/test endpoint creates a test notification."""
    res = client.post("/notifications/test")
    assert res.status_code == 200
    assert res.json()["status"] == "sent"
