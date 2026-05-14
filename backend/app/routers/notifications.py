from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, auth, database
from ..websockets import manager as ws_manager

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def get_notifications(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """List all notifications for the current user (newest first)."""
    notifs = db.query(models.Notification).filter(
        models.Notification.user_id == user.id
    ).order_by(models.Notification.created_at.desc()).all()
    return [{
        "id": n.id, "type": n.type, "title": n.title, "content": n.content,
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
