from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import timedelta
from .. import models, schemas, auth, database
from ..websockets import manager as ws_manager

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
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@router.put("/me/profile")
async def update_profile(data: dict, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    if "team_name" in data:
        user.team_name = data["team_name"]
    db.commit()
    db.refresh(user)
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "updated", "team_name": user.team_name}

@router.get("/me/points-history")
def get_points_history(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Get breakdown of how the user earned their points across tournaments."""
    from .tournaments import _compute_projected_standings
    
    tournaments = db.query(models.Tournament).filter(
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
                        "placement_pts": r.get("placement_pts", 0),
                        "participation_pts": r.get("participation_pts", 0),
                        "score_pts": r.get("score_pts", 0),
                        "total": r.get("total", 0), "team_name": None
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
                            "placement_pts": r.get("placement_pts", 0),
                            "participation_pts": r.get("participation_pts", 0),
                            "score_pts": r.get("score_pts", 0),
                            "total": r.get("total", 0), "team_name": r.get("name")
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
                    "placement_pts": entry["placement_pts"],
                    "participation_pts": entry["participation_pts"],
                    "score_pts": entry["score_pts"],
                    "total": entry["total"],
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
    awards = db.query(models.Award).filter(models.Award.user_id == user.id).order_by(models.Award.created_at.desc()).all()
    awards_list = [{
        "id": a.id,
        "title": a.title,
        "description": a.description,
        "created_at": a.created_at.isoformat() if a.created_at else None
    } for a in awards]

    return {"total_points": user.points or 0, "history": history, "awards": awards_list}

# --- ADMIN: User Management ---

@router.get("/admin/users")
def admin_list_users(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """List all users with details for admin management."""
    users = db.query(models.User).all()
    return [{"id": u.id, "username": u.username, "team_name": u.team_name, "is_admin": u.is_admin, "ia_blocked": u.ia_blocked or False, "seat_id": u.seat_id, "points": u.points} for u in users]

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
            target.points = int(data["points"])
        except (ValueError, TypeError):
            pass
    if "is_admin" in data:
        target.is_admin = bool(data["is_admin"])
    if "ia_blocked" in data:
        target.ia_blocked = bool(data["ia_blocked"])
    db.commit()
    db.refresh(target)
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "updated", "id": target.id, "username": target.username, "team_name": target.team_name, "seat_id": target.seat_id, "points": target.points, "is_admin": target.is_admin, "ia_blocked": target.ia_blocked or False}

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
    # Remove tournament participations
    db.query(models.TournamentParticipant).filter(models.TournamentParticipant.user_id == user_id).delete()
    db.delete(target)
    db.commit()
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "deleted", "id": user_id}

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
    if non_admin_ids:
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
        db.query(models.User).filter(models.User.id.in_(non_admin_ids)).delete(synchronize_session=False)
    db.commit()
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "nuked", "deleted_players": count}

@router.delete("/admin/nuke/games")
def admin_nuke_games(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete ALL games (cascades to tournaments via FK)."""
    count = db.query(models.Game).count()
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
    return {"status": "nuked", "deleted_games": count}

@router.delete("/admin/nuke/notifications")
def admin_nuke_notifications(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete ALL notifications for all users."""
    count = db.query(models.Notification).count()
    db.query(models.Notification).delete()
    db.commit()
    return {"status": "nuked", "deleted_notifications": count}

# --- ADMIN: Awards & Prizes (Prix loufoques & classiques) ---
from pydantic import BaseModel

# --- ADMIN: Awards & Prizes (Prix loufoques & classiques) ---
from pydantic import BaseModel
import json
import asyncio

# Metadata mapping for all 12 stats-driven awards
AWARD_METADATA = {
    "premier": {
        "criteria": "Premier du classement général individuel de la LAN.",
        "default_title": "🏆 Roi de la LAN",
        "default_description": "Félicitations pour avoir dominé le tournoi avec un total impressionnant de {points} points !"
    },
    "team": {
        "criteria": "Membres de l'équipe ayant accumulé le plus de points.",
        "default_title": "🛡️ L'Union fait la Force",
        "default_description": "L'équipe {team_name} a écrasé la compétition en cumulant {points} points au total !"
    },
    "bourreau": {
        "criteria": "Joueur ayant infligé le plus de défaites en solo (1v1).",
        "default_title": "⚔️ Le Bourreau des Brackets",
        "default_description": "Pour avoir accumulé le plus grand nombre de victoires en solo ({wins} victoires)."
    },
    "coop": {
        "criteria": "Joueur gagnant en équipe mais très discret en solo.",
        "default_title": "🤝 Le Roi du Coop",
        "default_description": "Un joueur d'équipe exceptionnel ! Gagnant en équipe ({team_wins} victoires) mais très discret en solo ({solo_wins} victoires)."
    },
    "loup": {
        "criteria": "Joueur redoutable en solo mais n'ayant pas gagné en équipe.",
        "default_title": "🐺 Le Loup Solitaire",
        "default_description": "Redoutable en solo avec {solo_wins} victoires, mais n'a pas trouvé ses marques en équipe (0 victoire)."
    },
    "participate": {
        "criteria": "Joueur ayant disputé au moins 2 matchs avec le taux de victoire le plus bas.",
        "default_title": "🕊️ L'Important c'est de Participer",
        "default_description": "Pour son esprit sportif inébranlable et sa persévérance à travers {matches_played} matchs disputés !"
    },
    "marathon": {
        "criteria": "Joueur infatigable ayant disputé le plus de matchs dans toute la LAN.",
        "default_title": "🏃 Le Marathonien",
        "default_description": "Le joueur infatigable de la LAN avec un record absolu de {matches_played} matchs joués !"
    },
    "gachette": {
        "criteria": "Joueur ayant réalisé le score maximal le plus élevé en une seule partie.",
        "default_title": "🎯 La Gâchette Facile",
        "default_description": "Pour avoir réalisé le carton de la LAN avec un score maximal de {highest_score} points en une seule partie !"
    },
    "passoire": {
        "criteria": "Joueur ayant encaissé le plus de points/buts au total.",
        "default_title": "🥅 La Passoire de la LAN",
        "default_description": "Une défense très généreuse... {total_score_conceded} buts/points encaissés au total !"
    },
    "bye": {
        "criteria": "Joueur ayant bénéficié du plus grand nombre de BYE.",
        "default_title": "🍀 Le Chouchou des BYE",
        "default_description": "Le grand favori du destin qui a bénéficié de {bye_count} qualifications automatiques par BYE !"
    },
    "suisse": {
        "criteria": "Joueur ayant réalisé le plus grand nombre de matchs nuls.",
        "default_title": "🇨🇭 Le Suisse",
        "default_description": "Neutre et pacifique, spécialiste incontesté du partage des points avec {draws} égalités."
    },
    "lb": {
        "criteria": "Joueur ayant joué le plus de matchs dans le Loser Bracket.",
        "default_title": "🩹 Le Survivant du LB",
        "default_description": "Celui qui a pris le chemin le plus long et le plus difficile en disputant {lb_matches} matchs dans le Loser Bracket !"
    }
}

class AwardTextUpdate(BaseModel):
    title: str
    description: str

def _compute_awards_suggestions(db: Session) -> dict:
    users = db.query(models.User).all()
    user_map = {u.id: u for u in users}

    # Initialize statistics counters
    stats = {}
    for u in users:
        stats[u.id] = {
            "user_id": u.id,
            "username": u.username,
            "points": u.points or 0,
            "team_name": u.team_name,
            "solo_wins": 0,
            "team_wins": 0,
            "solo_losses": 0,
            "team_losses": 0,
            "matches_played": 0,
            "total_score_scored": 0,
            "total_score_conceded": 0,
            "highest_score": 0,
            "bye_count": 0,
            "draws": 0,
            "lb_matches_played": 0,
        }

    # Query all tournaments that are running, done, or closed
    tournaments = db.query(models.Tournament).filter(
        models.Tournament.status.in_(["RUNNING", "DONE", "CLOSED"])
    ).all()

    for t in tournaments:
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        bracket_type = config.get("bracket_type", "single_elim")
        
        # Build team member mapping for this tournament
        team_to_users = {}
        if use_teams:
            members = db.query(models.TournamentTeamMember).join(
                models.TournamentTeam
            ).filter(
                models.TournamentTeam.tournament_id == t.id
            ).all()
            for m in members:
                team_to_users.setdefault(m.team_id, []).append(m.user_id)

        bracket = t.bracket or []
        for match in bracket:
            mid = match.get("id", {})
            section = mid.get("s", 1)  # 1: WB/Main, 2: LB
            is_lb = (section == 2)
            
            players = match.get("p", [])
            scores = match.get("score", [])

            if not players or len(players) < 2:
                continue

            # For FFA:
            if bracket_type == "ffa":
                if scores and all(s is not None and s > 0 for s in scores) and len(scores) == len(players):
                    for i, pid in enumerate(players):
                        if not pid or pid == 0:
                            continue
                        uids = [pid]
                        for uid in uids:
                            if uid in stats:
                                stats[uid]["matches_played"] += 1
                                score = scores[i]
                                if score == 1:
                                    stats[uid]["solo_wins"] += 1
                                else:
                                    stats[uid]["solo_losses"] += 1
                continue

            # For Duel or Championship:
            if len(players) == 2 and len(scores) == 2:
                p1, p2 = players[0], players[1]
                s1, s2 = scores[0], scores[1]

                # Identify if one of the slots is a BYE (0)
                if p1 == 0 or p2 == 0:
                    recipient = p1 if p2 == 0 else p2
                    if recipient and recipient != 0:
                        uids = team_to_users.get(abs(recipient), []) if (use_teams and recipient < 0) else [recipient]
                        for uid in uids:
                            if uid in stats:
                                stats[uid]["bye_count"] += 1
                    continue

                if s1 is not None and s2 is not None:
                    uids1 = team_to_users.get(abs(p1), []) if (use_teams and p1 < 0) else [p1]
                    uids2 = team_to_users.get(abs(p2), []) if (use_teams and p2 < 0) else [p2]

                    # Stats for group 1
                    for uid in uids1:
                        if uid in stats:
                            stats[uid]["matches_played"] += 1
                            if is_lb:
                                stats[uid]["lb_matches_played"] += 1
                            stats[uid]["total_score_scored"] += s1
                            stats[uid]["total_score_conceded"] += s2
                            if s1 > stats[uid]["highest_score"]:
                                stats[uid]["highest_score"] = s1

                            if s1 > s2:
                                if use_teams:
                                    stats[uid]["team_wins"] += 1
                                else:
                                    stats[uid]["solo_wins"] += 1
                            elif s1 < s2:
                                if use_teams:
                                    stats[uid]["team_losses"] += 1
                                else:
                                    stats[uid]["solo_losses"] += 1
                            else:
                                stats[uid]["draws"] += 1

                    # Stats for group 2
                    for uid in uids2:
                        if uid in stats:
                            stats[uid]["matches_played"] += 1
                            if is_lb:
                                stats[uid]["lb_matches_played"] += 1
                            stats[uid]["total_score_scored"] += s2
                            stats[uid]["total_score_conceded"] += s1
                            if s2 > stats[uid]["highest_score"]:
                                stats[uid]["highest_score"] = s2

                            if s2 > s1:
                                if use_teams:
                                    stats[uid]["team_wins"] += 1
                                else:
                                    stats[uid]["solo_wins"] += 1
                            elif s2 < s1:
                                if use_teams:
                                    stats[uid]["team_losses"] += 1
                                else:
                                    stats[uid]["solo_losses"] += 1
                            else:
                                stats[uid]["draws"] += 1

    # Calculate derived awards suggestions
    # 1. Premier de la LAN
    premier = max(users, key=lambda u: u.points or 0, default=None)
    premier_suggestion = {
        "user_ids": [premier.id] if premier else [],
        "username": premier.username if premier else None,
        "points": premier.points if premier else 0,
        "title": "🏆 Premier de la LAN",
        "description": f"Félicitations pour avoir dominé le tournoi avec un total impressionnant de {premier.points if premier else 0} points !",
        "stats_label": f"{premier.points if premier else 0} points"
    } if premier and (premier.points or 0) > 0 else None

    # 2. Équipe Championne
    team_points = {}
    for u in users:
        if u.team_name:
            team_points[u.team_name] = team_points.get(u.team_name, 0) + (u.points or 0)
    best_team = max(team_points.items(), key=lambda x: x[1], default=None)
    best_team_name = best_team[0] if best_team else None
    team_member_ids = [u.id for u in users if u.team_name == best_team_name] if best_team_name else []
    
    team_suggestion = {
        "user_ids": team_member_ids,
        "username": f"Membres de {best_team_name}" if best_team_name else None,
        "team_name": best_team_name,
        "points": best_team[1] if best_team else 0,
        "title": "🛡️ L'Union fait la Force",
        "description": f"L'équipe {best_team_name} a écrasé la compétition en cumulant {best_team[1] if best_team else 0} points au total !",
        "stats_label": f"Équipe {best_team_name} ({best_team[1] if best_team else 0} pts)"
    } if best_team and best_team[1] > 0 else None

    # 3. Le Bourreau des Brackets (Most solo wins)
    most_solo_wins_uid = max(stats.keys(), key=lambda uid: stats[uid]["solo_wins"], default=None)
    most_solo_wins = stats[most_solo_wins_uid] if most_solo_wins_uid and stats[most_solo_wins_uid]["solo_wins"] > 0 else None
    bourreau_suggestion = {
        "user_ids": [most_solo_wins["user_id"]] if most_solo_wins else [],
        "username": most_solo_wins["username"] if most_solo_wins else None,
        "wins": most_solo_wins["solo_wins"] if most_solo_wins else 0,
        "title": "⚔️ Le Bourreau des Brackets",
        "description": f"Pour avoir accumulé le plus grand nombre de victoires en solo ({most_solo_wins['solo_wins'] if most_solo_wins else 0} victoires).",
        "stats_label": f"{most_solo_wins['solo_wins'] if most_solo_wins else 0} victoires"
    } if most_solo_wins else None

    # 4. Le Roi du Coop
    coop_players = [stats[uid] for uid in stats if stats[uid]["team_wins"] >= 2 and stats[uid]["solo_wins"] <= 1]
    roi_coop = max(coop_players, key=lambda s: s["team_wins"], default=None)
    coop_suggestion = {
        "user_ids": [roi_coop["user_id"]] if roi_coop else [],
        "username": roi_coop["username"] if roi_coop else None,
        "team_wins": roi_coop["team_wins"] if roi_coop else 0,
        "solo_wins": roi_coop["solo_wins"] if roi_coop else 0,
        "title": "🤝 Le Roi du Coop",
        "description": f"Un joueur d'équipe exceptionnel ! Gagnant en équipe ({roi_coop['team_wins'] if roi_coop else 0} victoires) mais très discret en solo ({roi_coop['solo_wins'] if roi_coop else 0} victoires).",
        "stats_label": f"{roi_coop['team_wins'] if roi_coop else 0} victoires en équipe"
    } if roi_coop else None

    # 5. Le Loup Solitaire
    solitary_players = [stats[uid] for uid in stats if stats[uid]["solo_wins"] >= 2 and stats[uid]["team_wins"] == 0]
    loup_solitaire = max(solitary_players, key=lambda s: s["solo_wins"], default=None)
    loup_suggestion = {
        "user_ids": [loup_solitaire["user_id"]] if loup_solitaire else [],
        "username": loup_solitaire["username"] if loup_solitaire else None,
        "solo_wins": loup_solitaire["solo_wins"] if loup_solitaire else 0,
        "title": "🐺 Le Loup Solitaire",
        "description": f"Redoutable en solo avec {loup_solitaire['solo_wins'] if loup_solitaire else 0} victoires, mais n'a pas trouvé ses marques en équipe (0 victoire).",
        "stats_label": f"{loup_solitaire['solo_wins'] if loup_solitaire else 0} victoires solo"
    } if loup_solitaire else None

    # 6. L'Important c'est de Participer
    participating_players = [stats[uid] for uid in stats if stats[uid]["matches_played"] >= 2]
    for p in participating_players:
        p["win_rate"] = (p["solo_wins"] + p["team_wins"]) / p["matches_played"]
    participate_player = min(participating_players, key=lambda s: s["win_rate"], default=None)
    participate_suggestion = {
        "user_ids": [participate_player["user_id"]] if participate_player else [],
        "username": participate_player["username"] if participate_player else None,
        "win_rate": f"{round(participate_player['win_rate'] * 100)}%" if participate_player else "0%",
        "matches_played": participate_player["matches_played"] if participate_player else 0,
        "title": "🕊️ L'Important c'est de Participer",
        "description": f"Pour son esprit sportif inébranlable et sa persévérance à travers {participate_player['matches_played'] if participate_player else 0} matchs disputés !",
        "stats_label": f"{round(participate_player['win_rate'] * 100) if participate_player else 0}% de victoires ({participate_player['matches_played'] if participate_player else 0} matchs)"
    } if participate_player else None

    # 7. Le Marathonien
    marathonien = max(stats.values(), key=lambda s: s["matches_played"], default=None)
    marathon_suggestion = {
        "user_ids": [marathonien["user_id"]] if marathonien else [],
        "username": marathonien["username"] if marathonien else None,
        "matches_played": marathonien["matches_played"] if marathonien else 0,
        "title": "🏃 Le Marathonien",
        "description": f"Le joueur infatigable de la LAN avec un record absolu de {marathonien['matches_played'] if marathonien else 0} matchs joués !",
        "stats_label": f"{marathonien['matches_played'] if marathonien else 0} matchs joués"
    } if marathonien and marathonien["matches_played"] > 0 else None

    # 8. La Gâchette Facile
    gachette = max(stats.values(), key=lambda s: s["highest_score"], default=None)
    gachette_suggestion = {
        "user_ids": [gachette["user_id"]] if gachette else [],
        "username": gachette["username"] if gachette else None,
        "highest_score": gachette["highest_score"] if gachette else 0,
        "title": "🎯 La Gâchette Facile",
        "description": f"Pour avoir réalisé le carton de la LAN avec un score maximal de {gachette['highest_score'] if gachette else 0} points en une seule partie !",
        "stats_label": f"Score max de {gachette['highest_score'] if gachette else 0}"
    } if gachette and gachette["highest_score"] > 0 else None

    # 9. La Passoire de la LAN
    passoire = max(stats.values(), key=lambda s: s["total_score_conceded"], default=None)
    passoire_suggestion = {
        "user_ids": [passoire["user_id"]] if passoire else [],
        "username": passoire["username"] if passoire else None,
        "total_score_conceded": passoire["total_score_conceded"] if passoire else 0,
        "title": "🥅 La Passoire de la LAN",
        "description": f"Une défense très généreuse... {passoire['total_score_conceded'] if passoire else 0} buts/points encaissés au total !",
        "stats_label": f"{passoire['total_score_conceded'] if passoire else 0} buts/points encaissés"
    } if passoire and passoire["total_score_conceded"] > 0 else None

    # 10. Le Chouchou des BYE
    bye_player = max(stats.values(), key=lambda s: s["bye_count"], default=None)
    bye_suggestion = {
        "user_ids": [bye_player["user_id"]] if bye_player else [],
        "username": bye_player["username"] if bye_player else None,
        "bye_count": bye_player["bye_count"] if bye_player else 0,
        "title": "🍀 Le Chouchou des BYE",
        "description": f"Le grand favori du destin qui a bénéficié de {bye_player['bye_count'] if bye_player else 0} qualifications automatiques par BYE !",
        "stats_label": f"{bye_player['bye_count'] if bye_player else 0} BYE reçus"
    } if bye_player and bye_player["bye_count"] > 0 else None

    # 11. Le Suisse
    suisse = max(stats.values(), key=lambda s: s["draws"], default=None)
    suisse_suggestion = {
        "user_ids": [suisse["user_id"]] if suisse else [],
        "username": suisse["username"] if suisse else None,
        "draws": suisse["draws"] if suisse else 0,
        "title": "🇨🇭 Le Suisse",
        "description": f"Neutre et pacifique, spécialiste incontesté du partage des points avec {suisse['draws'] if suisse else 0} égalités.",
        "stats_label": f"{suisse['draws'] if suisse else 0} égalités"
    } if suisse and suisse["draws"] > 0 else None

    # 12. Le Survivant du LB
    lb_survivor = max(stats.values(), key=lambda s: s["lb_matches_played"], default=None)
    lb_suggestion = {
        "user_ids": [lb_survivor["user_id"]] if lb_survivor else [],
        "username": lb_survivor["username"] if lb_survivor else None,
        "lb_matches": lb_survivor["lb_matches_played"] if lb_survivor else 0,
        "title": "🩹 Le Survivant du LB",
        "description": f"Celui qui a pris le chemin le plus long et le plus difficile en disputant {lb_survivor['lb_matches_played'] if lb_survivor else 0} matchs dans le Loser Bracket !",
        "stats_label": f"{lb_survivor['lb_matches_played'] if lb_survivor else 0} matchs LB"
    } if lb_survivor and lb_survivor["lb_matches_played"] > 0 else None

    return {
        "premier": premier_suggestion,
        "team": team_suggestion,
        "bourreau": bourreau_suggestion,
        "coop": coop_suggestion,
        "loup": loup_suggestion,
        "participate": participate_suggestion,
        "marathon": marathon_suggestion,
        "gachette": gachette_suggestion,
        "passoire": passoire_suggestion,
        "bye": bye_suggestion,
        "suisse": suisse_suggestion,
        "lb": lb_suggestion
    }

def sync_automatic_awards(db: Session):
    """Synchronize stats-driven automatic awards with user assignments and handle notifications."""
    suggestions = _compute_awards_suggestions(db)
    for category, meta in AWARD_METADATA.items():
        suggestion = suggestions.get(category)
        
        # Get custom texts
        config_row = db.query(models.SystemConfig).filter(models.SystemConfig.key == f"award_text_{category}").first()
        custom_title = None
        custom_desc = None
        if config_row:
            try:
                data = json.loads(config_row.value)
                custom_title = data.get("title")
                custom_desc = data.get("description")
            except Exception:
                pass
        
        title = custom_title or meta["default_title"]
        description = custom_desc or meta["default_description"]
        
        computed_uids = set(suggestion["user_ids"]) if suggestion else set()
        
        # Interpolate variables if present in the description template
        if suggestion:
            try:
                params = {
                    "points": suggestion.get("points", 0),
                    "wins": suggestion.get("wins", 0),
                    "team_wins": suggestion.get("team_wins", 0),
                    "solo_wins": suggestion.get("solo_wins", 0),
                    "matches_played": suggestion.get("matches_played", 0),
                    "highest_score": suggestion.get("highest_score", 0),
                    "total_score_conceded": suggestion.get("total_score_conceded", 0),
                    "bye_count": suggestion.get("bye_count", 0),
                    "draws": suggestion.get("draws", 0),
                    "lb_matches": suggestion.get("lb_matches", 0),
                    "team_name": suggestion.get("team_name", ""),
                }
                description = description.format(**params)
            except Exception:
                pass

        # Query current awardees in database for this category
        existing_awards = db.query(models.Award).filter(models.Award.award_key == category).all()
        existing_uids = {a.user_id for a in existing_awards}
        
        if existing_uids != computed_uids:
            # Delete old awards
            db.query(models.Award).filter(models.Award.award_key == category).delete()
            db.commit()
            
            # Recreate with new awardees
            for uid in computed_uids:
                new_award = models.Award(
                    user_id=uid,
                    award_key=category,
                    title=title,
                    description=description
                )
                db.add(new_award)
                
                # Notification
                notif = models.Notification(
                    user_id=uid,
                    type="award",
                    title=f"🏆 Prix obtenu : {title} !",
                    content=description
                )
                db.add(notif)
                
                # WS Broadcast trigger
                asyncio.create_task(ws_manager.broadcast({"type": "notification_new", "user_id": uid}))
            db.commit()
        else:
            # Only update title/description texts if changed
            for a in existing_awards:
                if a.title != title or a.description != description:
                    a.title = title
                    a.description = description
            db.commit()

@router.get("/admin/awards")
def admin_list_awards(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """List all categories of awards with statistics, recipient details, and editable templates."""
    # Ensure database is up to date before serving
    sync_automatic_awards(db)
    
    suggestions = _compute_awards_suggestions(db)
    
    results = []
    for category, meta in AWARD_METADATA.items():
        # Get custom texts if any
        config_row = db.query(models.SystemConfig).filter(models.SystemConfig.key == f"award_text_{category}").first()
        custom_title = None
        custom_desc = None
        if config_row:
            try:
                data = json.loads(config_row.value)
                custom_title = data.get("title")
                custom_desc = data.get("description")
            except Exception:
                pass
        
        suggestion = suggestions.get(category)
        recipient_name = suggestion["username"] if suggestion else None
        stats_label = suggestion["stats_label"] if suggestion else None
        
        results.append({
            "key": category,
            "criteria": meta["criteria"],
            "default_title": meta["default_title"],
            "default_description": meta["default_description"],
            "title": custom_title or meta["default_title"],
            "description": custom_desc or meta["default_description"],
            "custom_title": custom_title,
            "custom_description": custom_desc,
            "recipient_name": recipient_name,
            "stats_label": stats_label,
            "has_recipient": suggestion is not None
        })
    return results

@router.put("/admin/awards/{category_key}")
async def admin_update_award_text(
    category_key: str,
    body: AwardTextUpdate,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Save custom title and description overrides for a stats award category."""
    if category_key not in AWARD_METADATA:
        raise HTTPException(status_code=404, detail="Award category not found")
        
    value_json = json.dumps({
        "title": body.title.strip(),
        "description": body.description.strip()
    })
    
    config_row = db.query(models.SystemConfig).filter(models.SystemConfig.key == f"award_text_{category_key}").first()
    if config_row:
        config_row.value = value_json
    else:
        config_row = models.SystemConfig(key=f"award_text_{category_key}", value=value_json)
        db.add(config_row)
        
    db.commit()
    
    # Re-sync to propagate changes instantly
    sync_automatic_awards(db)
    db.commit()
    
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "updated", "key": category_key}

@router.delete("/admin/awards/{category_key}/text")
async def admin_delete_award_text(
    category_key: str,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Restore default text for a stats award category."""
    if category_key not in AWARD_METADATA:
        raise HTTPException(status_code=404, detail="Award category not found")
        
    db.query(models.SystemConfig).filter(models.SystemConfig.key == f"award_text_{category_key}").delete()
    db.commit()
    
    # Re-sync to propagate defaults
    sync_automatic_awards(db)
    db.commit()
    
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "restored", "key": category_key}

@router.delete("/admin/nuke/awards")
async def admin_nuke_awards(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete all custom configurations and assigned awards, resetting everything to defaults."""
    db.query(models.Award).delete()
    db.query(models.SystemConfig).filter(models.SystemConfig.key.like("award_text_%")).delete()
    db.commit()
    
    # Re-sync back to default awards
    sync_automatic_awards(db)
    db.commit()
    
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "nuked"}
