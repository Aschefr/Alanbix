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
    },
    {
        "type": "function",
        "function": {
            "name": "ping_host",
            "description": "Effectuer un ping ICMP réel vers une machine (IP ou nom de domaine) pour mesurer la latence et la perte de paquets. Utilise cette fonction quand l'utilisateur te demande de pinguer un hôte, de tester la latence, de faire un diagnostic réseau, ou de vérifier si une machine répond.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "L'adresse IP ou le nom de domaine à pinguer (ex: 8.8.8.8, google.com)"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Le nombre de paquets ICMP à envoyer (optionnel, défaut: 4, max: 10)",
                        "minimum": 1,
                        "maximum": 10
                    }
                },
                "required": ["host"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "traceroute_host",
            "description": "Effectuer un traceroute réel vers une machine (IP ou nom de domaine) pour visualiser les sauts réseau (hops) et localiser d'éventuels ralentissements. Utilise cette fonction quand l'utilisateur demande un diagnostic réseau approfondi ou de retracer le chemin vers un hôte.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "L'adresse IP ou le nom de domaine cible"
                    }
                },
                "required": ["host"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dns_lookup",
            "description": "Effectuer une résolution DNS réelle (lookup/nslookup) sur un nom de domaine pour vérifier son adresse IP associée. Utilise cette fonction quand l'utilisateur demande l'adresse IP d'un domaine ou des infos de résolution DNS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Le nom de domaine à résoudre (ex: google.com)"
                    }
                },
                "required": ["domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_server_health",
            "description": "Vérifier la santé du serveur (charge CPU, utilisation de la mémoire RAM, et espace disque restant). Utilise cette fonction quand l'utilisateur demande si le serveur va bien, quelle est la charge machine, ou les ressources disponibles.",
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
            "name": "scan_local_network",
            "description": "Scanner le réseau local (table ARP) pour détecter et lister les hôtes/adresses IP et MAC actuellement actifs sur la LAN. Utilise cette fonction quand l'utilisateur demande de scanner le réseau local ou de voir les machines connectées.",
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
            "name": "get_game_rules",
            "description": "Obtenir les règles COMPLÈTES non tronquées et la configuration d'un jeu spécifique de la LAN. Utilise cette fonction quand l'utilisateur demande les détails précis, les notes, ou les règles complètes d'un jeu particulier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_name": {
                        "type": "string",
                        "description": "Le nom du jeu à rechercher (ex: Trackmania, Counter-Strike)"
                    }
                },
                "required": ["game_name"]
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
    from .database import SessionLocal
    from . import models

    with SessionLocal() as db:
        # Check if it's a network tool and network tools are disabled
        network_tool_names = {"ping_host", "traceroute_host", "dns_lookup", "check_server_health", "scan_local_network"}
        if name in network_tool_names:
            from .routers.ia import get_effective_config
            ia_cfg = get_effective_config(db)
            if not ia_cfg.get("network_tools_enabled", True):
                return json.dumps({"error": f"L'outil '{name}' est désactivé par l'administrateur dans les paramètres de l'IA."})

        if name == "get_current_datetime":
            return _tool_get_current_datetime(arguments)
        elif name == "get_tournaments":
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
        elif name == "ping_host":
            return _tool_ping_host(arguments)
        elif name == "traceroute_host":
            return _tool_traceroute_host(arguments)
        elif name == "dns_lookup":
            return _tool_dns_lookup(arguments)
        elif name == "check_server_health":
            return _tool_check_server_health()
        elif name == "scan_local_network":
            return _tool_scan_local_network()
        elif name == "get_game_rules":
            return _tool_get_game_rules(db, models, arguments)
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
# Helpers & Network Diagnostics
# ---------------------------------------------------------------------------
import re

def _sanitize_host(host: str) -> bool:
    """Return True if host is a valid IPv4, IPv6, or domain name without injection characters."""
    if not host or not isinstance(host, str):
        return False
    # Only allow characters standard for domain names or IP addresses
    # (letters, numbers, dots, hyphens)
    return bool(re.match(r"^[a-zA-Z0-9.-]+$", host))


def _tool_ping_host(args: dict) -> str:
    import subprocess
    host = args.get("host", "").strip()
    if not _sanitize_host(host):
        return json.dumps({"error": f"Nom d'hôte ou IP invalide: '{host}'."}, ensure_ascii=False)
    
    count = args.get("count", 4)
    try:
        count = int(count)
        if count < 1: count = 1
        if count > 10: count = 10
    except:
        count = 4
        
    try:
        res = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", host],
            capture_output=True, text=True, timeout=15
        )
        return json.dumps({
            "host": host,
            "success": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Le test de ping a expiré (timeout)."}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Erreur lors du ping: {str(e)}"}, ensure_ascii=False)


def _tool_traceroute_host(args: dict) -> str:
    import subprocess
    host = args.get("host", "").strip()
    if not _sanitize_host(host):
        return json.dumps({"error": f"Nom d'hôte ou IP invalide: '{host}'."}, ensure_ascii=False)
        
    try:
        res = subprocess.run(
            ["traceroute", "-m", "15", "-q", "1", host],
            capture_output=True, text=True, timeout=20
        )
        return json.dumps({
            "host": host,
            "stdout": res.stdout,
            "stderr": res.stderr
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Le traceroute a expiré."}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Erreur lors du traceroute: {str(e)}"}, ensure_ascii=False)


def _tool_dns_lookup(args: dict) -> str:
    import socket
    domain = args.get("domain", "").strip()
    if not _sanitize_host(domain):
        return json.dumps({"error": f"Nom de domaine invalide: '{domain}'."}, ensure_ascii=False)
        
    try:
        name, aliases, addresses = socket.gethostbyname_ex(domain)
        return json.dumps({
            "domain": domain,
            "canonical_name": name,
            "aliases": aliases,
            "ips": addresses
        }, ensure_ascii=False)
    except Exception as e:
        import subprocess
        try:
            res = subprocess.run(
                ["nslookup", domain],
                capture_output=True, text=True, timeout=5
            )
            return json.dumps({
                "domain": domain,
                "stdout": res.stdout,
                "stderr": res.stderr
            }, ensure_ascii=False)
        except Exception as shell_err:
            return json.dumps({"error": f"Impossible de résoudre le domaine: {str(e)} (nslookup err: {str(shell_err)})"}, ensure_ascii=False)


def _tool_check_server_health() -> str:
    import shutil
    import os
    
    health = {}
    
    # 1. CPU load average
    try:
        if os.path.exists("/proc/loadavg"):
            with open("/proc/loadavg", "r") as f:
                load = f.read().strip().split()
                if len(load) >= 3:
                    health["cpu_load_1m"] = float(load[0])
                    health["cpu_load_5m"] = float(load[1])
                    health["cpu_load_15m"] = float(load[2])
        else:
            loadavg = os.getloadavg()
            health["cpu_load_1m"] = loadavg[0]
            health["cpu_load_5m"] = loadavg[1]
            health["cpu_load_15m"] = loadavg[2]
    except Exception as e:
        health["cpu_load_error"] = str(e)
        
    # 2. Memory RAM Info
    try:
        if os.path.exists("/proc/meminfo"):
            mem_total = 0
            mem_free = 0
            mem_available = 0
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].replace(":", "")
                        val = int(parts[1])
                        if key == "MemTotal":
                            mem_total = val
                        elif key == "MemFree":
                            mem_free = val
                        elif key == "MemAvailable":
                            mem_available = val
            health["ram_total_mb"] = round(mem_total / 1024)
            health["ram_free_mb"] = round(mem_free / 1024)
            health["ram_available_mb"] = round(mem_available / 1024)
            health["ram_used_mb"] = round((mem_total - mem_available) / 1024) if mem_available else round((mem_total - mem_free) / 1024)
        else:
            health["ram_note"] = "Info de RAM non disponible via /proc/meminfo"
    except Exception as e:
        health["ram_error"] = str(e)
        
    # 3. Disk space
    try:
        total, used, free = shutil.disk_usage("/")
        health["disk_total_gb"] = round(total / (1024**3), 1)
        health["disk_used_gb"] = round(used / (1024**3), 1)
        health["disk_free_gb"] = round(free / (1024**3), 1)
        health["disk_use_percent"] = round((used / total) * 100, 1)
    except Exception as e:
        health["disk_error"] = str(e)
        
    return json.dumps(health, ensure_ascii=False)


def _tool_scan_local_network() -> str:
    import os
    hosts = []
    try:
        if os.path.exists("/proc/net/arp"):
            with open("/proc/net/arp", "r") as f:
                lines = f.readlines()
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 6:
                        ip = parts[0]
                        mac = parts[3]
                        device = parts[5]
                        if mac != "00:00:00:00:00:00":
                            hosts.append({
                                "ip": ip,
                                "mac": mac,
                                "interface": device
                            })
        else:
            import subprocess
            res = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
            for line in res.stdout.splitlines():
                if "at" in line:
                    parts = line.split()
                    try:
                        ip = parts[1].strip("()")
                        mac = parts[3]
                        hosts.append({"ip": ip, "mac": mac})
                    except:
                        pass
    except Exception as e:
        return json.dumps({"error": f"Erreur lors du scan réseau: {str(e)}"}, ensure_ascii=False)
        
    return json.dumps({
        "hosts": hosts,
        "count": len(hosts),
        "note": "Affiche les machines connectées découvertes dans la table ARP du serveur."
    }, ensure_ascii=False)


def _tool_get_game_rules(db, models, args: dict) -> str:
    game_name = args.get("game_name", "").strip()
    if not game_name:
        return json.dumps({"error": "Nom du jeu requis"}, ensure_ascii=False)
        
    game = db.query(models.Game).filter(models.Game.name.ilike(game_name)).first()
    if not game:
        game = db.query(models.Game).filter(models.Game.name.ilike(f"%{game_name}%")).first()
        
    if not game:
        return json.dumps({"error": f"Jeu '{game_name}' introuvable dans la bibliothèque"}, ensure_ascii=False)
        
    return json.dumps({
        "name": game.name,
        "rules": game.rules or "Aucune règle spécifique de configurée pour ce jeu.",
        "default_config": game.default_config or {}
    }, ensure_ascii=False)


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
