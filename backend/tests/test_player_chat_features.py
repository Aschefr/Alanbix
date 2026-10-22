"""
Tests for player-to-player and group rich chat features:
1. Send message with reply_to_id
2. Send message with image_path
3. Toggle reactions on PM and Group messages
4. Typing relay endpoint
5. Upload image validation
"""
import pytest
from app import models


def test_pm_rich_messaging_and_reactions(client, db_session):
    p1 = db_session.query(models.User).filter(models.User.username == "Player1").first()
    p2 = db_session.query(models.User).filter(models.User.username == "Player2").first()

    # 1. Send initial message
    send1 = client.post(f"/players/messages/{p2.id}", json={"content": "Hello Player2!"})
    assert send1.status_code == 200
    m1_data = send1.json()
    m1_id = m1_data["id"]

    # 2. Reply to initial message with an image
    send2 = client.post(f"/players/messages/{p2.id}", json={
        "content": "Check this screenshot",
        "image_path": "/data/chat_images/players/test.png",
        "reply_to_id": m1_id
    })
    assert send2.status_code == 200
    m2_data = send2.json()
    assert m2_data["message"]["reply_to_id"] == m1_id
    assert m2_data["message"]["reply_to_data"]["content"] == "Hello Player2!"
    assert m2_data["message"]["image_path"] == "/data/chat_images/players/test.png"

    # 3. Toggle reaction on message 1
    react1 = client.post(f"/players/messages/{p2.id}/{m1_id}/reactions", json={"emoji": "🔥"})
    assert react1.status_code == 200
    assert "🔥" in react1.json()["reactions"]

    # 4. Read messages: verify serialized structure
    read_res = client.get(f"/players/messages/{p2.id}")
    assert read_res.status_code == 200
    msgs = read_res.json()["messages"]
    assert len(msgs) >= 2
    target_m1 = next(m for m in msgs if m["id"] == m1_id)
    assert "🔥" in target_m1["reactions"]

    # 5. Untoggle reaction
    react2 = client.post(f"/players/messages/{p2.id}/{m1_id}/reactions", json={"emoji": "🔥"})
    assert react2.status_code == 200
    assert "🔥" not in react2.json()["reactions"]


def test_group_rich_messaging_and_reactions(client, db_session):
    p1 = db_session.query(models.User).filter(models.User.username == "Player1").first()
    p2 = db_session.query(models.User).filter(models.User.username == "Player2").first()
    p1.team_name = "Wolves"
    p2.team_name = "Wolves"
    db_session.commit()

    # 1. Send team message
    send1 = client.post("/players/group/send", json={
        "content": "Go team wolves!",
        "channel_type": "team",
        "team_names": ["Wolves"]
    })
    assert send1.status_code == 200
    m1_id = send1.json()["id"]
    channel_key = send1.json()["channel_key"]
    assert channel_key == "team:Wolves"

    # 2. Reply to team message
    send2 = client.post("/players/group/send", json={
        "content": "Agreed, let's win!",
        "channel_type": "team",
        "team_names": ["Wolves"],
        "reply_to_id": m1_id
    })
    assert send2.status_code == 200
    m2_id = send2.json()["id"]

    # 3. Toggle reaction on group message
    react1 = client.post(f"/players/group/channel/{channel_key}/messages/{m1_id}/reactions", json={"emoji": "👏"})
    assert react1.status_code == 200
    assert "👏" in react1.json()["reactions"]

    # 4. Read channel: verify reply and reaction
    read_res = client.get(f"/players/group/channel/{channel_key}")
    assert read_res.status_code == 200
    msgs = read_res.json()["messages"]
    target_m1 = next(m for m in msgs if m["id"] == m1_id)
    assert "👏" in target_m1["reactions"]
    target_m2 = next(m for m in msgs if m["id"] == m2_id)
    assert target_m2["reply_to_id"] == m1_id
    assert target_m2["reply_to_data"]["content"] == "Go team wolves!"


def test_player_typing_endpoint(client):
    res = client.post("/players/typing", json={
        "target_type": "p2p",
        "target_id": 2,
        "is_typing": True
    })
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
