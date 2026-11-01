"""Archiving notifications: the inbox empties without deleting, and the archive can be emptied for good."""
from app import models


def _add(db, user, title, **kw):
    n = models.Notification(user_id=user.id, type="system", title=title, content="", **kw)
    db.add(n)
    db.commit()
    return n


def test_archive_unarchive_and_delete_archived(client, db_session):
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    other = db_session.query(models.User).filter(models.User.username == "Player1").first()
    a = _add(db_session, admin, "a")
    b = _add(db_session, admin, "b")
    legacy = _add(db_session, admin, "legacy", is_archived=None)  # row created before the column existed
    foreign = _add(db_session, other, "not mine")

    assert {n["title"] for n in client.get("/notifications").json()} == {"a", "b", "legacy"}
    assert client.get("/notifications/unread-count").json()["count"] == 3

    # one notification archived: out of the inbox, counted as read, listed in the archive
    assert client.put(f"/notifications/{a.id}/archive").status_code == 200
    assert {n["title"] for n in client.get("/notifications").json()} == {"b", "legacy"}
    assert [n["title"] for n in client.get("/notifications?archived=true").json()] == ["a"]
    assert client.get("/notifications/unread-count").json()["count"] == 2

    # back to the inbox
    assert client.put(f"/notifications/{a.id}/unarchive").status_code == 200
    assert client.get("/notifications/archived-count").json()["count"] == 0

    # archive everything, then empty the archive for good; other players are untouched
    assert client.put("/notifications/archive-all").json()["archived"] == 3
    assert client.get("/notifications").json() == []
    assert client.get("/notifications/archived-count").json()["count"] == 3
    assert client.delete("/notifications/archived").json()["deleted"] == 3
    assert client.get("/notifications?archived=true").json() == []
    assert db_session.query(models.Notification).filter(models.Notification.id == foreign.id).first() is not None


def test_cannot_archive_someone_elses_notification(client, db_session):
    other = db_session.query(models.User).filter(models.User.username == "Player1").first()
    foreign = _add(db_session, other, "not mine")
    assert client.put(f"/notifications/{foreign.id}/archive").status_code == 404
