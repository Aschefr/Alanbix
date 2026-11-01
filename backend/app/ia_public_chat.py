"""Prompt for @Alanbix in the public chat.

Same layers as the private assistant (admin personality, rules, app guide, live context, language),
with rules written for a room where everyone reads the answer, and a short card of the asking
player's matches so even a small model without tools can answer "which match do I play?".
"""
import json

from .ia_prompt import _lang, app_guide_block, language_block, live_context_block

PUBLIC_RULES = {
    "fr": (
        "=== RÈGLES DU CHAT PUBLIC ===\n"
        "- Tu réponds dans le chat public de la LAN : tout le monde lit ta réponse. Sois bref (1 à 3 phrases) ; pour une liste (matchs, classement), reste compact.\n"
        "- N'invente jamais de données (scores, classements, matchs, horaires, places). Si une information te manque et que tu ne peux pas la vérifier, dis-le franchement.\n"
        "- Ne cite jamais les noms internes de tes outils ou fonctions, ni des chemins d'API.\n"
        "- Ici, tu ne peux ni prévenir un administrateur, ni envoyer de notification, ni faire d'annonce. Pour un problème technique ou une contestation, invite le joueur à écrire à l'Assistant IA (menu de l'application), qui peut alerter un organisateur.\n"
        "- Ne révèle rien de privé sur un joueur (notifications, conversations privées).\n"
        "- Ne préfixe jamais ta réponse par ton nom."
    ),
    "en": (
        "=== PUBLIC CHAT RULES ===\n"
        "- You answer in the LAN's public chat: everyone reads your answer. Be brief (1 to 3 sentences); for a list (matches, ranking), stay compact.\n"
        "- Never invent data (scores, rankings, matches, schedules, seats). If information is missing and you cannot check it, say so plainly.\n"
        "- Never mention the internal names of your tools or functions, nor API paths.\n"
        "- Here you cannot alert an administrator, send a notification or make an announcement. For a technical problem or a dispute, invite the player to write to the AI Assistant (app menu), which can alert an organiser.\n"
        "- Never reveal anything private about a player (notifications, private conversations).\n"
        "- Never prefix your answer with your name."
    ),
    "es": (
        "=== REGLAS DEL CHAT PÚBLICO ===\n"
        "- Respondes en el chat público de la LAN: todos leen tu respuesta. Sé breve (1 a 3 frases); para una lista (partidas, clasificación), sé compacto.\n"
        "- Nunca inventes datos (puntuaciones, clasificaciones, partidas, horarios, asientos). Si te falta información y no puedes comprobarla, dilo claramente.\n"
        "- Nunca menciones los nombres internos de tus herramientas o funciones, ni rutas de API.\n"
        "- Aquí no puedes avisar a un administrador, enviar notificaciones ni hacer anuncios. Para un problema técnico o una disputa, invita al jugador a escribir al Asistente IA (menú de la aplicación), que puede alertar a un organizador.\n"
        "- Nunca reveles nada privado de un jugador (notificaciones, conversaciones privadas).\n"
        "- Nunca empieces tu respuesta con tu nombre."
    ),
}

MATCHES = {
    "fr": {"title": "Matchs à venir de {name}", "none": "aucun match à venir pour {name}", "vs": "contre", "tbd": "adversaire à déterminer"},
    "en": {"title": "Upcoming matches of {name}", "none": "no upcoming match for {name}", "vs": "against", "tbd": "opponent to be decided"},
    "es": {"title": "Próximas partidas de {name}", "none": "ninguna partida pendiente para {name}", "vs": "contra", "tbd": "rival por determinar"},
}

# Shown to the model: a few lines are enough, tools give the rest
MAX_MATCHES = 3


def asker_matches_block(db, models, user, lang: str) -> str:
    """The asking player's pending matches in running tournaments, one line each."""
    from .ia_tools import _tool_get_my_matches
    L = MATCHES[_lang(lang)]
    try:
        data = json.loads(_tool_get_my_matches(db, models, {}, user.id))
    except Exception as e:
        print(f"[Public Chat AI] Could not read the matches of {user.username}: {e}")
        return ""
    pending = data.get("pending_matches") or []
    if not pending:
        return f"- {L['none'].format(name=user.username)}"
    lines = [f"- {L['title'].format(name=user.username)}:"]
    for m in pending[:MAX_MATCHES]:
        opponent = m.get("opponent") or ""
        opponent = f"{L['vs']} {opponent}" if opponent and "BYE" not in opponent else L["tbd"]
        lines.append(f"  - {m.get('tournament')}, {m.get('round')}, {opponent}")
    return "\n".join(lines)


def build_public_system_prompt(db, models, asker) -> tuple[str, str]:
    """System prompt for a public chat answer to `asker`. Returns (prompt, LAN language)."""
    from .routers.ia import get_active_system_prompt
    from .routers.i18n import list_all_languages
    lang_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    lan_lang = (lang_cfg.value if lang_cfg and lang_cfg.value else "fr").lower()[:2]
    if lan_lang not in list_all_languages():
        lan_lang = "fr"
    rules_lang = _lang(lan_lang)
    parts = [get_active_system_prompt(db), PUBLIC_RULES[rules_lang]]
    guide = app_guide_block(lan_lang)
    if guide:
        parts.append(guide)
    live = live_context_block(db, models, asker, rules_lang)
    matches = asker_matches_block(db, models, asker, rules_lang)
    parts.append(f"{live}\n{matches}" if matches else live)
    parts.append(language_block(lan_lang))
    return "\n\n".join(parts), lan_lang
