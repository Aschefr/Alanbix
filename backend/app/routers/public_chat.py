import os
import re
import time
import uuid
import datetime
import asyncio
from html import unescape
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func

from .. import models, schemas, auth, database
from ..websockets import manager as ws_manager

router = APIRouter(prefix="/public-chat", tags=["Public Chat"])

DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
PUBLIC_CHAT_IMAGES_DIR = os.path.join(DATA_DIR, "chat_images", "public")
os.makedirs(PUBLIC_CHAT_IMAGES_DIR, exist_ok=True)

# In-memory tracking for rate limiting & AI cooldowns
_user_last_post_time: Dict[int, float] = {}  # user_id -> timestamp
_user_last_post_content: Dict[int, str] = {}  # user_id -> last_content
_last_ai_reply_time: float = 0.0
_link_preview_cache: Dict[str, dict] = {}

URL_REGEX = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
MENTION_REGEX = re.compile(r'@(\w+)', re.IGNORECASE)


def get_public_chat_config(db: Session) -> dict:
    default_config = {
        "enabled": True,
        "slowmode_seconds": 3,
        "max_length": 250,
        "block_duplicates": True,
        "banned_words": [],
        "ai_mention_enabled": True,
        "ai_cooldown_seconds": 15
    }
    cfg_row = db.query(models.SystemConfig).filter(models.SystemConfig.key == "public_chat_config").first()
    if cfg_row and isinstance(cfg_row.value, dict):
        default_config.update(cfg_row.value)
    return default_config


async def extract_link_preview(url: str) -> Optional[dict]:
    """Fetch OpenGraph metadata for rich preview card."""
    if url in _link_preview_cache:
        return _link_preview_cache[url]
    
    try:
        clean_url = url.strip()
        if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = "https://" + clean_url
            
        async with httpx.AsyncClient(timeout=3.5, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 AlanbixLinkPreview/1.0"}) as client:
            resp = await client.get(clean_url)
            if resp.status_code >= 400:
                return None
            html_text = resp.text[:60000]

            title = None
            m_title = (
                re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I) or
                re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:title["\']', html_text, re.I)
            )
            if m_title:
                title = unescape(m_title.group(1).strip())
            else:
                m_tag = re.search(r'<title[^>]*>(.*?)</title>', html_text, re.I | re.S)
                if m_tag:
                    title = unescape(m_tag.group(1).strip())

            desc = None
            m_desc = (
                re.search(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I) or
                re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I) or
                re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']', html_text, re.I)
            )
            if m_desc:
                desc = unescape(m_desc.group(1).strip())
                if len(desc) > 200:
                    desc = desc[:197] + "..."

            image = None
            m_img = (
                re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I) or
                re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', html_text, re.I)
            )
            if m_img:
                image = m_img.group(1).strip()
                if image.startswith("//"):
                    image = "https:" + image
                elif image.startswith("/") and not image.startswith("//"):
                    parsed = urlparse(clean_url)
                    image = f"{parsed.scheme}://{parsed.netloc}{image}"

            parsed_url = urlparse(clean_url)
            domain = parsed_url.netloc

            if title or desc or image:
                preview = {
                    "url": clean_url,
                    "title": title or domain,
                    "description": desc,
                    "image": image,
                    "domain": domain
                }
                _link_preview_cache[url] = preview
                return preview
    except Exception:
        pass
    return None


def serialize_message(msg: models.PublicChatMessage) -> dict:
    """Helper to convert a PublicChatMessage into a frontend-friendly dictionary."""
    user = msg.user
    reply_to_data = None
    if msg.reply_to_id and msg.reply_to and not msg.reply_to.is_deleted:
        parent_user = msg.reply_to.user
        reply_to_data = {
            "id": msg.reply_to.id,
            "username": parent_user.username if parent_user else (msg.reply_to.sender_name or ("Alanbix" if msg.reply_to.is_bot else "Anonyme")),
            "content": msg.reply_to.content[:100] if msg.reply_to.content else "",
            "is_bot": bool(msg.reply_to.is_bot)
        }

    return {
        "id": msg.id,
        "user_id": msg.user_id,
        "sender_name": msg.sender_name or (user.username if user else "Alanbix" if msg.is_bot else "Anonyme"),
        "is_bot": bool(msg.is_bot),
        "content": msg.content,
        "image_path": msg.image_path,
        "link_preview": msg.link_preview,
        "mentions": msg.mentions,
        "reactions": msg.reactions or {},
        "reply_to_id": msg.reply_to_id,
        "reply_to": reply_to_data,
        "created_at": msg.created_at.isoformat() if msg.created_at else datetime.datetime.utcnow().isoformat(),
        "username": user.username if user else (msg.sender_name or ("Alanbix" if msg.is_bot else None)),
        "avatar_url": user.avatar_url if user else ("/favicon.svg" if msg.is_bot else None),
        "avatar_shape": user.avatar_shape if user else "circle",
        "team_name": user.team_name if user else None,
        "seat_id": user.seat_id if user else None,
        "is_admin": bool(user.is_admin) if user else False
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/config")
def get_config(db: Session = Depends(database.get_db)):
    """Get public chat configuration (slowmode, max_length, etc.)."""
    return get_public_chat_config(db)


@router.put("/config")
async def update_config(
    new_cfg: schemas.PublicChatConfig,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Update public chat anti-spam & AI settings (Admin only)."""
    cfg_row = db.query(models.SystemConfig).filter(models.SystemConfig.key == "public_chat_config").first()
    cfg_dict = new_cfg.model_dump()
    if not cfg_row:
        cfg_row = models.SystemConfig(key="public_chat_config", value=cfg_dict)
        db.add(cfg_row)
    else:
        cfg_row.value = cfg_dict
    db.commit()
    await ws_manager.broadcast({"type": "public_chat_config_updated", "config": cfg_dict})
    return {"status": "ok", "config": cfg_dict}


@router.post("/typing")
async def report_typing(
    payload: schemas.PublicChatTypingRequest,
    user: models.User = Depends(auth.get_current_user)
):
    """Broadcast typing status of a user to public chat."""
    await ws_manager.broadcast({
        "type": "public_chat_typing",
        "user_id": user.id,
        "username": user.username,
        "is_bot": False,
        "is_typing": bool(payload.is_typing)
    })
    return {"status": "ok"}


@router.get("/messages")
def get_recent_messages(
    limit: int = 50,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Get the latest non-deleted public chat messages."""
    limit = min(max(1, limit), 100)
    messages = (
        db.query(models.PublicChatMessage)
        .filter(models.PublicChatMessage.is_deleted == False)
        .order_by(models.PublicChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    # Reverse to chronological order (oldest to newest)
    messages.reverse()
    return [serialize_message(m) for m in messages]


@router.post("/messages")
async def send_message(
    payload: schemas.PublicChatMessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Send a message to the public chat with anti-spam, mentions, and optional AI trigger."""
    global _last_ai_reply_time
    now = time.time()
    config = get_public_chat_config(db)

    # 1. Master Toggle
    if not config.get("enabled", True) and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le chat public est temporairement désactivé par les organisateurs."
        )

    # 2. Check Mute
    if user.public_chat_muted_until:
        if user.public_chat_muted_until > datetime.datetime.utcnow():
            remaining = int((user.public_chat_muted_until - datetime.datetime.utcnow()).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Vous êtes temporairement exclu du chat public ({remaining}s restantes)."
            )
        else:
            # Auto-unmute expired
            user.public_chat_muted_until = None
            db.commit()

    content = payload.content.strip() if payload.content else ""
    image_path = payload.image_path.strip() if payload.image_path else None

    if not content and not image_path:
        raise HTTPException(status_code=400, detail="Le message ne peut pas être vide.")

    # 3. Max length validation
    max_len = config.get("max_length", 250)
    if len(content) > max_len:
        raise HTTPException(
            status_code=400,
            detail=f"Message trop long ({len(content)}/{max_len} caractères autorisés)."
        )

    # 4. Anti-spam Slowmode check
    slowmode = config.get("slowmode_seconds", 3)
    if not user.is_admin and slowmode > 0:
        last_time = _user_last_post_time.get(user.id, 0)
        elapsed = now - last_time
        if elapsed < slowmode:
            cooldown_left = round(slowmode - elapsed, 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Slowmode actif : veuillez patienter {cooldown_left}s."
            )

    # 5. Duplicate Message check
    if not user.is_admin and config.get("block_duplicates", True):
        last_content = _user_last_post_content.get(user.id, "")
        if content and content.lower() == last_content.lower() and (now - _user_last_post_time.get(user.id, 0)) < 60:
            raise HTTPException(
                status_code=400,
                detail="Message identique au précédent (anti-flood)."
            )

    # 6. Word Blacklist Filter
    banned_words = config.get("banned_words", [])
    if banned_words:
        lower_content = content.lower()
        for bw in banned_words:
            if bw and bw.strip().lower() in lower_content:
                raise HTTPException(
                    status_code=400,
                    detail=f"Votre message contient un terme interdit."
                )

    # Update anti-spam state
    _user_last_post_time[user.id] = now
    if content:
        _user_last_post_content[user.id] = content

    # 7. Extract Link Preview (First URL detected)
    link_preview = None
    urls = URL_REGEX.findall(content)
    if urls:
        first_url = urls[0]
        link_preview = await extract_link_preview(first_url)

    # 8. Mentions Parsing
    mentions_data = {"user_ids": [], "has_alanbix": False}
    found_handles = MENTION_REGEX.findall(content)
    has_alanbix = False
    
    if found_handles:
        for handle in found_handles:
            if handle.lower() == "alanbix":
                has_alanbix = True
            else:
                matched_user = db.query(models.User).filter(func.lower(models.User.username) == handle.lower()).first()
                if matched_user and matched_user.id not in mentions_data["user_ids"]:
                    mentions_data["user_ids"].append(matched_user.id)

    mentions_data["has_alanbix"] = has_alanbix

    # 8b. Reply-To Validation
    reply_to_id = None
    if payload.reply_to_id:
        parent_msg = db.query(models.PublicChatMessage).filter(
            models.PublicChatMessage.id == payload.reply_to_id,
            models.PublicChatMessage.is_deleted == False
        ).first()
        if parent_msg:
            reply_to_id = parent_msg.id

    # 9. Create and Save Message
    db_msg = models.PublicChatMessage(
        user_id=user.id,
        content=content,
        image_path=image_path,
        link_preview=link_preview,
        mentions=mentions_data,
        reply_to_id=reply_to_id,
        reactions={},
        is_bot=False,
        is_deleted=False,
        created_at=datetime.datetime.utcnow()
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)

    serialized = serialize_message(db_msg)

    # 10. Broadcast via WebSocket
    await ws_manager.broadcast({
        "type": "public_chat_message",
        "message": serialized,
        "seat_id": user.seat_id,
        "user_id": user.id
    })

    # Clear sender's typing state
    await ws_manager.broadcast({
        "type": "public_chat_typing",
        "user_id": user.id,
        "username": user.username,
        "is_bot": False,
        "is_typing": False
    })

    # 11. Trigger AI Reply if @Alanbix mentioned
    if has_alanbix and config.get("ai_mention_enabled", True):
        ai_cd = config.get("ai_cooldown_seconds", 15)
        if (now - _last_ai_reply_time) >= ai_cd:
            _last_ai_reply_time = now
            # Immediately show Alanbix as typing
            await ws_manager.broadcast({
                "type": "public_chat_typing",
                "user_id": 0,
                "username": "Alanbix",
                "is_bot": True,
                "is_typing": True
            })
            background_tasks.add_task(_process_alanbix_public_reply, db_msg.id, content, user.username)

    return serialized


async def _process_alanbix_public_reply(trigger_msg_id: int, user_prompt: str, author_username: str):
    """Background task to generate Alanbix's reply in public chat via Ollama/IA queue."""
    from ..ia_queue import queue_manager, QueueEntry
    from ..database import SessionLocal
    from .ia import get_instances

    try:
        await asyncio.sleep(0.3)

        with SessionLocal() as db:
            # Check active Ollama instances
            instances = [i for i in get_instances(db) if i.get("enabled", True)]
            if not instances:
                print("[Public Chat AI] No active Ollama instances configured")
                return

            instance = instances[0]
            ollama_host = instance.get("url") or instance.get("host") or "http://localhost:11434"
            model_to_use = instance.get("model") or "llama3"

            # Fetch sliding window (last 6 messages)
            recent_msgs = (
                db.query(models.PublicChatMessage)
                .filter(models.PublicChatMessage.is_deleted == False)
                .order_by(models.PublicChatMessage.id.desc())
                .limit(6)
                .all()
            )
            recent_msgs.reverse()

            # Build conversation context string
            context_lines = []
            for m in recent_msgs:
                sender = m.user.username if m.user else (m.sender_name or "Alanbix")
                context_lines.append(f"{sender}: {m.content}")
            chat_context = "\n".join(context_lines)

            system_prompt = (
                "Tu es Alanbix, l'IA mascotte et arbitre joviale de la LAN Party. "
                "Tu interviens directement dans le chat public de la salle. "
                "Réponds de manière concise (1 à 3 phrases maximum), avec humour, dynamisme, esprit gamer et bienveillance. "
                "N'utilise pas de formalisme inutile. Ne préfixe jamais ta réponse par 'Alanbix:'."
            )

            full_prompt = (
                f"Voici les derniers échanges dans le chat public de la LAN :\n"
                f"{chat_context}\n\n"
                f"{author_username} s'est adressé à toi avec : \"{user_prompt}\"\n"
                f"Réponds-lui directement dans le chat :"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ]

            entry = QueueEntry(
                priority=10,
                created_at=time.time(),
                user_id=0,
                username="Alanbix",
                task_type="public_chat",
                payload={
                    "ollama_host": ollama_host,
                    "model": model_to_use,
                    "messages": messages,
                    "temperature": 0.7,
                    "context_window": 4096
                }
            )

            try:
                entry, _ = await queue_manager.enqueue(entry)
                res = await entry.result_stream.get()
                if not res or res.get("error"):
                    err_text = res.get("result") if res else "Unknown error"
                    print(f"[Public Chat AI] Error from queue: {err_text}")
                    return

                clean_response = (res.get("result") or "").strip()
                if clean_response:
                    # Remove any accidental "Alanbix: " prefix
                    if clean_response.lower().startswith("alanbix:"):
                        clean_response = clean_response[8:].strip()

                    bot_msg = models.PublicChatMessage(
                        user_id=None,
                        sender_name="Alanbix",
                        is_bot=True,
                        content=clean_response,
                        is_deleted=False,
                        created_at=datetime.datetime.utcnow()
                    )
                    db.add(bot_msg)
                    db.commit()
                    db.refresh(bot_msg)

                    serialized_bot = serialize_message(bot_msg)
                    await ws_manager.broadcast({
                        "type": "public_chat_message",
                        "message": serialized_bot,
                        "seat_id": None,
                        "user_id": None
                    })
            except Exception as e:
                print(f"[Public Chat AI] Error generating reply: {e}")
    finally:
        # Guarantee Alanbix typing status is cleared
        await ws_manager.broadcast({
            "type": "public_chat_typing",
            "user_id": 0,
            "username": "Alanbix",
            "is_bot": True,
            "is_typing": False
        })


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    user: models.User = Depends(auth.get_current_user)
):
    """Upload an image or GIF for public chat (max 8MB)."""
    # Check mute
    if user.public_chat_muted_until and user.public_chat_muted_until > datetime.datetime.utcnow():
        raise HTTPException(status_code=403, detail="Vous êtes exclu du chat public.")

    allowed_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    _, ext = os.path.splitext(file.filename or "")
    ext = ext.lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Format non supporté (PNG, JPG, WEBP, GIF acceptés).")

    contents = await file.read()
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image trop volumineuse (max 8 Mo).")

    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(PUBLIC_CHAT_IMAGES_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(contents)

    rel_path = f"/data/chat_images/public/{filename}"
    return {"image_path": rel_path}


@router.post("/messages/{msg_id}/react")
async def toggle_reaction(
    msg_id: int,
    payload: schemas.PublicChatReactionRequest,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Toggle an emoji reaction on a public chat message."""
    msg = db.query(models.PublicChatMessage).filter(models.PublicChatMessage.id == msg_id, models.PublicChatMessage.is_deleted == False).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé.")

    emoji = payload.emoji.strip()
    if not emoji or len(emoji) > 20:
        raise HTTPException(status_code=400, detail="Émoji invalide.")

    reactions = dict(msg.reactions) if msg.reactions and isinstance(msg.reactions, dict) else {}
    user_list = list(reactions.get(emoji, []))

    if user.id in user_list:
        user_list.remove(user.id)
        if user_list:
            reactions[emoji] = user_list
        else:
            reactions.pop(emoji, None)
    else:
        user_list.append(user.id)
        reactions[emoji] = user_list

    msg.reactions = reactions
    flag_modified(msg, "reactions")
    db.commit()

    await ws_manager.broadcast({
        "type": "public_chat_reaction_updated",
        "message_id": msg_id,
        "reactions": reactions
    })
    return {"status": "ok", "message_id": msg_id, "reactions": reactions}


@router.get("/pinned")
def get_pinned_message(db: Session = Depends(database.get_db)):
    """Get the active pinned message if any."""
    pin_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "public_chat_pinned").first()
    if not pin_cfg or not isinstance(pin_cfg.value, dict):
        return {"pinned": None}
    
    msg_id = pin_cfg.value.get("message_id")
    if not msg_id:
        return {"pinned": None}
    
    msg = db.query(models.PublicChatMessage).filter(models.PublicChatMessage.id == msg_id, models.PublicChatMessage.is_deleted == False).first()
    if not msg:
        return {"pinned": None}

    return {
        "pinned": {
            "message": serialize_message(msg),
            "pinned_by": pin_cfg.value.get("pinned_by", "Admin"),
            "pinned_at": pin_cfg.value.get("pinned_at")
        }
    }


@router.post("/pin")
async def pin_message(
    payload: schemas.PublicChatPinRequest,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Pin or unpin a public chat message (Admin only)."""
    pin_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "public_chat_pinned").first()
    if not pin_cfg:
        pin_cfg = models.SystemConfig(key="public_chat_pinned", value=None)
        db.add(pin_cfg)

    pinned_payload = None
    if payload.message_id:
        msg = db.query(models.PublicChatMessage).filter(models.PublicChatMessage.id == payload.message_id, models.PublicChatMessage.is_deleted == False).first()
        if not msg:
            raise HTTPException(status_code=404, detail="Message non trouvé.")
        
        now_iso = datetime.datetime.utcnow().isoformat()
        pinned_val = {
            "message_id": msg.id,
            "pinned_by": admin.username,
            "pinned_at": now_iso
        }
        pin_cfg.value = pinned_val
        flag_modified(pin_cfg, "value")
        db.commit()

        pinned_payload = {
            "message": serialize_message(msg),
            "pinned_by": admin.username,
            "pinned_at": now_iso
        }
    else:
        pin_cfg.value = None
        flag_modified(pin_cfg, "value")
        db.commit()

    await ws_manager.broadcast({
        "type": "public_chat_pinned_updated",
        "pinned": pinned_payload
    })
    return {"status": "ok", "pinned": pinned_payload}


@router.delete("/messages/{msg_id}")
async def delete_message(
    msg_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Soft delete a public chat message (Admin only)."""
    msg = db.query(models.PublicChatMessage).filter(models.PublicChatMessage.id == msg_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé.")
    
    msg.is_deleted = True
    db.commit()

    # If the deleted message was pinned, clear pin
    pin_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "public_chat_pinned").first()
    if pin_cfg and isinstance(pin_cfg.value, dict) and pin_cfg.value.get("message_id") == msg_id:
        pin_cfg.value = None
        flag_modified(pin_cfg, "value")
        db.commit()
        await ws_manager.broadcast({"type": "public_chat_pinned_updated", "pinned": None})

    await ws_manager.broadcast({
        "type": "public_chat_message_deleted",
        "message_id": msg_id
    })
    return {"status": "ok", "deleted_id": msg_id}


@router.post("/clear")
async def clear_chat(
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Clear all public chat messages (Admin only)."""
    db.query(models.PublicChatMessage).update({"is_deleted": True})
    db.commit()

    pin_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "public_chat_pinned").first()
    if pin_cfg and pin_cfg.value:
        pin_cfg.value = None
        flag_modified(pin_cfg, "value")
        db.commit()
        await ws_manager.broadcast({"type": "public_chat_pinned_updated", "pinned": None})

    await ws_manager.broadcast({"type": "public_chat_cleared"})
    return {"status": "ok"}


@router.post("/mute/{user_id}")
async def mute_user(
    user_id: int,
    data: dict,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Mute/Unmute a player from public chat for a duration in minutes (Admin only)."""
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Joueur non trouvé.")

    duration_minutes = data.get("duration_minutes", 10)
    if duration_minutes is None or duration_minutes <= 0:
        target.public_chat_muted_until = None
    else:
        target.public_chat_muted_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=duration_minutes)

    db.commit()
    await ws_manager.broadcast({"type": "users_updated"})
    return {
        "status": "ok",
        "user_id": target.id,
        "muted_until": target.public_chat_muted_until.isoformat() if target.public_chat_muted_until else None
    }
