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
        "seat_id": u.seat_id, "points": u.points or 0, "is_admin": u.is_admin,
        "avatar_url": u.avatar_url, "avatar_shape": u.avatar_shape,
        "is_online": u.is_online
    } for u in users]


@router.get("/teams")
def list_global_teams(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """List all unique team names currently associated with players."""
    teams = db.query(models.User.team_name).filter(
        models.User.team_name != None,
        models.User.team_name != ""
    ).distinct().all()
    return [t[0] for t in teams]


@router.get("/{user_id}/points-history")
def get_player_points_history(user_id: int, db: Session = Depends(database.get_db), current: models.User = Depends(auth.get_current_user)):
    """Get point breakdown for any player across tournaments."""
    from .tournaments import _compute_projected_standings

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404, "User not found")

    tournaments = db.query(models.Tournament).filter(
        models.Tournament.status.in_(["OPEN", "RUNNING", "DONE", "CLOSED"])
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

        if t.status == "OPEN":
            history.append({
                "tournament_id": t.id, "tournament_name": t.name,
                "game_name": game_name, "status": t.status, "live": False,
                "rank": None, "placement_pts": 0.0, "participation_pts": 0.0,
                "score_pts": 0.0, "total": 0.0, "team_name": participant.team_name
            })
            continue

        if t.status == "CLOSED" and t.results:
            for r in t.results:
                eid = r.get("entity_id")
                if not use_teams and eid == user_id:
                    history.append({
                        "tournament_id": t.id, "tournament_name": t.name,
                        "game_name": game_name, "status": t.status, "live": False,
                        "rank": r.get("rank"),
                        "placement_pts": round(r.get("placement_pts", 0), 1),
                        "participation_pts": round(r.get("participation_pts", 0), 1),
                        "score_pts": round(r.get("score_pts", 0), 1),
                        "total": round(r.get("total", 0), 1), "team_name": None
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
                            "placement_pts": round(r.get("placement_pts", 0), 1),
                            "participation_pts": round(r.get("participation_pts", 0), 1),
                            "score_pts": round(r.get("score_pts", 0), 1),
                            "total": round(r.get("total", 0), 1), "team_name": r.get("name")
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

    # Fetch awards for target user
    awards_diffused_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "awards_diffused").first()
    is_diffused = awards_diffused_config.value if awards_diffused_config else False

    awards_list = []
    if is_diffused:
        awards = db.query(models.Award).filter(models.Award.user_id == user_id).order_by(models.Award.created_at.desc()).all()
        awards_list = [{
            "id": a.id,
            "award_key": a.award_key,
            "title": a.title,
            "description": a.description,
            "created_at": a.created_at.isoformat() if a.created_at else None
        } for a in awards]

    calculated_total = round(sum(h["total"] for h in history), 1)
    return {"total_points": calculated_total, "history": history, "awards": awards_list}


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
            "team_name": peer.team_name, "seat_id": peer.seat_id,
            "avatar_url": peer.avatar_url, "avatar_shape": peer.avatar_shape,
            "is_online": peer.is_online
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
        "sender_name": user.username,
        "receiver_id": peer_id,
        "message_id": msg.id,
        "preview": content[:100]
    })

    return {
        "status": "sent", "id": msg.id,
        "created_at": msg.created_at.isoformat() if msg.created_at else None
    }


# --- Group Messaging (AXE-12) ---

def _make_channel_key(channel_type: str, team_names: list) -> str:
    """Build deterministic channel key from type and team names."""
    if channel_type == "team":
        return f"team:{team_names[0]}"
    else:
        sorted_names = sorted(team_names)
        return f"inter:{sorted_names[0]}|{sorted_names[1]}"


def _user_can_access_channel(user: models.User, channel: models.GroupChannel) -> bool:
    """Check if user's team_name is in the channel's team_names."""
    if user.is_admin:
        return True
    if not user.team_name:
        return False
    return user.team_name in (channel.team_names or [])


def _get_or_create_channel(db: Session, channel_type: str, team_names: list) -> models.GroupChannel:
    """Get existing channel or create one."""
    key = _make_channel_key(channel_type, team_names)
    channel = db.query(models.GroupChannel).filter(models.GroupChannel.channel_key == key).first()
    if not channel:
        channel = models.GroupChannel(
            channel_key=key,
            channel_type=channel_type,
            team_names=sorted(team_names) if channel_type == "inter" else team_names
        )
        db.add(channel)
        db.commit()
        db.refresh(channel)
    return channel


@router.get("/group/unread-count")
def group_unread_count(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Total unread group messages across all accessible channels."""
    if not user.team_name:
        return {"count": 0}

    # Find all channels the user can access
    channels = db.query(models.GroupChannel).all()
    accessible = [c for c in channels if _user_can_access_channel(user, c)]

    total = 0
    for ch in accessible:
        read_record = db.query(models.GroupMessageRead).filter(
            models.GroupMessageRead.channel_id == ch.id,
            models.GroupMessageRead.user_id == user.id
        ).first()
        last_read = read_record.last_read_message_id if read_record else 0
        unread = db.query(models.GroupMessage).filter(
            models.GroupMessage.channel_id == ch.id,
            models.GroupMessage.id > last_read,
            models.GroupMessage.sender_id != user.id
        ).count()
        total += unread
    return {"count": total}


@router.get("/group/channels")
def group_channels(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """List group channels accessible to user with unread counts & last message."""
    if not user.team_name:
        return []

    channels = db.query(models.GroupChannel).all()
    result = []

    for ch in channels:
        if not _user_can_access_channel(user, ch):
            continue

        read_record = db.query(models.GroupMessageRead).filter(
            models.GroupMessageRead.channel_id == ch.id,
            models.GroupMessageRead.user_id == user.id
        ).first()
        last_read = read_record.last_read_message_id if read_record else 0

        unread = db.query(models.GroupMessage).filter(
            models.GroupMessage.channel_id == ch.id,
            models.GroupMessage.id > last_read,
            models.GroupMessage.sender_id != user.id
        ).count()

        last_msg = db.query(models.GroupMessage).filter(
            models.GroupMessage.channel_id == ch.id
        ).order_by(models.GroupMessage.created_at.desc()).first()

        last_sender = None
        if last_msg:
            sender = db.query(models.User).filter(models.User.id == last_msg.sender_id).first()
            last_sender = sender.username if sender else "?"

        # Count members currently in this channel
        member_count = 0
        for tn in (ch.team_names or []):
            member_count += db.query(models.User).filter(models.User.team_name == tn).count()

        result.append({
            "channel_key": ch.channel_key,
            "channel_type": ch.channel_type,
            "team_names": ch.team_names or [],
            "member_count": member_count,
            "unread": unread,
            "last_message": last_msg.content[:100] if last_msg else None,
            "last_sender": last_sender,
            "last_at": last_msg.created_at.isoformat() if last_msg and last_msg.created_at else None
        })

    # Sort by most recent message
    result.sort(key=lambda x: x["last_at"] or "", reverse=True)
    return result


class GroupSendMessage(BaseModel):
    content: str
    channel_type: str  # "team" or "inter"
    team_names: list   # ["Alpha Wolves"] or ["Alpha Wolves", "Neon Vipers"]


@router.get("/group/channel/{channel_key:path}")
def group_read(channel_key: str, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Read messages from a group channel. Auto-marks as read."""
    channel = db.query(models.GroupChannel).filter(models.GroupChannel.channel_key == channel_key).first()
    if not channel:
        return {"channel": None, "messages": [], "members": []}

    if not _user_can_access_channel(user, channel):
        raise HTTPException(403, "Access denied to this channel")

    # Mark as read
    last_msg = db.query(models.GroupMessage).filter(
        models.GroupMessage.channel_id == channel.id
    ).order_by(models.GroupMessage.id.desc()).first()

    if last_msg:
        read_record = db.query(models.GroupMessageRead).filter(
            models.GroupMessageRead.channel_id == channel.id,
            models.GroupMessageRead.user_id == user.id
        ).first()
        if read_record:
            read_record.last_read_message_id = last_msg.id
        else:
            db.add(models.GroupMessageRead(
                channel_id=channel.id, user_id=user.id,
                last_read_message_id=last_msg.id
            ))
        db.commit()

    # Fetch messages
    messages = db.query(models.GroupMessage).filter(
        models.GroupMessage.channel_id == channel.id
    ).order_by(models.GroupMessage.created_at.asc()).all()

    # Resolve sender names
    sender_ids = list(set(m.sender_id for m in messages))
    users_map = {}
    if sender_ids:
        senders = db.query(models.User).filter(models.User.id.in_(sender_ids)).all()
        users_map = {u.id: u.username for u in senders}

    # Get channel members
    members = []
    for tn in (channel.team_names or []):
        team_users = db.query(models.User).filter(models.User.team_name == tn).all()
        for u in team_users:
            members.append({"id": u.id, "username": u.username, "team_name": u.team_name})

    return {
        "channel": {
            "channel_key": channel.channel_key,
            "channel_type": channel.channel_type,
            "team_names": channel.team_names or []
        },
        "messages": [{
            "id": m.id, "sender_id": m.sender_id,
            "sender_name": users_map.get(m.sender_id, "?"),
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None
        } for m in messages],
        "members": members
    }


@router.post("/group/send")
async def group_send(body: GroupSendMessage, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Send a message to a group channel (creates channel if needed)."""
    if not user.team_name and not user.is_admin:
        raise HTTPException(400, "You must have a team to use group chat")

    if body.channel_type not in ("team", "inter"):
        raise HTTPException(400, "Invalid channel_type")

    if body.channel_type == "team":
        if len(body.team_names) != 1:
            raise HTTPException(400, "Team channel requires exactly 1 team name")
        if user.team_name != body.team_names[0] and not user.is_admin:
            raise HTTPException(403, "Cannot access another team's private channel")
    elif body.channel_type == "inter":
        if len(body.team_names) != 2:
            raise HTTPException(400, "Inter channel requires exactly 2 team names")
        if user.team_name not in body.team_names and not user.is_admin:
            raise HTTPException(403, "You must be a member of one of the teams")

    content = (body.content or "").strip()
    if not content:
        raise HTTPException(400, "Message cannot be empty")
    if len(content) > 2000:
        raise HTTPException(400, "Message too long (max 2000 chars)")

    channel = _get_or_create_channel(db, body.channel_type, body.team_names)

    msg = models.GroupMessage(
        channel_id=channel.id, sender_id=user.id, content=content
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Auto-mark as read for sender
    read_record = db.query(models.GroupMessageRead).filter(
        models.GroupMessageRead.channel_id == channel.id,
        models.GroupMessageRead.user_id == user.id
    ).first()
    if read_record:
        read_record.last_read_message_id = msg.id
    else:
        db.add(models.GroupMessageRead(
            channel_id=channel.id, user_id=user.id,
            last_read_message_id=msg.id
        ))
    db.commit()

    # WebSocket broadcast
    await ws_manager.broadcast({
        "type": "group_message_new",
        "channel_key": channel.channel_key,
        "channel_type": channel.channel_type,
        "team_names": channel.team_names or [],
        "sender_id": user.id,
        "sender_name": user.username,
        "message_id": msg.id,
        "preview": content[:100]
    })

    return {
        "status": "sent", "id": msg.id,
        "channel_key": channel.channel_key,
        "created_at": msg.created_at.isoformat() if msg.created_at else None
    }

