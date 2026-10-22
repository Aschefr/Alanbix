import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.websockets import ConnectionManager
from app.auth import create_access_token, get_user_id_from_token
from app import models


@pytest.mark.asyncio
async def test_websocket_presence_single_tab():
    """Verify registering a user on websocket broadcasts online presence and disconnect broadcasts offline."""
    mgr = ConnectionManager()

    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()

    await mgr.connect(mock_ws)
    assert len(mgr.active_connections) == 1
    assert mgr.is_user_online(99) is False

    # Register user (tab 1 opened)
    await mgr.register_user(mock_ws, 99)
    assert mgr.is_user_online(99) is True

    # Check broadcast was sent to active connections
    mock_ws.send_json.assert_called_with({
        "type": "user_presence",
        "user_id": 99,
        "is_online": True
    })

    # Disconnect socket (tab 1 closed)
    mock_ws.send_json.reset_mock()
    await mgr.disconnect(mock_ws)
    assert mgr.is_user_online(99) is False
    assert len(mgr.active_connections) == 0


@pytest.mark.asyncio
async def test_websocket_presence_multi_tab():
    """Verify multi-tab presence: user stays online until all tabs are closed."""
    mgr = ConnectionManager()

    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await mgr.connect(ws1)
    await mgr.connect(ws2)

    # Open Tab 1
    await mgr.register_user(ws1, 100)
    assert mgr.is_user_online(100) is True

    # Open Tab 2 for same user
    ws1.send_json.reset_mock()
    ws2.send_json.reset_mock()
    await mgr.register_user(ws2, 100)
    assert mgr.is_user_online(100) is True
    # Should not re-broadcast online event if already online
    ws1.send_json.assert_not_called()

    # Close Tab 1
    await mgr.disconnect(ws1)
    assert mgr.is_user_online(100) is True  # Tab 2 still alive!
    ws2.send_json.assert_not_called()

    # Close Tab 2 (last tab)
    await mgr.disconnect(ws2)
    assert mgr.is_user_online(100) is False


def test_get_user_id_from_token(db_session):
    """Verify get_user_id_from_token validates tokens properly."""
    # Invalid tokens
    assert get_user_id_from_token("invalid_token") is None
    assert get_user_id_from_token("") is None

    # Valid token with non-existent user
    token_ghost = create_access_token({"sub": "ghost_player_does_not_exist"})
    assert get_user_id_from_token(token_ghost) is None

    # Valid user in db
    user = models.User(username="presence_test_user", hashed_password="dummy")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token_valid = create_access_token({"sub": "presence_test_user"})
    assert get_user_id_from_token(token_valid, db=db_session) == user.id


@pytest.mark.asyncio
async def test_user_is_online_property(db_session):
    """Verify User.is_online reflects websocket presence state."""
    from app.websockets import manager as global_mgr

    user = models.User(username="online_prop_test", hashed_password="dummy")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # Initially offline
    assert user.is_online is False

    # Simulate active websocket
    mock_ws = AsyncMock()
    await global_mgr.register_user(mock_ws, user.id)
    try:
        assert user.is_online is True
    finally:
        await global_mgr.disconnect(mock_ws)

    assert user.is_online is False


@pytest.mark.asyncio
async def test_websocket_broadcast_cleans_dead_connections():
    """Verify that failed/dead connections during broadcast are immediately disconnected and cleaned up."""
    mgr = ConnectionManager()

    alive_ws = AsyncMock()
    dead_ws = AsyncMock()

    await mgr.connect(alive_ws)
    await mgr.connect(dead_ws)
    await mgr.register_user(dead_ws, 200)

    assert len(mgr.active_connections) == 2
    assert mgr.is_user_online(200) is True

    # Now simulate dead socket (connection dropped/broken pipe)
    dead_ws.send_json.side_effect = RuntimeError("Broken pipe / Connection reset")

    # Broadcast message: dead_ws fails on send_json and is purged
    await mgr.broadcast({"type": "test_message"})

    # Dead socket should have been purged from active_connections and user_connections
    assert len(mgr.active_connections) == 1
    assert alive_ws in mgr.active_connections
    assert dead_ws not in mgr.active_connections
    assert mgr.is_user_online(200) is False

