from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import timedelta
import os
from .. import models, schemas, auth, database
from ..websockets import manager as ws_manager
from ..visibility import visible_tournaments

router = APIRouter(tags=["Users"])

# --- Rate-limiting for check-username (anti-spam) ---
import time as _time
_check_username_last_call: dict[str, float] = {}
_CHECK_USERNAME_COOLDOWN = 0.2  # 200ms

@router.get("/check-username/{username}")
def check_username_exists(username: str, request: Request, db: Session = Depends(database.get_db)):
    """Check if a username already exists. Public endpoint for login/register flow."""
    client_ip = request.client.host if request.client else "unknown"
    now = _time.monotonic()
    last = _check_username_last_call.get(client_ip, 0)
    if now - last < _CHECK_USERNAME_COOLDOWN:
        raise HTTPException(status_code=429, detail="Too many requests")
    _check_username_last_call[client_ip] = now
    return {"exists": db.query(models.User).filter(models.User.username == username).first() is not None}


# --- Brute-force guard for /token ---
# After too many wrong passwords from one address, that address waits before trying again.
# Counted per address + username (guessing one account) and per address (trying many accounts).
_LOGIN_WINDOW = 15 * 60
_LOGIN_LOCK = 5 * 60
_LOGIN_MAX_PER_ACCOUNT = 5
_LOGIN_MAX_PER_ADDRESS = 20
_login_failures: dict[tuple, list[float]] = {}


def _recent_failures(key, now):
    stamps = [s for s in _login_failures.get(key, []) if now - s < _LOGIN_WINDOW]
    if stamps:
        _login_failures[key] = stamps
    else:
        _login_failures.pop(key, None)
    return stamps


def _login_wait(client_ip, username, now):
    """Seconds this address must still wait before trying this username, 0 if it may try now."""
    wait = 0
    for key, limit in (((client_ip, username), _LOGIN_MAX_PER_ACCOUNT), ((client_ip, None), _LOGIN_MAX_PER_ADDRESS)):
        stamps = _recent_failures(key, now)
        if len(stamps) >= limit:
            wait = max(wait, stamps[-1] + _LOGIN_LOCK - now)
    return int(wait) + 1 if wait > 0 else 0


def _record_login_failure(client_ip, username, now):
    if len(_login_failures) > 5000:
        for key in list(_login_failures):
            _recent_failures(key, now)
    for key in ((client_ip, username), (client_ip, None)):
        _login_failures.setdefault(key, []).append(now)


def _too_many_attempts(wait):
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": "too_many_attempts", "message": "Too many failed attempts", "retry_after": wait},
        headers={"Retry-After": str(wait)},
    )


@router.post("/register", response_model=schemas.User)
async def register_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # First user is admin (simple rule for LAN)
    is_admin = db.query(models.User).count() == 0
    
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_password, is_admin=is_admin)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    await ws_manager.broadcast({"type": "users_updated"})
    return new_user

@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    client_ip = request.client.host if request.client else "unknown"
    now = _time.monotonic()
    wait = _login_wait(client_ip, form_data.username, now)
    if wait:
        raise _too_many_attempts(wait)
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        _record_login_failure(client_ip, form_data.username, now)
        wait = _login_wait(client_ip, form_data.username, now)
        if wait:
            raise _too_many_attempts(wait)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _login_failures.pop((client_ip, form_data.username), None)
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/token/refresh")
async def refresh_access_token(current_user: models.User = Depends(auth.get_current_user)):
    """A fresh session for a player still using the app, so only inactivity logs out."""
    access_token = auth.create_access_token(
        data={"sub": current_user.username},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@router.delete("/me")
async def delete_my_account(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Self-service account deletion (Apple App Store 5.1.1(v) & Google Play compliance)."""
    if current_user.is_admin:
        raise HTTPException(status_code=400, detail="Cannot delete an admin account")
    data_dir = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
    files, folders = _user_owned_files(db, current_user, data_dir)
    _anonymise_closed_results(db, {current_user.id})
    db.query(models.TournamentParticipant).filter(models.TournamentParticipant.user_id == current_user.id).delete()
    # Messages, AI conversations, notifications, devices... go with the user (ON DELETE CASCADE)
    db.delete(current_user)
    db.commit()
    # Files only once the database rows are gone
    _remove_files(files, folders)
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "deleted", "id": current_user.id}


def _anonymise_closed_results(db: Session, user_ids: set):
    """Closed tournaments keep a snapshot of the final standings: replace these players' names by #id."""
    from sqlalchemy.orm.attributes import flag_modified
    for t in db.query(models.Tournament).filter(models.Tournament.results.isnot(None)):
        changed = False
        for entry in (t.results if isinstance(t.results, list) else []):
            uid = entry.get("entity_id") if isinstance(entry, dict) else None
            if uid in user_ids and entry.get("name") != f"#{uid}":
                entry["name"] = f"#{uid}"
                changed = True
        if changed:
            flag_modified(t, "results")


def _remove_files(files, folders):
    import shutil
    for path in files:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)


# Where each kind of uploaded image lives, as stored in the database
_CHAT_IMAGE_PREFIXES = {"/data/chat_images/players/": "players", "/data/chat_images/public/": "public"}


def _user_owned_files(db: Session, user: models.User, data_dir: str):
    """Images a player uploaded (avatar and its thumbnails, chat images, AI conversation images).
    Stored paths partly come from the client, so only a bare file name inside the image folders
    is ever trusted: a crafted path can never point at another file on the server."""
    files, folders = [], []
    if user.avatar_url:
        name = os.path.basename(user.avatar_url.split("?")[0])
        if name and not name.startswith("."):
            files.append(os.path.join(data_dir, "avatars", name))
            stem = os.path.splitext(name)[0]
            thumbs_root = os.path.join(data_dir, "thumbs")
            if os.path.isdir(thumbs_root):
                for width in os.listdir(thumbs_root):
                    files.append(os.path.join(thumbs_root, width, "avatars", stem + ".webp"))

    stored = [m.image_path for m in db.query(models.PrivateMessage).filter(
        (models.PrivateMessage.sender_id == user.id) | (models.PrivateMessage.receiver_id == user.id))]
    stored += [m.image_path for m in db.query(models.GroupMessage).filter(models.GroupMessage.sender_id == user.id)]
    stored += [m.image_path for m in db.query(models.PublicChatMessage).filter(models.PublicChatMessage.user_id == user.id)]
    for path in stored:
        if not path:
            continue
        for prefix, folder in _CHAT_IMAGE_PREFIXES.items():
            if path.startswith(prefix):
                name = os.path.basename(path)
                if name and not name.startswith(".") and path == prefix + name:
                    files.append(os.path.join(data_dir, "chat_images", folder, name))
                break

    # AI images live in one folder per conversation, named after its numeric id
    for conv in db.query(models.Conversation).filter(models.Conversation.user_id == user.id):
        folders.append(os.path.join(data_dir, "chat_images", str(int(conv.id))))
    return files, folders

@router.put("/me/profile")
async def update_profile(data: dict, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    if "team_name" in data:
        user.team_name = data["team_name"]
    if "avatar_shape" in data:
        user.avatar_shape = data["avatar_shape"]
    db.commit()
    db.refresh(user)
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "updated", "team_name": user.team_name, "avatar_shape": user.avatar_shape}

@router.get("/me/points-history")
def get_points_history(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Get breakdown of how the user earned their points across tournaments."""
    from .tournaments import _compute_projected_standings
    
    tournaments = visible_tournaments(db).filter(
        models.Tournament.status.in_(["RUNNING", "DONE", "CLOSED"])
    ).all()
    history = []
    
    for t in tournaments:
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        game_name = None
        if t.game_id:
            game = db.query(models.Game).filter(models.Game.id == t.game_id).first()
            game_name = game.name if game else None

        # Check if user participates
        participant = db.query(models.TournamentParticipant).filter(
            models.TournamentParticipant.tournament_id == t.id,
            models.TournamentParticipant.user_id == user.id
        ).first()
        if not participant:
            continue

        is_live = t.status in ("RUNNING", "DONE")

        if t.status == "CLOSED" and t.results:
            # Use stored results for CLOSED tournaments
            for r in t.results:
                eid = r.get("entity_id")
                if not use_teams and eid == user.id:
                    history.append({
                        "tournament_id": t.id, "tournament_name": t.name,
                        "game_name": game_name, "status": t.status, "live": False,
                        "rank": r.get("rank"),
                        "placement_pts": round(float(r.get("placement_pts", 0)), 1),
                        "participation_pts": round(float(r.get("participation_pts", 0)), 1),
                        "score_pts": round(float(r.get("score_pts", 0)), 1),
                        "total": round(float(r.get("total", 0)), 1), "team_name": None
                    })
                    break
                elif use_teams and isinstance(eid, int) and eid < 0:
                    team_member = db.query(models.TournamentTeamMember).join(
                        models.TournamentTeam
                    ).filter(
                        models.TournamentTeam.tournament_id == t.id,
                        models.TournamentTeam.id == abs(eid),
                        models.TournamentTeamMember.user_id == user.id
                    ).first()
                    if team_member:
                        history.append({
                            "tournament_id": t.id, "tournament_name": t.name,
                            "game_name": game_name, "status": t.status, "live": False,
                            "rank": r.get("rank"),
                            "placement_pts": round(float(r.get("placement_pts", 0)), 1),
                            "participation_pts": round(float(r.get("participation_pts", 0)), 1),
                            "score_pts": round(float(r.get("score_pts", 0)), 1),
                            "total": round(float(r.get("total", 0)), 1), "team_name": r.get("name")
                        })
                        break
        else:
            # Use shared projected standings for RUNNING/DONE
            standings = _compute_projected_standings(t, db)

            # Find user's entry
            user_entity = user.id
            team_name_found = None
            if use_teams:
                team_member = db.query(models.TournamentTeamMember).join(
                    models.TournamentTeam
                ).filter(
                    models.TournamentTeam.tournament_id == t.id,
                    models.TournamentTeamMember.user_id == user.id
                ).first()
                if team_member:
                    user_entity = -team_member.team_id
                    team = db.query(models.TournamentTeam).get(team_member.team_id)
                    team_name_found = team.name if team else None

            entry = next((s for s in standings if s["entity_id"] == user_entity), None)
            if entry:
                # Each team member gets full team points (no division)
                history.append({
                    "tournament_id": t.id, "tournament_name": t.name,
                    "game_name": game_name, "status": t.status, "live": True,
                    "rank": entry["rank"],
                    "placement_pts": round(float(entry["placement_pts"]), 1),
                    "participation_pts": round(float(entry["participation_pts"]), 1),
                    "score_pts": round(float(entry["score_pts"]), 1),
                    "total": round(float(entry["total"]), 1),
                    "team_name": team_name_found
                })
            else:
                history.append({
                    "tournament_id": t.id, "tournament_name": t.name,
                    "game_name": game_name, "status": t.status, "live": True,
                    "rank": None, "placement_pts": 0, "participation_pts": 0,
                    "score_pts": 0, "total": 0, "team_name": None
                })

    # Fetch awards for current user
    awards_diffused_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "awards_diffused").first()
    is_diffused = awards_diffused_config.value if awards_diffused_config else False

    awards_list = []
    if is_diffused:
        awards = db.query(models.Award).filter(models.Award.user_id == user.id).order_by(models.Award.created_at.desc()).all()
        awards_list = [{
            "id": a.id,
            "award_key": a.award_key,
            "title": a.title,
            "description": a.description,
            "created_at": a.created_at.isoformat() if a.created_at else None
        } for a in awards]

    return {"total_points": round(float(user.points or 0), 1), "history": history, "awards": awards_list}

# --- ADMIN: User Management ---

@router.get("/admin/users")
def admin_list_users(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """List all users with details for admin management."""
    users = db.query(models.User).all()
    return [{"id": u.id, "username": u.username, "team_name": u.team_name, "is_admin": u.is_admin, "ia_blocked": u.ia_blocked or False, "seat_id": u.seat_id, "points": round(float(u.points), 1) if u.points is not None else 0, "avatar_url": u.avatar_url, "avatar_shape": u.avatar_shape, "is_online": u.is_online} for u in users]

@router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: int, data: dict, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin updates a user's username and/or team_name."""
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account from this panel")
    if "username" in data and data["username"].strip():
        existing = db.query(models.User).filter(models.User.username == data["username"], models.User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        target.username = data["username"].strip()
    if "team_name" in data:
        target.team_name = data["team_name"].strip() if data["team_name"] else None
    if "seat_id" in data:
        target.seat_id = data["seat_id"].strip() if data["seat_id"] else None
    if "points" in data:
        try:
            target.points = round(float(data["points"]), 1)
        except (ValueError, TypeError):
            pass
    if "is_admin" in data:
        target.is_admin = bool(data["is_admin"])
    if "ia_blocked" in data:
        target.ia_blocked = bool(data["ia_blocked"])
    db.commit()
    db.refresh(target)
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "updated", "id": target.id, "username": target.username, "team_name": target.team_name, "seat_id": target.seat_id, "points": round(float(target.points), 1) if target.points is not None else 0, "is_admin": target.is_admin, "ia_blocked": target.ia_blocked or False, "avatar_url": target.avatar_url, "avatar_shape": target.avatar_shape}

@router.post("/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, data: dict, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin resets a user's password."""
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_password = data.get("password", "lan2025")
    target.hashed_password = auth.get_password_hash(new_password)
    db.commit()
    return {"status": "password_reset", "username": target.username}

@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin deletes a user account."""
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.is_admin:
        raise HTTPException(status_code=400, detail="Cannot delete an admin account")
    # Clean up avatar file from disk
    if target.avatar_url:
        DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
        avatar_path = os.path.join(DATA_DIR, "avatars", os.path.basename(target.avatar_url.split("?")[0]))
        if os.path.exists(avatar_path):
            try:
                os.remove(avatar_path)
            except Exception:
                pass
    # Remove tournament participations
    db.query(models.TournamentParticipant).filter(models.TournamentParticipant.user_id == user_id).delete()
    db.delete(target)
    db.commit()
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "deleted", "id": user_id}

@router.post("/admin/config/test-searxng")
async def test_searxng(data: dict, admin: models.User = Depends(auth.get_current_admin)):
    """Test validity of a SearXNG instance URL."""
    url = data.get("url", "").strip()
    if not url:
        return {"ok": False, "error": "L'URL est vide."}
    
    # Ensure URL formatting
    url = url.rstrip("/")
    if not url.endswith("/search"):
        target_url = f"{url}/search"
    else:
        target_url = url
        
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            # We perform a real search test, e.g. querying for "test"
            resp = await client.get(
                target_url,
                params={
                    "q": "test",
                    "format": "json",
                    "categories": "images",
                },
                timeout=8.0
            )
            if resp.status_code != 200:
                return {
                    "ok": False, 
                    "error": f"Le serveur a répondu avec le statut {resp.status_code}. Vérifiez l'URL."
                }
            try:
                res_data = resp.json()
            except ValueError:
                return {
                    "ok": False, 
                    "error": "La réponse n'est pas au format JSON. Vérifiez que l'accès JSON est activé sur votre instance SearXNG."
                }
            
            if "results" not in res_data:
                return {
                    "ok": False, 
                    "error": "La réponse JSON ne contient pas la clé 'results'. Est-ce une instance SearXNG valide ?"
                }
                
            return {
                "ok": True, 
                "message": "Instance SearXNG valide et fonctionnelle (format JSON supporté)."
            }
    except httpx.ConnectError:
        return {"ok": False, "error": "Impossible de se connecter au serveur. Vérifiez l'URL ou la connexion réseau."}
    except httpx.TimeoutException:
        return {"ok": False, "error": "La requête a expiré (timeout de 8.0s)."}
    except Exception as e:
        return {"ok": False, "error": f"Erreur lors du test : {str(e)}"}

@router.get("/admin/config/{key}")
def admin_get_config(key: str, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin reads a system config value."""
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if not config:
        return {"key": key, "value": None}
    return {"key": key, "value": config.value}

@router.put("/admin/config/{key}")
async def admin_set_config(key: str, data: dict, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin sets a system config value."""
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if config:
        config.value = data.get("value")
    else:
        config = models.SystemConfig(key=key, value=data.get("value"))
        db.add(config)
    db.commit()
    await ws_manager.broadcast({"type": "config_updated"})
    return {"status": "updated", "key": key, "value": data.get("value")}

@router.delete("/admin/config/{key}")
async def admin_delete_config(key: str, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin deletes a system config value."""
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if config:
        db.delete(config)
        db.commit()
        await ws_manager.broadcast({"type": "config_updated"})
        return {"status": "deleted", "key": key}
    return {"status": "not_found", "key": key}

@router.get("/admin/prompts/status")
def admin_get_prompts_status(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin gets a list of translated prompt languages."""
    configs = db.query(models.SystemConfig).filter(
        models.SystemConfig.key.startswith('system_prompt_')
    ).all()
    translated_langs = []
    for c in configs:
        lang = c.key.replace("system_prompt_", "")
        if c.value and len(c.value.strip()) > 0:
            translated_langs.append(lang)
            
    # Also check if legacy "system_prompt" was customized and treat it as 'fr'
    legacy = db.query(models.SystemConfig).filter(models.SystemConfig.key == "system_prompt").first()
    if legacy and legacy.value and "fr" not in translated_langs:
        translated_langs.append("fr")
        
    return {"translated_langs": list(set(translated_langs))}

# --- ADMIN: Create Player ---

@router.post("/admin/users/create")
async def admin_create_user(data: dict, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin manually creates a player account."""
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    team_name = (data.get("team_name") or "").strip() or None
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
    existing = db.query(models.User).filter(models.User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")
    new_user = models.User(
        username=username,
        hashed_password=auth.get_password_hash(password),
        team_name=team_name,
        is_admin=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "created", "id": new_user.id, "username": new_user.username, "team_name": new_user.team_name}

@router.post("/admin/users/generate-test-pool")
async def admin_generate_test_pool(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Generate 20 test players spread across 4 teams for development."""
    import random
    teams = ["Alpha Wolves", "Neon Vipers", "Shadow Foxes", "Iron Bears"]
    pseudos = [
        "xX_DarkSlayer_Xx", "FragMaster2000", "NoobKiller", "ShadowNinja",
        "PixelHunter", "RocketQueen", "CyberWolf", "GlitchMaster",
        "Firefox", "NightHawk", "TurboGamer", "IcePhoenix",
        "StormBringer", "LaserCat", "DragonByte", "QuantumLeap",
        "BlazeRunner", "ArcticFox", "VoltStrike", "CosmicDust"
    ]
    created = []
    for i, pseudo in enumerate(pseudos):
        # Skip if username already exists
        existing = db.query(models.User).filter(models.User.username == pseudo).first()
        if existing:
            continue
        team = teams[i % len(teams)]
        new_user = models.User(
            username=pseudo,
            hashed_password=auth.get_password_hash("test"),
            team_name=team,
            is_admin=False,
            points=0
        )
        db.add(new_user)
        created.append({"username": pseudo, "team": team})
    db.commit()
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "generated", "created_count": len(created), "players": created}

# --- ADMIN: Nuke / Reset ---

@router.delete("/admin/nuke/tournaments")
def admin_nuke_tournaments(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete ALL tournaments, participants, teams, match reports, conflicts. Reset player points."""
    count = db.query(models.Tournament).count()
    db.query(models.MatchReport).delete()
    db.query(models.Conflict).delete()
    db.query(models.TournamentTeamMember).delete()
    db.query(models.TournamentTeam).delete()
    db.query(models.TournamentParticipant).delete()
    db.query(models.Tournament).delete()
    # Reset all player points to 0
    db.query(models.User).update({models.User.points: 0})
    db.commit()
    return {"status": "nuked", "deleted_tournaments": count}

@router.delete("/admin/nuke/players")
async def admin_nuke_players(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete ALL non-admin players and their data."""
    non_admins = db.query(models.User).filter(models.User.is_admin == False).all()
    count = len(non_admins)
    non_admin_ids = [u.id for u in non_admins]
    files, folders = [], []
    if non_admin_ids:
        # Same cleanup as a player deleting their own account: uploaded images, names in closed standings
        data_dir = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
        for u in non_admins:
            f, d = _user_owned_files(db, u, data_dir)
            files += f
            folders += d
        _anonymise_closed_results(db, set(non_admin_ids))
        # Clean up participations, team memberships, conversations, chat messages
        db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.user_id.in_(non_admin_ids)).delete(synchronize_session=False)
        db.query(models.TournamentParticipant).filter(models.TournamentParticipant.user_id.in_(non_admin_ids)).delete(synchronize_session=False)
        db.query(models.MatchReport).filter(models.MatchReport.user_id.in_(non_admin_ids)).delete(synchronize_session=False)
        # Delete conversations and messages
        convos = db.query(models.Conversation).filter(models.Conversation.user_id.in_(non_admin_ids)).all()
        for c in convos:
            db.query(models.ChatMessage).filter(models.ChatMessage.conversation_id == c.id).delete(synchronize_session=False)
        db.query(models.Conversation).filter(models.Conversation.user_id.in_(non_admin_ids)).delete(synchronize_session=False)
        # Delete private messages sent or received by these users
        db.query(models.PrivateMessage).filter(
            or_(models.PrivateMessage.sender_id.in_(non_admin_ids), models.PrivateMessage.receiver_id.in_(non_admin_ids))
        ).delete(synchronize_session=False)
        # Notifications, devices, awards, group and public chat messages, admin calls go with the user (ON DELETE CASCADE)
        db.query(models.User).filter(models.User.id.in_(non_admin_ids)).delete(synchronize_session=False)
    db.commit()
    _remove_files(files, folders)
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "nuked", "deleted_players": count}

@router.delete("/admin/nuke/games")
def admin_nuke_games(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete ALL games (cascades to tournaments via FK)."""
    count = db.query(models.Game).count()
    data_dir = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
    covers = [os.path.basename(g.image_url) for g in db.query(models.Game) if (g.image_url or "").startswith("/data/game_images/")]
    # Knowledge base entries written for a specific game have no game left to belong to
    for doc in db.query(models.KnowledgeBase).all():
        if isinstance(doc.metadata_json, dict) and doc.metadata_json.get("game_id"):
            db.delete(doc)
    # Must delete tournaments first due to FK constraints
    db.query(models.MatchReport).delete()
    db.query(models.Conflict).delete()
    db.query(models.TournamentTeamMember).delete()
    db.query(models.TournamentTeam).delete()
    db.query(models.TournamentParticipant).delete()
    db.query(models.Tournament).delete()
    db.query(models.Game).delete()
    # Reset points
    db.query(models.User).update({models.User.points: 0})
    db.commit()
    files = []
    thumbs_root = os.path.join(data_dir, "thumbs")
    for name in covers:
        if name and not name.startswith("."):
            files.append(os.path.join(data_dir, "game_images", name))
            if os.path.isdir(thumbs_root):
                for width in os.listdir(thumbs_root):
                    files.append(os.path.join(thumbs_root, width, "game_images", os.path.splitext(name)[0] + ".webp"))
    _remove_files(files, [])
    return {"status": "nuked", "deleted_games": count}

from pydantic import BaseModel as _BaseModel


class FullResetRequest(_BaseModel):
    keep_admins: bool = True
    confirm: str = ""


@router.post("/admin/reset-all")
async def admin_reset_all(body: FullResetRequest, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Factory reset: empty every table and every uploaded file, as on a new installation.
    Admin accounts can be kept (their LAN data is cleared, login, password and avatar stay).
    The session signing key is kept, so a kept admin stays logged in."""
    if body.confirm.strip().upper() != "RESET":
        raise HTTPException(status_code=400, detail="Type RESET to confirm")
    import shutil
    from ..database import Base
    data_dir = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
    kept = db.query(models.User).filter(models.User.is_admin == True).all() if body.keep_admins else []
    kept_avatars = {os.path.basename(u.avatar_url.split("?")[0]) for u in kept if u.avatar_url}

    # Children first, so foreign keys never block a delete
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == "users" and body.keep_admins:
            db.execute(table.delete().where(table.c.is_admin == False))
        else:
            db.execute(table.delete())
    if body.keep_admins:
        db.query(models.User).update({
            models.User.points: 0, models.User.seat_id: None, models.User.team_name: None,
            models.User.ia_blocked: False, models.User.public_chat_muted_until: None,
        }, synchronize_session=False)
    db.commit()

    # Uploaded files and generated copies; customised translations go too (factory texts come back)
    for sub in ("chat_images", "game_images", "thumbs", "info_files", "i18n"):
        shutil.rmtree(os.path.join(data_dir, sub), ignore_errors=True)
    avatars_dir = os.path.join(data_dir, "avatars")
    if os.path.isdir(avatars_dir):
        for name in os.listdir(avatars_dir):
            if name not in kept_avatars:
                try:
                    os.remove(os.path.join(avatars_dir, name))
                except OSError:
                    pass
    for sub in ("chat_images/players", "chat_images/public", "game_images", "info_files", "i18n", "avatars"):
        os.makedirs(os.path.join(data_dir, sub), exist_ok=True)
    try:
        from .i18n import _I18N_CACHE
        _I18N_CACHE.clear()
    except Exception:
        pass
    from ..database import ACTIVE_USERS
    ACTIVE_USERS.clear()

    await ws_manager.broadcast({"type": "server_reset", "kept_admins": body.keep_admins})
    return {"status": "reset", "kept_admins": len(kept)}


@router.delete("/admin/nuke/notifications")
def admin_nuke_notifications(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete ALL notifications for all users."""
    count = db.query(models.Notification).count()
    db.query(models.Notification).delete()
    db.commit()
    return {"status": "nuked", "deleted_notifications": count}


@router.delete("/admin/nuke/room")
async def admin_nuke_room(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete the room map (tables, seats, elements) and free every player's seat."""
    seats = 0
    for room in db.query(models.RoomMap).all():
        seats += len((room.layout or {}).get("seats") or [])
        db.delete(room)
    freed = db.query(models.User).filter(models.User.seat_id.isnot(None)).update({models.User.seat_id: None}, synchronize_session=False)
    db.commit()
    await ws_manager.broadcast({"type": "room_updated"})
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "nuked", "deleted_seats": seats, "freed_players": freed}

@router.post("/me/avatar")
async def upload_my_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    await file.seek(0)
    size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="L'image est trop grande (max 10 Mo)")
    await file.seek(0)

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être une image")

    ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    ext = "".join(c for c in ext if c.isalnum())[:5]

    DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
    avatars_dir = os.path.join(DATA_DIR, "avatars")
    os.makedirs(avatars_dir, exist_ok=True)

    if user.avatar_url:
        old_filename = os.path.basename(user.avatar_url.split("?")[0])
        old_file_path = os.path.join(avatars_dir, old_filename)
        if os.path.exists(old_file_path):
            try:
                os.remove(old_file_path)
            except Exception:
                pass

    filename = f"{user.id}_avatar.{ext}"
    filepath = os.path.join(avatars_dir, filename)
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    import time
    user.avatar_url = f"/data/avatars/{filename}?t={int(time.time())}"
    db.commit()
    db.refresh(user)
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "success", "avatar_url": user.avatar_url}

@router.delete("/me/avatar")
async def delete_my_avatar(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    if user.avatar_url:
        DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
        avatars_dir = os.path.join(DATA_DIR, "avatars")
        filename = os.path.basename(user.avatar_url.split("?")[0])
        filepath = os.path.join(avatars_dir, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
        user.avatar_url = None
        db.commit()
        db.refresh(user)
        await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "success"}

@router.delete("/admin/users/{user_id}/avatar")
async def admin_delete_user_avatar(
    user_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    if target.avatar_url:
        DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
        avatars_dir = os.path.join(DATA_DIR, "avatars")
        filename = os.path.basename(target.avatar_url.split("?")[0])
        filepath = os.path.join(avatars_dir, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
        target.avatar_url = None
        db.commit()
        db.refresh(target)
        await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "success"}


_trace_base = None


@router.get("/admin/diagnostics/memory")
async def memory_diagnostics(top: int = 0, trace: str = "", admin: models.User = Depends(auth.get_current_admin)):
    """Process memory and the size of every long-lived registry, to spot a leak on a running server."""
    import gc
    from ..websockets import manager
    from ..database import ACTIVE_USERS
    from ..ia_queue import queue_manager
    from ..ia_tools import pending_client_calls
    from .public_chat import _link_preview_cache
    from .ia import _health_cache, active_chats
    rss_kb = None
    try:
        with open("/proc/self/status") as f:
            rss_kb = next((int(l.split()[1]) for l in f if l.startswith("VmRSS")), None)
    except OSError:
        pass
    result = {}
    # trace=start records allocations from now on; trace=diff lists the code lines that grew since
    import tracemalloc
    global _trace_base
    if trace == "start":
        tracemalloc.start(15)
        _trace_base = tracemalloc.take_snapshot()
    elif trace == "diff" and tracemalloc.is_tracing() and _trace_base:
        stats = tracemalloc.take_snapshot().compare_to(_trace_base, "traceback")[:8]
        result["trace_diff"] = [{"kb": round(st.size_diff / 1024, 1), "count": st.count_diff,
                                 "where": [f"{fr.filename.split('site-packages/')[-1]}:{fr.lineno}" for fr in st.traceback[-6:]]} for st in stats]
    elif trace == "stop" and tracemalloc.is_tracing():
        tracemalloc.stop()
        _trace_base = None
    if top:
        # Most numerous live Python object types: compare two calls to see what accumulates
        from collections import Counter
        counts = Counter(type(o).__name__ for o in gc.get_objects())
        result["top_types"] = counts.most_common(min(top, 50))
    return result | {
        "rss_mb": round(rss_kb / 1024, 1) if rss_kb else None,
        "ws_active_connections": len(manager.active_connections),
        "ws_connection_users": len(manager.connection_users),
        "ws_connection_clients": len(manager.connection_clients),
        "ws_user_connections": sum(len(s) for s in manager.user_connections.values()),
        "ws_objects_alive": sum(1 for o in gc.get_objects() if type(o).__name__ == "WebSocket"),
        "active_users": len(ACTIVE_USERS),
        "ia_queue_pending": len(queue_manager._pending),
        "ia_queue_active": len(queue_manager._active),
        "ia_pending_client_calls": len(pending_client_calls),
        "ia_active_chats": len(active_chats),
        "health_cache": len(_health_cache),
        "link_preview_cache": len(_link_preview_cache),
        "asyncio_tasks": len(__import__("asyncio").all_tasks()),
    }
