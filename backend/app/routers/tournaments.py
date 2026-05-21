from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from .. import models, schemas, auth, database
from ..websockets import manager
from ..tournament_engine import Duel, RoundRobin, FFA, MatchId
import asyncio
import json
import httpx

router = APIRouter(prefix="/tournaments", tags=["Tournaments"])

# --- Helper: download external images locally ---
def _localize_image_url(url: str) -> str:
    """If url is external (http), download it to static/uploads/games/ and return local path."""
    if not url or not url.startswith(("http://", "https://")):
        return url  # already local
    import os, uuid, httpx
    upload_dir = os.path.join("static", "uploads", "games")
    os.makedirs(upload_dir, exist_ok=True)
    try:
        resp = httpx.get(url, timeout=10.0, follow_redirects=True)
        if resp.status_code != 200:
            return url  # keep external if download fails
        ct = resp.headers.get("content-type", "")
        ext = "png"
        if "jpeg" in ct or "jpg" in ct:
            ext = "jpg"
        elif "webp" in ct:
            ext = "webp"
        elif "gif" in ct:
            ext = "gif"
        filename = f"{uuid.uuid4().hex[:12]}.{ext}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as f:
            f.write(resp.content)
        return f"/static/uploads/games/{filename}"
    except Exception:
        return url  # keep external on error

# --- GAMES ---

@router.get("/games", response_model=List[schemas.Game])
def list_games(db: Session = Depends(database.get_db)):
    """Public endpoint — no auth required."""
    return db.query(models.Game).all()

@router.post("/games", response_model=schemas.Game)
def create_game(game: schemas.GameCreate, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    data = game.model_dump()
    if data.get("image_url"):
        data["image_url"] = _localize_image_url(data["image_url"])
    db_game = models.Game(**data)
    db.add(db_game)
    db.commit()
    db.refresh(db_game)
    return db_game

@router.put("/games/{game_id}", response_model=schemas.Game)
def update_game(game_id: int, game_update: schemas.GameUpdate, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    update_data = game_update.model_dump(exclude_unset=True)
    if "image_url" in update_data and update_data["image_url"]:
        update_data["image_url"] = _localize_image_url(update_data["image_url"])
    for key, value in update_data.items():
        setattr(db_game, key, value)
        
    db.commit()
    db.refresh(db_game)
    return db_game

@router.delete("/games/{game_id}")
def delete_game(game_id: int, force: bool = False, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
        
    if not force and len(game.tournaments) > 0:
        raise HTTPException(status_code=409, detail=f"Ce jeu est lié à {len(game.tournaments)} tournoi(s). Veuillez confirmer la suppression.", headers={"X-Affected-Tournaments": str(len(game.tournaments))})
        
    db.delete(game)
    db.commit()
    return {"status": "deleted"}

@router.post("/games/localize-images")
def localize_all_images(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Download all external game images to local storage."""
    games = db.query(models.Game).all()
    count = 0
    for g in games:
        if g.image_url and g.image_url.startswith(("http://", "https://")):
            new_url = _localize_image_url(g.image_url)
            if new_url != g.image_url:
                g.image_url = new_url
                count += 1
    db.commit()
    return {"status": "ok", "localized": count}

@router.post("/games/upload-image")
async def upload_game_image(
    file: UploadFile,
    admin: models.User = Depends(auth.get_current_admin)
):
    """Upload a game cover image to local storage."""
    import os, uuid
    upload_dir = os.path.join("static", "uploads", "games")
    os.makedirs(upload_dir, exist_ok=True)
    
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
    filepath = os.path.join(upload_dir, filename)
    
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    
    return {"url": f"/static/uploads/games/{filename}"}

@router.get("/games/search-covers")
async def search_game_covers(q: str):
    """Search game covers via self-hosted SearXNG image search."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://search.amify-studio.fr/search",
                params={
                    "q": f"{q} game cover",
                    "format": "json",
                    "categories": "images",
                    "language": "en",
                },
                timeout=8.0
            )
            if resp.status_code != 200:
                return {"results": []}
            data = resp.json()
            seen = set()
            results = []
            for g in data.get("results", []):
                img = g.get("img_src", "")
                if not img or img in seen:
                    continue
                seen.add(img)
                results.append({
                    "name": g.get("title", ""),
                    "image": img,
                    "thumbnail": g.get("thumbnail_src", img),
                })
                if len(results) >= 12:
                    break
            return {"results": results}
    except:
        return {"results": []}

# --- TOURNAMENTS ---

@router.get("", response_model=List[schemas.Tournament])
def list_tournaments(db: Session = Depends(database.get_db)):
    """Public endpoint — no auth required (for spectator mode)."""
    return db.query(models.Tournament).all()

@router.post("", response_model=schemas.Tournament)
async def create_tournament(
    tournament: schemas.TournamentCreate, 
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    game = db.query(models.Game).filter(models.Game.id == tournament.game_id).first()
    # Fallback name to game name if empty
    if not tournament.name:
        tournament.name = game.name if game else f"Tournoi #{tournament.game_id}"
    if tournament.config is None:
        if game and game.default_config:
            tournament.config = game.default_config
            
    db_tournament = models.Tournament(**tournament.model_dump())
    db.add(db_tournament)
    db.commit()
    db.refresh(db_tournament)
    
    await manager.broadcast({"type": "tournament_created", "data": schemas.Tournament.from_orm(db_tournament).dict()})
    return db_tournament

@router.get("/{tournament_id}", response_model=schemas.Tournament)
def get_tournament(tournament_id: int, db: Session = Depends(database.get_db)):
    """Public endpoint — no auth required (for spectator mode)."""
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return t

@router.put("/{tournament_id}", response_model=schemas.Tournament)
async def update_tournament(
    tournament_id: int,
    tournament_update: schemas.TournamentUpdate,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    db_tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not db_tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
        
    update_data = tournament_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_tournament, key, value)
    
    # Ensure JSON column mutations are detected by SQLAlchemy
    from sqlalchemy.orm.attributes import flag_modified
    for json_col in ("bracket", "config", "results"):
        if json_col in update_data:
            flag_modified(db_tournament, json_col)
    
    # If resetting to OPEN, also clear results
    if update_data.get("status") == "OPEN":
        db_tournament.bracket = None
        db_tournament.results = None
        flag_modified(db_tournament, "bracket")
        flag_modified(db_tournament, "results")
    
    db.commit()
    db.refresh(db_tournament)
    
    await manager.broadcast({"type": "tournament_updated", "data": schemas.Tournament.from_orm(db_tournament).dict()})
    return db_tournament

@router.delete("/{tournament_id}")
async def delete_tournament(tournament_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    db.delete(t)
    db.commit()
    await manager.broadcast({"type": "tournament_deleted", "tournament_id": tournament_id})
    return {"status": "deleted"}

class JoinRequest(BaseModel):
    user_id: Optional[int] = None

@router.post("/{tournament_id}/join")
async def join_tournament(
    tournament_id: int,
    body: JoinRequest = JoinRequest(),
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Admin force-add: use body.user_id if provided and caller is admin
    target_id = user.id
    if body.user_id and user.is_admin:
        target_id = body.user_id
    
    existing = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id,
        models.TournamentParticipant.user_id == target_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Already joined")
    
    participant = models.TournamentParticipant(tournament_id=tournament_id, user_id=target_id)
    db.add(participant)
    db.commit()
    await manager.broadcast({"type": "participant_joined", "tournament_id": tournament_id, "user_id": target_id})
    return {"status": "joined"}

@router.get("/{tournament_id}/participants")
def get_tournament_participants(
    tournament_id: int,
    db: Session = Depends(database.get_db)
):
    participants = db.query(models.TournamentParticipant).filter(models.TournamentParticipant.tournament_id == tournament_id).all()
    users = db.query(models.User).filter(models.User.id.in_([p.user_id for p in participants])).all()
    user_map = {u.id: {"username": u.username, "team_name": u.team_name} for u in users}
    
    return [
        {"id": p.id, "user_id": p.user_id, "username": user_map.get(p.user_id, {}).get("username", "Unknown"), "team_name": user_map.get(p.user_id, {}).get("team_name")} 
        for p in participants
    ]

@router.delete("/{tournament_id}/participants/{user_id}")
async def delete_tournament_participant(
    tournament_id: int,
    user_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    participant = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id,
        models.TournamentParticipant.user_id == user_id
    ).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    db.delete(participant)
    db.commit()
    await manager.broadcast({"type": "participant_left", "tournament_id": tournament_id, "user_id": user_id})
    return {"status": "deleted"}

@router.post("/{tournament_id}/join-all")
async def join_all_players(
    tournament_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Admin bulk-registers ALL users into the tournament."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.status != "OPEN":
        raise HTTPException(status_code=400, detail="Tournament must be OPEN")
    all_users = db.query(models.User).all()
    existing_ids = {p.user_id for p in db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id
    ).all()}
    added = 0
    for u in all_users:
        if u.id not in existing_ids:
            db.add(models.TournamentParticipant(tournament_id=tournament_id, user_id=u.id))
            added += 1
    db.commit()
    await manager.broadcast({"type": "participant_joined", "tournament_id": tournament_id})
    return {"status": "ok", "added": added}

@router.post("/{tournament_id}/leave-all")
async def leave_all_players(
    tournament_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Admin bulk-removes ALL participants from the tournament."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.status != "OPEN":
        raise HTTPException(status_code=400, detail="Tournament must be OPEN")
    count = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id
    ).delete()
    # Also remove team memberships
    teams = db.query(models.TournamentTeam).filter(models.TournamentTeam.tournament_id == tournament_id).all()
    for t in teams:
        db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == t.id).delete()
    db.commit()
    await manager.broadcast({"type": "participant_left", "tournament_id": tournament_id})
    return {"status": "ok", "removed": count}

@router.post("/{tournament_id}/start")
async def start_tournament(
    tournament_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    import random
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    config = tournament.config or {}
    bracket_type = config.get("bracket_type", "single_elim")
    use_teams = config.get("use_teams", False)
    
    if use_teams:
        teams = db.query(models.TournamentTeam).filter(models.TournamentTeam.tournament_id == tournament_id).all()
        teams_with_members = [t for t in teams if len(t.members) > 0]
        if len(teams_with_members) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 teams with members")
        random.shuffle(teams_with_members)
        opponents = [{"id": -t.id, "label": t.name} for t in teams_with_members]
    else:
        participants = list(tournament.participants)
        if len(participants) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 participants")
        random.shuffle(participants)
        opponents = [{"id": p.user_id, "label": None} for p in participants]
    
    num = len(opponents)
    
    if bracket_type == "round_robin":
        engine = RoundRobin(num)
    elif bracket_type == "double_elim":
        engine = Duel(num, double_elim=True)
    elif bracket_type == "ffa":
        engine = FFA(num)
    else:
        engine = Duel(num, double_elim=False)
    
    if bracket_type == "ffa":
        # FFA: single match with all players
        engine.matches[0].p = [o["id"] for o in opponents]
    else:
        # Seed R1
        seed_idx = 0
        for match in engine.matches:
            if match.id.r == 1 and match.id.s == 1:
                if match.p[0] == 0 and seed_idx < len(opponents):
                    match.p[0] = opponents[seed_idx]["id"]
                    seed_idx += 1
                if match.p[1] == 0 and seed_idx < len(opponents):
                    match.p[1] = opponents[seed_idx]["id"]
                    seed_idx += 1
    
    if bracket_type == "round_robin":
        for match in engine.matches:
            for slot in range(2):
                seed = match.p[slot]
                if 1 <= seed <= len(opponents):
                    match.p[slot] = opponents[seed - 1]["id"]
                else:
                    match.p[slot] = 0
    
    bracket_data = []
    for m in engine.matches:
        bracket_data.append({"id": {"s": m.id.s, "r": m.id.r, "m": m.id.m}, "p": list(m.p), "score": [None] * len(m.p)})
    
    if bracket_type not in ("round_robin", "ffa"):
        # Multi-pass BYE resolution using feeder-aware check
        changed = True
        while changed:
            changed = False
            for match in bracket_data:
                p0, p1 = match["p"][0], match["p"][1]
                s0, s1 = match["score"][0], match["score"][1]
                if s0 is not None or s1 is not None:
                    continue
                if p0 != 0 and p1 == 0 and _is_genuine_bye(bracket_data, match):
                    match["score"] = [1, 0]
                    _advance_bracket(bracket_data, match, bracket_type)
                    changed = True
                elif p1 != 0 and p0 == 0 and _is_genuine_bye(bracket_data, match):
                    match["score"] = [0, 1]
                    _advance_bracket(bracket_data, match, bracket_type)
                    changed = True
    
    if use_teams:
        config["_team_map"] = {str(-t.id): t.name for t in teams_with_members}
        tournament.config = config
    
    tournament.bracket = bracket_data
    tournament.status = "RUNNING"
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(tournament, "config")
    db.commit()
    
    await manager.broadcast({"type": "tournament_started", "id": tournament_id})
    return {"status": "started", "matches_count": len(bracket_data)}

# --- TEAMS ---

class TeamCreate(BaseModel):
    name: str

class TeamMemberAdd(BaseModel):
    user_id: int

@router.get("/{tournament_id}/teams")
def get_teams(tournament_id: int, db: Session = Depends(database.get_db)):
    teams = db.query(models.TournamentTeam).filter(models.TournamentTeam.tournament_id == tournament_id).all()
    result = []
    for t in teams:
        members = db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == t.id).all()
        users = db.query(models.User).filter(models.User.id.in_([m.user_id for m in members])).all()
        user_map = {u.id: u.username for u in users}
        result.append({
            "id": t.id, "name": t.name, "created_by": t.created_by,
            "members": [{"user_id": m.user_id, "username": user_map.get(m.user_id, "?")} for m in members]
        })
    return result

@router.post("/{tournament_id}/teams")
async def create_team(tournament_id: int, body: TeamCreate, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    team = models.TournamentTeam(tournament_id=tournament_id, name=body.name, created_by=user.id)
    db.add(team)
    db.commit()
    db.refresh(team)
    await manager.broadcast({"type": "teams_updated", "tournament_id": tournament_id})
    return {"id": team.id, "name": team.name, "created_by": user.id, "members": []}

@router.delete("/{tournament_id}/teams/{team_id}")
async def delete_team(tournament_id: int, team_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    team = db.query(models.TournamentTeam).filter(models.TournamentTeam.id == team_id, models.TournamentTeam.tournament_id == tournament_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    # Only creator or admin can delete
    if not user.is_admin and team.created_by != user.id:
        raise HTTPException(status_code=403, detail="Only the team creator or an admin can delete this team")
    db.delete(team)
    db.commit()
    await manager.broadcast({"type": "teams_updated", "tournament_id": tournament_id})
    return {"status": "deleted"}

@router.post("/{tournament_id}/teams/{team_id}/members")
async def add_team_member(tournament_id: int, team_id: int, body: TeamMemberAdd, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    # Non-admin can only add themselves
    if not user.is_admin and body.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only add yourself to a team")
    # Must be a participant to join a team
    if not user.is_admin:
        is_participant = db.query(models.TournamentParticipant).filter(
            models.TournamentParticipant.tournament_id == tournament_id,
            models.TournamentParticipant.user_id == body.user_id
        ).first()
        if not is_participant:
            raise HTTPException(status_code=400, detail="You must join the tournament first")
    all_teams = db.query(models.TournamentTeam).filter(models.TournamentTeam.tournament_id == tournament_id).all()
    for t in all_teams:
        existing = db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == t.id, models.TournamentTeamMember.user_id == body.user_id).first()
        if existing:
            db.delete(existing)
    # AXE-05: Enforce team_size constraint
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    max_size = (tournament.config or {}).get("team_size", 99) if tournament else 99
    current_count = db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == team_id).count()
    if current_count >= max_size:
        raise HTTPException(status_code=400, detail=f"Team is full ({max_size} max)")
    member = models.TournamentTeamMember(team_id=team_id, user_id=body.user_id)
    db.add(member)
    db.commit()
    await manager.broadcast({"type": "teams_updated", "tournament_id": tournament_id})
    return {"status": "added"}

@router.delete("/{tournament_id}/teams/{team_id}/members/{user_id}")
async def remove_team_member(tournament_id: int, team_id: int, user_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    # Non-admin can only remove themselves
    if not user.is_admin and user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only remove yourself from a team")
    member = db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == team_id, models.TournamentTeamMember.user_id == user_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    db.commit()
    await manager.broadcast({"type": "teams_updated", "tournament_id": tournament_id})
    return {"status": "removed"}

@router.post("/{tournament_id}/teams/randomize")
async def randomize_teams(tournament_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    import random
    teams = db.query(models.TournamentTeam).filter(models.TournamentTeam.tournament_id == tournament_id).all()
    if not teams:
        raise HTTPException(status_code=400, detail="No teams created")
    for t in teams:
        db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == t.id).delete()
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    max_size = (tournament.config or {}).get("team_size", 99)
    participants = db.query(models.TournamentParticipant).filter(models.TournamentParticipant.tournament_id == tournament_id).all()
    user_ids = [p.user_id for p in participants]
    random.shuffle(user_ids)
    team_counts = {t.id: 0 for t in teams}
    team_idx = 0
    for uid in user_ids:
        assigned = False
        for _ in range(len(teams)):
            team = teams[team_idx % len(teams)]
            team_idx += 1
            if team_counts[team.id] < max_size:
                db.add(models.TournamentTeamMember(team_id=team.id, user_id=uid))
                team_counts[team.id] += 1
                assigned = True
                break
        if not assigned:
            break  # All teams are full, stop assigning
    db.commit()
    await manager.broadcast({"type": "teams_updated", "tournament_id": tournament_id})
    return {"status": "randomized"}

# --- SCORE ---

class ScoreUpdate(BaseModel):
    match_s: int
    match_r: int
    match_m: int
    score: List[Optional[int]]

def _find_match(bracket, s, r, m):
    for match in bracket:
        mid = match["id"]
        if mid["s"] == s and mid["r"] == r and mid["m"] == m:
            return match
    return None

def _get_max_round(bracket, section=None):
    matches = bracket if section is None else [m for m in bracket if m["id"]["s"] == section]
    return max((m["id"]["r"] for m in matches), default=0)

def _get_feeder(bd, s, r, m, slot):
    """Get the match that feeds into the given slot."""
    if s == 1:  # WB
        # Special case: GF (last WB round) slot 1 comes from LB Final
        max_wb = _get_max_round(bd, section=1)
        if r == max_wb and slot == 1:
            max_lb = _get_max_round(bd, section=2)
            return _find_match(bd, 2, max_lb, 1) if max_lb > 0 else None
        return _find_match(bd, 1, r - 1, 2 * m - 1 + slot)
    if s == 2:  # LB
        if r % 2 == 0:  # Even LB: slot0 from LB prev, slot1 from WB
            if slot == 0:
                return _find_match(bd, 2, r - 1, m)
            else:
                wb_r = r // 2 + 1
                return _find_match(bd, 1, wb_r, m)
        else:  # Odd LB (>1): halving from prev even
            return _find_match(bd, 2, r - 1, 2 * m - 1 + slot)
    return None

def _is_match_dead(bd, match):
    """Recursively check if a [0,0] match will NEVER produce any real players."""
    if match["p"][0] != 0 or match["p"][1] != 0:
        return False  # Has at least one real player → alive
    mid = match["id"]
    if mid["r"] == 1:
        return True  # R1 [0,0] = genuine double-BYE (seed slots)
    # Check both feeders recursively
    for slot in [0, 1]:
        feeder = _get_feeder(bd, mid["s"], mid["r"], mid["m"], slot)
        if feeder is None:
            continue
        # Special: LB even round slot 1 = WB dropout (need the LOSER, not winner)
        if mid["s"] == 2 and mid["r"] % 2 == 0 and slot == 1:
            # WB match [player, 0] → loser is 0 → this slot is dead
            if feeder["p"][0] != 0 and feeder["p"][1] != 0:
                return False  # Two real players → real loser → alive
            # [player, 0] or [0, player] → loser is 0 → dead from this slot
            # [0, 0] → check recursively
            if feeder["p"][0] == 0 and feeder["p"][1] == 0:
                if not _is_match_dead(bd, feeder):
                    return False
            continue  # This slot is dead (BYE has no real loser)
        # Normal case: need WINNER from feeder
        if not _is_match_dead(bd, feeder):
            return False  # Feeder is alive → this match will get a player
    return True

def _is_genuine_bye(bd, match):
    """Check if a [player,0] or [0,player] match is a true BYE."""
    mid = match["id"]
    empty_slot = 0 if match["p"][0] == 0 else 1
    
    if mid["r"] == 1 and mid["s"] == 1:
        return True  # WB R1: any 0 is a seed BYE
    
    if mid["r"] == 1 and mid["s"] == 2:
        # LB R1: feeder is the LOSER of WB R1 M(2*m - 1 + slot)
        wb_feeder_m = 2 * mid["m"] - 1 + empty_slot
        feeder = _find_match(bd, 1, 1, wb_feeder_m)
        if feeder is None:
            return True
        if feeder["p"][0] == 0 and feeder["p"][1] == 0:
            return True
        if feeder["p"][0] == 0 or feeder["p"][1] == 0:
            return True
        return False
    
    # R2+: check feeder match for the empty slot
    feeder = _get_feeder(bd, mid["s"], mid["r"], mid["m"], empty_slot)
    if feeder is None:
        return True  # No feeder → genuine BYE
    # If feeder has two real players → someone will come → NOT a BYE
    if feeder["p"][0] != 0 and feeder["p"][1] != 0:
        return False
    # If feeder is [0,0], use recursive dead-check
    if feeder["p"][0] == 0 and feeder["p"][1] == 0:
        return _is_match_dead(bd, feeder)
    # Feeder has [player, 0] — one real, one empty
    # For LB even rounds slot 1: feeder is WB match, we need its LOSER
    if mid["s"] == 2 and mid["r"] % 2 == 0 and empty_slot == 1:
        return True  # WB match [player, 0] → loser is 0
    # For WB: [player, 0] feeder means the BYE winner is real → someone WILL come
    if mid["s"] == 1:
        return False
    # For LB: check if scored
    if mid["s"] == 2:
        fs = feeder["score"]
        if any(s is None for s in fs) or (fs[0] == 0 and fs[1] == 0):
            return False  # Not scored yet → wait
    return False

def _advance_bracket(bracket, scored_match, bracket_type="single_elim", lower_is_better=False):
    if bracket_type == "round_robin":
        return False
    score = scored_match.get("score", [0, 0])
    # If any score is None (not yet entered), do not advance
    if any(s is None for s in score):
        return False
    if score[0] == score[1]:
        return False
    # Require at least one non-zero score for real matches (not byes)
    p0_id = scored_match["p"][0]
    p1_id = scored_match["p"][1]
    is_bye = (p0_id == 0 or p1_id == 0)
    if not is_bye and score[0] == 0 and score[1] == 0:
        return False
    mid = scored_match["id"]
    winner_idx = (0 if score[0] < score[1] else 1) if lower_is_better else (0 if score[0] > score[1] else 1)
    loser_idx = 1 - winner_idx
    winner_id = scored_match["p"][winner_idx]
    loser_id = scored_match["p"][loser_idx]
    p0 = scored_match["p"][0]
    p1 = scored_match["p"][1]

    max_wb = _get_max_round(bracket, section=1)
    # In double_elim, GF is the last WB round (p+1)
    wb_final_r = max_wb - 1 if bracket_type == "double_elim" else max_wb

    if mid["s"] == 1:  # Winners Bracket match scored
        if mid["r"] < wb_final_r:
            # Winner advances in WB
            next_r = mid["r"] + 1
            next_m = (mid["m"] + 1) // 2
            slot = (mid["m"] - 1) % 2
            nm = _find_match(bracket, 1, next_r, next_m)
            if nm:
                _clear_player(nm, p0)
                _clear_player(nm, p1)
                nm["p"][slot] = winner_id
        elif mid["r"] == wb_final_r and bracket_type == "double_elim":
            # WB final winner → Grand Final slot 0
            gf = _find_match(bracket, 1, max_wb, 1)
            if gf:
                _clear_player(gf, p0)
                _clear_player(gf, p1)
                gf["p"][0] = winner_id
        
        if bracket_type == "double_elim" and loser_id and loser_id != 0:
            # Standard DE: WB R1 losers pair in LB R1, WB R(k>=2) losers drop to LB R(2*(k-1))
            if mid["r"] < wb_final_r:
                if mid["r"] == 1:
                    # WB R1 losers pair up in LB R1 (odd round)
                    lb_r = 1
                    lb_m = (mid["m"] + 1) // 2
                    slot = (mid["m"] - 1) % 2
                else:
                    # WB R(k) losers → LB R(2*(k-1)) as slot 1 (WB dropdown opponents)
                    lb_r = 2 * (mid["r"] - 1)
                    lb_m = mid["m"]  # direct 1:1 mapping
                    slot = 1  # WB dropdown always fills slot 1
                lm = _find_match(bracket, 2, lb_r, lb_m)
                if lm:
                    _clear_player(lm, p0)
                    _clear_player(lm, p1)
                    if lm["p"][slot] == 0:
                        lm["p"][slot] = loser_id
                    elif lm["p"][0] == 0:
                        lm["p"][0] = loser_id
                    elif lm["p"][1] == 0:
                        lm["p"][1] = loser_id
            elif mid["r"] == wb_final_r:
                # WB Final loser → last LB round (even) as opponent
                max_lb = _get_max_round(bracket, section=2)
                lm = _find_match(bracket, 2, max_lb, 1)
                if lm:
                    _clear_player(lm, p0)
                    _clear_player(lm, p1)
                    if lm["p"][1] == 0:
                        lm["p"][1] = loser_id
                    elif lm["p"][0] == 0:
                        lm["p"][0] = loser_id
    
    if mid["s"] == 2:  # Losers Bracket match scored
        max_lb = _get_max_round(bracket, section=2)
        if mid["r"] < max_lb:
            # LB winner advances to next LB round
            next_r = mid["r"] + 1
            if mid["r"] % 2 == 1:
                # Odd → Even: same match count, winner stays in same position
                next_m = mid["m"]
                slot = 0  # LB internal: winner goes to slot 0, WB dropdown fills slot 1
            else:
                # Even → Odd: halving (like WB)
                next_m = (mid["m"] + 1) // 2
                slot = (mid["m"] - 1) % 2
            nm = _find_match(bracket, 2, next_r, next_m)
            if nm:
                _clear_player(nm, p0)
                _clear_player(nm, p1)
                if nm["p"][slot] == 0:
                    nm["p"][slot] = winner_id
                elif nm["p"][0] == 0:
                    nm["p"][0] = winner_id
                elif nm["p"][1] == 0:
                    nm["p"][1] = winner_id
        elif mid["r"] == max_lb and bracket_type == "double_elim":
            # LB Final winner → Grand Final slot 1
            gf = _find_match(bracket, 1, max_wb, 1)
            if gf:
                _clear_player(gf, p0)
                _clear_player(gf, p1)
                gf["p"][1] = winner_id
    return True


def _clear_player(match, player_id):
    """Remove a player from a match's slots (for score correction)."""
    if not player_id or player_id == 0:
        return
    for i in range(len(match["p"])):
        if match["p"][i] == player_id:
            match["p"][i] = 0
            # Also reset score if clearing
            match["score"] = [None] * len(match["score"])


def _rollback_advancement(bracket, match, bracket_type, lower_is_better=False):
    """Recursively undo all downstream effects of a previously scored match."""
    old_score = match.get("score", [0, 0])
    if any(s is None for s in old_score):
        return  # Partial score, no advancement happened
    if old_score[0] == 0 and old_score[1] == 0:
        return  # Never scored, nothing to rollback
    if old_score[0] == old_score[1]:
        return  # Tie, no advancement happened
    # If not a bye and both scores are 0, no advancement happened
    is_bye = (match["p"][0] == 0 or match["p"][1] == 0)
    if not is_bye and old_score[0] == 0 and old_score[1] == 0:
        return

    mid = match["id"]
    p0, p1 = match["p"][0], match["p"][1]
    old_winner_idx = (0 if old_score[0] < old_score[1] else 1) if lower_is_better else (0 if old_score[0] > old_score[1] else 1)
    old_loser_idx = 1 - old_winner_idx
    old_winner = match["p"][old_winner_idx]
    old_loser = match["p"][old_loser_idx]

    max_wb = _get_max_round(bracket, section=1)
    wb_final_r = max_wb - 1 if bracket_type == "double_elim" else max_wb

    downstream = []  # list of (downstream_match, player_to_clear)

    if mid["s"] == 1:  # WB match
        # Winner went to next WB round
        if mid["r"] < wb_final_r:
            next_r = mid["r"] + 1
            next_m = (mid["m"] + 1) // 2
            nm = _find_match(bracket, 1, next_r, next_m)
            if nm:
                downstream.append((nm, old_winner))
        elif mid["r"] == wb_final_r and bracket_type == "double_elim":
            gf = _find_match(bracket, 1, max_wb, 1)
            if gf:
                downstream.append((gf, old_winner))

        # In DE, loser was sent to LB
        if bracket_type == "double_elim" and old_loser and old_loser != 0:
            if mid["r"] < wb_final_r:
                if mid["r"] == 1:
                    lb_r = 1
                    lb_m = (mid["m"] + 1) // 2
                else:
                    lb_r = 2 * (mid["r"] - 1)
                    lb_m = mid["m"]
                lm = _find_match(bracket, 2, lb_r, lb_m)
                if lm:
                    downstream.append((lm, old_loser))
            elif mid["r"] == wb_final_r:
                max_lb = _get_max_round(bracket, section=2)
                lm = _find_match(bracket, 2, max_lb, 1)
                if lm:
                    downstream.append((lm, old_loser))

    elif mid["s"] == 2:  # LB match
        max_lb = _get_max_round(bracket, section=2)
        if mid["r"] < max_lb:
            next_r = mid["r"] + 1
            if mid["r"] % 2 == 1:
                next_m = mid["m"]
            else:
                next_m = (mid["m"] + 1) // 2
            nm = _find_match(bracket, 2, next_r, next_m)
            if nm:
                downstream.append((nm, old_winner))
        elif mid["r"] == max_lb and bracket_type == "double_elim":
            gf = _find_match(bracket, 1, max_wb, 1)
            if gf:
                downstream.append((gf, old_winner))

    # Recursively rollback each downstream match, then clear the player
    for nm, player_id in downstream:
        if player_id and player_id != 0 and player_id in nm["p"]:
            # First rollback any advancement FROM the downstream match
            _rollback_advancement(bracket, nm, bracket_type, lower_is_better)
            # Then clear the player and reset the match score
            _clear_player(nm, player_id)
            nm["score"] = [None] * len(nm["score"])

@router.put("/{tournament_id}/score")
async def update_match_score(
    tournament_id: int,
    body: ScoreUpdate,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament or not tournament.bracket:
        raise HTTPException(status_code=404, detail="Tournament or bracket not found")
    # Allow admin or match participant in this tournament
    if not user.is_admin:
        participant = db.query(models.TournamentParticipant).filter(
            models.TournamentParticipant.tournament_id == tournament_id,
            models.TournamentParticipant.user_id == user.id
        ).first()
        if not participant:
            raise HTTPException(status_code=403, detail="Only participants or admins can update scores")
    
    config = tournament.config or {}
    bracket_type = config.get("bracket_type", "single_elim")
    bracket = list(tournament.bracket)
    scored_match = _find_match(bracket, body.match_s, body.match_r, body.match_m)
    if not scored_match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Non-admin: verify player is in this specific match
    if not user.is_admin:
        user_in_match = user.id in scored_match["p"]
        # Team mode: check if user is a member of a team in this match
        if not user_in_match and config.get("use_teams"):
            for pid in scored_match["p"]:
                if pid < 0:
                    # pid is -team_id, so team_id = abs(pid)
                    team_id = abs(pid)
                    member = db.query(models.TournamentTeamMember).filter(
                        models.TournamentTeamMember.team_id == team_id,
                        models.TournamentTeamMember.user_id == user.id
                    ).first()
                    if member:
                        user_in_match = True
                        break
        if not user_in_match:
            raise HTTPException(status_code=403, detail="You can only update scores for matches you are playing in")
        # AXE-15: Non-admin cannot edit a finalized match
        existing_scores = scored_match.get("score", [])
        if bracket_type in ("single_elim", "double_elim", "round_robin"):
            if len(existing_scores) >= 2:
                es0, es1 = existing_scores[0], existing_scores[1]
                is_locked = (es0 is not None and es1 is not None) and (
                    (es0 != es1 and (es0 != 0 or es1 != 0)) or (
                        es0 == es1 and es0 != 0 and bracket_type == "round_robin" and config.get("allow_draws")
                    )
                )
                if is_locked:
                    raise HTTPException(status_code=403, detail="Ce match est terminé. Seul un admin peut modifier le score.")
        elif bracket_type == "ffa":
            if existing_scores and all(s is not None and s > 0 for s in existing_scores):
                raise HTTPException(status_code=403, detail="Cette manche est terminée. Seul un admin peut modifier les classements.")
    # Rollback previous advancement if match was already scored (score correction)
    lower_is_better = config.get("lower_score_is_better", False)
    if bracket_type not in ("round_robin", "ffa"):
        _rollback_advancement(bracket, scored_match, bracket_type, lower_is_better)
    
    scored_match["score"] = body.score
    if bracket_type not in ("round_robin", "ffa"):
        _advance_bracket(bracket, scored_match, bracket_type, lower_is_better)
        # Post-advance BYE resolution: auto-advance any newly created BYE matches
        bye_changed = True
        while bye_changed:
            bye_changed = False
            for m in bracket:
                p0, p1 = m["p"][0], m["p"][1]
                s0, s1 = m["score"][0], m["score"][1]
                already_scored = (s0 != 0 or s1 != 0)
                if already_scored:
                    continue
                if p0 != 0 and p1 == 0 and _is_genuine_bye(bracket, m):
                    m["score"] = [1, 0]
                    _advance_bracket(bracket, m, bracket_type, lower_is_better)
                    bye_changed = True
                elif p1 != 0 and p0 == 0 and _is_genuine_bye(bracket, m):
                    m["score"] = [0, 1]
                    _advance_bracket(bracket, m, bracket_type, lower_is_better)
                    bye_changed = True
    
    tournament_done = False
    if bracket_type == "round_robin":
        all_scored = all((m["score"][0] is not None and m["score"][1] is not None and (m["score"][0] != 0 or m["score"][1] != 0)) for m in bracket)
        if all_scored:
            tournament_done = True
    elif bracket_type == "ffa":
        # FFA: never auto-done from scoring — admin explicitly ends or advances
        pass
    else:
        # Both single_elim and double_elim: GF is the last WB round
        max_round = _get_max_round(bracket, section=1)
        final = _find_match(bracket, 1, max_round, 1)
        if final and final.get("score") and final["score"][0] != final["score"][1]:
            tournament_done = True
    
    if tournament_done:
        tournament.status = "DONE"
    
    tournament.bracket = bracket
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(tournament, "bracket")
    db.commit()
    
    await manager.broadcast({"type": "score_updated", "tournament_id": tournament_id, "done": tournament_done, "match": {"r": body.match_r, "m": body.match_m, "p1": scored_match["p"][0], "p2": scored_match["p"][1], "score": body.score}})
    return {"status": "updated", "advanced": True, "done": tournament_done}


class FFAAdvance(BaseModel):
    keep_count: int  # Number of top players to advance

@router.post("/{tournament_id}/ffa-advance")
async def ffa_advance_round(
    tournament_id: int,
    body: FFAAdvance,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Create the next FFA round with the top N players from the current round."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament or not tournament.bracket:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    config = tournament.config or {}
    if config.get("bracket_type") != "ffa":
        raise HTTPException(status_code=400, detail="Not an FFA tournament")
    
    bracket = list(tournament.bracket)
    # Find latest round
    max_r = max(m["id"]["r"] for m in bracket)
    current = _find_match(bracket, 1, max_r, 1)
    if not current:
        raise HTTPException(status_code=404, detail="Current round not found")
    
    # Validate scores exist
    scores = current.get("score", [])
    players = current.get("p", [])
    if not all(s is not None and s > 0 for s in scores):
        raise HTTPException(status_code=400, detail="All placements must be entered before advancing")
    
    if body.keep_count < 2:
        raise HTTPException(status_code=400, detail="Must keep at least 2 players")
    if body.keep_count >= len(players):
        raise HTTPException(status_code=400, detail="Must eliminate at least 1 player")
    
    # Sort by placement (score = ranking position, lower = better)
    paired = list(zip(players, scores))
    paired.sort(key=lambda x: x[1])
    advancing = [p for p, s in paired[:body.keep_count]]
    
    # Create next round
    next_r = max_r + 1
    new_match = {"id": {"s": 1, "r": next_r, "m": 1}, "p": advancing, "score": [None] * len(advancing)}
    bracket.append(new_match)
    
    tournament.bracket = bracket
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(tournament, "bracket")
    db.commit()
    
    await manager.broadcast({"type": "ffa_advanced", "tournament_id": tournament_id, "round": next_r})
    return {"status": "advanced", "round": next_r, "players": len(advancing)}


@router.post("/{tournament_id}/ffa-finish")
async def ffa_finish(
    tournament_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Mark an FFA tournament as DONE (admin declares final results)."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    tournament.status = "DONE"
    db.commit()
    await manager.broadcast({"type": "score_updated", "tournament_id": tournament_id, "done": True})
    return {"status": "done"}


@router.post("/{tournament_id}/close")
async def close_tournament(
    tournament_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Close a tournament: calculate standings, distribute points, set CLOSED."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.status not in ("DONE", "RUNNING"):
        raise HTTPException(status_code=400, detail="Tournament must be DONE or RUNNING to close")
    
    config = tournament.config or {}
    bracket_type = config.get("bracket_type", "single_elim")
    use_teams = config.get("use_teams", False)
    
    # Rebuild _team_map if missing (can be lost during config edits or reopen cycles)
    if use_teams and not config.get("_team_map"):
        teams_for_map = db.query(models.TournamentTeam).filter(
            models.TournamentTeam.tournament_id == tournament_id
        ).all()
        config["_team_map"] = {str(-t.id): t.name for t in teams_for_map}
        tournament.config = config
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(tournament, "config")
    
    # Points config (from tournament config, with defaults)
    pts_winner = config.get("pts_winner", 10)
    pts_second = config.get("pts_second", 6)
    pts_third = config.get("pts_third", 4)
    pts_participation = config.get("pts_participation", 1)
    pts_per_match = config.get("pts_per_match", config.get("pts_per_goal", 1.0))
    
    bracket = tournament.bracket or []
    
    # --- Calculate standings ---
    standings = _compute_standings(bracket, bracket_type, config.get("lower_score_is_better", False))
    
    # --- Calculate score bonus via cumulated score normalization ---
    # For FFA multi-round: normalize per-round separately so eliminated players
    # don't unfairly benefit from lower cumulated scores.
    # For other modes: single-pool normalization across all matches.
    lower_is_better = config.get("lower_score_is_better", False)
    cumulated_scores = {}  # entity_id -> total raw score
    matches_count = {}  # entity_id -> number of scored matches
    for match in bracket:
        players = match.get("p", [])
        scores = match.get("score", [])
        has_scores = any(s is not None and s > 0 for s in scores)
        if not has_scores:
            continue
        for i, pid in enumerate(players):
            if pid and pid != 0 and i < len(scores):
                cumulated_scores[pid] = cumulated_scores.get(pid, 0) + max(0, scores[i])
                matches_count[pid] = matches_count.get(pid, 0) + 1

    # Normalize and compute bonus
    score_totals = {}
    if bracket_type == "ffa" and cumulated_scores:
        # FFA: normalize per-round, then sum. Each round contributes pts_per_match × (1 + normalized).
        round_matches = {}
        for m in bracket:
            r = m["id"]["r"]
            if m["id"]["m"] == 1:
                round_matches[r] = m
        for r in sorted(round_matches.keys()):
            m = round_matches[r]
            players = m.get("p", [])
            scores = m.get("score", [])
            if not any(s is not None and s > 0 for s in scores):
                continue
            round_data = [(pid, scores[i]) for i, pid in enumerate(players)
                          if pid and pid != 0 and i < len(scores) and scores[i] > 0]
            if not round_data:
                continue
            round_scores = [s for _, s in round_data]
            min_rs = min(round_scores)
            max_rs = max(round_scores)
            rng = max_rs - min_rs
            for pid, sc in round_data:
                if rng > 0:
                    # FFA scores are always placements (lower = better)
                    normalized = (max_rs - sc) / rng
                else:
                    normalized = 1.0
                score_totals[pid] = round(score_totals.get(pid, 0) + pts_per_match * (1 + normalized), 1)
    elif cumulated_scores:
        # Non-FFA: single-pool normalization (existing logic)
        scores_list = list(cumulated_scores.values())
        min_cs = min(scores_list)
        max_cs = max(scores_list)
        score_range = max_cs - min_cs
        for eid, cs in cumulated_scores.items():
            if score_range > 0:
                if lower_is_better:
                    normalized = (max_cs - cs) / score_range
                else:
                    normalized = (cs - min_cs) / score_range
            else:
                normalized = 1.0  # everyone equal → everyone gets full bonus
            score_totals[eid] = round(pts_per_match * (1 + normalized), 1)
    
    # --- Build results & distribute points ---
    results = []
    placement_pts_map = {1: pts_winner, 2: pts_second, 3: pts_third}
    
    # Map team IDs to user IDs for team mode
    team_members_map = {}
    if use_teams:
        teams = db.query(models.TournamentTeam).filter(
            models.TournamentTeam.tournament_id == tournament_id
        ).all()
        for team in teams:
            members = db.query(models.TournamentTeamMember).filter(
                models.TournamentTeamMember.team_id == team.id
            ).all()
            team_members_map[-team.id] = [m.user_id for m in members]
    
    participants = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id
    ).all()
    participant_uids = {p.user_id for p in participants}
    
    # Track who got placement points
    placed_uids = set()
    
    for rank, entity_id in standings:
        placement = placement_pts_map.get(rank, 0)
        score_pts = round(score_totals.get(entity_id, 0), 1)
        mp = matches_count.get(entity_id, 0)
        participation = round(pts_participation * mp, 1)  # Strictly matches played
        total = round(placement + participation + score_pts, 1)
        
        if use_teams and entity_id < 0:
            # Team: give points to all members
            member_uids = team_members_map.get(entity_id, [])
            team_name = config.get("_team_map", {}).get(str(entity_id), f"Team {abs(entity_id)}")
            results.append({
                "rank": rank, "entity_id": entity_id, "name": team_name,
                "placement_pts": placement, "score_pts": score_pts,
                "participation_pts": participation, "total": total
            })
            for uid in member_uids:
                user = db.query(models.User).filter(models.User.id == uid).first()
                if user:
                    user.points = (user.points or 0) + int(total)
                    placed_uids.add(uid)
        else:
            # Solo player
            user = db.query(models.User).filter(models.User.id == entity_id).first()
            uname = user.username if user else f"#{entity_id}"
            results.append({
                "rank": rank, "entity_id": entity_id, "name": uname,
                "placement_pts": placement, "score_pts": score_pts,
                "participation_pts": participation, "total": total
            })
            if user:
                user.points = (user.points or 0) + int(total)
                placed_uids.add(entity_id)
    
    # Give participation points to remaining participants not in standings
    for uid in participant_uids:
        if uid not in placed_uids:
            score_pts = round(score_totals.get(uid, 0), 1)
            mp = matches_count.get(uid, 0)
            participation = round(pts_participation * mp, 1)
            total = round(participation + score_pts, 1)
            user = db.query(models.User).filter(models.User.id == uid).first()
            if user:
                user.points = (user.points or 0) + int(total)
                results.append({
                    "rank": None, "entity_id": uid, "name": user.username,
                    "placement_pts": 0, "score_pts": score_pts,
                    "participation_pts": participation, "total": total
                })
    
    tournament.results = results
    tournament.status = "CLOSED"
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(tournament, "results")
    db.commit()
    
    await manager.broadcast({"type": "tournament_closed", "tournament_id": tournament_id})

    # Fire-and-forget: generate AI personalized notifications for participants
    _game_name = tournament.game.name if tournament.game else tournament.name
    asyncio.create_task(_generate_tournament_notifications(
        tournament_id, tournament.name, _game_name, results, list(participant_uids), use_teams,
        bracket=bracket, config=config
    ))

    return {"status": "closed", "results": results}


@router.post("/{tournament_id}/reopen")
async def reopen_tournament(
    tournament_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Reopen a CLOSED tournament: rollback distributed points, set status back to DONE."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.status != "CLOSED":
        raise HTTPException(status_code=400, detail="Only CLOSED tournaments can be reopened")

    config = tournament.config or {}
    use_teams = config.get("use_teams", False)
    results = tournament.results or []

    # --- Rollback points from results ---
    rolled_back_uids = set()
    for r in results:
        total = int(r.get("total", 0))
        if total <= 0:
            continue
        entity_id = r.get("entity_id")
        if use_teams and isinstance(entity_id, int) and entity_id < 0:
            # Team: rollback for all members
            team_id = abs(entity_id)
            members = db.query(models.TournamentTeamMember).filter(
                models.TournamentTeamMember.team_id == team_id
            ).all()
            for m in members:
                user = db.query(models.User).filter(models.User.id == m.user_id).first()
                if user:
                    user.points = max(0, (user.points or 0) - total)
                    rolled_back_uids.add(m.user_id)
        else:
            # Solo player (including rank=None participation-only entries)
            user = db.query(models.User).filter(models.User.id == entity_id).first()
            if user:
                user.points = max(0, (user.points or 0) - total)
                rolled_back_uids.add(entity_id)

    # Also rollback participation-only players not in results (legacy data before fix)
    participants = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id
    ).all()
    # No extra rollback needed — all participants now appear in results after the fix

    tournament.results = None
    tournament.status = "DONE"
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(tournament, "results")
    db.commit()

    await manager.broadcast({"type": "tournament_reopened", "tournament_id": tournament_id})
    return {"status": "reopened", "rolled_back_users": len(rolled_back_uids)}


@router.post("/{tournament_id}/retry-notifications")
async def retry_notifications(tournament_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin-only: Re-trigger AI notification generation for a closed tournament."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(404, "Tournament not found")
    if tournament.status != "CLOSED":
        raise HTTPException(400, "Tournament must be CLOSED")
    if not tournament.results:
        raise HTTPException(400, "No results to generate notifications from")

    config = tournament.config or {}
    use_teams = config.get("use_teams", False)
    _game_name = tournament.game.name if tournament.game else tournament.name

    # Get participant UIDs
    participants = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id
    ).all()
    participant_uids = [p.user_id for p in participants]

    asyncio.create_task(_generate_tournament_notifications(
        tournament_id, tournament.name, _game_name, tournament.results, participant_uids, use_teams,
        bracket=tournament.bracket or [], config=config
    ))
    return {"status": "retrying"}


@router.get("/{tournament_id}/ai-prompt-preview")
async def ai_prompt_preview(tournament_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Admin-only: Preview the full prompt that would be sent to Ollama for closing notifications."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(404, "Tournament not found")
    if not tournament.results:
        raise HTTPException(400, "No results available")

    config = tournament.config or {}
    use_teams = config.get("use_teams", False)
    _game_name = tournament.game.name if tournament.game else tournament.name
    bracket = tournament.bracket or []

    participants = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id
    ).all()
    participant_uids = [p.user_id for p in participants]

    prompt = _build_closing_prompt(
        tournament.name, _game_name, tournament.results, participant_uids,
        use_teams, bracket, config, db
    )
    estimated_tokens = len(prompt.split()) * 1.3
    return {"prompt": prompt, "estimated_tokens": int(estimated_tokens)}

def _build_player_narratives(bracket, bracket_type, results, config, db, participant_uids, use_teams):
    """Extract per-player narrative facts from bracket data for richer AI prompts."""
    narratives = {}  # entity_id -> list of facts
    lower_is_better = config.get("lower_score_is_better", False)

    if not bracket:
        return narratives

    # Build name map for all entities
    name_map = {}
    for r in results:
        name_map[r.get("entity_id")] = r.get("name", "?")
    for uid in participant_uids:
        if uid not in name_map:
            user = db.query(models.User).filter(models.User.id == uid).first()
            if user:
                name_map[uid] = user.username

    # Analyze each entity's matches
    all_entities = set()
    for m in bracket:
        for pid in m.get("p", []):
            if pid and pid != 0:
                all_entities.add(pid)

    max_wb_round = max((m["id"]["r"] for m in bracket if m["id"]["s"] == 1), default=0)
    max_lb_round = max((m["id"]["r"] for m in bracket if m["id"]["s"] == 2), default=0)

    for eid in all_entities:
        facts = []
        wins = 0
        losses = 0
        streak = 0
        max_streak = 0
        biggest_win_delta = 0
        biggest_win_label = ""
        closest_match_delta = 999
        closest_match_label = ""
        was_in_lb = False
        reached_gf = False
        elim_round = None
        elim_section = None

        # Gather matches involving this entity, sorted by section then round
        entity_matches = sorted(
            [m for m in bracket if eid in m.get("p", [])],
            key=lambda m: (m["id"]["s"], m["id"]["r"])
        )

        for m in entity_matches:
            p = m.get("p", [])
            s = m.get("score", [])
            mid = m["id"]
            if len(s) < 2 or (s[0] == 0 and s[1] == 0):
                continue  # Unscored
            if 0 in p:
                continue  # BYE

            idx = p.index(eid) if eid in p else -1
            if idx < 0:
                continue
            opp_idx = 1 - idx

            my_score = s[idx] if idx < len(s) else 0
            opp_score = s[opp_idx] if opp_idx < len(s) else 0

            if my_score == opp_score:
                continue  # Tie, no resolution

            if lower_is_better:
                won = my_score < opp_score
            else:
                won = my_score > opp_score

            delta = abs(my_score - opp_score)
            round_label = f"Manche {mid['r']}"
            if bracket_type == "double_elim":
                if mid["s"] == 2:
                    round_label = f"Manche {mid['r']} du Losers Bracket"
                elif mid["r"] == max_wb_round:
                    round_label = "Finale"
                else:
                    round_label = f"Manche {mid['r']} du Winners Bracket"

            if won:
                wins += 1
                streak += 1
                max_streak = max(max_streak, streak)
                if delta > biggest_win_delta:
                    biggest_win_delta = delta
                    biggest_win_label = f"{my_score}-{opp_score} ({round_label})"
            else:
                losses += 1
                streak = 0
                elim_round = mid["r"]
                elim_section = mid["s"]

            if delta < closest_match_delta and delta > 0:
                closest_match_delta = delta
                closest_match_label = f"{my_score}-{opp_score} ({round_label})"

            # Track LB presence
            if mid["s"] == 2:
                was_in_lb = True
            # Track Grand Final presence
            if mid["s"] == 1 and mid["r"] == max_wb_round:
                reached_gf = True

        # Build narrative
        if wins + losses > 0:
            facts.append(f"Bilan : {wins} victoire{'s' if wins > 1 else ''}, {losses} défaite{'s' if losses > 1 else ''}")

        if max_streak >= 3:
            facts.append(f"Streak : {max_streak} victoires consécutives")

        if biggest_win_delta >= 2 and biggest_win_label:
            facts.append(f"Score le plus large : {biggest_win_label}")

        if closest_match_delta <= 2 and closest_match_label and (wins + losses) > 1:
            facts.append(f"Match le plus serré : {closest_match_label}")

        # Comeback detection (double_elim specific)
        if bracket_type == "double_elim" and was_in_lb and reached_gf:
            facts.append("🔥 Reverse sweep depuis le Losers Bracket !")

        # Early elimination
        if losses > 0 and elim_round and not reached_gf:
            total_rounds = max_wb_round
            if bracket_type in ("single_elim", "double_elim") and elim_round <= total_rounds // 2:
                facts.append(f"Éliminé au Round {elim_round} sur {total_rounds}")

        # Team members
        if use_teams and eid < 0:
            team_id = abs(eid)
            members = db.query(models.TournamentTeamMember).filter(
                models.TournamentTeamMember.team_id == team_id
            ).all()
            member_names = []
            for m in members:
                user = db.query(models.User).filter(models.User.id == m.user_id).first()
                if user:
                    member_names.append(user.username)
            if member_names:
                facts.append(f"Membres : {', '.join(member_names)}")

        if facts:
            narratives[eid] = facts

    return narratives


def _build_closing_prompt(tournament_name, game_name, results, participant_uids, use_teams, bracket, config, db):
    """Build the full prompt for Ollama closing notifications. Reusable by both generation and preview."""
    bracket_type = config.get("bracket_type", "single_elim")
    bracket_labels = {
        "single_elim": "Élimination Directe",
        "double_elim": "Double Élimination",
        "round_robin": "Championnat (Round Robin)",
        "ffa": "Free For All"
    }

    # Read admin-customizable intro from SystemConfig
    closing_prompt_cfg = db.query(models.SystemConfig).filter(
        models.SystemConfig.key == "tournament_closing_prompt"
    ).first()
    if closing_prompt_cfg and closing_prompt_cfg.value:
        intro = closing_prompt_cfg.value
    else:
        intro = "Tu es le commentateur sportif surexcité d'une LAN party."

    # Build standings summary
    standings_text = ""
    player_names = []
    for r in results:
        rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r.get("rank"), f"#{r.get('rank', '?')}")
        standings_text += f"{rank_emoji} {r['name']} — {r.get('total', 0)} pts (Placement: {r.get('placement_pts', 0)}, Bonus: {r.get('score_pts', 0)}, Participation: {r.get('participation_pts', 0)})\n"
        player_names.append(r['name'])

    # Also get usernames for solo mode participants not in standings
    if not use_teams:
        for uid in participant_uids:
            user = db.query(models.User).filter(models.User.id == uid).first()
            if user and user.username not in player_names:
                player_names.append(user.username)
                standings_text += f"  {user.username} — participant\n"

    # Build narratives
    narratives = _build_player_narratives(bracket, bracket_type, results, config, db, participant_uids, use_teams)
    narratives_text = ""
    for r in results:
        eid = r.get("entity_id")
        name = r.get("name", "?")
        facts = narratives.get(eid, [])
        if facts:
            narratives_text += f"{name} : {'. '.join(facts)}.\n"
    # Add narratives for participants not in results
    if not use_teams:
        for uid in participant_uids:
            if uid not in [r.get("entity_id") for r in results]:
                facts = narratives.get(uid, [])
                user = db.query(models.User).filter(models.User.id == uid).first()
                name = user.username if user else f"#{uid}"
                if facts:
                    narratives_text += f"{name} : {'. '.join(facts)}.\n"

    prompt = f"{intro}\n"
    prompt += f'Le tournoi "{tournament_name}" ({game_name or "jeu inconnu"}) vient de se terminer !\n'
    prompt += f"Format : {bracket_labels.get(bracket_type, bracket_type)} — {len(participant_uids)} joueurs\n\n"
    prompt += f"=== Résultats ===\n{standings_text}\n"
    if narratives_text:
        prompt += f"=== Faits Marquants par Joueur ===\n{narratives_text}\n"
    prompt += (
        'Génère un message COURT (1-2 phrases max), personnalisé et humoristique pour CHAQUE joueur/équipe.\n'
        'Utilise les faits marquants ci-dessus pour personnaliser chaque message.\n'
        'Réponds UNIQUEMENT en JSON valide, sans markdown, sans backticks :\n'
        '{"messages": [{"player": "nom", "message": "ton message"}, ...]}'
    )
    return prompt


async def _generate_tournament_notifications(tournament_id, tournament_name, game_name, results, participant_uids, use_teams, bracket=None, config=None):
    """Fire-and-forget: Ask Ollama to generate personalized messages for participants (via AI queue)."""
    bracket = bracket or []
    config = config or {}
    try:
        from .ia import pick_instance, get_effective_config
        from ..database import SessionLocal
        from ..ia_queue import queue_manager, QueueEntry
        import time

        db = SessionLocal()
        try:
            ia_cfg = get_effective_config(db)
            instance = await pick_instance(db)
            ollama_host = instance["url"] if instance else ia_cfg.get('ollama_host', 'http://host.docker.internal:11434')
            model = instance.get("model") if instance else ia_cfg.get('model', 'llama3')

            prompt = _build_closing_prompt(
                tournament_name, game_name, results, participant_uids,
                use_teams, bracket, config, db
            )

            # Enqueue through AI queue (priority 20 = background)
            entry = QueueEntry(
                priority=20,
                created_at=time.time(),
                user_id=0,  # System task, no user limit
                username=f"[Tournoi] {tournament_name}",
                conversation_id=0,
                task_type="notification",
                payload={
                    "ollama_host": ollama_host,
                    "model": model,
                    "prompt": prompt,
                    "context_window": ia_cfg.get("context_window", 4096),
                }
            )
            entry, _ = await queue_manager.enqueue(entry)

            # Wait for the worker to finish (with generous timeout for background task)
            await asyncio.wait_for(entry.done_event.wait(), timeout=180.0)

            # Read result
            result_data = await entry.result_stream.get()
            if result_data.get("error"):
                raise Exception(result_data.get("result", "Erreur de génération IA"))

            raw = result_data.get("result", "")
            # Clean up potential markdown wrapping
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(raw)
            ai_messages = data.get("messages", [])

            # Map player names to user IDs
            name_to_uid = {}
            for uid in participant_uids:
                user = db.query(models.User).filter(models.User.id == uid).first()
                if user:
                    name_to_uid[user.username.lower()] = uid

            # Also map team names to member UIDs
            if use_teams:
                for r in results:
                    if r.get("entity_id") and isinstance(r["entity_id"], int) and r["entity_id"] < 0:
                        team_id = abs(r["entity_id"])
                        members = db.query(models.TournamentTeamMember).filter(
                            models.TournamentTeamMember.team_id == team_id
                        ).all()
                        name_to_uid[r["name"].lower()] = [m.user_id for m in members]

            # Create notifications
            for ai_msg in ai_messages:
                player_name = ai_msg.get("player", "").lower()
                message = ai_msg.get("message", "")
                if not message:
                    continue

                target_uids = name_to_uid.get(player_name, [])
                if isinstance(target_uids, int):
                    target_uids = [target_uids]

                for uid in target_uids:
                    notif = models.Notification(
                        user_id=uid,
                        type="tournament_closed",
                        title=f"🏆 {tournament_name}",
                        content=message,
                        metadata_json={"tournament_id": tournament_id}
                    )
                    db.add(notif)

            db.commit()
            # Broadcast to all clients that new notifications are available
            await manager.broadcast({"type": "notification_new"})

        finally:
            db.close()
    except Exception as e:
        # Notify all admins about the failure
        import traceback
        traceback.print_exc()
        error_detail = f"{type(e).__name__}: {str(e)[:300]}"
        try:
            from ..database import SessionLocal
            err_db = SessionLocal()
            try:
                admins = err_db.query(models.User).filter(models.User.is_admin == True).all()
                for admin in admins:
                    notif = models.Notification(
                        user_id=admin.id,
                        type="system",
                        title=f"\u26a0\ufe0f \u00c9chec IA \u2014 {tournament_name}",
                        content=f"La g\u00e9n\u00e9ration de messages personnalis\u00e9s a \u00e9chou\u00e9.\n{error_detail}",
                        metadata_json={"tournament_id": tournament_id, "error": True}
                    )
                    err_db.add(notif)
                err_db.commit()
                await manager.broadcast({"type": "notification_new"})
            finally:
                err_db.close()
        except Exception:
            pass  # Last resort


def _compute_standings(bracket, bracket_type, lower_is_better=False):
    """Return list of (rank, player_id) from the bracket data."""
    standings = []
    
    if bracket_type == "ffa":
        # FFA multi-round: rank by survival depth, then by placement within each round.
        # Players in the LAST round get the best ranks (1st, 2nd, 3rd...).
        # Players eliminated in earlier rounds are ranked after, ordered by:
        #   1) Elimination round descending (eliminated later = better)
        #   2) Their placement/score within that round (lower placement = better)
        max_r = max((m["id"]["r"] for m in bracket), default=0)

        # Collect all players per round
        round_matches = {}
        for m in bracket:
            r = m["id"]["r"]
            if m["id"]["m"] == 1:
                round_matches[r] = m

        # Build: who is in each round, and who was eliminated after each round
        players_in_round = {}  # round -> set of player ids
        for r in sorted(round_matches.keys()):
            m = round_matches[r]
            players_in_round[r] = set(pid for pid in m["p"] if pid and pid != 0)

        # For each round except the last, eliminated = in this round but NOT in next round
        eliminated_per_round = {}  # round -> [(pid, score)]
        for r in sorted(round_matches.keys()):
            if r == max_r:
                continue  # Last round players are survivors, not eliminated
            next_r = r + 1
            next_players = players_in_round.get(next_r, set())
            m = round_matches[r]
            scores = m.get("score", [])
            for i, pid in enumerate(m["p"]):
                if pid and pid != 0 and pid not in next_players:
                    score = scores[i] if i < len(scores) else 0
                    eliminated_per_round.setdefault(r, []).append((pid, score))

        # Rank last-round players first
        last_match = round_matches.get(max_r)
        current_rank = 0
        if last_match:
            paired = list(zip(last_match["p"], last_match.get("score", [])))
            valid = [(pid, s) for pid, s in paired if pid and pid != 0 and s and s > 0]
            # In FFA, score = placement position (lower = better regardless of config)
            # because ffa-advance sorts by score ascending to pick top N
            valid.sort(key=lambda x: x[1])
            prev_score = None
            for pid, score in valid:
                if score != prev_score:
                    current_rank += 1
                    prev_score = score
                standings.append((current_rank, pid))

        # Then rank eliminated players, latest elimination round first
        for r in sorted(eliminated_per_round.keys(), reverse=True):
            elim = eliminated_per_round[r]
            # Sort eliminated: lower score = better (they got a better placement before being cut)
            elim.sort(key=lambda x: x[1])
            base_rank = current_rank + 1
            prev_score = None
            local_rank = base_rank - 1
            for pid, score in elim:
                if score != prev_score:
                    local_rank += 1
                    prev_score = score
                standings.append((local_rank, pid))
                current_rank = max(current_rank, local_rank)

        return standings

    
    if bracket_type == "round_robin":
        # Round robin: compute win totals
        win_counts = {}
        played_matches = {}  # Track which players have actually played a scored match
        for m in bracket:
            p0, p1 = m["p"][0], m["p"][1]
            s0, s1 = m.get("score", [0, 0])[0], m.get("score", [0, 0])[1]
            if p0: win_counts.setdefault(p0, 0)
            if p1: win_counts.setdefault(p1, 0)
            if s0 is None or s1 is None:
                continue
            # Check if this match has been scored (at least one non-zero score or a draw)
            match_scored = (s0 != 0 or s1 != 0) or (s0 == s1 and s0 != 0)
            if match_scored:
                if p0: played_matches[p0] = played_matches.get(p0, 0) + 1
                if p1: played_matches[p1] = played_matches.get(p1, 0) + 1
            if lower_is_better:
                if s0 < s1 and s0 > 0 and p0:
                    win_counts[p0] = win_counts.get(p0, 0) + 1
                elif s1 < s0 and s1 > 0 and p1:
                    win_counts[p1] = win_counts.get(p1, 0) + 1
            else:
                if s0 > s1 and p0:
                    win_counts[p0] = win_counts.get(p0, 0) + 1
                elif s1 > s0 and p1:
                    win_counts[p1] = win_counts.get(p1, 0) + 1
        # Only rank players who have played at least one scored match
        active_players = {pid: w for pid, w in win_counts.items() if played_matches.get(pid, 0) > 0}
        sorted_players = sorted(active_players.items(), key=lambda x: x[1], reverse=True)
        prev_wins = None
        current_rank = 0
        for i, (pid, wins) in enumerate(sorted_players):
            if wins != prev_wins:
                current_rank += 1
                prev_wins = wins
            standings.append((current_rank, pid))
        return standings
    
    # Single/Double elim: find final match winner
    max_wb = max((m["id"]["r"] for m in bracket if m["id"]["s"] == 1), default=0)
    final = next((m for m in bracket if m["id"]["s"] == 1 and m["id"]["r"] == max_wb and m["id"]["m"] == 1), None)
    
    if final:
        s = final.get("score", [0, 0])
        s0 = s[0] if len(s) > 0 and s[0] is not None else 0
        s1 = s[1] if len(s) > 1 and s[1] is not None else 0
        if s0 != s1:
            w_idx = 0 if s0 > s1 else 1
            l_idx = 1 - w_idx
            standings.append((1, final["p"][w_idx]))  # 1st
            standings.append((2, final["p"][l_idx]))  # 2nd
    
    # 3rd place: loser of WB semi-final or LB semi-final
    if bracket_type == "double_elim":
        max_lb = max((m["id"]["r"] for m in bracket if m["id"]["s"] == 2), default=0)
        lb_final = next((m for m in bracket if m["id"]["s"] == 2 and m["id"]["r"] == max_lb and m["id"]["m"] == 1), None)
        if lb_final:
            s = lb_final.get("score", [0, 0])
            s0 = s[0] if len(s) > 0 and s[0] is not None else 0
            s1 = s[1] if len(s) > 1 and s[1] is not None else 0
            if s0 != s1:
                l_idx = 1 if s0 > s1 else 0
                loser_id = lb_final["p"][l_idx]
                if loser_id and loser_id != 0 and loser_id not in [x[1] for x in standings]:
                    standings.append((3, loser_id))
    elif bracket_type == "single_elim" and max_wb >= 2:
        # Semi-final losers get 3rd
        semis = [m for m in bracket if m["id"]["s"] == 1 and m["id"]["r"] == max_wb - 1]
        for semi in semis:
            s = semi.get("score", [0, 0])
            s0 = s[0] if len(s) > 0 and s[0] is not None else 0
            s1 = s[1] if len(s) > 1 and s[1] is not None else 0
            if s0 != s1:
                l_idx = 1 if s0 > s1 else 0
                loser_id = semi["p"][l_idx]
                if loser_id and loser_id != 0 and loser_id not in [x[1] for x in standings]:
                    standings.append((3, loser_id))
    
    return standings


def _compute_projected_standings(tournament, db):
    """Single source of truth: compute projected points for all participants."""
    config = tournament.config or {}
    bracket = tournament.bracket or []
    bracket_type = config.get("bracket_type", "single_elim")
    use_teams = config.get("use_teams", False)
    lower_is_better = config.get("lower_score_is_better", False)
    pts_winner = config.get("pts_winner", 10)
    pts_second = config.get("pts_second", 6)
    pts_third = config.get("pts_third", 4)
    pts_participation = config.get("pts_participation", 1)
    pts_per_match = config.get("pts_per_match", config.get("pts_per_goal", 1.0))
    ppw = tournament.points_per_win or 3

    if not bracket:
        participants = db.query(models.TournamentParticipant).filter(
            models.TournamentParticipant.tournament_id == tournament.id
        ).all()
        users = db.query(models.User).filter(models.User.id.in_([p.user_id for p in participants])).all()
        user_map = {u.id: u.username for u in users}
        return [{"rank": None, "entity_id": p.user_id, "name": user_map.get(p.user_id, f"#{p.user_id}"),
                 "placement_pts": 0, "participation_pts": 0, "score_pts": 0,
                 "total": 0, "per_member": 0, "member_count": 1, "team_name": None, "wins": 0
                 } for p in participants]

    # Step 1: Compute wins + cumulated scores from bracket
    wins = {}
    cumulated_scores = {}  # entity_id -> total raw score
    matches_played = {}  # match count per entity
    for m in bracket:
        p = m.get("p", [])
        s = m.get("score", [])
        if 0 in p:
            continue
        has_scores = any(v is not None and v > 0 for v in s)
        for i, pid in enumerate(p):
            if pid and pid != 0:
                wins.setdefault(pid, 0)
                cumulated_scores.setdefault(pid, 0)
                matches_played.setdefault(pid, 0)
                if has_scores and i < len(s):
                    val = s[i] if s[i] is not None else 0
                    cumulated_scores[pid] += max(0, val)
                    matches_played[pid] += 1
        if bracket_type != "ffa" and len(s) >= 2 and s[0] is not None and s[1] is not None and s[0] != s[1]:
            w_idx = (0 if s[0] < s[1] else 1) if lower_is_better else (0 if s[0] > s[1] else 1)
            w_id = p[w_idx] if w_idx < len(p) else None
            if w_id and w_id != 0:
                wins[w_id] = wins.get(w_id, 0) + 1

    # Normalize cumulated scores → score bonus
    score_bonus = {}
    if bracket_type == "ffa":
        # FFA: normalize per-round separately, then sum
        round_matches = {}
        for m in bracket:
            r = m["id"]["r"]
            if m["id"]["m"] == 1:
                round_matches[r] = m
        for r in sorted(round_matches.keys()):
            rm = round_matches[r]
            rp = rm.get("p", [])
            rs = rm.get("score", [])
            if not any(v is not None and v > 0 for v in rs):
                continue
            round_data = [(pid, rs[i]) for i, pid in enumerate(rp)
                          if pid and pid != 0 and i < len(rs) and rs[i] is not None and rs[i] > 0]
            if not round_data:
                continue
            round_scores = [s for _, s in round_data]
            min_rs = min(round_scores)
            max_rs = max(round_scores)
            rng = max_rs - min_rs
            for pid, sc in round_data:
                if rng > 0:
                    normalized = (max_rs - sc) / rng
                else:
                    normalized = 1.0
                score_bonus[pid] = round(score_bonus.get(pid, 0) + pts_per_match * (1 + normalized), 1)
    else:
        # Non-FFA: single-pool normalization
        all_cs = [v for v in cumulated_scores.values() if v > 0] or [0]
        min_cs = min(all_cs)
        max_cs = max(all_cs)
        score_range = max_cs - min_cs
        for eid, cs in cumulated_scores.items():
            if cs <= 0:
                score_bonus[eid] = 0
            elif score_range > 0:
                if lower_is_better:
                    normalized = (max_cs - cs) / score_range
                else:
                    normalized = (cs - min_cs) / score_range
                score_bonus[eid] = round(pts_per_match * (1 + normalized), 1)
            else:
                score_bonus[eid] = pts_per_match * 2  # everyone equal → full bonus

    # Step 2: Bracket-based placement for elimination formats
    bracket_standings = _compute_standings(bracket, bracket_type, lower_is_better)
    bracket_rank_map = {eid: rank for rank, eid in bracket_standings}

    # Step 3: Rank all entities by competitive score
    all_entities = set(list(wins.keys()) + list(score_bonus.keys()))
    ranked = []
    for eid in all_entities:
        w = wins.get(eid, 0)
        sb = score_bonus.get(eid, 0)
        rank_score = w * ppw + sb  # Keep full precision to avoid artificial ties
        ranked.append({"entity_id": eid, "wins": w, "score_bonus": sb, "rank_score": rank_score,
                       "matches_played": matches_played.get(eid, 0),
                       "cumulated_score": cumulated_scores.get(eid, 0)})
    ranked.sort(key=lambda x: x["rank_score"], reverse=True)

    placement_map = {1: pts_winner, 2: pts_second, 3: pts_third}
    team_map = config.get("_team_map", {})

    # Team member counts
    team_member_counts = {}
    if use_teams:
        teams_db = db.query(models.TournamentTeam).filter(
            models.TournamentTeam.tournament_id == tournament.id).all()
        for t in teams_db:
            count = db.query(models.TournamentTeamMember).filter(
                models.TournamentTeamMember.team_id == t.id).count()
            team_member_counts[-t.id] = max(count, 1)

    # Step 4: Build results with ex-aequo support
    # Compute dense competition ranks (1,1,2,2,3...) based on rank_score
    exaequo_ranks = []
    prev_score = None
    current_rank = 0
    for i, entry in enumerate(ranked):
        if entry["rank_score"] != prev_score:
            current_rank += 1
            prev_score = entry["rank_score"]
        exaequo_ranks.append(current_rank)

    results = []
    for i, entry in enumerate(ranked):
        eid = entry["entity_id"]
        mp = entry["matches_played"]
        has_explicit_rank = eid in bracket_rank_map
        
        # Rank and placement points
        if mp > 0 or has_explicit_rank:
            rank = bracket_rank_map.get(eid, exaequo_ranks[i])
            placement_pts = placement_map.get(rank, 0)
        else:
            rank = None
            placement_pts = 0
            
        score_pts = round(entry["score_bonus"], 1) if mp > 0 else 0
        participation = round(pts_participation * mp, 1)  # Strictly matches played
        total = round(placement_pts + participation + score_pts, 1)
        
        if use_teams and eid < 0:
            name = team_map.get(str(eid), f"Team #{abs(eid)}")
        else:
            user = db.query(models.User).filter(models.User.id == eid).first()
            name = user.username if user else f"#{eid}"
            
        member_count = team_member_counts.get(eid, 1) if use_teams else 1
        per_member = total  # No division — each member gets full team points
        results.append({
            "rank": rank, "entity_id": eid, "name": name, "wins": entry["wins"],
            "placement_pts": placement_pts, "participation_pts": participation,
            "score_pts": score_pts, "total": total, "per_member": per_member,
            "member_count": member_count, "team_name": name if (use_teams and eid < 0) else None,
            "matches_played": mp, "pts_per_match": pts_per_match,
            "cumulated_score": entry["cumulated_score"]
        })

    results.sort(key=lambda x: (x["rank"] if x["rank"] else 999, -x["total"]))

    # Include participants not in bracket
    placed_eids = {r["entity_id"] for r in results}
    participants = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament.id).all()
    if not use_teams:
        for p in participants:
            if p.user_id not in placed_eids:
                user = db.query(models.User).filter(models.User.id == p.user_id).first()
                results.append({
                    "rank": None, "entity_id": p.user_id,
                    "name": user.username if user else f"#{p.user_id}",
                    "wins": 0, "placement_pts": 0, "participation_pts": 0,
                    "score_pts": 0, "total": 0, "per_member": 0,
                    "member_count": 1, "team_name": None,
                    "matches_played": 0, "pts_per_match": pts_per_match, "cumulated_score": 0
                })
    return results


@router.get("/{tournament_id}/standings")
def get_tournament_standings(tournament_id: int, db: Session = Depends(database.get_db)):
    """Single source of truth for projected standings. Public endpoint."""
    tournament = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.status == "CLOSED" and tournament.results:
        # Augment stored results with per_member/member_count for frontend
        config = tournament.config or {}
        use_teams = config.get("use_teams", False)
        results = []
        team_member_counts = {}
        if use_teams:
            teams_db = db.query(models.TournamentTeam).filter(
                models.TournamentTeam.tournament_id == tournament_id).all()
            for t in teams_db:
                count = db.query(models.TournamentTeamMember).filter(
                    models.TournamentTeamMember.team_id == t.id).count()
                team_member_counts[-t.id] = max(count, 1)
        for r in tournament.results:
            entry = dict(r)
            eid = entry.get("entity_id")
            # Sanitize floating-point artifacts from legacy data
            for k in ("total", "placement_pts", "participation_pts", "score_pts"):
                if k in entry:
                    entry[k] = round(entry[k], 1)
            mc = team_member_counts.get(eid, 1) if use_teams else 1
            entry.setdefault("member_count", mc)
            entry.setdefault("per_member", round(entry.get("total", 0) / mc, 1))
            entry.setdefault("wins", 0)
            results.append(entry)
        return {"status": "closed", "standings": results}
    if tournament.status in ("RUNNING", "DONE"):
        standings = _compute_projected_standings(tournament, db)
        return {"status": "live", "standings": standings}
    return {"status": "open", "standings": []}
