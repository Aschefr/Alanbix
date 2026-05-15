"""
IA Tool Calling — Live LAN data tools for Ollama.
Defines read-only tools that the AI can invoke to query tournament data,
scores, and leaderboard. Each tool returns compact JSON for the model.
"""
import json
import datetime
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Tool Definitions (Ollama JSON Schema format)
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_tournaments",
            "description": "Obtenir la liste des tournois de la LAN avec leur statut, jeu, type de bracket et nombre de participants. Utilise cette fonction quand l'utilisateur pose des questions sur les tournois en cours, prévus ou terminés.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filtrer par statut (optionnel). OPEN = inscriptions ouvertes, RUNNING = en cours, DONE = terminé en attente de clôture, CLOSED = clôturé avec résultats.",
                        "enum": ["OPEN", "RUNNING", "DONE", "CLOSED"]
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tournament_standings",
            "description": "Obtenir le classement d'un tournoi spécifique avec les scores, victoires et points par joueur/équipe. Utilise cette fonction quand l'utilisateur demande les résultats ou scores d'un tournoi précis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tournament_name": {
                        "type": "string",
                        "description": "Le nom (ou partie du nom) du tournoi à rechercher"
                    }
                },
                "required": ["tournament_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_leaderboard",
            "description": "Obtenir le classement général de la LAN (top joueurs et top équipes). Utilise cette fonction quand l'utilisateur demande qui est en tête, le classement global ou les scores généraux.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_info",
            "description": "Obtenir les informations d'un joueur : points, équipe, rang, participations aux tournois. Si aucun nom n'est donné, retourne les infos du joueur qui pose la question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Le pseudo du joueur à rechercher (optionnel — si vide, retourne les infos de l'utilisateur courant)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_matches",
            "description": "Obtenir les matchs en cours et à venir d'un joueur dans les tournois actifs. Utilise cette fonction quand l'utilisateur demande contre qui il joue, son prochain match ou ses résultats récents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Le pseudo du joueur (optionnel — si vide, utilise l'utilisateur courant)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_games",
            "description": "Obtenir la liste des jeux disponibles dans la bibliothèque de la LAN avec leurs règles. Utilise cette fonction quand l'utilisateur demande quels jeux sont disponibles ou les règles d'un jeu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Rechercher un jeu par nom (optionnel)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_info",
            "description": "Obtenir les informations générales de l'événement LAN : nom, contenu de la page d'informations (règles, planning, etc.). Utilise cette fonction quand l'utilisateur demande les règles générales, le planning ou des infos sur la LAN.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_notifications",
            "description": "Obtenir les dernières notifications du joueur (messages de tournoi, annonces système). Utilise cette fonction quand l'utilisateur demande ses notifications ou messages récents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "unread_only": {
                        "type": "boolean",
                        "description": "Si true, ne retourne que les notifications non lues (défaut: false)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Obtenir la date et l'heure actuelles. Utilise cette fonction quand l'utilisateur demande l'heure, la date ou le jour.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_seat",
            "description": "Obtenir la place assignée d'un joueur dans la salle (plan de salle). Le format est T{table}_S{siège}, par exemple T1_S1 = Table 1, Siège 1. Utilise cette fonction quand l'utilisateur demande où il est assis, où est un joueur, ou sa place dans la salle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Le pseudo du joueur (optionnel — si vide, utilise l'utilisateur courant)"
                    }
                },
                "required": []
            }
        }
    }
]


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------
def execute_tool(name: str, arguments: Dict[str, Any], user_id: int = 0) -> str:
    """Execute a tool by name with given arguments. Returns JSON string result.
    user_id is the ID of the user making the request (for personalized tools).
    """
    # Tools that don't need DB
    if name == "get_current_datetime":
        return _tool_get_current_datetime(arguments)

    from .database import SessionLocal
    from . import models

    with SessionLocal() as db:
        if name == "get_tournaments":
            return _tool_get_tournaments(db, models, arguments)
        elif name == "get_tournament_standings":
            return _tool_get_tournament_standings(db, models, arguments)
        elif name == "get_leaderboard":
            return _tool_get_leaderboard(db, models, arguments)
        elif name == "get_player_info":
            return _tool_get_player_info(db, models, arguments, user_id)
        elif name == "get_my_matches":
            return _tool_get_my_matches(db, models, arguments, user_id)
        elif name == "get_games":
            return _tool_get_games(db, models, arguments)
        elif name == "get_event_info":
            return _tool_get_event_info(db, models, arguments)
        elif name == "get_notifications":
            return _tool_get_notifications(db, models, arguments, user_id)
        elif name == "get_player_seat":
            return _tool_get_player_seat(db, models, arguments, user_id)
        else:
            return json.dumps({"error": f"Outil inconnu: {name}"})


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def _tool_get_tournaments(db, models, args: dict) -> str:
    """List tournaments with optional status filter."""
    query = db.query(models.Tournament)
    status = args.get("status")
    if status:
        query = query.filter(models.Tournament.status == status)

    tournaments = query.order_by(models.Tournament.id.desc()).all()
    result = []
    for t in tournaments[:20]:
        game = db.query(models.Game).filter(models.Game.id == t.game_id).first()
        participants = db.query(models.TournamentParticipant).filter(
            models.TournamentParticipant.tournament_id == t.id
        ).count()
        config = t.config or {}
        result.append({
            "id": t.id,
            "name": t.name,
            "game": game.name if game else "?",
            "status": t.status,
            "participants": participants,
            "bracket_type": config.get("bracket_type", "single_elim"),
            "use_teams": config.get("use_teams", False),
        })

    return json.dumps({
        "tournaments": result,
        "total": len(tournaments),
    }, ensure_ascii=False)


def _tool_get_tournament_standings(db, models, args: dict) -> str:
    """Get standings for a specific tournament by name search."""
    search = args.get("tournament_name", "").strip()
    if not search:
        return json.dumps({"error": "Nom du tournoi requis"})

    tournaments = db.query(models.Tournament).filter(
        models.Tournament.name.ilike(f"%{search}%")
    ).all()

    if not tournaments:
        return json.dumps({"error": f"Aucun tournoi trouvé pour '{search}'"})

    tournament = tournaments[0]
    config = tournament.config or {}
    use_teams = config.get("use_teams", False)

    if tournament.status == "CLOSED" and tournament.results:
        standings = []
        for r in tournament.results[:20]:
            entry = dict(r)
            name = _resolve_entity_name(db, models, entry.get("entity_id"), use_teams, tournament.id)
            standings.append({
                "rank": entry.get("rank", "?"),
                "name": name,
                "total_points": entry.get("total", 0),
                "wins": entry.get("wins", 0),
            })
        return json.dumps({"tournament": tournament.name, "status": "CLOSED", "standings": standings}, ensure_ascii=False)

    elif tournament.status in ("RUNNING", "DONE"):
        from .routers.tournaments import _compute_projected_standings
        standings_raw = _compute_projected_standings(tournament, db)
        standings = []
        for s in standings_raw[:20]:
            name = _resolve_entity_name(db, models, s.get("entity_id"), use_teams, tournament.id)
            standings.append({
                "rank": s.get("rank", "?"),
                "name": name,
                "total_points": s.get("total", 0),
                "wins": s.get("wins", 0),
            })
        return json.dumps({"tournament": tournament.name, "status": tournament.status, "standings": standings}, ensure_ascii=False)

    else:
        return json.dumps({
            "tournament": tournament.name, "status": tournament.status,
            "standings": [], "note": "Le tournoi est en phase d'inscription, pas encore de classement."
        }, ensure_ascii=False)


def _tool_get_leaderboard(db, models, args: dict) -> str:
    """Get overall LAN leaderboard (players + teams)."""
    from .routers.dashboard import get_stats, get_team_leaderboard

    stats = get_stats(db)
    player_lb = stats.get("leaderboard", [])[:10]

    team_lb_raw = get_team_leaderboard(db)
    team_lb = [{"team": t["team_name"], "score": t["score"], "members": t["member_count"]} for t in team_lb_raw[:10]]

    return json.dumps({
        "event_name": stats.get("event_name", "Alanbix LAN"),
        "player_leaderboard": player_lb,
        "team_leaderboard": team_lb,
        "total_players": stats.get("players", 0),
        "total_tournaments": stats.get("tournaments", 0),
        "active_tournaments": stats.get("active", 0),
    }, ensure_ascii=False)


def _tool_get_player_info(db, models, args: dict, user_id: int) -> str:
    """Get info about a specific player or the current user."""
    username = args.get("username", "").strip()

    if username:
        user = db.query(models.User).filter(models.User.username.ilike(username)).first()
        if not user:
            # Fuzzy search
            user = db.query(models.User).filter(models.User.username.ilike(f"%{username}%")).first()
        if not user:
            return json.dumps({"error": f"Joueur '{username}' introuvable"})
    else:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return json.dumps({"error": "Utilisateur courant introuvable"})

    # Participations
    participations = db.query(models.TournamentParticipant).filter(
        models.TournamentParticipant.user_id == user.id
    ).all()
    tournament_ids = [p.tournament_id for p in participations]
    tournament_names = []
    for tid in tournament_ids:
        t = db.query(models.Tournament).filter(models.Tournament.id == tid).first()
        if t:
            tournament_names.append({"name": t.name, "status": t.status})

    # Compute live points (DB + running tournaments)
    from .routers.dashboard import get_stats
    stats = get_stats(db)
    lb = stats.get("leaderboard", [])
    rank = None
    total_points = user.points or 0
    for i, entry in enumerate(lb):
        if entry["username"] == user.username:
            rank = i + 1
            total_points = entry["points"]
            break

    return json.dumps({
        "username": user.username,
        "team": user.team_name or "Aucune équipe",
        "total_points": total_points,
        "rank": rank or "Non classé",
        "is_admin": user.is_admin,
        "participations": len(tournament_names),
        "tournaments": tournament_names[:15],
    }, ensure_ascii=False)


def _tool_get_my_matches(db, models, args: dict, user_id: int) -> str:
    """Get a player's matches in running tournaments."""
    username = args.get("username", "").strip()

    if username:
        user = db.query(models.User).filter(models.User.username.ilike(f"%{username}%")).first()
        if not user:
            return json.dumps({"error": f"Joueur '{username}' introuvable"})
    else:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return json.dumps({"error": "Utilisateur courant introuvable"})

    # Find running/done tournaments where this user participates
    running = db.query(models.Tournament).filter(
        models.Tournament.status.in_(["RUNNING", "DONE"])
    ).all()

    all_matches = []
    for t in running:
        bracket = t.bracket or []
        config = t.config or {}
        use_teams = config.get("use_teams", False)

        # Find the entity_id for this user
        entity_ids = set()
        if use_teams:
            # Check team memberships
            teams = db.query(models.TournamentTeam).filter(
                models.TournamentTeam.tournament_id == t.id
            ).all()
            for team in teams:
                is_member = db.query(models.TournamentTeamMember).filter(
                    models.TournamentTeamMember.team_id == team.id,
                    models.TournamentTeamMember.user_id == user.id
                ).first()
                if is_member:
                    entity_ids.add(-team.id)
        else:
            entity_ids.add(user.id)

        if not entity_ids:
            continue

        for match in bracket:
            players = match.get("p", [])
            scores = match.get("score", [])
            mid = match.get("id", {})

            # Check if user is in this match
            user_in_match = any(pid in entity_ids for pid in players if pid)
            if not user_in_match:
                continue

            # Determine match status
            has_scores = len(scores) >= 2 and any(s > 0 for s in scores)
            opponent_ids = [pid for pid in players if pid and pid not in entity_ids and pid != 0]
            opponent_names = []
            for oid in opponent_ids:
                opponent_names.append(_resolve_entity_name(db, models, oid, use_teams, t.id))

            # Round label
            section = mid.get("s", 1)
            round_num = mid.get("r", 1)
            section_label = "WB" if section == 1 else "LB" if section == 2 else "GF"

            match_info = {
                "tournament": t.name,
                "round": f"{section_label} Round {round_num}",
                "opponent": ", ".join(opponent_names) if opponent_names else "À déterminer (BYE)",
                "scores": scores if has_scores else None,
                "status": "Terminé" if has_scores else "En attente" if 0 not in players else "À venir",
            }
            all_matches.append(match_info)

    # Sort: pending matches first, then completed
    pending = [m for m in all_matches if m["status"] != "Terminé"]
    completed = [m for m in all_matches if m["status"] == "Terminé"]

    return json.dumps({
        "player": user.username,
        "pending_matches": pending[:10],
        "completed_matches": completed[-5:],  # Last 5 completed
        "total_pending": len(pending),
        "total_completed": len(completed),
    }, ensure_ascii=False)


def _tool_get_games(db, models, args: dict) -> str:
    """List available games in the library."""
    query = db.query(models.Game)
    search = args.get("search", "").strip()
    if search:
        query = query.filter(models.Game.name.ilike(f"%{search}%"))

    games = query.order_by(models.Game.name).all()
    result = []
    for g in games[:30]:
        tournament_count = db.query(models.Tournament).filter(
            models.Tournament.game_id == g.id
        ).count()
        result.append({
            "name": g.name,
            "rules": (g.rules[:300] + "...") if g.rules and len(g.rules) > 300 else g.rules,
            "tournaments_count": tournament_count,
            "has_config": bool(g.default_config),
        })

    return json.dumps({
        "games": result,
        "total": len(games),
    }, ensure_ascii=False)


def _tool_get_event_info(db, models, args: dict) -> str:
    """Get general event information from the info page."""
    event_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "event_name").first()
    event_name = event_config.value if event_config else "Alanbix LAN"

    info_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "info_page_content").first()
    info_content = info_config.value if info_config else ""

    # Truncate if very long
    if info_content and len(info_content) > 2000:
        info_content = info_content[:2000] + "\n\n[... contenu tronqué]"

    # Stats
    players = db.query(models.User).count()
    tournaments = db.query(models.Tournament).count()
    active = db.query(models.Tournament).filter(models.Tournament.status == "RUNNING").count()

    return json.dumps({
        "event_name": event_name,
        "info_page": info_content or "Aucune information publiée.",
        "stats": {"players": players, "tournaments": tournaments, "active": active},
    }, ensure_ascii=False)


def _tool_get_notifications(db, models, args: dict, user_id: int) -> str:
    """Get the user's recent notifications."""
    query = db.query(models.Notification).filter(
        models.Notification.user_id == user_id
    )
    unread_only = args.get("unread_only", False)
    if unread_only:
        query = query.filter(models.Notification.is_read == False)

    notifications = query.order_by(models.Notification.created_at.desc()).limit(15).all()
    result = []
    for n in notifications:
        result.append({
            "title": n.title,
            "content": (n.content[:200] + "...") if n.content and len(n.content) > 200 else n.content,
            "type": n.type,
            "is_read": n.is_read,
            "date": n.created_at.strftime("%d/%m %H:%M") if n.created_at else "?",
        })

    unread_count = db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.is_read == False
    ).count()

    return json.dumps({
        "notifications": result,
        "unread_count": unread_count,
        "total_shown": len(result),
    }, ensure_ascii=False)


def _tool_get_current_datetime(args: dict) -> str:
    """Return the current date and time in local timezone (Europe/Paris)."""
    import zoneinfo
    tz = zoneinfo.ZoneInfo("Europe/Paris")
    now = datetime.datetime.now(tz)
    return json.dumps({
        "date": now.strftime("%A %d %B %Y"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "timezone": "Europe/Paris",
        "iso": now.isoformat(),
    }, ensure_ascii=False)


def _tool_get_player_seat(db, models, args: dict, user_id: int) -> str:
    """Get a player's seat assignment in the room."""
    username = args.get("username", "").strip()

    if username:
        user = db.query(models.User).filter(models.User.username.ilike(f"%{username}%")).first()
        if not user:
            return json.dumps({"error": f"Joueur '{username}' introuvable"})
    else:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return json.dumps({"error": "Utilisateur courant introuvable"})

    if not user.seat_id:
        return json.dumps({
            "player": user.username,
            "seat": None,
            "note": f"{user.username} n'a pas encore de place assignée dans la salle."
        }, ensure_ascii=False)

    # Parse seat_id format: T{table}_S{seat}
    seat_label = user.seat_id
    parts = seat_label.split("_")
    table_num = parts[0].replace("T", "Table ") if len(parts) >= 1 else "?"
    seat_num = parts[1].replace("S", "Siège ") if len(parts) >= 2 else "?"

    # Find neighbors at the same table
    table_prefix = parts[0] + "_" if len(parts) >= 1 else ""
    neighbors = []
    if table_prefix:
        table_users = db.query(models.User).filter(
            models.User.seat_id.like(f"{table_prefix}%"),
            models.User.id != user.id
        ).all()
        neighbors = [{"username": u.username, "seat": u.seat_id} for u in table_users]

    return json.dumps({
        "player": user.username,
        "seat_id": seat_label,
        "table": table_num,
        "seat": seat_num,
        "description": f"{user.username} est à {table_num}, {seat_num}",
        "neighbors": neighbors,
    }, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_entity_name(db, models, entity_id, use_teams: bool, tournament_id: int) -> str:
    """Resolve a player or team entity_id to a human-readable name."""
    if not entity_id:
        return "?"
    if use_teams and entity_id < 0:
        team = db.query(models.TournamentTeam).filter(
            models.TournamentTeam.id == abs(entity_id)
        ).first()
        return team.name if team else f"Équipe #{abs(entity_id)}"
    else:
        user = db.query(models.User).filter(models.User.id == entity_id).first()
        return user.username if user else f"Joueur #{entity_id}"
