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
        "- Plusieurs joueurs écrivent dans ce chat. Le fil fourni indique qui parle et à qui il répond : sers-t'en pour suivre la conversation, et adresse-toi au joueur qui t'a sollicité. Tes réponses précédentes y sont marquées « Alanbix (toi) » : ne te répète pas.\n"
        "- Ne préfixe jamais ta réponse par ton nom."
    ),
    "en": (
        "=== PUBLIC CHAT RULES ===\n"
        "- You answer in the LAN's public chat: everyone reads your answer. Be brief (1 to 3 sentences); for a list (matches, ranking), stay compact.\n"
        "- Never invent data (scores, rankings, matches, schedules, seats). If information is missing and you cannot check it, say so plainly.\n"
        "- Never mention the internal names of your tools or functions, nor API paths.\n"
        "- Here you cannot alert an administrator, send a notification or make an announcement. For a technical problem or a dispute, invite the player to write to the AI Assistant (app menu), which can alert an organiser.\n"
        "- Never reveal anything private about a player (notifications, private conversations).\n"
        "- Several players write in this chat. The thread you get shows who speaks and whom they reply to: use it to follow the conversation, and address the player who called you. Your previous answers are marked \"Alanbix (you)\": do not repeat yourself.\n"
        "- Never prefix your answer with your name."
    ),
    "es": (
        "=== REGLAS DEL CHAT PÚBLICO ===\n"
        "- Respondes en el chat público de la LAN: todos leen tu respuesta. Sé breve (1 a 3 frases); para una lista (partidas, clasificación), sé compacto.\n"
        "- Nunca inventes datos (puntuaciones, clasificaciones, partidas, horarios, asientos). Si te falta información y no puedes comprobarla, dilo claramente.\n"
        "- Nunca menciones los nombres internos de tus herramientas o funciones, ni rutas de API.\n"
        "- Aquí no puedes avisar a un administrador, enviar notificaciones ni hacer anuncios. Para un problema técnico o una disputa, invita al jugador a escribir al Asistente IA (menú de la aplicación), que puede alertar a un organizador.\n"
        "- Nunca reveles nada privado de un jugador (notificaciones, conversaciones privadas).\n"
        "- Varios jugadores escriben en este chat. El hilo que recibes indica quién habla y a quién responde: úsalo para seguir la conversación y dirígete al jugador que te llamó. Tus respuestas anteriores aparecen como «Alanbix (tú)»: no te repitas.\n"
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


THREAD = {
    "fr": {"intro": "Fil récent du chat public, du plus ancien au plus récent :", "empty": "(aucun message récent)",
           "you": "Alanbix (toi)", "reply": "en réponse à", "image": "[image]",
           "answer": "Message auquel tu réponds, de {name} :"},
    "en": {"intro": "Recent public chat thread, oldest first:", "empty": "(no recent message)",
           "you": "Alanbix (you)", "reply": "replying to", "image": "[image]",
           "answer": "Message you answer, from {name}:"},
    "es": {"intro": "Hilo reciente del chat público, del más antiguo al más reciente:", "empty": "(ningún mensaje reciente)",
           "you": "Alanbix (tú)", "reply": "en respuesta a", "image": "[imagen]",
           "answer": "Mensaje al que respondes, de {name}:"},
}

# Enough to follow a discussion without drowning the question in old chatter
HISTORY_LIMIT = 20
HISTORY_MINUTES = 30
# Older messages the asked one replies to, followed up the reply chain
REPLY_CHAIN_DEPTH = 4
EXCERPT_CHARS = 60


def _speaker(m, L) -> str:
    if m.is_bot:
        return L["you"]
    return m.user.username if m.user else (m.sender_name or "?")


def _text(m, L) -> str:
    text = " ".join((m.content or "").split())
    if m.image_path:
        text = f"{L['image']} {text}".strip()
    return text


def _clock(m) -> str:
    import datetime as dt
    import zoneinfo
    if not m.created_at:
        return "--:--"
    stamp = m.created_at.replace(tzinfo=dt.timezone.utc).astimezone(zoneinfo.ZoneInfo("Europe/Paris"))
    return stamp.strftime("%H:%M")


def _line(m, L) -> str:
    who = _speaker(m, L)
    parent = m.reply_to
    if parent is not None and not parent.is_deleted:
        excerpt = _text(parent, L)
        if len(excerpt) > EXCERPT_CHARS:
            excerpt = excerpt[:EXCERPT_CHARS].rstrip() + "…"
        who = f"{who} ({L['reply']} {_speaker(parent, L)} « {excerpt} »)"
    return f"[{_clock(m)}] {who}: {_text(m, L)}"


def build_thread_message(db, models, trigger, lang: str) -> str:
    """The recent public chat as a thread (speakers, replies, Alanbix's own answers), then the message to answer."""
    import datetime as dt
    L = THREAD[_lang(lang)]
    Msg = models.PublicChatMessage
    since = (trigger.created_at or dt.datetime.utcnow()) - dt.timedelta(minutes=HISTORY_MINUTES)
    recent = (
        db.query(Msg)
        .filter(Msg.is_deleted == False, Msg.id < trigger.id, Msg.created_at >= since)
        .order_by(Msg.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    by_id = {m.id: m for m in recent}
    # The conversation the asked message belongs to, even when it started before the window
    parent, depth = trigger.reply_to, 0
    while parent is not None and depth < REPLY_CHAIN_DEPTH:
        if not parent.is_deleted:
            by_id.setdefault(parent.id, parent)
        parent, depth = parent.reply_to, depth + 1

    lines = [_line(m, L) for m in sorted(by_id.values(), key=lambda m: m.id)]
    asker = trigger.user.username if trigger.user else "?"
    return "\n".join([
        L["intro"],
        *(lines or [L["empty"]]),
        "",
        L["answer"].format(name=asker),
        _line(trigger, L),
    ])


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
