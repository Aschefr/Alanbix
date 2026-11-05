"""Stats-driven awards: computing who wins what, editing the texts, sending them to players."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .. import models, auth, database
from ..websockets import manager as ws_manager
from ..visibility import visible_tournaments

router = APIRouter(tags=["Awards"])


def get_i18n_dict(lang: str) -> dict:
    lang = "en" if lang == "en" else "fr"
    try:
        from .i18n import load_i18n_merged
        return load_i18n_merged(lang) or {}
    except Exception as e:
        print(f"Failed to load i18n dict for {lang}: {e}")
        return {}

# Metadata mapping for all 12 stats-driven awards with translation keys and defaults
AWARD_METADATA = {
    "premier": {
        "crit_key": "award_crit_premier",
        "title_key": "award_title_premier",
        "desc_key": "award_desc_premier",
        "criteria": "Premier du classement général individuel de la LAN.",
        "default_title": "Roi de la LAN",
        "default_description": "Félicitations pour avoir dominé le tournoi avec un total impressionnant de {points} points !"
    },
    "team": {
        "crit_key": "award_crit_team",
        "title_key": "award_title_team",
        "desc_key": "award_desc_team",
        "criteria": "Membres de l'équipe ayant accumulé le plus de points.",
        "default_title": "L'Union fait la Force",
        "default_description": "L'équipe {team_name} a écrasé la compétition en cumulant {points} points au total !"
    },
    "bourreau": {
        "crit_key": "award_crit_bourreau",
        "title_key": "award_title_bourreau",
        "desc_key": "award_desc_bourreau",
        "criteria": "Joueur ayant infligé le plus de défaites en solo (1v1).",
        "default_title": "Le Bourreau des Brackets",
        "default_description": "Pour avoir accumulé le plus grand nombre de victoires en solo ({wins} victoires)."
    },
    "coop": {
        "crit_key": "award_crit_coop",
        "title_key": "award_title_coop",
        "desc_key": "award_desc_coop",
        "criteria": "Joueur gagnant en équipe mais très discret en solo.",
        "default_title": "Le Roi du Coop",
        "default_description": "Un joueur d'équipe exceptionnel ! Gagnant en équipe ({team_wins} victoires) mais très discret en solo ({solo_wins} victoires)."
    },
    "loup": {
        "crit_key": "award_crit_loup",
        "title_key": "award_title_loup",
        "desc_key": "award_desc_loup",
        "criteria": "Joueur redoutable en solo mais n'ayant pas gagné en équipe.",
        "default_title": "Le Loup Solitaire",
        "default_description": "Redoutable en solo avec {solo_wins} victoires, mais n'a pas trouvé ses marques en équipe (0 victoire)."
    },
    "participate": {
        "crit_key": "award_crit_participate",
        "title_key": "award_title_participate",
        "desc_key": "award_desc_participate",
        "criteria": "Joueur ayant disputé au moins 2 matchs avec le taux de victoire le plus bas.",
        "default_title": "L'Important c'est de Participer",
        "default_description": "Pour son esprit sportif inébranlable et sa persévérance à travers {matches_played} matchs disputés !"
    },
    "marathon": {
        "crit_key": "award_crit_marathon",
        "title_key": "award_title_marathon",
        "desc_key": "award_desc_marathon",
        "criteria": "Joueur infatigable ayant disputé le plus de matchs dans toute la LAN.",
        "default_title": "Le Marathonien",
        "default_description": "Le joueur infatigable de la LAN avec un record absolu de {matches_played} matchs joués !"
    },
    "gachette": {
        "crit_key": "award_crit_gachette",
        "title_key": "award_title_gachette",
        "desc_key": "award_desc_gachette",
        "criteria": "Joueur ayant réalisé le score maximal le plus élevé en une seule partie.",
        "default_title": "La Gâchette Facile",
        "default_description": "Pour avoir réalisé le carton de la LAN avec un score maximal de {highest_score} points en une seule partie !"
    },
    "passoire": {
        "crit_key": "award_crit_passoire",
        "title_key": "award_title_passoire",
        "desc_key": "award_desc_passoire",
        "criteria": "Joueur ayant encaissé le plus de points/buts au total.",
        "default_title": "La Passoire de la LAN",
        "default_description": "Une défense très généreuse... {total_score_conceded} buts/points encaissés au total !"
    },
    "bye": {
        "crit_key": "award_crit_bye",
        "title_key": "award_title_bye",
        "desc_key": "award_desc_bye",
        "criteria": "Joueur ayant bénéficié du plus grand nombre de BYE.",
        "default_title": "Le Chouchou des BYE",
        "default_description": "Le grand favori du destin qui a bénéficié de {bye_count} qualifications automatiques par BYE !"
    },
    "suisse": {
        "crit_key": "award_crit_suisse",
        "title_key": "award_title_suisse",
        "desc_key": "award_desc_suisse",
        "criteria": "Joueur ayant réalisé le plus grand nombre de matchs nuls.",
        "default_title": "Le Suisse",
        "default_description": "Neutre et pacifique, spécialiste incontesté du partage des points avec {draws} égalités."
    },
    "lb": {
        "crit_key": "award_crit_lb",
        "title_key": "award_title_lb",
        "desc_key": "award_desc_lb",
        "criteria": "Joueur ayant joué le plus de matchs dans le Loser Bracket.",
        "default_title": "Le Survivant du LB",
        "default_description": "Celui qui a pris le chemin le plus long et le plus difficile en disputant {lb_matches} matchs dans le Loser Bracket !"
    }
}

class AwardTextUpdate(BaseModel):
    title: str
    description: str

def _compute_awards_suggestions(db: Session, lang: str = "fr") -> dict:
    users = db.query(models.User).all()
    user_map = {u.id: u for u in users}
    i18n = get_i18n_dict(lang)

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
    tournaments = visible_tournaments(db).filter(
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
        "title": i18n.get("award_title_premier", "🏆 Roi de la LAN"),
        "description": i18n.get("award_desc_premier", "Félicitations pour avoir dominé le tournoi avec un total impressionnant de {points} points !"),
        "stats_label": i18n.get("stats_points", "{count} points").format(count=premier.points if premier else 0)
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
        "username": i18n.get("members_of", "Membres de {team_name}").format(team_name=best_team_name) if best_team_name else None,
        "team_name": best_team_name,
        "points": best_team[1] if best_team else 0,
        "title": i18n.get("award_title_team", "🛡️ L'Union fait la Force"),
        "description": i18n.get("award_desc_team", "L'équipe {team_name} a écrasé la compétition en cumulant {points} points au total !"),
        "stats_label": i18n.get("stats_team", "Équipe {team_name} ({count} pts)").format(team_name=best_team_name, count=best_team[1] if best_team else 0)
    } if best_team and best_team[1] > 0 else None

    # 3. Le Bourreau des Brackets (Most solo wins)
    most_solo_wins_uid = max(stats.keys(), key=lambda uid: stats[uid]["solo_wins"], default=None)
    most_solo_wins = stats[most_solo_wins_uid] if most_solo_wins_uid and stats[most_solo_wins_uid]["solo_wins"] > 0 else None
    bourreau_suggestion = {
        "user_ids": [most_solo_wins["user_id"]] if most_solo_wins else [],
        "username": most_solo_wins["username"] if most_solo_wins else None,
        "wins": most_solo_wins["solo_wins"] if most_solo_wins else 0,
        "title": i18n.get("award_title_bourreau", "⚔️ Le Bourreau des Brackets"),
        "description": i18n.get("award_desc_bourreau", "Pour avoir accumulé le plus grand nombre de victoires en solo ({wins} victoires)."),
        "stats_label": i18n.get("stats_wins", "{count} victoires").format(count=most_solo_wins["solo_wins"] if most_solo_wins else 0)
    } if most_solo_wins else None

    # 4. Le Roi du Coop
    coop_players = [stats[uid] for uid in stats if stats[uid]["team_wins"] >= 2 and stats[uid]["solo_wins"] <= 1]
    roi_coop = max(coop_players, key=lambda s: s["team_wins"], default=None)
    coop_suggestion = {
        "user_ids": [roi_coop["user_id"]] if roi_coop else [],
        "username": roi_coop["username"] if roi_coop else None,
        "team_wins": roi_coop["team_wins"] if roi_coop else 0,
        "solo_wins": roi_coop["solo_wins"] if roi_coop else 0,
        "title": i18n.get("award_title_coop", "🤝 Le Roi du Coop"),
        "description": i18n.get("award_desc_coop", "Un joueur d'équipe exceptionnel ! Gagnant en équipe ({team_wins} victoires) mais très discret en solo ({solo_wins} victoires)."),
        "stats_label": i18n.get("stats_team_wins", "{count} victoires en équipe").format(count=roi_coop["team_wins"] if roi_coop else 0)
    } if roi_coop else None

    # 5. Le Loup Solitaire
    solitary_players = [stats[uid] for uid in stats if stats[uid]["solo_wins"] >= 2 and stats[uid]["team_wins"] == 0]
    loup_solitaire = max(solitary_players, key=lambda s: s["solo_wins"], default=None)
    loup_suggestion = {
        "user_ids": [loup_solitaire["user_id"]] if loup_solitaire else [],
        "username": loup_solitaire["username"] if loup_solitaire else None,
        "solo_wins": loup_solitaire["solo_wins"] if loup_solitaire else 0,
        "title": i18n.get("award_title_loup", "🐺 Le Loup Solitaire"),
        "description": i18n.get("award_desc_loup", "Redoutable en solo avec {solo_wins} victoires, mais n'a pas trouvé ses marques en équipe (0 victoire)."),
        "stats_label": i18n.get("stats_solo_wins", "{count} victoires solo").format(count=loup_solitaire["solo_wins"] if loup_solitaire else 0)
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
        "title": i18n.get("award_title_participate", "🕊️ L'Important c'est de Participer"),
        "description": i18n.get("award_desc_participate", "Pour son esprit sportif inébranlable et sa persévérance à travers {matches_played} matchs disputés !"),
        "stats_label": i18n.get("stats_participate", "{rate}% de victoires ({count} matchs)").format(
            rate=round(participate_player['win_rate'] * 100) if participate_player else 0,
            count=participate_player['matches_played'] if participate_player else 0
        )
    } if participate_player else None

    # 7. Le Marathonien
    marathonien = max(stats.values(), key=lambda s: s["matches_played"], default=None)
    marathon_suggestion = {
        "user_ids": [marathonien["user_id"]] if marathonien else [],
        "username": marathonien["username"] if marathonien else None,
        "matches_played": marathonien["matches_played"] if marathonien else 0,
        "title": i18n.get("award_title_marathon", "🏃 Le Marathonien"),
        "description": i18n.get("award_desc_marathon", "Le joueur infatigable de la LAN avec un record absolu de {matches_played} matchs joués !"),
        "stats_label": i18n.get("stats_matches_played", "{count} matchs joués").format(count=marathonien["matches_played"] if marathonien else 0)
    } if marathonien and marathonien["matches_played"] > 0 else None

    # 8. La Gâchette Facile
    gachette = max(stats.values(), key=lambda s: s["highest_score"], default=None)
    gachette_suggestion = {
        "user_ids": [gachette["user_id"]] if gachette else [],
        "username": gachette["username"] if gachette else None,
        "highest_score": gachette["highest_score"] if gachette else 0,
        "title": i18n.get("award_title_gachette", "🎯 La Gâchette Facile"),
        "description": i18n.get("award_desc_gachette", "Pour avoir réalisé le carton de la LAN avec un score maximal de {highest_score} points en une seule partie !"),
        "stats_label": i18n.get("stats_max_score", "Score max de {count}").format(count=gachette["highest_score"] if gachette else 0)
    } if gachette and gachette["highest_score"] > 0 else None

    # 9. La Passoire de la LAN
    passoire = max(stats.values(), key=lambda s: s["total_score_conceded"], default=None)
    passoire_suggestion = {
        "user_ids": [passoire["user_id"]] if passoire else [],
        "username": passoire["username"] if passoire else None,
        "total_score_conceded": passoire["total_score_conceded"] if passoire else 0,
        "title": i18n.get("award_title_passoire", "🥅 La Passoire de la LAN"),
        "description": i18n.get("award_desc_passoire", "Une défense très généreuse... {total_score_conceded} buts/points encaissés au total !"),
        "stats_label": i18n.get("stats_conceded", "{count} buts/points encaissés").format(count=passoire["total_score_conceded"] if passoire else 0)
    } if passoire and passoire["total_score_conceded"] > 0 else None

    # 10. Le Chouchou des BYE
    bye_player = max(stats.values(), key=lambda s: s["bye_count"], default=None)
    bye_suggestion = {
        "user_ids": [bye_player["user_id"]] if bye_player else [],
        "username": bye_player["username"] if bye_player else None,
        "bye_count": bye_player["bye_count"] if bye_player else 0,
        "title": i18n.get("award_title_bye", "🍀 Le Chouchou des BYE"),
        "description": i18n.get("award_desc_bye", "Le grand favori du destin qui a bénéficié de {bye_count} qualifications automatiques par BYE !"),
        "stats_label": i18n.get("stats_byes", "{count} BYE reçus").format(count=bye_player["bye_count"] if bye_player else 0)
    } if bye_player and bye_player["bye_count"] > 0 else None

    # 11. Le Suisse
    suisse = max(stats.values(), key=lambda s: s["draws"], default=None)
    suisse_suggestion = {
        "user_ids": [suisse["user_id"]] if suisse else [],
        "username": suisse["username"] if suisse else None,
        "draws": suisse["draws"] if suisse else 0,
        "title": i18n.get("award_title_suisse", "🇨🇭 Le Suisse"),
        "description": i18n.get("award_desc_suisse", "Neutre et pacifique, spécialiste incontesté du partage des points avec {draws} égalités."),
        "stats_label": i18n.get("stats_draws", "{count} égalités").format(count=suisse["draws"] if suisse else 0)
    } if suisse and suisse["draws"] > 0 else None

    # 12. Le Survivant du LB
    lb_survivor = max(stats.values(), key=lambda s: s["lb_matches_played"], default=None)
    lb_suggestion = {
        "user_ids": [lb_survivor["user_id"]] if lb_survivor else [],
        "username": lb_survivor["username"] if lb_survivor else None,
        "lb_matches": lb_survivor["lb_matches_played"] if lb_survivor else 0,
        "title": i18n.get("award_title_lb", "🩹 Le Survivant du LB"),
        "description": i18n.get("award_desc_lb", "Celui qui a pris le chemin le plus long et le plus difficile en disputant {lb_matches} matchs dans le Loser Bracket !"),
        "stats_label": i18n.get("stats_lb_matches", "{count} matchs LB").format(count=lb_survivor["lb_matches_played"] if lb_survivor else 0)
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

async def sync_automatic_awards(db: Session, lang: str = None):
    """Synchronize stats-driven automatic awards with user assignments and handle notifications."""
    if lang is None:
        config_lang = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
        lang = config_lang.value if config_lang else "fr"
        
    i18n = get_i18n_dict(lang)
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
        
        default_title = i18n.get(meta["title_key"], meta["default_title"])
        default_description = i18n.get(meta["desc_key"], meta["default_description"])
        
        title = custom_title or default_title
        description = custom_desc or default_description
        
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
            db.commit()
        else:
            # Only update title/description texts if changed
            for a in existing_awards:
                if a.title != title or a.description != description:
                    a.title = title
                    a.description = description
            db.commit()

@router.get("/admin/awards")
async def admin_list_awards(lang: str = "fr", db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """List all categories of awards with statistics, recipient details, and editable templates."""
    # Ensure database is up to date before serving (uses system default language for database sync)
    config_lang = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    db_lang = config_lang.value if config_lang else "fr"
    await sync_automatic_awards(db, db_lang)
    
    suggestions = _compute_awards_suggestions(db, lang)
    i18n = get_i18n_dict(lang)
    
    results = []
    for category, meta in AWARD_METADATA.items():
        # Get translated default texts
        default_title = i18n.get(meta["title_key"], meta["default_title"])
        default_description = i18n.get(meta["desc_key"], meta["default_description"])
        criteria = i18n.get(meta["crit_key"], meta["criteria"])
        
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
            "criteria": criteria,
            "default_title": default_title,
            "default_description": default_description,
            "title": custom_title or default_title,
            "description": custom_desc or default_description,
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
    await sync_automatic_awards(db)
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
    await sync_automatic_awards(db)
    db.commit()
    
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "restored", "key": category_key}

@router.delete("/admin/nuke/awards")
async def admin_nuke_awards(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete all custom configurations and assigned awards, resetting everything to defaults."""
    db.query(models.Award).delete()
    db.query(models.SystemConfig).filter(models.SystemConfig.key.like("award_text_%")).delete()
    db.query(models.SystemConfig).filter(models.SystemConfig.key == "awards_diffused").delete()
    db.commit()
    
    # Re-sync back to default awards
    await sync_automatic_awards(db)
    db.commit()
    
    await ws_manager.broadcast({"type": "users_updated"})
    return {"status": "nuked"}

@router.post("/admin/awards/notify")
async def admin_notify_awards(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Send notifications to all players who have been awarded a prize."""
    # Set awards_diffused to True
    config_row = db.query(models.SystemConfig).filter(models.SystemConfig.key == "awards_diffused").first()
    if config_row:
        config_row.value = True
    else:
        config_row = models.SystemConfig(key="awards_diffused", value=True)
        db.add(config_row)
    db.commit()

    config_lang = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    db_lang = config_lang.value if config_lang else "fr"
    i18n = get_i18n_dict(db_lang)
    notif_title_tpl = i18n.get("notifs_award_title", "🏆 Prix obtenu : {title}")

    awards = db.query(models.Award).all()
    notified_users = set()
    
    for a in awards:
        # Check if notification already exists to avoid duplicates
        title = notif_title_tpl.format(title=a.title)
        existing = db.query(models.Notification).filter(
            models.Notification.user_id == a.user_id,
            models.Notification.type == "award",
            models.Notification.title == title
        ).first()
        
        if not existing:
            notif = models.Notification(
                user_id=a.user_id,
                type="award",
                title=title,
                content=a.description
            )
            db.add(notif)
            notified_users.add(a.user_id)
            
    db.commit()
    
    # Broadcast via WebSockets
    for uid in notified_users:
        await ws_manager.broadcast({"type": "notification_new", "user_id": uid})
        
    return {"status": "success", "notified_players_count": len(notified_users)}

