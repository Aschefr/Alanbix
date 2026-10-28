from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, auth, database
from ..websockets import manager as ws_manager

router = APIRouter(prefix="/notifications", tags=["Notifications"])


async def notify_user(
    db: Session,
    user_id: int,
    category: str,
    title: str,
    body: str,
    link: Optional[str] = None,
    data: Optional[dict] = None
) -> models.Notification:
    """Create a persistent Notification record and emit targeted push & notification_new events."""
    notif = models.Notification(
        user_id=user_id,
        type=category,
        category=category,
        title=title,
        content=body,
        link=link,
        metadata_json=data or {},
        created_at=datetime.utcnow()
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # 1. Unified push event for background service / notifications engine
    push_event = {
        "type": "push",
        "id": f"notif_{notif.id}",
        "notification_id": notif.id,
        "category": category,
        "title": title,
        "body": body,
        "link": link or "/dashboard/notifications",
        "data": data or {},
        "created_at": notif.created_at.isoformat() if notif.created_at else datetime.utcnow().isoformat()
    }
    await ws_manager.send_to_user(user_id, push_event)

    # 2. Real-time badge update for web clients
    await ws_manager.send_to_user(user_id, {
        "type": "notification_new",
        "user_id": user_id,
        "notification_id": notif.id
    })

    return notif


@router.get("")
def get_notifications(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """List all notifications for the current user (newest first)."""
    notifs = db.query(models.Notification).filter(
        models.Notification.user_id == user.id
    ).order_by(models.Notification.created_at.desc()).all()
    return [{
        "id": n.id, "type": n.type, "category": n.category or n.type,
        "title": n.title, "content": n.content, "link": n.link,
        "is_read": n.is_read, "created_at": n.created_at.isoformat() if n.created_at else None,
        "metadata": n.metadata_json
    } for n in notifs]


@router.get("/unread-count")
def get_unread_count(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Return the number of unread notifications."""
    count = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.is_read == False
    ).count()
    return {"count": count}


@router.get("/missed")
async def get_missed_events(
    since: Optional[str] = None,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Retrieve notifications, PMs, and mentions missed since a given ISO timestamp."""
    since_dt = None
    if since:
        try:
            cleaned = since.replace("Z", "+00:00")
            since_dt = datetime.fromisoformat(cleaned).replace(tzinfo=None)
        except Exception:
            since_dt = None

    if not since_dt:
        # Default: last 24 hours
        since_dt = datetime.utcnow() - timedelta(hours=24)

    # 1. System notifications
    notifs = db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.created_at >= since_dt
    ).order_by(models.Notification.created_at.asc()).all()

    events = []
    for n in notifs:
        events.append({
            "id": f"notif_{n.id}",
            "notification_id": n.id,
            "category": n.category or n.type or "system",
            "title": n.title,
            "body": n.content,
            "link": n.link or "/dashboard/notifications",
            "data": n.metadata_json or {},
            "created_at": n.created_at.isoformat() if n.created_at else None
        })

    # 2. Unread private messages
    pms = db.query(models.PrivateMessage).filter(
        models.PrivateMessage.receiver_id == user.id,
        models.PrivateMessage.is_read == False,
        models.PrivateMessage.created_at >= since_dt
    ).order_by(models.PrivateMessage.created_at.asc()).all()

    for pm in pms:
        sender_name = pm.sender.username if pm.sender else "Quelqu'un"
        events.append({
            "id": f"pm_{pm.id}",
            "category": "private_message",
            "title": f"💬 {sender_name}",
            "body": (pm.content or ("📷 Image" if pm.image_path else ""))[:100],
            "link": f"/dashboard/players?chat={pm.sender_id}",
            "data": {"sender_id": pm.sender_id, "message_id": pm.id},
            "created_at": pm.created_at.isoformat() if pm.created_at else None
        })

    # Sort all events chronologically
    events.sort(key=lambda e: e.get("created_at") or "")
    return {"since": since_dt.isoformat(), "count": len(events), "events": events}


@router.post("/test")
async def send_test_notification(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Trigger an immediate test push notification for current user to verify mobile settings."""
    notif = await notify_user(
        db=db,
        user_id=user.id,
        category="system",
        title="🔔 Test Alanbix",
        body="Vos notifications mobiles fonctionnent parfaitement !",
        link="/dashboard/settings",
        data={"is_test": True}
    )
    return {"status": "sent", "notification_id": notif.id}


@router.put("/{notif_id}/read")
async def mark_read(notif_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Mark a single notification as read."""
    notif = db.query(models.Notification).filter(
        models.Notification.id == notif_id,
        models.Notification.user_id == user.id
    ).first()
    if not notif:
        raise HTTPException(404, "Notification not found")
    notif.is_read = True
    db.commit()
    return {"status": "ok"}


@router.put("/read-all")
async def mark_all_read(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Mark all notifications as read."""
    db.query(models.Notification).filter(
        models.Notification.user_id == user.id,
        models.Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"status": "ok"}


@router.delete("/{notif_id}")
async def delete_notification(notif_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Delete a single notification."""
    notif = db.query(models.Notification).filter(
        models.Notification.id == notif_id,
        models.Notification.user_id == user.id
    ).first()
    if not notif:
        raise HTTPException(404, "Notification not found")
    db.delete(notif)
    db.commit()
    return {"status": "ok"}
