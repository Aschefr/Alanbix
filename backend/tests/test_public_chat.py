import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
from app import models

def test_get_and_update_public_chat_config(client):
    # Test GET config
    res = client.get("/public-chat/config")
    assert res.status_code == 200
    data = res.json()
    assert "enabled" in data
    assert "slowmode_seconds" in data
    assert "max_length" in data
    assert "block_duplicates" in data
    assert "banned_words" in data

    # Test PUT config (admin)
    update_payload = {
        "enabled": True,
        "slowmode_seconds": 5,
        "max_length": 300,
        "block_duplicates": True,
        "banned_words": ["badword", "cheater"],
        "ai_mention_enabled": True,
        "ai_cooldown_seconds": 20
    }
    res = client.put("/public-chat/config", json=update_payload)
    assert res.status_code == 200
    updated = res.json()
    assert updated["slowmode_seconds"] == 5
    assert updated["max_length"] == 300
    assert "badword" in updated["banned_words"]

def test_post_and_get_public_chat_messages(client, db_session):
    # Send a message
    with patch("app.routers.public_chat.manager.broadcast", new_callable=AsyncMock):
        res = client.post("/public-chat/messages", json={"content": "Hello LAN arena!"})
        assert res.status_code == 200
        msg_data = res.json()
        assert msg_data["content"] == "Hello LAN arena!"
        assert msg_data["username"] == "admin"
        assert msg_data["is_bot"] is False

    # Get messages
    res = client.get("/public-chat/messages")
    assert res.status_code == 200
    messages = res.json()
    assert len(messages) >= 1
    assert any(m["content"] == "Hello LAN arena!" for m in messages)

def test_banned_words_filter(client):
    # Set banned words
    client.put("/public-chat/config", json={
        "enabled": True,
        "slowmode_seconds": 0,
        "max_length": 500,
        "block_duplicates": False,
        "banned_words": ["forbidden", "toxic"],
        "ai_mention_enabled": True,
        "ai_cooldown_seconds": 10
    })

    # Message with banned word should be rejected
    res = client.post("/public-chat/messages", json={"content": "This is totally forbidden here"})
    assert res.status_code == 400
    assert "interdit" in res.json()["detail"].lower()

def test_max_length_filter(client):
    client.put("/public-chat/config", json={
        "enabled": True,
        "slowmode_seconds": 0,
        "max_length": 20,
        "block_duplicates": False,
        "banned_words": [],
        "ai_mention_enabled": True,
        "ai_cooldown_seconds": 10
    })

    # Message exceeding length limit
    res = client.post("/public-chat/messages", json={"content": "This is a very long message exceeding twenty characters"})
    assert res.status_code == 400
    assert "long" in res.json()["detail"].lower()

def test_duplicate_message_block(client):
    client.put("/public-chat/config", json={
        "enabled": True,
        "slowmode_seconds": 0,
        "max_length": 500,
        "block_duplicates": True,
        "banned_words": [],
        "ai_mention_enabled": True,
        "ai_cooldown_seconds": 10
    })

    with patch("app.routers.public_chat.manager.broadcast", new_callable=AsyncMock):
        res1 = client.post("/public-chat/messages", json={"content": "Unique message 123"})
        assert res1.status_code == 200

        res2 = client.post("/public-chat/messages", json={"content": "Unique message 123"})
        assert res2.status_code == 400
        assert "identique" in res2.json()["detail"].lower()

def test_mute_player_and_prevent_chat(client, db_session):
    player1 = db_session.query(models.User).filter(models.User.username == "Player1").first()
    assert player1 is not None

    # Admin mutes player1
    res = client.post(f"/public-chat/mute/{player1.id}", json={"duration_minutes": 15})
    assert res.status_code == 200
    assert res.json()["is_muted"] is True

    # Check that player1's muted_until was set in DB
    db_session.refresh(player1)
    assert player1.public_chat_muted_until is not None

    # Test unmute
    res_unmute = client.post(f"/public-chat/mute/{player1.id}", json={"duration_minutes": 0})
    assert res_unmute.status_code == 200
    assert res_unmute.json()["is_muted"] is False

def test_delete_message_and_clear_chat(client, db_session):
    with patch("app.routers.public_chat.manager.broadcast", new_callable=AsyncMock):
        res = client.post("/public-chat/messages", json={"content": "Message to be deleted"})
        assert res.status_code == 200
        msg_id = res.json()["id"]

        # Delete message
        del_res = client.delete(f"/public-chat/messages/{msg_id}")
        assert del_res.status_code == 200
        assert del_res.json()["deleted_id"] == msg_id

        # Post another and clear all
        client.post("/public-chat/messages", json={"content": "Another message"})
        clear_res = client.post("/public-chat/clear")
        assert clear_res.status_code == 200
        assert clear_res.json()["cleared"] is True

        # Messages list should now be empty
        list_res = client.get("/public-chat/messages")
        assert list_res.status_code == 200
        assert len(list_res.json()) == 0


def test_public_chat_pagination_cursor(client, db_session):
    with patch("app.routers.public_chat.manager.broadcast", new_callable=AsyncMock):
        # Post 5 sequential messages
        ids = []
        for i in range(1, 6):
            res = client.post("/public-chat/messages", json={"content": f"Pagination test message {i}"})
            assert res.status_code == 200
            ids.append(res.json()["id"])

        # Fetch latest 2 messages
        res_latest = client.get("/public-chat/messages?limit=2")
        assert res_latest.status_code == 200
        latest_msgs = res_latest.json()
        assert len(latest_msgs) == 2
        assert latest_msgs[-1]["id"] == ids[-1]
        assert latest_msgs[0]["id"] == ids[-2]

        # Fetch 2 messages before the oldest retrieved id
        oldest_retrieved_id = latest_msgs[0]["id"]
        res_before = client.get(f"/public-chat/messages?limit=2&before_id={oldest_retrieved_id}")
        assert res_before.status_code == 200
        before_msgs = res_before.json()
        assert len(before_msgs) == 2
        assert before_msgs[-1]["id"] == ids[-3]
        assert before_msgs[0]["id"] == ids[-4]

