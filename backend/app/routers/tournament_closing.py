"""Closing a tournament (points handed out) and reopening it (points taken back)."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import auth, database, models
from ..websockets import manager
from .tournaments import _hidden_tournament_guard, _compute_projected_standings, _generate_tournament_notifications

router = APIRouter(prefix="/tournaments", tags=["Tournaments"], dependencies=[Depends(_hidden_tournament_guard)])


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
    pts_winner = config.get("pts_winner", 1.5)
    pts_second = config.get("pts_second", 1.3)
    pts_third = config.get("pts_third", 1.0)
    pts_participation = config.get("pts_participation", 1.0)
    pts_per_match = config.get("pts_per_match", config.get("pts_per_goal", 0.5))
    
    bracket = tournament.bracket or []
    
    # --- Calculate standings & results using the single source of truth ---
    results = _compute_projected_standings(tournament, db)
    
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
            
    # Distribute points to users based on computed standings
    for entry in results:
        total = entry["total"]
        entity_id = entry["entity_id"]
        
        if use_teams and entity_id < 0:
            member_uids = team_members_map.get(entity_id, [])
            for uid in member_uids:
                user = db.query(models.User).filter(models.User.id == uid).first()
                if user:
                    user.points = round((user.points or 0) + round(total, 1), 1)
        elif not use_teams and entity_id > 0:
            user = db.query(models.User).filter(models.User.id == entity_id).first()
            if user:
                user.points = round((user.points or 0) + round(total, 1), 1)
    
    tournament.results = results
    tournament.status = "CLOSED"
    from sqlalchemy.orm.attributes import flag_modified
    db.commit()
    
    try:
        from .awards import sync_automatic_awards
        await sync_automatic_awards(db)
    except Exception as e:
        print(f"Error syncing awards on close: {e}")
    
    await manager.broadcast({"type": "tournament_closed", "tournament_id": tournament_id})

    # Fire-and-forget: generate AI personalized notifications for participants
    participants = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id
    ).all()
    participant_uids = {p.user_id for p in participants}

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
        total = round(float(r.get("total", 0)), 1)
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
                    user.points = round(max(0.0, (user.points or 0) - total), 1)
                    rolled_back_uids.add(m.user_id)
        else:
            # Solo player (including rank=None participation-only entries)
            user = db.query(models.User).filter(models.User.id == entity_id).first()
            if user:
                user.points = round(max(0.0, (user.points or 0) - total), 1)
                rolled_back_uids.add(entity_id)

    # Also rollback participation-only players not in results (legacy data before fix)
    participants = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.tournament_id == tournament_id
    ).all()
    # No extra rollback needed — all participants now appear in results after the fix

    tournament.results = None
    tournament.status = "DONE"
    db.commit()

    try:
        from .awards import sync_automatic_awards
        await sync_automatic_awards(db)
    except Exception as e:
        print(f"Error syncing awards on reopen: {e}")

    await manager.broadcast({"type": "tournament_reopened", "tournament_id": tournament_id})
    return {"status": "reopened", "rolled_back_users": len(rolled_back_uids)}
