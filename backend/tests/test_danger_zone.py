"""Danger zone: every purge removes what it announces, and the full reset empties the server."""
import os

from app import models
from app.routers import ia as ia_router


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x")
    return path


def _users(db):
    return {u.username: u for u in db.query(models.User).all()}


def test_full_reset_requires_confirmation(client):
    assert client.post("/admin/reset-all", json={"keep_admins": True, "confirm": "oui"}).status_code == 400


def test_full_reset_keeping_admins(client, db_session, tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("DATABASE_PATH", str(data / "alanbix.db"))
    u = _users(db_session)
    admin = u["admin"]
    admin.points, admin.seat_id, admin.team_name, admin.avatar_url = 42, "T1_S1", "LDF", "/data/avatars/adm.png"
    db_session.add_all([
        models.Game(name="Quake"),
        models.Notification(user_id=admin.id, type="system", title="x", content=""),
        models.PublicChatMessage(user_id=u["Player1"].id, sender_name="Player1", content="hi"),
        models.SystemConfig(key="event_name", value="LAN"),
        models.KnowledgeBase(content="doc"),
    ])
    db_session.commit()
    kept_avatar = _touch(str(data / "avatars" / "adm.png"))
    gone = [_touch(str(data / "avatars" / "p1.png")), _touch(str(data / "chat_images" / "public" / "a.png")),
            _touch(str(data / "game_images" / "q.png")), _touch(str(data / "info_files" / "rules.pdf")),
            _touch(str(data / "i18n" / "fr.json"))]

    res = client.post("/admin/reset-all", json={"keep_admins": True, "confirm": "reset"})
    assert res.status_code == 200
    db_session.expire_all()
    users = db_session.query(models.User).all()
    assert [x.username for x in users] == ["admin"]
    assert (users[0].points, users[0].seat_id, users[0].team_name) == (0, None, None)
    for model in (models.Game, models.Notification, models.PublicChatMessage, models.SystemConfig, models.KnowledgeBase):
        assert db_session.query(model).count() == 0, model.__name__
    assert os.path.exists(kept_avatar)
    for path in gone:
        assert not os.path.exists(path), path
    assert os.path.isdir(data / "chat_images" / "players") and os.path.isdir(data / "chat_images" / "public")


def test_full_reset_without_admins(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "alanbix.db"))
    assert client.post("/admin/reset-all", json={"keep_admins": False, "confirm": "RESET"}).status_code == 200
    db_session.expire_all()
    assert db_session.query(models.User).count() == 0


def test_purge_images_clears_every_reference_and_keeps_upload_folders(client, db_session, tmp_path, monkeypatch):
    chat_dir = tmp_path / "chat_images"
    monkeypatch.setattr(ia_router, "CHAT_IMAGES_DIR", str(chat_dir))
    _touch(str(chat_dir / "players" / "pm.png"))
    u = _users(db_session)
    db_session.add_all([
        models.PrivateMessage(sender_id=u["Player1"].id, receiver_id=u["Player2"].id, content="", image_path="/data/chat_images/players/pm.png"),
        models.PublicChatMessage(user_id=u["Player1"].id, sender_name="Player1", content="", image_path="/data/chat_images/public/a.png"),
    ])
    db_session.commit()
    assert client.delete("/ia/admin/nuke-images").status_code == 200
    db_session.expire_all()
    assert db_session.query(models.PrivateMessage).filter(models.PrivateMessage.image_path != None).count() == 0
    assert db_session.query(models.PublicChatMessage).filter(models.PublicChatMessage.image_path != None).count() == 0
    assert not os.path.exists(chat_dir / "players" / "pm.png")
    assert os.path.isdir(chat_dir / "players") and os.path.isdir(chat_dir / "public")


def test_purge_players_removes_their_images(client, db_session, tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("DATABASE_PATH", str(data / "alanbix.db"))
    u = _users(db_session)
    img = _touch(str(data / "chat_images" / "public" / "p.png"))
    db_session.add(models.PublicChatMessage(user_id=u["Player1"].id, sender_name="Player1", content="", image_path="/data/chat_images/public/p.png"))
    db_session.commit()
    assert client.delete("/admin/nuke/players").status_code == 200
    assert not os.path.exists(img)
    db_session.expire_all()
    assert db_session.query(models.User).filter(models.User.is_admin == False).count() == 0


def test_public_chat_purge_deletes_messages(client, db_session):
    u = _users(db_session)
    db_session.add(models.PublicChatMessage(user_id=u["Player1"].id, sender_name="Player1", content="hi"))
    db_session.commit()
    assert client.post("/public-chat/clear").status_code == 200
    db_session.expire_all()
    assert db_session.query(models.PublicChatMessage).count() == 0


def test_purge_room_map_frees_every_seat(client, db_session):
    u = _users(db_session)
    db_session.add(models.RoomMap(layout={"tables": [{"id": "T1"}], "seats": [{"id": "T1_S1"}, {"id": "T1_S2"}], "furniture": []}))
    u["Player1"].seat_id = "T1_S1"
    db_session.commit()
    res = client.delete("/admin/nuke/room")
    assert res.status_code == 200 and res.json()["deleted_seats"] == 2
    db_session.expire_all()
    assert db_session.query(models.RoomMap).count() == 0
    assert db_session.query(models.User).filter(models.User.seat_id.isnot(None)).count() == 0
