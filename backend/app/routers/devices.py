import secrets
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, auth, database

router = APIRouter(prefix="/devices", tags=["Devices"])


class DeviceRegisterRequest(BaseModel):
    platform: str  # "android", "ios", "web"
    name: Optional[str] = None  # "Pixel 8", "iPhone 15", etc.
    push_token: Optional[str] = None
    device_key: Optional[str] = None


class DeviceResponse(BaseModel):
    id: int
    token: str
    platform: str
    name: Optional[str]
    created_at: Optional[str]
    last_seen: Optional[str]


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceRegisterRequest,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Register or update a companion mobile device and return a long-lived device token."""
    platform = (payload.platform or "android").lower().strip()
    if platform not in ("android", "ios", "web"):
        raise HTTPException(400, "Plateforme invalide (android, ios, web)")

    # Generate a cryptographically secure token prefixed with dev_
    dev_token = "dev_" + secrets.token_urlsafe(32)

    device = models.Device(
        user_id=user.id,
        token=dev_token,
        platform=platform,
        name=payload.name.strip() if payload.name else None,
        push_token=payload.push_token.strip() if payload.push_token else None,
        device_key=payload.device_key.strip() if payload.device_key else None,
        created_at=datetime.utcnow(),
        last_seen=datetime.utcnow()
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    return {
        "status": "registered",
        "id": device.id,
        "token": device.token,
        "platform": device.platform,
        "name": device.name,
        "created_at": device.created_at.isoformat() if device.created_at else None
    }


@router.get("/me")
async def list_my_devices(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """List all registered companion devices for the current user."""
    devices = db.query(models.Device).filter(models.Device.user_id == user.id).all()
    return [
        {
            "id": d.id,
            "platform": d.platform,
            "name": d.name,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "created_at": d.created_at.isoformat() if d.created_at else None
        }
        for d in devices
    ]


@router.delete("/{device_id}")
async def revoke_device(
    device_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Revoke a companion device token."""
    device = db.query(models.Device).filter(
        models.Device.id == device_id,
        models.Device.user_id == user.id
    ).first()
    if not device:
        raise HTTPException(404, "Appareil non trouvé")

    db.delete(device)
    db.commit()
    return {"status": "revoked", "id": device_id}


@router.post("/revoke-token")
async def revoke_device_by_token(
    payload: dict,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Revoke a companion device token by value (used upon mobile logout)."""
    token = payload.get("token", "")
    if token:
        db.query(models.Device).filter(
            models.Device.token == token,
            models.Device.user_id == user.id
        ).delete()
        db.commit()
    return {"status": "ok"}

