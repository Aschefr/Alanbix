"""Notifications sent to players by tournaments."""
from sqlalchemy.orm import Session
from .. import models
from .awards import get_i18n_dict
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

    # Stored in the language of the LAN; the app shows it in each player's language
    config_lang = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    i18n = get_i18n_dict(config_lang.value if config_lang else "fr")
    opponent_fallback = i18n.get("notif_match_opponent_fallback", "Adversaire")
    title = f"⚔️ {i18n.get('notif_match_ready_title', 'Match prêt !')}"
    body_template = i18n.get("notif_match_ready_body", "Votre match contre {opponent} est prêt dans {tournament}.")

    def body(opponent: str) -> str:
        return body_template.replace("{opponent}", opponent).replace("{tournament}", tournament.name)

    # Resolve p0
    p0_name = opponent_fallback
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
    p1_name = opponent_fallback
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
            db, uid, "match_ready", title, body(p1_name),
            link=link,
            data={"tournament_id": tournament.id, "tournament_name": tournament.name, "opponent": p1_name, "match": match.get("id")}
        )
    for uid in p1_uids:
        await notify_user(
            db, uid, "match_ready", title, body(p0_name),
            link=link,
            data={"tournament_id": tournament.id, "tournament_name": tournament.name, "opponent": p0_name, "match": match.get("id")}
        )
