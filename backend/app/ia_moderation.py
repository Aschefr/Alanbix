"""Moderation tools of the AI assistant: block a player from the assistant, mute them in the public chat.

Who may sanction whom is checked here, never left to the model. Split out of ia_tools.py.
"""
import datetime
import json

from .clock import utcnow


def _named_player(db, models, name: str):
    """The player an administrator named: exact username (any case), else the only one containing it.
    No fuzzy guess: a sanction must never land on the wrong player. Returns (user, other candidates)."""
    q = (name or "").strip().lower()
    users = db.query(models.User).all()
    for u in users:
        if u.username.lower() == q:
            return u, []
    part = [u for u in users if q and q in u.username.lower()]
    if len(part) == 1:
        return part[0], []
    return None, [u.username for u in part][:10]


def _not_found(name: str, candidates: list) -> str:
    if candidates:
        return json.dumps({"error": f"Several players match '{name}': {', '.join(candidates)}. Nothing was done: ask which one."}, ensure_ascii=False)
    return json.dumps({"error": f"No player named '{name}'. Nothing was done."}, ensure_ascii=False)


def _tool_block_user_from_ia(db, models, args: dict, user_id: int) -> str:
    """Block the person writing from the AI assistant, or, for an administrator, the player they name."""
    reason = (args.get("reason") or "Comportement inapproprié ou abusif envers l'assistant IA").strip()
    if not user_id:
        return json.dumps({"error": "Cannot tell who is writing. Nothing was done."})

    caller = db.query(models.User).filter(models.User.id == user_id).first()
    if not caller:
        return json.dumps({"error": "Unknown user. Nothing was done."})

    user = caller
    name = (args.get("username") or "").strip()
    if name:
        found, candidates = _named_player(db, models, name)
        if not found:
            return _not_found(name, candidates)
        if found.id != caller.id:
            # Checked here, not left to the model: only an administrator blocks someone else
            if not caller.is_admin:
                return json.dumps({"error": "Only an administrator can block another player. Nothing was done: tell the player so."})
            user = found

    if user.is_admin:
        return json.dumps({"error": "An administrator cannot be blocked. Nothing was done."})

    user.ia_blocked = True
    # An administrator's "ban" also silences the player in the public chat: blocking the assistant
    # alone left a banned player writing there (prod, 2026-11-11)
    muted_minutes = 0
    if args.get("ban") is True and caller.is_admin and user.id != caller.id:
        muted_minutes = BAN_MUTE_MINUTES
        user.public_chat_muted_until = utcnow() + datetime.timedelta(minutes=muted_minutes)

    from .routers.notifications import localized_text
    params = {"username": user.username, "reason": reason.rstrip(".")}

    # Create notification for the user
    title, content, meta = localized_text(db, "notif_ia_blocked_title", "notif_ia_blocked_body", params)
    notif = models.Notification(user_id=user.id, type="system", title=title, content=content, metadata_json=meta)
    db.add(notif)

    # Notify all administrators
    title, content, meta = localized_text(db, "notif_ia_blocked_admin_title", "notif_ia_blocked_admin_body", params)
    admins = db.query(models.User).filter(models.User.is_admin == True).all()
    for admin in admins:
        admin_notif = models.Notification(user_id=admin.id, type="admin_message", title=title, content=content, metadata_json=meta)
        db.add(admin_notif)
        
    db.commit()

    result = {
        "success": True,
        "username": user.username,
        "message": f"Le joueur {user.username} a été bloqué avec succès de l'assistant IA pour la raison suivante : {reason}."
    }
    if muted_minutes:
        _broadcast_users_updated()
        result["muted_minutes"] = muted_minutes
        result["message"] += f" They also cannot write in the public chat for {muted_minutes // 60} hours."
    return json.dumps(result, ensure_ascii=False)


MUTE_DEFAULT_MINUTES = 15
MUTE_MAX_MINUTES = 1440
BAN_MUTE_MINUTES = 1440


def _broadcast_users_updated():
    """Tell the pages a player's chat rights changed (mute shown at once)."""
    from .websockets import manager as ws_manager
    import asyncio
    try:
        asyncio.get_running_loop().create_task(ws_manager.broadcast({"type": "users_updated"}))
    except RuntimeError:
        pass


def _tool_mute_player_in_public_chat(db, models, args: dict, user_id: int) -> str:
    """Administrator's request: stop a player from writing in the public chat for a while
    (same effect as the mute button of the administration)."""
    caller = db.query(models.User).filter(models.User.id == user_id).first() if user_id else None
    if not caller or not caller.is_admin:
        return json.dumps({"error": "Only an administrator can mute a player. Nothing was done: tell the player so."})
    name = (args.get("username") or "").strip()
    if not name:
        return json.dumps({"error": "Which player? Nothing was done."})
    target, candidates = _named_player(db, models, name)
    if not target:
        return _not_found(name, candidates)
    if target.is_admin:
        return json.dumps({"error": "An administrator cannot be muted. Nothing was done."})
    try:
        minutes = int(args.get("minutes") or MUTE_DEFAULT_MINUTES)
    except (TypeError, ValueError):
        minutes = MUTE_DEFAULT_MINUTES
    minutes = max(1, min(minutes, MUTE_MAX_MINUTES))
    target.public_chat_muted_until = utcnow() + datetime.timedelta(minutes=minutes)
    db.commit()

    _broadcast_users_updated()
    return json.dumps({"success": True, "username": target.username, "minutes": minutes,
                       "message": f"{target.username} cannot write in the public chat for {minutes} minutes."}, ensure_ascii=False)
