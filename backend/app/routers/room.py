from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List
from .. import models, schemas, auth, database
from ..websockets import manager as ws_manager

router = APIRouter(prefix="/room", tags=["Room Map"])

@router.get("/layout")
def get_layout(db: Session = Depends(database.get_db)):
    layout = db.query(models.RoomMap).first()
    if not layout:
        return {"name": "Default Room", "layout": {"seats": [], "tables": []}}
    return layout

@router.post("/layout")
async def update_layout(
    layout_data: dict, 
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    db_layout = db.query(models.RoomMap).first()
    if not db_layout:
        db_layout = models.RoomMap(layout=layout_data)
        db.add(db_layout)
    else:
        db_layout.layout = layout_data
        flag_modified(db_layout, "layout")
    db.commit()
    db.refresh(db_layout)
    await ws_manager.broadcast({"type": "room_updated"})
    return db_layout

@router.get("/users")
def list_users_for_assignment(db: Session = Depends(database.get_db)):
    """List all users with their seat assignments for the map."""
    users = db.query(models.User).all()
    return [{"id": u.id, "username": u.username, "seat_id": u.seat_id, "is_admin": u.is_admin, "team_name": u.team_name, "avatar_url": u.avatar_url, "avatar_shape": u.avatar_shape} for u in users]

@router.post("/assign-seat")
async def assign_seat(
    data: dict,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    # Check if free seating is locked
    lock_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "seating_locked").first()
    if lock_cfg and lock_cfg.value == "true" and not user.is_admin:
        raise HTTPException(status_code=403, detail="Le placement libre est verrouillé par l'administrateur.")
    seat_id = data.get("seat_id")
    user.seat_id = seat_id
    db.commit()
    await ws_manager.broadcast({"type": "room_updated"})
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "assigned", "seat_id": user.seat_id, "username": user.username}

@router.post("/unassign-seat")
async def unassign_seat(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    user.seat_id = None
    db.commit()
    await ws_manager.broadcast({"type": "room_updated"})
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "unassigned"}

@router.post("/admin-assign-seat")
async def admin_assign_seat(
    data: dict,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Admin assigns a specific user to a specific seat."""
    user_id = data.get("user_id")
    seat_id = data.get("seat_id")
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(404, "User not found")
    target_user.seat_id = seat_id
    db.commit()
    await ws_manager.broadcast({"type": "room_updated"})
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "assigned", "username": target_user.username, "seat_id": seat_id}

@router.post("/admin-unassign-seat")
async def admin_unassign_seat(
    data: dict,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Admin removes a user from their seat."""
    seat_id = data.get("seat_id")
    target = db.query(models.User).filter(models.User.seat_id == seat_id).first()
    if target:
        target.seat_id = None
        db.commit()
        await ws_manager.broadcast({"type": "room_updated"})
        await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "unassigned"}

@router.post("/admin-unassign-all")
async def admin_unassign_all(
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Admin removes ALL users from their seats."""
    users = db.query(models.User).filter(models.User.seat_id != None).all()
    count = len(users)
    for u in users:
        u.seat_id = None
    db.commit()
    await ws_manager.broadcast({"type": "room_updated"})
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "unassigned_all", "count": count}

@router.get("/seating-locked")
def get_seating_locked(db: Session = Depends(database.get_db)):
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "seating_locked").first()
    return {"locked": cfg.value == "true" if cfg else False}

@router.post("/seating-locked")
async def set_seating_locked(data: dict, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    locked = data.get("locked", False)
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "seating_locked").first()
    if cfg:
        cfg.value = "true" if locked else "false"
    else:
        db.add(models.SystemConfig(key="seating_locked", value="true" if locked else "false"))
    db.commit()
    await ws_manager.broadcast({"type": "room_updated"})
    return {"locked": locked}
