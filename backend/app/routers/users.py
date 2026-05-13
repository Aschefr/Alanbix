from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from .. import models, schemas, auth, database

router = APIRouter(tags=["Users"])

@router.post("/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
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
def update_profile(data: dict, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    if "team_name" in data:
        user.team_name = data["team_name"]
    db.commit()
    db.refresh(user)
    return {"status": "updated", "team_name": user.team_name}

@router.get("/me/points-history")
def get_points_history(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Get breakdown of how the user earned their points across tournaments."""
    from .tournaments import _compute_standings
    
    tournaments = db.query(models.Tournament).filter(
        models.Tournament.status.in_(["RUNNING", "DONE", "CLOSED"])
    ).all()
    history = []
    
    for t in tournaments:
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        is_closed = t.status == "CLOSED"
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

        if is_closed and t.results:
            # Use stored results for CLOSED tournaments
            results = t.results or []
            for r in results:
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
            # Compute live standings for RUNNING/DONE tournaments
            bracket = t.bracket or []
            if not bracket:
                history.append({
                    "tournament_id": t.id, "tournament_name": t.name,
                    "game_name": game_name, "status": t.status, "live": True,
                    "rank": None, "placement_pts": 0, "participation_pts": 0,
                    "score_pts": 0, "total": 0, "team_name": None
                })
                continue

            bracket_type = config.get("bracket_type", "single_elim")
            lower_is_better = config.get("lower_score_is_better", False)
            ppw = t.points_per_win or 3
            ppg = config.get("pts_per_goal", 0)

            # Compute wins per entity
            wins = {}
            goals = {}
            for m in bracket:
                p = m.get("p", [])
                s = m.get("score", [])
                if 0 in p:
                    continue  # Skip byes
                for i, pid in enumerate(p):
                    if pid and pid != 0:
                        goals.setdefault(pid, 0)
                        wins.setdefault(pid, 0)
                        raw = max(0, s[i] if i < len(s) else 0)
                        if lower_is_better and raw > 0:
                            max_score = max((v for v in s if v > 0), default=0)
                            goals[pid] += (max_score + 1 - raw)
                        else:
                            goals[pid] += raw
                if len(s) >= 2 and s[0] > 0 and s[1] > 0 and s[0] != s[1]:
                    w_idx = (0 if s[0] < s[1] else 1) if lower_is_better else (0 if s[0] > s[1] else 1)
                    w_id = p[w_idx] if w_idx < len(p) else None
                    if w_id and w_id != 0:
                        wins[w_id] = wins.get(w_id, 0) + 1

            # Find user's entity
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

            user_wins = wins.get(user_entity, 0)
            user_goals = goals.get(user_entity, 0)
            score_pts = round(user_goals * ppg, 1)
            live_pts = user_wins * ppw + score_pts

            # Compute rank
            all_pts = {eid: w * ppw + round(goals.get(eid, 0) * ppg, 1) for eid, w in wins.items()}
            sorted_entities = sorted(all_pts.items(), key=lambda x: x[1], reverse=True)
            rank = None
            for i, (eid, pts) in enumerate(sorted_entities):
                if eid == user_entity:
                    rank = i + 1
                    break

            history.append({
                "tournament_id": t.id, "tournament_name": t.name,
                "game_name": game_name, "status": t.status, "live": True,
                "rank": rank, "placement_pts": user_wins * ppw, "participation_pts": 0,
                "score_pts": score_pts, "total": live_pts, "team_name": team_name_found
            })

    return {"total_points": user.points or 0, "history": history}

# --- ADMIN: User Management ---

@router.get("/admin/users")
def admin_list_users(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """List all users with details for admin management."""
    users = db.query(models.User).all()
    return [{"id": u.id, "username": u.username, "team_name": u.team_name, "is_admin": u.is_admin, "seat_id": u.seat_id, "points": u.points} for u in users]

@router.put("/admin/users/{user_id}")
def admin_update_user(user_id: int, data: dict, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
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
    if "is_admin" in data:
        target.is_admin = bool(data["is_admin"])
    db.commit()
    db.refresh(target)
    return {"status": "updated", "id": target.id, "username": target.username, "team_name": target.team_name, "is_admin": target.is_admin}

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
def admin_delete_user(user_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
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
    return {"status": "deleted", "id": user_id}

@router.put("/admin/config/{key}")
def admin_set_config(key: str, data: dict, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin sets a system config value."""
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if config:
        config.value = data.get("value")
    else:
        config = models.SystemConfig(key=key, value=data.get("value"))
        db.add(config)
    db.commit()
    return {"status": "updated", "key": key, "value": data.get("value")}

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
def admin_nuke_players(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
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
        db.query(models.User).filter(models.User.id.in_(non_admin_ids)).delete(synchronize_session=False)
    db.commit()
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
