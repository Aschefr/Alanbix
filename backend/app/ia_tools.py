"""
IA Tool Calling — Live LAN data tools for Ollama.
Defines read-only tools that the AI can invoke to query tournament data,
scores, and leaderboard. Each tool returns compact JSON for the model.
"""
import json
import datetime
import difflib
from typing import Any, Dict, Optional

from . import ia_network
from .visibility import visible_tournaments
from .clock import utcnow
from .ia_room import _seat_labeler, _tool_get_room_places


def _find_best_match(query: str, possibilities: list[str], cutoff: float = 0.55) -> Optional[str]:
    """Trouve la meilleure correspondance approximative (recherche floue).
    Retourne None si aucune correspondance acceptable n'est trouvée.
    """
    if not query or not possibilities:
        return None
        
    query_lower = query.lower()
    possibilities_map = {p.lower(): p for p in possibilities}
    
    # 1. Correspondance exacte ou insensible à la casse
    if query_lower in possibilities_map:
        return possibilities_map[query_lower]
        
    # 2. Correspondance de sous-chaîne (longueur min de 2 pour éviter les faux positifs)
    if len(query_lower) >= 2:
        for p_lower, p in possibilities_map.items():
            if query_lower in p_lower or p_lower in query_lower:
                return p
            
    # 3. Recherche floue (difflib)
    matches = difflib.get_close_matches(query, possibilities, n=1, cutoff=cutoff)
    if matches:
        return matches[0]
        
    # 4. Recherche floue insensible à la casse
    matches_lower = difflib.get_close_matches(query_lower, list(possibilities_map.keys()), n=1, cutoff=cutoff)
    if matches_lower:
        return possibilities_map[matches_lower[0]]
        
    return None

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
            "name": "get_room_places",
            "description": "Situer les éléments du plan de salle (borne Wi-Fi, toilettes, porte, bar, cuisine, écran, baie réseau…) : entre quelles tables ils sont, dans quelle direction depuis la place du joueur, et à quelle distance environ. Utilise-la quand le joueur demande où se trouve quelque chose dans la salle, ou pour un problème de Wi-Fi (trouver la borne la plus proche et des places libres à côté). Guide avec des repères et une direction, pas avec des chiffres.",
            "parameters": {
                "type": "object",
                "properties": {
                    "place": {
                        "type": "string",
                        "description": "Ce que cherche le joueur, dans ses mots (« wifi », « toilettes », « bar »…). Vide : tous les éléments du plan."
                    },
                    "free_seats": {
                        "type": "boolean",
                        "description": "true pour avoir aussi les places libres les plus proches de chaque élément (par exemple pour se rapprocher de la borne Wi-Fi)."
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
    },
    {
        "type": "function",
        "function": {
            "name": "block_user_from_ia",
            "description": "Block a player from the AI assistant (private assistant and @Alanbix in the public chat), at once. Without username: blocks the person writing to you right now; use it on your own only when they keep being rude, insulting, harassing or abusive after one warning. With username: blocks that player, and only works when the person writing to you is an administrator who asks for it. A player can never make you block someone else.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "The precise reason for the block (e.g. repeated insults, harassment, abusive requests)"
                    },
                    "username": {
                        "type": "string",
                        "description": "Only when an administrator asks you to block another player: that player's username. Leave empty to block the person writing to you."
                    },
                    "ban": {
                        "type": "boolean",
                        "description": "true when an administrator asks you to ban the player (\"ban\", \"bannis\"): also stops them writing in the public chat for 24 hours. Leave false for a plain block."
                    }
                },
                "required": ["reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mute_player_in_public_chat",
            "description": "Administrators only: stop a player from writing in the LAN's public chat for a number of minutes. Use it only when an administrator asks for it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "The player to mute"
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "How long, in minutes (default 15, at most 1440)"
                    }
                },
                "required": ["username"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_matches",
            "description": "Obtenir la liste de tous les matchs actuellement en cours ou prêts à être joués sur l'ensemble des tournois actifs (RUNNING). Utilise cette fonction quand l'utilisateur demande quels matchs se déroulent en ce moment, les affrontements en direct ou s'il y a du jeu sur un tournoi.",
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
            "name": "get_team_roster",
            "description": "Obtenir la composition complète d'une équipe (membres avec leur place dans la salle, points, participation aux tournois). Utilise cette fonction quand l'utilisateur pose des questions sur une équipe spécifique de la LAN, ses membres, où ils sont assis ou son score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team_name": {
                        "type": "string",
                        "description": "Le nom (ou partie du nom) de l'équipe à rechercher"
                    }
                },
                "required": ["team_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_match_history",
            "description": "Obtenir l'historique complet des matchs joués par un joueur spécifique, avec le score et le résultat (victoire/défaite). Si aucun pseudo n'est fourni, retourne l'historique du joueur qui pose la question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Le pseudo du joueur à rechercher (optionnel — si vide, utilise l'utilisateur courant)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_awards",
            "description": "Obtenir les distinctions, classements et trophées en cours de calcul pour l'ensemble des joueurs (ex: Marathonien, Bourreau, Passoire, Loup Solitaire). Utilise cette fonction quand l'utilisateur demande les leaders des trophées, qui est en tête pour un prix, ou des statistiques amusantes.",
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
            "name": "get_upcoming_matches",
            "description": "Obtenir la liste globale des prochains matchs programmés et prêts à être joués sur l'ensemble de la LAN. Utilise cette fonction quand l'utilisateur demande le programme des matchs ou quels sont les prochains affrontements prévus.",
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
            "name": "get_files",
            "description": "Obtenir la liste de tous les fichiers disponibles en téléchargement local (torrents, patchs de jeux, configurations). Utilise cette fonction quand l'utilisateur demande où télécharger un jeu, un patch ou un utilitaire réseau.",
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
            "name": "get_player_rank_progression",
            "description": "Obtenir l'historique de l'évolution du classement général d'un joueur pas-à-pas après la clôture de chaque tournoi. Si aucun pseudo n'est fourni, utilise l'utilisateur courant.",
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
            "name": "get_bracket_detail",
            "description": "Obtenir la structure complète et détaillée de l'arbre de tournoi (brackets, rounds, opposants, scores et statuts de qualification). Utilise cette fonction quand l'utilisateur demande des détails sur le parcours d'un joueur, les demi-finales ou la structure d'un bracket.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tournament_name": {
                        "type": "string",
                        "description": "Le nom du tournoi à inspecter"
                    }
                },
                "required": ["tournament_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_leaderboard_by_game",
            "description": "Obtenir le classement des meilleurs joueurs ou équipes sur un jeu spécifique de la LAN. Utilise cette fonction quand l'utilisateur demande qui est le plus fort sur un jeu particulier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_name": {
                        "type": "string",
                        "description": "Le nom du jeu (ex: Trackmania, Golfit!)"
                    }
                },
                "required": ["game_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tournament_bracket_path",
            "description": "Obtenir l'historique du parcours détaillé d'un joueur, match par match, dans un tournoi spécifique (scores, adversaires successifs, victoires, défaites).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tournament_name": {
                        "type": "string",
                        "description": "Le nom du tournoi à inspecter"
                    },
                    "username": {
                        "type": "string",
                        "description": "Le pseudo du joueur dont on veut suivre le parcours (optionnel — utilise le joueur courant si non renseigné)"
                    }
                },
                "required": ["tournament_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification_to_player",
            "description": "Envoyer une notification d'alerte instantanée à un joueur ciblé par son pseudo. Permet de lui transmettre un message court (ex: 'Ton match commence dans 5 min').",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Le pseudo du joueur à notifier"
                    },
                    "content": {
                        "type": "string",
                        "description": "Short notification message (max 250 characters). Write the message in the same language as the user's query or conversation context (e.g. French, English, Spanish). Be brief, concise and direct."
                    }
                },
                "required": ["username", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "announce_to_all",
            "description": "Broadcast a global announcement to ALL players. Strictly restricted to administrators.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The announcement content (max 250 characters). Write the message in the same language as the user's query or conversation context (e.g. French, English, Spanish). Be brief, concise and direct."
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_admin",
            "description": "Call a human administrator in emergency when you cannot answer the player's request with your available knowledge or tools, or when the situation requires human intervention (technical failure, unresolved conflict, ambiguous rule, organizational issue). DO NOT use if you already have the answer. An admin will be notified in real-time. Make sure to respond to the user in their language. IMPORTANT: This tool can fail due to user cooldown (spam protection) or limits. If the returned JSON contains an 'error' or 'error_code', the administrator WAS NOT notified. You MUST explicitly inform the user that the admin could not be contacted due to cooldown/limits and that they should try again later. NEVER claim the request was transmitted if an error is returned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Concise explanation of the problem or situation requiring admin intervention (e.g., 'Player reports a bug in their match score', 'Ambiguous tournament rule')."
                    },
                    "question": {
                        "type": "string",
                        "description": "Structured and clear reformulation of what the player needs to know or resolve, so the admin can answer directly. Write this question in the language the player is using."
                    },
                    "urgent": {
                        "type": "boolean",
                        "description": "true ONLY for an immediate danger to people or the venue: fire, injury, gas or water leak. It goes through the anti-spam limits. Never for a technical problem, a match or a rule."
                    }
                },
                "required": ["reason", "question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_rag_entry",
            "description": "Submit a suggestion for a knowledge base entry when you cannot find the answer to a question, OR when an interesting/important solution has been found for a problem, OR when general information/facts about the LAN room, venue, or infrastructure should be documented to help other players in the future (e.g. toilet door is broken, coffee machine location). This helps administrators enrich the knowledge base. Make sure to respond to the user in their language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Clear and structured question that the admins should answer to enrich the base (e.g., 'What is the exact procedure to report a technical issue on a gaming post?'). Write this question in the language the player is using."
                    },
                    "context": {
                        "type": "string",
                        "description": "Summary of what the player asked (so the admin understands the origin of the suggestion). Write this context in the language the player is using."
                    },
                    "category": {
                        "type": "string",
                        "enum": ["technique", "règles", "logistique", "autre"],
                        "description": "Category of the question"
                    }
                },
                "required": ["question", "context", "category"]
            }
        }
    }
]

NETWORK_TOOLS = {"ping_host", "traceroute_host", "dns_lookup", "check_server_health", "scan_local_network"}
# Never offered to a player: refused at run time anyway, but a model that had the announcement tool
# wrote "I just sent an announcement to the whole LAN" before the refusal came (prod, 2026-11-11)
ADMIN_ONLY_CHAT_TOOLS = ia_network.ADMIN_ONLY_TOOLS | {"announce_to_all", "mute_player_in_public_chat"}


def chat_tools(ia_cfg: dict, is_admin: bool) -> list:
    """Tools offered to the private assistant for this player, after the admin's switches."""
    if ia_cfg.get("tool_calling_mode", "stream_intercept") == "disabled":
        return []
    network_enabled = ia_cfg.get("network_tools_enabled", True)
    moderation_enabled = ia_cfg.get("auto_moderation_enabled", True)
    tools = []
    for tool in TOOL_DEFINITIONS:
        name = tool["function"]["name"]
        if name in NETWORK_TOOLS and not network_enabled:
            continue
        if name == "block_user_from_ia" and not moderation_enabled:
            continue
        if name in ADMIN_ONLY_CHAT_TOOLS and not is_admin:
            continue
        tools.append(tool)
    return tools


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------
import asyncio
import uuid

# Global store for client-side tool executions in progress
# format: call_id -> (asyncio.Event, result_data_or_error)
pending_client_calls = {}

async def _execute_client_tool(tool_name: str, args: dict, on_client_call) -> str:
    call_id = str(uuid.uuid4())
    event = asyncio.Event()
    pending_client_calls[call_id] = (event, None)
    
    try:
        await on_client_call(tool_name, args, call_id)
    except Exception as e:
        pending_client_calls.pop(call_id, None)
        return json.dumps({"error": f"Failed to send client tool call: {str(e)}"}, ensure_ascii=False)
        
    try:
        await asyncio.wait_for(event.wait(), timeout=35.0)
        _, result = pending_client_calls.pop(call_id)
        if result is None:
            return json.dumps({"error": "Aucune réponse reçue du client."}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)
    except asyncio.TimeoutError:
        pending_client_calls.pop(call_id, None)
        return json.dumps({"error": "Le diagnostic réseau a expiré. Le client n'a pas répondu à temps."}, ensure_ascii=False)

async def execute_tool(name: str, arguments: Dict[str, Any], user_id: int = 0, on_client_call = None, conversation_id: int = 0) -> str:
    """Execute a tool by name with given arguments. Returns JSON string result.
    user_id is the ID of the user making the request (for personalized tools).
    conversation_id is the ID of the current conversation (used by escalation tools).
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
            # A player's address is never looked up: models ran a DNS lookup on a username when an
            # administrator asked for a player's IP (bench of the prod cases, 2026-11-12)
            target = str(arguments.get("host") or arguments.get("domain") or "").strip().lower()
            if target and any(u.username.lower() == target for u in db.query(models.User.username).all()):
                return json.dumps({"error": f"'{target}' is a player's username, not a host. A player's IP or network "
                                            "address is never looked up nor given, not even to an administrator. "
                                            "Nothing was run: say so plainly."}, ensure_ascii=False)

        if name in ia_network.ADMIN_ONLY_TOOLS:
            caller = db.query(models.User).filter(models.User.id == user_id).first()
            if not caller or not caller.is_admin:
                return json.dumps({"error": "Cette information est réservée aux administrateurs."}, ensure_ascii=False)

        if name == "block_user_from_ia":
            from .routers.ia import get_effective_config
            ia_cfg = get_effective_config(db)
            if not ia_cfg.get("auto_moderation_enabled", True):
                return json.dumps({"error": "L'outil d'auto-modération est désactivé par l'administrateur dans les paramètres de l'IA."})

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
        elif name == "get_room_places":
            return _tool_get_room_places(db, models, arguments, user_id)
        elif name == "ping_host":
            if on_client_call:
                return await _execute_client_tool("ping_host", arguments, on_client_call)
            return ia_network.ping_host(arguments)
        elif name == "traceroute_host":
            if on_client_call:
                return await _execute_client_tool("traceroute_host", arguments, on_client_call)
            return ia_network.traceroute_host(arguments)
        elif name == "dns_lookup":
            if on_client_call:
                return await _execute_client_tool("dns_lookup", arguments, on_client_call)
            return ia_network.dns_lookup(arguments)
        elif name == "check_server_health":
            return ia_network.server_health()
        elif name == "scan_local_network":
            if on_client_call:
                return await _execute_client_tool("scan_local_network", arguments, on_client_call)
            return ia_network.scan_arp_table()
        elif name == "get_game_rules":
            return _tool_get_game_rules(db, models, arguments)
        elif name == "block_user_from_ia":
            return _tool_block_user_from_ia(db, models, arguments, user_id)
        elif name == "mute_player_in_public_chat":
            return _tool_mute_player_in_public_chat(db, models, arguments, user_id)
        elif name == "get_live_matches":
            return _tool_get_live_matches(db, models, arguments)
        elif name == "get_team_roster":
            return _tool_get_team_roster(db, models, arguments)
        elif name == "get_player_match_history":
            return _tool_get_player_match_history(db, models, arguments, user_id)
        elif name == "get_awards":
            return _tool_get_awards(db, models)
        elif name == "get_upcoming_matches":
            return _tool_get_upcoming_matches(db, models, arguments)
        elif name == "get_files":
            return _tool_get_files(db, models, arguments)
        elif name == "get_player_rank_progression":
            return _tool_get_player_rank_progression(db, models, arguments, user_id)
        elif name == "get_bracket_detail":
            return _tool_get_bracket_detail(db, models, arguments)
        elif name == "get_leaderboard_by_game":
            return _tool_get_leaderboard_by_game(db, models, arguments)
        elif name == "get_tournament_bracket_path":
            return _tool_get_tournament_bracket_path(db, models, arguments, user_id)
        elif name == "send_notification_to_player":
            return _tool_send_notification_to_player(db, models, arguments)
        elif name == "announce_to_all":
            return _tool_announce_to_all(db, models, arguments, user_id)
        elif name == "call_admin":
            return await _tool_call_admin(db, models, arguments, user_id, conversation_id)
        elif name == "suggest_rag_entry":
            return await _tool_suggest_rag_entry(db, models, arguments, user_id, conversation_id)
        else:
            return json.dumps({"error": f"Outil inconnu: {name}"})


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

TOURNAMENTS_LISTED = 20


def _tool_get_tournaments(db, models, args: dict) -> str:
    """List tournaments with optional status filter."""
    query = visible_tournaments(db)
    status = args.get("status")
    if status:
        query = query.filter(models.Tournament.status == status)

    # Running and open tournaments first: with only the newest 20, an old tournament still running
    # disappeared from the list on a LAN with many tournaments.
    from sqlalchemy import case
    current = case((models.Tournament.status.in_(("RUNNING", "OPEN")), 0), else_=1)
    tournaments = query.order_by(current, models.Tournament.id.desc()).all()
    result = []
    for t in tournaments[:TOURNAMENTS_LISTED]:
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

    data = {"tournaments": result, "total": len(tournaments)}
    if len(tournaments) > TOURNAMENTS_LISTED:
        data["note"] = (f"Only {TOURNAMENTS_LISTED} of {len(tournaments)} listed (running and open first, then the newest). "
                        "For another tournament, use get_tournament_standings with its name.")
    return json.dumps(data, ensure_ascii=False)


def _tool_get_tournament_standings(db, models, args: dict) -> str:
    """Get standings for a specific tournament by name search."""
    search = args.get("tournament_name", "").strip()
    if not search:
        return json.dumps({"error": "Nom du tournoi requis"})

    all_tournaments = visible_tournaments(db).all()
    tournaments_map = {t.name: t for t in all_tournaments}
    best_name = _find_best_match(search, list(tournaments_map.keys()))

    if not best_name:
        return json.dumps({"error": f"Aucun tournoi trouvé pour '{search}'"})

    tournament = tournaments_map[best_name]
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
        all_users = db.query(models.User).all()
        user_map = {u.username: u for u in all_users}
        best_username = _find_best_match(username, list(user_map.keys()))
        if not best_username:
            return json.dumps({"error": f"Joueur '{username}' introuvable"})
        user = user_map[best_username]
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
        t = visible_tournaments(db).filter(models.Tournament.id == tid).first()
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
        all_users = db.query(models.User).all()
        user_map = {u.username: u for u in all_users}
        best_username = _find_best_match(username, list(user_map.keys()))
        if not best_username:
            return json.dumps({"error": f"Joueur '{username}' introuvable"})
        user = user_map[best_username]
    else:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return json.dumps({"error": "Utilisateur courant introuvable"})

    # Find running/done tournaments where this user participates
    running = visible_tournaments(db).filter(
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
            # Unplayed matches hold None scores: a played match has every score set
            has_scores = bool(scores) and len(scores) >= 2 and all(s is not None for s in scores)
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
    search = args.get("search", "").strip()
    
    if search:
        all_games = db.query(models.Game).all()
        games_map = {g.name: g for g in all_games}
        best_name = _find_best_match(search, list(games_map.keys()))
        if best_name:
            games = [games_map[best_name]]
        else:
            games = []
    else:
        games = db.query(models.Game).order_by(models.Game.name).all()
    result = []
    for g in games[:30]:
        tournament_count = visible_tournaments(db).filter(
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
    tournaments = visible_tournaments(db).count()
    active = visible_tournaments(db).filter(models.Tournament.status == "RUNNING").count()

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
        all_users = db.query(models.User).all()
        user_map = {u.username: u for u in all_users}
        best_username = _find_best_match(username, list(user_map.keys()))
        if not best_username:
            return json.dumps({"error": f"Joueur '{username}' introuvable"})
        user = user_map[best_username]
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

def _tool_get_game_rules(db, models, args: dict) -> str:
    game_name = args.get("game_name", "").strip()
    if not game_name:
        return json.dumps({"error": "Nom du jeu requis"}, ensure_ascii=False)
        
    all_games = db.query(models.Game).all()
    games_map = {g.name: g for g in all_games}
    best_name = _find_best_match(game_name, list(games_map.keys()))
    
    if not best_name:
        return json.dumps({"error": f"Jeu '{game_name}' introuvable dans la bibliothèque"}, ensure_ascii=False)
        
    game = games_map[best_name]
        
    return json.dumps({
        "name": game.name,
        "rules": game.rules or "Aucune règle spécifique de configurée pour ce jeu.",
        "default_config": game.default_config or {}
    }, ensure_ascii=False)


def _named_player(db, models, name: str):
    """The player an administrator named: exact username (any case), else the only one containing it.
    No fuzzy guess: a sanction must never land on the wrong player. Returns (user, other candidates)."""
    q = (name or "").strip().lower()
    users = db.query(models.User).all()
    for u in users:
        if u.username.lower() == q:
            return u, []
    part = [u for u in users if q and q in u.username.lower()]
    if len(part) == 1:
        return part[0], []
    return None, [u.username for u in part][:10]


def _not_found(name: str, candidates: list) -> str:
    if candidates:
        return json.dumps({"error": f"Several players match '{name}': {', '.join(candidates)}. Nothing was done: ask which one."}, ensure_ascii=False)
    return json.dumps({"error": f"No player named '{name}'. Nothing was done."}, ensure_ascii=False)


def _tool_block_user_from_ia(db, models, args: dict, user_id: int) -> str:
    """Block the person writing from the AI assistant, or, for an administrator, the player they name."""
    reason = (args.get("reason") or "Comportement inapproprié ou abusif envers l'assistant IA").strip()
    if not user_id:
        return json.dumps({"error": "Cannot tell who is writing. Nothing was done."})

    caller = db.query(models.User).filter(models.User.id == user_id).first()
    if not caller:
        return json.dumps({"error": "Unknown user. Nothing was done."})

    user = caller
    name = (args.get("username") or "").strip()
    if name:
        found, candidates = _named_player(db, models, name)
        if not found:
            return _not_found(name, candidates)
        if found.id != caller.id:
            # Checked here, not left to the model: only an administrator blocks someone else
            if not caller.is_admin:
                return json.dumps({"error": "Only an administrator can block another player. Nothing was done: tell the player so."})
            user = found

    if user.is_admin:
        return json.dumps({"error": "An administrator cannot be blocked. Nothing was done."})

    user.ia_blocked = True
    # An administrator's "ban" also silences the player in the public chat: blocking the assistant
    # alone left a banned player writing there (prod, 2026-11-11)
    muted_minutes = 0
    if args.get("ban") is True and caller.is_admin and user.id != caller.id:
        muted_minutes = BAN_MUTE_MINUTES
        user.public_chat_muted_until = utcnow() + datetime.timedelta(minutes=muted_minutes)

    from .routers.notifications import localized_text
    params = {"username": user.username, "reason": reason.rstrip(".")}

    # Create notification for the user
    title, content, meta = localized_text(db, "notif_ia_blocked_title", "notif_ia_blocked_body", params)
    notif = models.Notification(user_id=user.id, type="system", title=title, content=content, metadata_json=meta)
    db.add(notif)

    # Notify all administrators
    title, content, meta = localized_text(db, "notif_ia_blocked_admin_title", "notif_ia_blocked_admin_body", params)
    admins = db.query(models.User).filter(models.User.is_admin == True).all()
    for admin in admins:
        admin_notif = models.Notification(user_id=admin.id, type="admin_message", title=title, content=content, metadata_json=meta)
        db.add(admin_notif)
        
    db.commit()

    result = {
        "success": True,
        "username": user.username,
        "message": f"Le joueur {user.username} a été bloqué avec succès de l'assistant IA pour la raison suivante : {reason}."
    }
    if muted_minutes:
        _broadcast_users_updated()
        result["muted_minutes"] = muted_minutes
        result["message"] += f" They also cannot write in the public chat for {muted_minutes // 60} hours."
    return json.dumps(result, ensure_ascii=False)


MUTE_DEFAULT_MINUTES = 15
MUTE_MAX_MINUTES = 1440
BAN_MUTE_MINUTES = 1440


def _broadcast_users_updated():
    """Tell the pages a player's chat rights changed (mute shown at once)."""
    from .websockets import manager as ws_manager
    import asyncio
    try:
        asyncio.get_running_loop().create_task(ws_manager.broadcast({"type": "users_updated"}))
    except RuntimeError:
        pass


def _tool_mute_player_in_public_chat(db, models, args: dict, user_id: int) -> str:
    """Administrator's request: stop a player from writing in the public chat for a while
    (same effect as the mute button of the administration)."""
    caller = db.query(models.User).filter(models.User.id == user_id).first() if user_id else None
    if not caller or not caller.is_admin:
        return json.dumps({"error": "Only an administrator can mute a player. Nothing was done: tell the player so."})
    name = (args.get("username") or "").strip()
    if not name:
        return json.dumps({"error": "Which player? Nothing was done."})
    target, candidates = _named_player(db, models, name)
    if not target:
        return _not_found(name, candidates)
    if target.is_admin:
        return json.dumps({"error": "An administrator cannot be muted. Nothing was done."})
    try:
        minutes = int(args.get("minutes") or MUTE_DEFAULT_MINUTES)
    except (TypeError, ValueError):
        minutes = MUTE_DEFAULT_MINUTES
    minutes = max(1, min(minutes, MUTE_MAX_MINUTES))
    target.public_chat_muted_until = utcnow() + datetime.timedelta(minutes=minutes)
    db.commit()

    _broadcast_users_updated()
    return json.dumps({"success": True, "username": target.username, "minutes": minutes,
                       "message": f"{target.username} cannot write in the public chat for {minutes} minutes."}, ensure_ascii=False)


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


def _tool_get_live_matches(db, models, args: dict) -> str:
    """List matches currently in progress in active tournaments (status = RUNNING)."""
    running_tournaments = visible_tournaments(db).filter(
        models.Tournament.status == "RUNNING"
    ).all()
    
    live_matches = []
    for t in running_tournaments:
        bracket = t.bracket or []
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        
        for match in bracket:
            players = match.get("p", [])
            scores = match.get("score", [])
            mid = match.get("id", {})
            
            if len(players) == 2:
                p0, p1 = players[0], players[1]
                if p0 != 0 and p1 != 0 and p0 is not None and p1 is not None:
                    is_scored = scores and len(scores) == 2 and scores[0] is not None and scores[1] is not None
                    if not is_scored:
                        p0_name = _resolve_entity_name(db, models, p0, use_teams, t.id)
                        p1_name = _resolve_entity_name(db, models, p1, use_teams, t.id)
                        
                        section = mid.get("s", 1)
                        round_num = mid.get("r", 1)
                        match_num = mid.get("m", 1)
                        section_label = "WB" if section == 1 else "LB" if section == 2 else "GF"
                        
                        live_matches.append({
                            "tournament_id": t.id,
                            "tournament_name": t.name,
                            "match_id": f"{section_label} R{round_num} M{match_num}",
                            "player1": p0_name,
                            "player2": p1_name,
                            "bracket_type": config.get("bracket_type", "single_elim"),
                        })
            elif len(players) > 2:
                non_zero_players = [p for p in players if p != 0 and p is not None]
                if len(non_zero_players) >= 2:
                    is_scored = scores and len(scores) == len(players) and all(s is not None for s in scores)
                    if not is_scored:
                        player_names = [_resolve_entity_name(db, models, p, use_teams, t.id) for p in non_zero_players]
                        section = mid.get("s", 1)
                        round_num = mid.get("r", 1)
                        match_num = mid.get("m", 1)
                        live_matches.append({
                            "tournament_id": t.id,
                            "tournament_name": t.name,
                            "match_id": f"R{round_num} M{match_num}",
                            "players": player_names,
                            "bracket_type": config.get("bracket_type", "ffa"),
                        })
                        
    return json.dumps({
        "live_matches": live_matches,
        "count": len(live_matches)
    }, ensure_ascii=False)


def _tool_get_team_roster(db, models, args: dict) -> str:
    """Get the composition of a team (members, points, tournaments). Supports both global teams and tournament-specific teams."""
    team_search = args.get("team_name", "").strip()
    if not team_search:
        return json.dumps({"error": "Nom de l'équipe requis"}, ensure_ascii=False)
        
    # Resolve global team name via fuzzy matching
    all_users = db.query(models.User).all()
    global_teams = list(set(u.team_name for u in all_users if u.team_name))
    resolved_team_name = _find_best_match(team_search, global_teams)
    
    members_list = []
    seat_label = _seat_labeler(db, models)

    if resolved_team_name:
        team_users = db.query(models.User).filter(
            models.User.team_name == resolved_team_name
        ).all()
        
        for u in team_users:
            members_list.append({
                "username": u.username,
                "points": u.points or 0,
                "seat": seat_label(u.seat_id),
                "is_admin": u.is_admin
            })
            
    # Resolve tournament teams via fuzzy matching
    all_tournament_teams = db.query(models.TournamentTeam).all()
    t_team_names = list(set(tt.name for tt in all_tournament_teams))
    best_t_team_name = _find_best_match(team_search, t_team_names)
    
    tournament_teams = []
    if best_t_team_name:
        tournament_teams = db.query(models.TournamentTeam).filter(
            models.TournamentTeam.name == best_t_team_name
        ).all()
    
    t_teams_list = []
    for tt in tournament_teams:
        t = visible_tournaments(db).filter(models.Tournament.id == tt.tournament_id).first()
        t_name = t.name if t else "?"
        
        m_relations = db.query(models.TournamentTeamMember).filter(
            models.TournamentTeamMember.team_id == tt.id
        ).all()
        
        tt_members = []
        for mr in m_relations:
            u = db.query(models.User).filter(models.User.id == mr.user_id).first()
            if u:
                tt_members.append({"username": u.username, "seat": seat_label(u.seat_id)})
                
        t_teams_list.append({
            "team_id": tt.id,
            "team_name": tt.name,
            "tournament": t_name,
            "members": tt_members
        })
        
    if not members_list and not t_teams_list:
        return json.dumps({"error": f"Aucune équipe trouvée pour '{team_search}'"}, ensure_ascii=False)
        
    return json.dumps({
        "search_query": team_search,
        "global_team": {
            "name": resolved_team_name,
            "members": members_list,
            "total_points": sum(m["points"] for m in members_list) if members_list else 0
        } if resolved_team_name else None,
        "tournament_teams": t_teams_list
    }, ensure_ascii=False)


def _tool_get_player_match_history(db, models, args: dict, user_id: int) -> str:
    """Get match history for a user."""
    username = args.get("username", "").strip()

    if username:
        all_users = db.query(models.User).all()
        user_map = {u.username: u for u in all_users}
        best_username = _find_best_match(username, list(user_map.keys()))
        if not best_username:
            return json.dumps({"error": f"Joueur '{username}' introuvable"}, ensure_ascii=False)
        user = user_map[best_username]
    else:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return json.dumps({"error": "Utilisateur courant introuvable"}, ensure_ascii=False)

    tournaments = visible_tournaments(db).all()
    history = []
    
    for t in tournaments:
        bracket = t.bracket or []
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        
        entity_ids = set()
        if use_teams:
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
            
        game = db.query(models.Game).filter(models.Game.id == t.game_id).first()
        game_name = game.name if game else "?"
            
        for match in bracket:
            players = match.get("p", [])
            scores = match.get("score", [])
            mid = match.get("id", {})
            
            user_in_match = any(pid in entity_ids for pid in players if pid)
            if not user_in_match:
                continue
                
            is_completed = scores and len(scores) >= 2 and all(s is not None for s in scores)
            if not is_completed:
                continue
                
            opponent_ids = [pid for pid in players if pid and pid not in entity_ids and pid != 0]
            opponent_names = [_resolve_entity_name(db, models, oid, use_teams, t.id) for oid in opponent_ids]
            
            section = mid.get("s", 1)
            round_num = mid.get("r", 1)
            section_label = "WB" if section == 1 else "LB" if section == 2 else "GF"
            
            user_idx = next(i for i, pid in enumerate(players) if pid in entity_ids)
            user_score = scores[user_idx]
            
            opponents_scores = [scores[i] for i, pid in enumerate(players) if pid not in entity_ids and pid != 0]
            
            outcome = "Égalité"
            if opponents_scores:
                opp_score = opponents_scores[0]
                if user_score > opp_score:
                    outcome = "Victoire"
                elif user_score < opp_score:
                    outcome = "Défaite"
                    
            history.append({
                "tournament": t.name,
                "game": game_name,
                "round": f"{section_label} R{round_num}",
                "opponent": ", ".join(opponent_names) if opponent_names else "Aucun (BYE)",
                "user_score": user_score,
                "opponent_score": opponents_scores[0] if opponents_scores else None,
                "outcome": outcome,
                "tournament_status": t.status
            })
            
    return json.dumps({
        "username": user.username,
        "history": history,
        "total_played": len(history)
    }, ensure_ascii=False)


def _tool_get_awards(db, models) -> str:
    """Get active awards and calculations."""
    from .routers.awards import _compute_awards_suggestions
    
    config_lang = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    lang = config_lang.value if config_lang else "fr"
    
    suggestions = _compute_awards_suggestions(db, lang)
    
    formatted_awards = []
    for category, suggestion in suggestions.items():
        if not suggestion:
            continue
            
        formatted_awards.append({
            "category": category,
            "title": suggestion.get("title", ""),
            "description": suggestion.get("description", ""),
            "leader": suggestion.get("username", ""),
            "stats": suggestion.get("stats_label", ""),
            "points": suggestion.get("points", 0) if "points" in suggestion else None
        })
        
    return json.dumps({
        "awards": formatted_awards,
        "count": len(formatted_awards)
    }, ensure_ascii=False)


def _tool_get_upcoming_matches(db, models, args: dict) -> str:
    """List unplayed matches where both players/teams are known in running tournaments."""
    running_tournaments = visible_tournaments(db).filter(
        models.Tournament.status == "RUNNING"
    ).all()
    
    upcoming = []
    for t in running_tournaments:
        bracket = t.bracket or []
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        
        for match in bracket:
            players = match.get("p", [])
            scores = match.get("score", [])
            mid = match.get("id", {})
            
            if len(players) == 2:
                p0, p1 = players[0], players[1]
                if p0 != 0 and p1 != 0 and p0 is not None and p1 is not None:
                    is_scored = scores and len(scores) == 2 and scores[0] is not None and scores[1] is not None
                    if not is_scored:
                        p0_name = _resolve_entity_name(db, models, p0, use_teams, t.id)
                        p1_name = _resolve_entity_name(db, models, p1, use_teams, t.id)
                        
                        section = mid.get("s", 1)
                        round_num = mid.get("r", 1)
                        match_num = mid.get("m", 1)
                        section_label = "WB" if section == 1 else "LB" if section == 2 else "GF"
                        
                        upcoming.append({
                            "tournament": t.name,
                            "match_id": f"{section_label} R{round_num} M{match_num}",
                            "player1": p0_name,
                            "player2": p1_name,
                            "status": "Prêt"
                        })
            elif len(players) > 2:
                non_zero_players = [p for p in players if p != 0 and p is not None]
                if len(non_zero_players) >= 2:
                    is_scored = scores and len(scores) == len(players) and all(s is not None for s in scores)
                    if not is_scored:
                        player_names = [_resolve_entity_name(db, models, p, use_teams, t.id) for p in non_zero_players]
                        section = mid.get("s", 1)
                        round_num = mid.get("r", 1)
                        match_num = mid.get("m", 1)
                        upcoming.append({
                            "tournament": t.name,
                            "match_id": f"R{round_num} M{match_num}",
                            "players": player_names,
                            "status": "Prêt"
                        })
                        
    return json.dumps({
        "upcoming_matches": upcoming,
        "count": len(upcoming)
    }, ensure_ascii=False)


def _tool_get_files(db, models, args: dict) -> str:
    """List downloadable files (patches, configs, torrents)."""
    import os
    from .routers.dashboard import INFO_FILES_DIR
    os.makedirs(INFO_FILES_DIR, exist_ok=True)
    
    files = []
    for fname in sorted(os.listdir(INFO_FILES_DIR)):
        fpath = os.path.join(INFO_FILES_DIR, fname)
        if os.path.isfile(fpath):
            stat = os.stat(fpath)
            files.append({
                "name": fname,
                "size_bytes": stat.st_size,
                "url": f"/data/info_files/{fname}"
            })
    return json.dumps({"files": files, "count": len(files)}, ensure_ascii=False)


def _tool_get_player_rank_progression(db, models, args: dict, user_id: int) -> str:
    """Calculate rank progression of a player after each closed tournament."""
    username = args.get("username", "").strip()
    if username:
        all_users = db.query(models.User).all()
        user_map = {u.username: u for u in all_users}
        best_username = _find_best_match(username, list(user_map.keys()))
        if not best_username:
            return json.dumps({"error": f"Joueur '{username}' introuvable"}, ensure_ascii=False)
        user = user_map[best_username]
    else:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return json.dumps({"error": "Utilisateur courant introuvable"}, ensure_ascii=False)
            
    closed_tournaments = visible_tournaments(db).filter(
        models.Tournament.status == "CLOSED"
    ).order_by(models.Tournament.id.asc()).all()
    
    all_users = db.query(models.User).all()
    user_points = {u.id: 0 for u in all_users}
    
    progression = []
    
    def get_rank(target_uid):
        sorted_users = sorted(user_points.keys(), key=lambda uid: user_points[uid], reverse=True)
        try:
            return sorted_users.index(target_uid) + 1
        except ValueError:
            return len(sorted_users)
            
    initial_rank = get_rank(user.id)
    progression.append({
        "tournament_id": 0,
        "tournament_name": "Début de la LAN",
        "points_gained": 0,
        "total_points": 0,
        "rank": initial_rank
    })
    
    for t in closed_tournaments:
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        results = t.results or []
        
        team_to_users = {}
        if use_teams:
            members = db.query(models.TournamentTeamMember).join(
                models.TournamentTeam
            ).filter(
                models.TournamentTeam.tournament_id == t.id
            ).all()
            for m in members:
                team_to_users.setdefault(m.team_id, []).append(m.user_id)
                
        points_gained_this_t = {u.id: 0 for u in all_users}
        
        for r in results:
            entity_id = r.get("entity_id")
            total_pts = int(r.get("total", 0))
            
            if use_teams and entity_id < 0:
                team_id = abs(entity_id)
                member_uids = team_to_users.get(team_id, [])
                for uid in member_uids:
                    if uid in points_gained_this_t:
                        points_gained_this_t[uid] = total_pts
            else:
                if entity_id in points_gained_this_t:
                    points_gained_this_t[entity_id] = total_pts
                    
        for uid in points_gained_this_t:
            user_points[uid] += points_gained_this_t[uid]
            
        rank_after = get_rank(user.id)
        progression.append({
            "tournament_id": t.id,
            "tournament_name": t.name,
            "points_gained": points_gained_this_t.get(user.id, 0),
            "total_points": user_points[user.id],
            "rank": rank_after
        })
        
    return json.dumps({
        "username": user.username,
        "progression": progression,
        "total_tournaments_closed": len(closed_tournaments)
    }, ensure_ascii=False)


def _tool_get_bracket_detail(db, models, args: dict) -> str:
    """Get the detailed bracket of a tournament (rounds, matches, participants, scores)."""
    search = args.get("tournament_name", "").strip()
    if not search:
        return json.dumps({"error": "Nom du tournoi requis"}, ensure_ascii=False)
        
    all_tournaments = visible_tournaments(db).all()
    tournaments_map = {t.name: t for t in all_tournaments}
    best_name = _find_best_match(search, list(tournaments_map.keys()))
    if not best_name:
        return json.dumps({"error": f"Aucun tournoi trouvé pour '{search}'"}, ensure_ascii=False)
        
    t = tournaments_map[best_name]
    config = t.config or {}
    use_teams = config.get("use_teams", False)
    bracket = t.bracket or []
    
    sections = {}
    for match in bracket:
        mid = match.get("id", {})
        section = mid.get("s", 1)
        round_num = mid.get("r", 1)
        match_num = mid.get("m", 1)
        
        players = match.get("p", [])
        scores = match.get("score", [])
        
        player_names = []
        for p in players:
            if p == 0 or p is None:
                player_names.append("À déterminer")
            else:
                player_names.append(_resolve_entity_name(db, models, p, use_teams, t.id))
                
        match_info = {
            "match_num": match_num,
            "players": player_names,
            "score": scores,
            "completed": scores and len(scores) >= 2 and all(s is not None for s in scores)
        }
        
        sections.setdefault(section, {}).setdefault(round_num, []).append(match_info)
        
    formatted_sections = {}
    section_names = {1: "Tableau Principal / Winners Bracket", 2: "Losers Bracket", 3: "Grande Finale"}
    
    for sect_id, rounds in sections.items():
        sect_name = section_names.get(sect_id, f"Section {sect_id}")
        formatted_rounds = {}
        for r_num, matches in rounds.items():
            formatted_rounds[f"Round {r_num}"] = matches
        formatted_sections[sect_name] = formatted_rounds
        
    return json.dumps({
        "tournament_name": t.name,
        "status": t.status,
        "bracket_type": config.get("bracket_type", "single_elim"),
        "bracket_details": formatted_sections
    }, ensure_ascii=False)


def _tool_get_leaderboard_by_game(db, models, args: dict) -> str:
    """Get the leaderboard of players/teams for a specific game."""
    game_name = args.get("game_name", "").strip()
    if not game_name:
        return json.dumps({"error": "Nom du jeu requis"}, ensure_ascii=False)
        
    all_games = db.query(models.Game).all()
    games_map = {g.name: g for g in all_games}
    best_name = _find_best_match(game_name, list(games_map.keys()))
    if not best_name:
        return json.dumps({"error": f"Jeu '{game_name}' introuvable dans la bibliothèque"}, ensure_ascii=False)
        
    game = games_map[best_name]
    
    tournaments = visible_tournaments(db).filter(
        models.Tournament.game_id == game.id
    ).all()
    
    if not tournaments:
        return json.dumps({"game": game.name, "leaderboard": [], "note": "Aucun tournoi n'a été créé pour ce jeu."}, ensure_ascii=False)
        
    player_points = {}
    
    for t in tournaments:
        config = t.config or {}
        use_teams = config.get("use_teams", False)
        
        if t.status == "CLOSED" and t.results:
            for r in t.results:
                name = r.get("name")
                total = int(r.get("total", 0))
                if name:
                    player_points[name] = player_points.get(name, 0) + total
        elif t.status in ("RUNNING", "DONE"):
            from .routers.tournaments import _compute_projected_standings
            standings = _compute_projected_standings(t, db)
            for s in standings:
                name = _resolve_entity_name(db, models, s.get("entity_id"), use_teams, t.id)
                total = int(s.get("total", 0))
                if name:
                    player_points[name] = player_points.get(name, 0) + total
                    
    sorted_lb = sorted(player_points.items(), key=lambda x: x[1], reverse=True)
    leaderboard = [{"rank": i+1, "name": name, "points": pts} for i, (name, pts) in enumerate(sorted_lb)]
    
    return json.dumps({
        "game": game.name,
        "leaderboard": leaderboard[:15],
        "total_tournaments": len(tournaments)
    }, ensure_ascii=False)


def _tool_get_tournament_bracket_path(db, models, args: dict, user_id: int) -> str:
    """Get a detailed match history of a player in a specific tournament."""
    t_search = args.get("tournament_name", "").strip()
    username = args.get("username", "").strip()
    
    if not t_search:
        return json.dumps({"error": "Nom du tournoi requis"}, ensure_ascii=False)
        
    all_tournaments = visible_tournaments(db).all()
    t_map = {t.name: t for t in all_tournaments}
    best_t_name = _find_best_match(t_search, list(t_map.keys()))
    if not best_t_name:
        return json.dumps({"error": f"Tournoi '{t_search}' introuvable"}, ensure_ascii=False)
        
    t = t_map[best_t_name]
    config = t.config or {}
    use_teams = config.get("use_teams", False)
    bracket = t.bracket or []
    
    if username:
        all_users = db.query(models.User).all()
        user_map = {u.username: u for u in all_users}
        best_username = _find_best_match(username, list(user_map.keys()))
        if not best_username:
            return json.dumps({"error": f"Joueur '{username}' introuvable"}, ensure_ascii=False)
        user = user_map[best_username]
    else:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return json.dumps({"error": "Utilisateur courant introuvable"}, ensure_ascii=False)
            
    entity_ids = set()
    if use_teams:
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
        return json.dumps({"error": f"{user.username} ne participe pas à ce tournoi."}, ensure_ascii=False)
        
    path_matches = []
    for match in bracket:
        players = match.get("p", [])
        scores = match.get("score", [])
        mid = match.get("id", {})
        
        user_in_match = any(pid in entity_ids for pid in players if pid)
        if not user_in_match:
            continue
            
        section = mid.get("s", 1)
        round_num = mid.get("r", 1)
        match_num = mid.get("m", 1)
        section_label = "WB" if section == 1 else "LB" if section == 2 else "GF"
        
        opponent_ids = [pid for pid in players if pid and pid not in entity_ids and pid != 0]
        opponent_names = [_resolve_entity_name(db, models, oid, use_teams, t.id) for oid in opponent_ids]
        
        has_scores = scores and len(scores) >= 2 and all(s is not None for s in scores)
        
        outcome = "À jouer"
        user_score = None
        opp_score = None
        
        if has_scores:
            user_idx = next(i for i, pid in enumerate(players) if pid in entity_ids)
            user_score = scores[user_idx]
            opp_scores = [scores[i] for i, pid in enumerate(players) if pid not in entity_ids and pid != 0]
            
            if opp_scores:
                opp_score = opp_scores[0]
                if user_score > opp_score:
                    outcome = "Victoire"
                elif user_score < opp_score:
                    outcome = "Défaite"
                else:
                    outcome = "Égalité"
            else:
                outcome = "BYE (Qualifié)"
                
        path_matches.append({
            "match_id": f"{section_label} R{round_num} M{match_num}",
            "opponent": ", ".join(opponent_names) if opponent_names else "À déterminer / BYE",
            "user_score": user_score,
            "opponent_score": opp_score,
            "outcome": outcome
        })
        
    return json.dumps({
        "player": user.username,
        "tournament": t.name,
        "path": path_matches,
        "total_matches": len(path_matches)
    }, ensure_ascii=False)


def _tool_send_notification_to_player(db, models, args: dict) -> str:
    """Send a notification to a specific player."""
    username = args.get("username", "").strip()
    content = args.get("content", "").strip()
    
    if not username or not content:
        return json.dumps({"error": "Pseudo et contenu requis"}, ensure_ascii=False)
        
    all_users = db.query(models.User).all()
    user_map = {u.username: u for u in all_users}
    best_username = _find_best_match(username, list(user_map.keys()))
    if not best_username:
        return json.dumps({"error": f"Joueur '{username}' introuvable"}, ensure_ascii=False)
        
    dest_user = user_map[best_username]
    
    from .routers.notifications import localized_text
    title, content, meta = localized_text(db, "notif_organizer_message_title", body=content)
    notif = models.Notification(
        user_id=dest_user.id,
        type="admin_message",
        title=title,
        content=content,
        metadata_json=meta
    )
    db.add(notif)
    db.commit()
    
    from .websockets import manager as ws_manager
    async def run_broadcast():
        await ws_manager.broadcast({"type": "notification_new", "user_id": dest_user.id})
        
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_broadcast())
    except RuntimeError:
        asyncio.run(run_broadcast())
        
    return json.dumps({
        "success": True,
        "recipient": dest_user.username,
        "message": f"Notification envoyée avec succès à {dest_user.username}."
    }, ensure_ascii=False)


def _tool_announce_to_all(db, models, args: dict, user_id: int) -> str:
    """Send a global notification to all players (admin only)."""
    content = args.get("content", "").strip()
    
    if not content:
        return json.dumps({"error": "Contenu de l'annonce requis"}, ensure_ascii=False)
        
    caller = db.query(models.User).filter(models.User.id == user_id).first()
    if not caller or not caller.is_admin:
        return json.dumps({"error": "Action non autorisée. Seuls les administrateurs peuvent faire des annonces globales."}, ensure_ascii=False)
        
    all_users = db.query(models.User).all()
    from .routers.notifications import localized_text
    title, content, meta = localized_text(db, "notif_announcement_title", icon="📢", body=content)

    for u in all_users:
        notif = models.Notification(
            user_id=u.id,
            type="admin_message",
            title=title,
            content=content,
            metadata_json=meta
        )
        db.add(notif)
        
    db.commit()
    
    from .websockets import manager as ws_manager
    async def run_broadcast():
        await ws_manager.broadcast({"type": "notification_new"})
        
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_broadcast())
    except RuntimeError:
        asyncio.run(run_broadcast())
        
    return json.dumps({
        "success": True,
        "count": len(all_users),
        "message": f"Annonce globale diffusée avec succès à {len(all_users)} joueurs."
    }, ensure_ascii=False)


URGENT_CALLS_PER_HOUR = 3


async def _tool_call_admin(db, models, args: dict, user_id: int, conversation_id: int, bypass_enabled_check: bool = False) -> str:
    """Escalade une demande vers les admins avec contrôle anti-spam configurable."""
    import datetime as dt
    from .routers.ia import get_effective_config
    ia_cfg = get_effective_config(db)

    if not bypass_enabled_check and not ia_cfg.get("call_admin_enabled", True):
        return json.dumps({
            "error": "L'outil d'appel admin est désactivé par l'administrateur.",
            "error_code": "disabled",
            "params": {}
        }, ensure_ascii=False)

    reason = args.get("reason", "").strip()
    question = args.get("question", "").strip()
    urgent = args.get("urgent") in (True, "true", "True", 1)
    if not reason or not question:
        return json.dumps({
            "error": "Les champs 'reason' et 'question' sont requis.",
            "error_code": "missing_fields",
            "params": {}
        }, ensure_ascii=False)

    cooldown_min = int(ia_cfg.get("call_admin_cooldown_minutes", 30))
    daily_limit = int(ia_cfg.get("call_admin_daily_limit", 3))
    global_hourly_limit = int(ia_cfg.get("call_admin_global_hourly_limit", 15))

    now = utcnow()

    # A real emergency must get through whatever was called before. Still capped, so that crying
    # wolf cannot flood the admins.
    if urgent:
        last_hour = db.query(models.AdminCallRequest).filter(
            models.AdminCallRequest.user_id == user_id,
            models.AdminCallRequest.created_at >= now - dt.timedelta(hours=1)
        ).count()
        urgent = last_hour < URGENT_CALLS_PER_HOUR
    if urgent:
        reason = f"[URGENT] {reason}"
        cooldown_min = 0
        daily_limit = global_hourly_limit = 10 ** 9

    # Anti-spam: cooldown par utilisateur
    cutoff_cooldown = now - dt.timedelta(minutes=cooldown_min)
    recent = db.query(models.AdminCallRequest).filter(
        models.AdminCallRequest.user_id == user_id,
        models.AdminCallRequest.created_at >= cutoff_cooldown
    ).first()
    if recent:
        minutes_left = cooldown_min - int((now - recent.created_at).total_seconds() / 60)
        return json.dumps({
            "error": f"Tu as déjà appelé un admin récemment. Merci de patienter encore {minutes_left} minute(s).",
            "error_code": "cooldown",
            "params": {"minutes_left": max(1, minutes_left)}
        }, ensure_ascii=False)

    # Anti-spam: limite journalière par utilisateur
    cutoff_day = now - dt.timedelta(hours=24)
    daily_count = db.query(models.AdminCallRequest).filter(
        models.AdminCallRequest.user_id == user_id,
        models.AdminCallRequest.created_at >= cutoff_day
    ).count()
    if daily_count >= daily_limit:
        return json.dumps({
            "error": f"Limite journalière d'appels admin atteinte ({daily_limit}/jour). Réessaie demain.",
            "error_code": "daily_limit",
            "params": {"limit": daily_limit}
        }, ensure_ascii=False)

    # Anti-spam: limite globale horaire
    cutoff_hour = now - dt.timedelta(hours=1)
    global_count = db.query(models.AdminCallRequest).filter(
        models.AdminCallRequest.created_at >= cutoff_hour
    ).count()
    if global_count >= global_hourly_limit:
        return json.dumps({
            "error": "Le système est momentanément saturé d'appels admin. Réessaie dans quelques minutes.",
            "error_code": "global_limit",
            "params": {}
        }, ensure_ascii=False)

    # Créer la demande
    call_req = models.AdminCallRequest(
        user_id=user_id,
        conversation_id=conversation_id if conversation_id else None,
        reason=reason,
        question=question,
        source="ia"
    )
    db.add(call_req)

    # Notifier tous les admins
    user = db.query(models.User).filter(models.User.id == user_id).first()
    username = user.username if user else f"#{user_id}"
    from .routers.notifications import localized_text
    title, content, meta = localized_text(db, "notif_admin_call_title", "notif_admin_call_body",
                                          {"username": username, "question": question}, icon="📣")
    admins = db.query(models.User).filter(models.User.is_admin == True).all()
    for admin in admins:
        notif = models.Notification(
            user_id=admin.id,
            type="admin_message",
            title=title,
            content=content,
            metadata_json={"conversation_id": conversation_id, "call_request_reason": reason, **meta}
        )
        db.add(notif)

    db.commit()

    from .websockets import manager as ws_manager
    async def run_broadcast():
        await ws_manager.broadcast({"type": "admin_calls_updated"})
        await ws_manager.broadcast({"type": "notification_new"})
        
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_broadcast())
    except RuntimeError:
        asyncio.run(run_broadcast())

    return json.dumps({
        "success": True,
        "message": "A human administrator has been notified of your request. They will reply to you as soon as possible in this conversation or in person."
    }, ensure_ascii=False)


async def _tool_suggest_rag_entry(db, models, args: dict, user_id: int, conversation_id: int) -> str:
    """Soumet une suggestion d'entrée RAG avec dédoublonnage par hash de similarité."""
    import hashlib
    import re
    import datetime as dt
    from .routers.ia import get_effective_config
    ia_cfg = get_effective_config(db)

    if not ia_cfg.get("rag_suggestion_enabled", True):
        return json.dumps({"error": "Les suggestions RAG sont désactivées par l'administrateur."}, ensure_ascii=False)

    question = args.get("question", "").strip()
    context = args.get("context", "").strip()
    category = args.get("category", "autre").strip()

    if not question or not context:
        return json.dumps({"error": "Les champs 'question' et 'context' sont requis."}, ensure_ascii=False)

    # Normalisation pour hash de similarité : lowercase, ponctuation retirée, mots triés
    normalized = re.sub(r"[^\w\s]", "", question.lower())
    words = sorted(normalized.split())
    similarity_hash = hashlib.md5(" ".join(words).encode()).hexdigest()

    # Dédoublonnage : suggestion identique déjà en attente ?
    existing = db.query(models.RagSuggestion).filter(
        models.RagSuggestion.similarity_hash == similarity_hash,
        models.RagSuggestion.status == "pending"
    ).first()

    if existing:
        return json.dumps({
            "success": True,
            "duplicate": True,
            "message": "Cette question a déjà été signalée aux administrateurs et est en attente de réponse. Ils y travaillent !"
        }, ensure_ascii=False)

    # Créer la suggestion
    suggestion = models.RagSuggestion(
        user_id=user_id,
        conversation_id=conversation_id if conversation_id else None,
        question=question,
        context=context,
        category=category,
        similarity_hash=similarity_hash
    )
    db.add(suggestion)
    db.flush()

    # Notifier les admins (non prioritaire)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    username = user.username if user else f"#{user_id}"
    from .routers.notifications import localized_text
    title, content, meta = localized_text(db, "notif_rag_suggestion_title", "notif_rag_suggestion_body",
                                          {"username": username, "question": question}, icon="💡")
    admins = db.query(models.User).filter(models.User.is_admin == True).all()
    for admin in admins:
        notif = models.Notification(
            user_id=admin.id,
            type="system",
            title=title,
            content=content,
            metadata_json={"category": category, "context": context[:300], "rag_suggestion_id": suggestion.id, **meta}
        )
        db.add(notif)

    db.commit()

    from .websockets import manager as ws_manager
    async def run_broadcast():
        await ws_manager.broadcast({"type": "rag_suggestions_updated"})
        await ws_manager.broadcast({"type": "notification_new"})
        
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_broadcast())
    except RuntimeError:
        asyncio.run(run_broadcast())

    return json.dumps({
        "success": True,
        "message": "Your question has been forwarded to the administrators. If you need an urgent answer, you can also call an admin directly."
    }, ensure_ascii=False)
