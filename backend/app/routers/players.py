from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, case
from pydantic import BaseModel
from .. import models, auth, database
from ..websockets import manager as ws_manager

router = APIRouter(prefix="/players", tags=["Players"])


@router.get("")
def list_players(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """List all players with basic info for the directory."""
    users = db.query(models.User).all()
    return [{
        "id": u.id, "username": u.username, "team_name": u.team_name,
        "seat_id": u.seat_id, "points": u.points or 0, "is_admin": u.is_admin
    } for u in users]


@router.get("/{user_id}/points-history")
def get_player_points_history(user_id: int, db: Session = Depends(database.get_db), current: models.User = Depends(auth.get_current_user)):
    """Get point breakdown for any player across tournaments."""
    from .tournaments import _compute_projected_standings

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404, "User not found")

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

        participant = db.query(models.TournamentParticipant).filter(
            models.TournamentParticipant.tournament_id == t.id,
            models.TournamentParticipant.user_id == user_id
        ).first()
        if not participant:
            continue

        if t.status == "CLOSED" and t.results:
            for r in t.results:
                eid = r.get("entity_id")
                if not use_teams and eid == user_id:
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
                        models.TournamentTeamMember.user_id == user_id
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
            standings = _compute_projected_standings(t, db)
            user_entity = user_id
            team_name_found = None
            if use_teams:
                team_member = db.query(models.TournamentTeamMember).join(
                    models.TournamentTeam
                ).filter(
                    models.TournamentTeam.tournament_id == t.id,
                    models.TournamentTeamMember.user_id == user_id
                ).first()
                if team_member:
                    user_entity = -team_member.team_id
                    team = db.query(models.TournamentTeam).get(team_member.team_id)
                    team_name_found = team.name if team else None

            entry = next((s for s in standings if s["entity_id"] == user_entity), None)
            if entry:
                if use_teams and entry["member_count"] > 1:
                    mc = entry["member_count"]
                    history.append({
                        "tournament_id": t.id, "tournament_name": t.name,
                        "game_name": game_name, "status": t.status, "live": True,
                        "rank": entry["rank"],
                        "placement_pts": round(entry["placement_pts"] / mc, 1),
                        "participation_pts": round(entry["participation_pts"] / mc, 1),
                        "score_pts": round(entry["score_pts"] / mc, 1),
                        "total": entry["per_member"], "team_name": team_name_found
                    })
                else:
                    history.append({
                        "tournament_id": t.id, "tournament_name": t.name,
                        "game_name": game_name, "status": t.status, "live": True,
                        "rank": entry["rank"],
                        "placement_pts": entry["placement_pts"],
                        "participation_pts": entry["participation_pts"],
                        "score_pts": entry["score_pts"],
                        "total": entry["total"], "team_name": team_name_found
                    })
            else:
                history.append({
                    "tournament_id": t.id, "tournament_name": t.name,
                    "game_name": game_name, "status": t.status, "live": True,
                    "rank": None, "placement_pts": 0, "participation_pts": 0,
                    "score_pts": 0, "total": 0, "team_name": None
                })

    return {"total_points": target.points or 0, "history": history}


# --- Private Messaging ---

class SendMessage(BaseModel):
    content: str


@router.get("/messages/unread-count")
def pm_unread_count(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Total unread private messages for current user."""
    count = db.query(models.PrivateMessage).filter(
        models.PrivateMessage.receiver_id == user.id,
        models.PrivateMessage.is_read == False
    ).count()
    return {"count": count}


@router.get("/messages/conversations")
def pm_conversations(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """List active conversations (peers with messages), sorted by most recent."""
    # Get all messages involving current user
    msgs = db.query(models.PrivateMessage).filter(
        or_(
            models.PrivateMessage.sender_id == user.id,
            models.PrivateMessage.receiver_id == user.id
        )
    ).order_by(models.PrivateMessage.created_at.desc()).all()

    # Group by peer
    seen = {}
    for m in msgs:
        peer_id = m.receiver_id if m.sender_id == user.id else m.sender_id
        if peer_id not in seen:
            peer = db.query(models.User).filter(models.User.id == peer_id).first()
            unread = db.query(models.PrivateMessage).filter(
                models.PrivateMessage.sender_id == peer_id,
                models.PrivateMessage.receiver_id == user.id,
                models.PrivateMessage.is_read == False
            ).count()
            seen[peer_id] = {
                "peer_id": peer_id,
                "peer_username": peer.username if peer else "?",
                "peer_team_name": peer.team_name if peer else None,
                "last_message": m.content[:100],
                "last_at": m.created_at.isoformat() if m.created_at else None,
                "unread": unread,
                "is_me_sender": m.sender_id == user.id
            }
    return list(seen.values())


@router.get("/messages/{peer_id}")
def pm_read(peer_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Read conversation with a specific peer. Auto-marks received messages as read."""
    # Mark unread messages from peer as read
    db.query(models.PrivateMessage).filter(
        models.PrivateMessage.sender_id == peer_id,
        models.PrivateMessage.receiver_id == user.id,
        models.PrivateMessage.is_read == False
    ).update({"is_read": True})
    db.commit()

    # Fetch all messages between the two users
    messages = db.query(models.PrivateMessage).filter(
        or_(
            and_(models.PrivateMessage.sender_id == user.id, models.PrivateMessage.receiver_id == peer_id),
            and_(models.PrivateMessage.sender_id == peer_id, models.PrivateMessage.receiver_id == user.id)
        )
    ).order_by(models.PrivateMessage.created_at.asc()).all()

    peer = db.query(models.User).filter(models.User.id == peer_id).first()

    return {
        "peer": {
            "id": peer.id, "username": peer.username,
            "team_name": peer.team_name, "seat_id": peer.seat_id
        } if peer else None,
        "messages": [{
            "id": m.id, "sender_id": m.sender_id, "receiver_id": m.receiver_id,
            "content": m.content, "is_read": m.is_read,
            "created_at": m.created_at.isoformat() if m.created_at else None
        } for m in messages]
    }


@router.post("/messages/{peer_id}")
async def pm_send(peer_id: int, body: SendMessage, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Send a private message to another player."""
    if peer_id == user.id:
        raise HTTPException(400, "Cannot message yourself")
    peer = db.query(models.User).filter(models.User.id == peer_id).first()
    if not peer:
        raise HTTPException(404, "User not found")
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(400, "Message cannot be empty")
    if len(content) > 2000:
        raise HTTPException(400, "Message too long (max 2000 chars)")

    msg = models.PrivateMessage(
        sender_id=user.id, receiver_id=peer_id, content=content
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Real-time broadcast so both sender and receiver update instantly
    await ws_manager.broadcast({
        "type": "private_message_new",
        "sender_id": user.id,
        "receiver_id": peer_id,
        "message_id": msg.id
    })

    return {
        "status": "sent", "id": msg.id,
        "created_at": msg.created_at.isoformat() if msg.created_at else None
    }
