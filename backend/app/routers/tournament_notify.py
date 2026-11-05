"""Notifications sent to players by tournaments."""
from sqlalchemy.orm import Session
from .. import models
from .notifications import notify_user


async def _notify_match_ready(db: Session, tournament: models.Tournament, match: dict, use_teams: bool = False):
    """Notify players when both opponents in a match are known and the match is ready to be played."""
    if tournament.is_hidden:
        return
    p = match.get("p") or []
    if len(p) < 2:
        return
    p0, p1 = p[0], p[1]
    if not p0 or not p1 or p0 == 0 or p1 == 0:
        return

    score = match.get("score") or []
    if len(score) >= 2 and (score[0] or score[1]):
        return

    # Resolve p0
    p0_name = "Adversaire"
    p0_uids = []
    if use_teams and p0 < 0:
        team0 = db.query(models.TournamentTeam).filter(models.TournamentTeam.id == abs(p0)).first()
        if team0:
            p0_name = team0.name
            p0_uids = [m.user_id for m in db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == abs(p0)).all()]
    else:
        u0 = db.query(models.User).filter(models.User.id == p0).first()
        if u0:
            p0_name = u0.username
            p0_uids = [u0.id]

    # Resolve p1
    p1_name = "Adversaire"
    p1_uids = []
    if use_teams and p1 < 0:
        team1 = db.query(models.TournamentTeam).filter(models.TournamentTeam.id == abs(p1)).first()
        if team1:
            p1_name = team1.name
            p1_uids = [m.user_id for m in db.query(models.TournamentTeamMember).filter(models.TournamentTeamMember.team_id == abs(p1)).all()]
    else:
        u1 = db.query(models.User).filter(models.User.id == p1).first()
        if u1:
            p1_name = u1.username
            p1_uids = [u1.id]

    link = f"/dashboard/tournaments/{tournament.id}"
    for uid in p0_uids:
        await notify_user(
            db, uid, "match_ready", "⚔️ Match prêt !",
            f"Votre match contre {p1_name} est prêt dans {tournament.name}.",
            link=link,
            data={"tournament_id": tournament.id, "opponent": p1_name, "match": match.get("id")}
        )
    for uid in p1_uids:
        await notify_user(
            db, uid, "match_ready", "⚔️ Match prêt !",
            f"Votre match contre {p0_name} est prêt dans {tournament.name}.",
            link=link,
            data={"tournament_id": tournament.id, "opponent": p0_name, "match": match.get("id")}
        )
