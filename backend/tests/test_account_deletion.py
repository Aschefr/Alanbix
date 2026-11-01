"""Deleting an account also removes the images the player uploaded, and nothing else on the server."""
import os

from app import models
from app.auth import get_current_user
from app.main import app


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x")
    return path


def test_delete_account_removes_uploaded_images_only(client, db_session, tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("DATABASE_PATH", str(data / "alanbix.db"))
    player = db_session.query(models.User).filter(models.User.username == "Player1").first()
    other = db_session.query(models.User).filter(models.User.username == "Player2").first()
    player.avatar_url = "/data/avatars/p1.png?v=3"

    avatar = _touch(str(data / "avatars" / "p1.png"))
    avatar_thumb = _touch(str(data / "thumbs" / "96" / "avatars" / "p1.webp"))
    pm_image = _touch(str(data / "chat_images" / "players" / "pm.png"))
    public_image = _touch(str(data / "chat_images" / "public" / "pub.png"))
    conv = models.Conversation(user_id=player.id, title="t")
    db_session.add(conv)
    db_session.flush()
    ai_image = _touch(str(data / "chat_images" / str(conv.id) / "ai.png"))

    # Files that must survive: another player's image and a crafted path aiming at the database
    kept_image = _touch(str(data / "chat_images" / "players" / "other.png"))
    database = _touch(str(data / "alanbix.db"))

    db_session.add_all([
        models.PrivateMessage(sender_id=player.id, receiver_id=other.id, content="", image_path="/data/chat_images/players/pm.png"),
        models.PrivateMessage(sender_id=player.id, receiver_id=other.id, content="", image_path="/data/chat_images/players/../../alanbix.db"),
        models.PrivateMessage(sender_id=other.id, receiver_id=db_session.query(models.User).filter(models.User.username == "Player3").first().id,
                              content="", image_path="/data/chat_images/players/other.png"),
        models.PublicChatMessage(user_id=player.id, sender_name=player.username, content="", image_path="/data/chat_images/public/pub.png"),
    ])
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: player
    res = client.delete("/me")
    assert res.status_code == 200

    for gone in (avatar, avatar_thumb, pm_image, public_image, ai_image):
        assert not os.path.exists(gone), gone
    assert os.path.exists(kept_image)
    assert os.path.exists(database)
    assert db_session.query(models.User).filter(models.User.username == "Player1").first() is None


def test_delete_account_anonymises_closed_tournament_results(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "alanbix.db"))
    player = db_session.query(models.User).filter(models.User.username == "Player1").first()
    other = db_session.query(models.User).filter(models.User.username == "Player2").first()
    t = models.Tournament(name="Cup", status="CLOSED", results=[
        {"rank": 1, "entity_id": player.id, "name": "Player1", "total": 10},
        {"rank": 2, "entity_id": other.id, "name": "Player2", "total": 5},
    ])
    db_session.add(t)
    db_session.commit()
    player_id = player.id

    app.dependency_overrides[get_current_user] = lambda: player
    assert client.delete("/me").status_code == 200

    db_session.expire_all()
    names = [e["name"] for e in db_session.query(models.Tournament).filter(models.Tournament.name == "Cup").first().results]
    assert names == [f"#{player_id}", "Player2"]
