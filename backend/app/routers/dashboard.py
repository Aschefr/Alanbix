from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from .. import models, database, auth
import os

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
INFO_FILES_DIR = os.path.join(DATA_DIR, "info_files")

@router.get("/stats")
def get_stats(db: Session = Depends(database.get_db)):
    """Public endpoint — no auth required (for spectator mode)."""
    tournaments_count = db.query(models.Tournament).count()
    users_count = db.query(models.User).count()
    games_count = db.query(models.Game).count()
    active_tournaments = db.query(models.Tournament).filter(models.Tournament.status == "RUNNING").count()
    
    # Leaderboard: DB points + live projected points from RUNNING tournaments
    all_users = db.query(models.User).all()
    user_pts = {u.id: {"username": u.username, "points": u.points or 0, "team_name": u.team_name} for u in all_users}
    
    # Add live points from running tournaments
    running = db.query(models.Tournament).filter(models.Tournament.status.in_(["RUNNING", "DONE"])).all()
    for t in running:
        bracket = t.bracket or []
        if not bracket:
            continue
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        ppw = t.points_per_win or 3
        ppg = config.get("pts_per_goal", 0)
        lower_is_better = config.get("lower_score_is_better", False)
        
        wins = {}
        goals = {}
        for m in bracket:
            p = m.get("p", [])
            s = m.get("score", [])
            if 0 in p:
                continue
            for i, pid in enumerate(p):
                if pid and pid != 0:
                    wins.setdefault(pid, 0)
                    goals.setdefault(pid, 0)
                    raw = max(0, s[i] if i < len(s) else 0)
                    if lower_is_better and raw > 0:
                        max_s = max((v for v in s if v > 0), default=0)
                        goals[pid] += (max_s + 1 - raw)
                    else:
                        goals[pid] += raw
            if len(s) >= 2 and s[0] > 0 and s[1] > 0 and s[0] != s[1]:
                w_idx = (0 if s[0] < s[1] else 1) if lower_is_better else (0 if s[0] > s[1] else 1)
                w_id = p[w_idx] if w_idx < len(p) else None
                if w_id and w_id != 0:
                    wins[w_id] = wins.get(w_id, 0) + 1
        
        # Map entity pts to user pts
        if use_teams:
            teams_db = db.query(models.TournamentTeam).filter(models.TournamentTeam.tournament_id == t.id).all()
            for team in teams_db:
                entity_id = -team.id
                entity_pts = wins.get(entity_id, 0) * ppw + round(goals.get(entity_id, 0) * ppg, 1)
                if entity_pts > 0:
                    members = db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == team.id).all()
                    for mem in members:
                        if mem.user_id in user_pts:
                            user_pts[mem.user_id]["points"] += entity_pts
        else:
            for eid, w in wins.items():
                if eid > 0 and eid in user_pts:
                    user_pts[eid]["points"] += w * ppw + round(goals.get(eid, 0) * ppg, 1)
    
    leaderboard = [{"username": v["username"], "points": round(v["points"], 1), "team_name": v["team_name"]} 
                   for v in user_pts.values() if v["points"] > 0]
    leaderboard.sort(key=lambda x: x["points"], reverse=True)
    leaderboard = leaderboard[:10]
    
    # Participation counts
    for entry in leaderboard:
        user = db.query(models.User).filter(models.User.username == entry["username"]).first()
        if user:
            entry["participations"] = db.query(models.TournamentParticipant).filter(
                models.TournamentParticipant.user_id == user.id
            ).count()
    
    # Get event name from system config
    event_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "event_name").first()
    event_name = event_config.value if event_config else "Alanbix LAN"

    # Team scoring mode
    team_mode_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "team_scoring_mode").first()
    team_scoring_mode = team_mode_config.value if team_mode_config else "weighted"

    return {
        "tournaments": tournaments_count,
        "players": users_count,
        "games": games_count,
        "active": active_tournaments,
        "leaderboard": leaderboard,
        "event_name": event_name,
        "team_scoring_mode": team_scoring_mode
    }


@router.get("/team-leaderboard")
def get_team_leaderboard(db: Session = Depends(database.get_db)):
    """Public endpoint — team leaderboard grouped by User.team_name."""
    from sqlalchemy import func
    
    # Get team scoring mode preference
    mode_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "team_scoring_mode").first()
    mode = mode_config.value if mode_config else "weighted"
    
    # Build live points per user (DB + running tournaments)
    all_users_q = db.query(models.User).filter(
        models.User.team_name.isnot(None),
        models.User.team_name != ""
    ).all()
    
    # Compute live pts per user_id
    live_pts = {}
    running = db.query(models.Tournament).filter(models.Tournament.status.in_(["RUNNING", "DONE"])).all()
    for t in running:
        bracket = t.bracket or []
        if not bracket:
            continue
        config = t.config or {}
        use_teams_t = config.get("use_teams", False)
        ppw = t.points_per_win or 3
        ppg = config.get("pts_per_goal", 0)
        lower_is_better = config.get("lower_score_is_better", False)
        
        wins = {}
        goals = {}
        for m in bracket:
            p = m.get("p", [])
            s = m.get("score", [])
            if 0 in p:
                continue
            for i, pid in enumerate(p):
                if pid and pid != 0:
                    wins.setdefault(pid, 0)
                    goals.setdefault(pid, 0)
                    raw = max(0, s[i] if i < len(s) else 0)
                    if lower_is_better and raw > 0:
                        max_s = max((v for v in s if v > 0), default=0)
                        goals[pid] += (max_s + 1 - raw)
                    else:
                        goals[pid] += raw
            if len(s) >= 2 and s[0] > 0 and s[1] > 0 and s[0] != s[1]:
                w_idx = (0 if s[0] < s[1] else 1) if lower_is_better else (0 if s[0] > s[1] else 1)
                w_id = p[w_idx] if w_idx < len(p) else None
                if w_id and w_id != 0:
                    wins[w_id] = wins.get(w_id, 0) + 1
        
        if use_teams_t:
            teams_db = db.query(models.TournamentTeam).filter(models.TournamentTeam.tournament_id == t.id).all()
            for team_t in teams_db:
                entity_id = -team_t.id
                entity_pts = wins.get(entity_id, 0) * ppw + round(goals.get(entity_id, 0) * ppg, 1)
                if entity_pts > 0:
                    members = db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == team_t.id).all()
                    for mem in members:
                        live_pts[mem.user_id] = live_pts.get(mem.user_id, 0) + entity_pts
        else:
            for eid, w in wins.items():
                if eid > 0:
                    live_pts[eid] = live_pts.get(eid, 0) + w * ppw + round(goals.get(eid, 0) * ppg, 1)
    
    # Group by team_name with combined pts
    teams = {}
    for u in all_users_q:
        tn = u.team_name.strip()
        if not tn:
            continue
        if tn not in teams:
            teams[tn] = {"members": [], "total_points": 0}
        total_u = (u.points or 0) + live_pts.get(u.id, 0)
        teams[tn]["members"].append({"username": u.username, "points": round(total_u, 1)})
        teams[tn]["total_points"] += total_u
    
    # Build result
    result = []
    for team_name, data in teams.items():
        count = len(data["members"])
        total = data["total_points"]
        avg = round(total / count, 1) if count > 0 else 0
        score = avg if mode == "weighted" else total
        result.append({
            "team_name": team_name,
            "total_points": total,
            "avg_points": avg,
            "score": score,
            "member_count": count,
            "members": data["members"]
        })
    
    result.sort(key=lambda x: x["score"], reverse=True)
    return result


@router.get("/info")
def get_info_page(db: Session = Depends(database.get_db)):
    """Public endpoint — serves info page content (markdown)."""
    content_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "info_page_content").first()
    spectator_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "info_spectator_content").first()
    return {
        "content": content_cfg.value if content_cfg else "",
        "spectator_content": spectator_cfg.value if spectator_cfg else ""
    }


# --- Info Page File Manager (AXE-13) ---

def _sanitize_filename(name: str) -> str:
    """Sanitize filename: keep alphanums, dots, hyphens, underscores."""
    import re
    name = name.strip().replace(" ", "_")
    name = re.sub(r'[^\w.\-]', '', name)
    return name or "file"


@router.get("/info/files")
def list_info_files():
    """Public — list uploaded files with name, size, date."""
    os.makedirs(INFO_FILES_DIR, exist_ok=True)
    files = []
    for fname in sorted(os.listdir(INFO_FILES_DIR)):
        fpath = os.path.join(INFO_FILES_DIR, fname)
        if os.path.isfile(fpath):
            stat = os.stat(fpath)
            files.append({
                "name": fname,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "url": f"/data/info_files/{fname}"
            })
    return files


@router.post("/info/files/upload")
async def upload_info_file(
    file: UploadFile = File(...),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Admin — upload a file (max 100MB)."""
    os.makedirs(INFO_FILES_DIR, exist_ok=True)
    
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 100 MB)")
    
    safe_name = _sanitize_filename(file.filename or "upload")
    filepath = os.path.join(INFO_FILES_DIR, safe_name)
    
    # Avoid overwriting: append counter if exists
    if os.path.exists(filepath):
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(filepath):
            safe_name = f"{base}_{counter}{ext}"
            filepath = os.path.join(INFO_FILES_DIR, safe_name)
            counter += 1
    
    with open(filepath, "wb") as f:
        f.write(content)
    
    return {
        "name": safe_name,
        "size": len(content),
        "url": f"/data/info_files/{safe_name}"
    }


@router.delete("/info/files/{filename}")
def delete_info_file(
    filename: str,
    admin: models.User = Depends(auth.get_current_admin)
):
    """Admin — delete a file."""
    safe_name = _sanitize_filename(filename)
    filepath = os.path.join(INFO_FILES_DIR, safe_name)
    if not os.path.isfile(filepath):
        raise HTTPException(404, "File not found")
    os.remove(filepath)
    return {"status": "deleted", "name": safe_name}


@router.delete("/info/files")
def nuke_info_files(
    admin: models.User = Depends(auth.get_current_admin)
):
    """Admin — delete ALL info files."""
    os.makedirs(INFO_FILES_DIR, exist_ok=True)
    count = 0
    for fname in os.listdir(INFO_FILES_DIR):
        fpath = os.path.join(INFO_FILES_DIR, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)
            count += 1
    return {"status": "nuked", "deleted": count}

