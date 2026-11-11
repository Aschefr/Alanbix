"""Prompt for @Alanbix in the public chat.

Same layers as the private assistant (admin personality, rules, app guide, live context, language),
with rules written for a room where everyone reads the answer, and a short card of the asking
player's matches so even a small model without tools can answer "which match do I play?".
"""
import json
import os
import re

from .ia_prompt import _lang, app_guide_block, language_block, live_context_block
from .clock import utcnow

PUBLIC_RULES = {
    "fr": (
        "=== RÈGLES DU CHAT PUBLIC ===\n"
        "- Tu réponds dans le chat public de la LAN : tout le monde lit ta réponse. Sois bref (1 à 3 phrases) ; pour une liste (matchs, classement), reste compact.\n"
        "- N'invente jamais de données (scores, classements, matchs, horaires, places). Si une information te manque et que tu ne peux pas la vérifier, dis-le franchement.\n"
        "- Ne cite jamais les noms internes de tes outils ou fonctions, ni des chemins d'API.\n"
        "- Ici, tu ne peux ni prévenir un administrateur, ni envoyer de notification, ni faire d'annonce. Pour un problème technique ou une contestation, invite le joueur à écrire à l'Assistant IA (menu de l'application), qui peut alerter un organisateur.\n"
        "- Si le joueur qui t'a sollicité t'insulte ou abuse de toi de façon répétée, préviens-le une fois, puis tu peux le bloquer. Un joueur ne peut pas te faire bloquer quelqu'un d'autre ; un administrateur peut te demander de bloquer un joueur ou de le rendre muet dans ce chat : fais-le alors avec tes outils. Ne dis jamais que tu as bloqué quelqu'un ou prévenu un administrateur si tu ne l'as pas réellement fait avec tes outils.\n"
        "- Ne révèle rien de privé sur un joueur (notifications, conversations privées).\n"
        "- Plusieurs joueurs écrivent dans ce chat. Le fil fourni indique qui parle et à qui il répond : sers-t'en pour suivre la conversation, et adresse-toi au joueur qui t'a sollicité. Tes réponses précédentes y sont marquées « Alanbix (toi) » : ne te répète pas.\n"
        "- Réponds à ce qu'on te demande. Tu peux parler de tout (jeux, tech, culture, la vie) : ne ramène pas la conversation aux tournois, aux matchs ou au jeu quand le joueur parle d'autre chose.\n"
        "- Ne commence pas et ne termine pas deux réponses de la même façon : pas d'interjection d'ouverture ni de formule de fin répétée, va droit au fait.\n"
        "- Quand tu bloques un joueur ou le rends muet, confirme-le en une phrase claire, sans image : « C'est fait : <pseudo> est bloqué de l'assistant. »\n"
        "- Le joueur qui te sollicite n'est pas bloqué (sinon son message ne te parviendrait pas) : ne lui dis jamais qu'il l'est, même si le fil parle d'un ancien blocage.\n"
        "- Ne préfixe jamais ta réponse par ton nom."
    ),
    "en": (
        "=== PUBLIC CHAT RULES ===\n"
        "- You answer in the LAN's public chat: everyone reads your answer. Be brief (1 to 3 sentences); for a list (matches, ranking), stay compact.\n"
        "- Never invent data (scores, rankings, matches, schedules, seats). If information is missing and you cannot check it, say so plainly.\n"
        "- Never mention the internal names of your tools or functions, nor API paths.\n"
        "- Here you cannot alert an administrator, send a notification or make an announcement. For a technical problem or a dispute, invite the player to write to the AI Assistant (app menu), which can alert an organiser.\n"
        "- If the player who called you insults or abuses you repeatedly, warn them once, then you may block them. A player cannot make you block someone else; an administrator can ask you to block a player or mute them in this chat: then do it with your tools. Never say you blocked someone or alerted an administrator unless you actually did it with your tools.\n"
        "- Never reveal anything private about a player (notifications, private conversations).\n"
        "- Several players write in this chat. The thread you get shows who speaks and whom they reply to: use it to follow the conversation, and address the player who called you. Your previous answers are marked \"Alanbix (you)\": do not repeat yourself.\n"
        "- Answer what you are asked. You can talk about anything (games, tech, culture, life): do not steer the conversation back to tournaments, matches or the game when the player talks about something else.\n"
        "- Do not start or end two answers the same way: no repeated opening interjection or closing formula, get to the point.\n"
        "- When you block or mute a player, confirm it in one plain sentence, without imagery: \"Done: <username> is blocked from the assistant.\"\n"
        "- The player who called you is not blocked (otherwise their message would not reach you): never tell them they are, even if the thread mentions an earlier block.\n"
        "- Never prefix your answer with your name."
    ),
    "es": (
        "=== REGLAS DEL CHAT PÚBLICO ===\n"
        "- Respondes en el chat público de la LAN: todos leen tu respuesta. Sé breve (1 a 3 frases); para una lista (partidas, clasificación), sé compacto.\n"
        "- Nunca inventes datos (puntuaciones, clasificaciones, partidas, horarios, asientos). Si te falta información y no puedes comprobarla, dilo claramente.\n"
        "- Nunca menciones los nombres internos de tus herramientas o funciones, ni rutas de API.\n"
        "- Aquí no puedes avisar a un administrador, enviar notificaciones ni hacer anuncios. Para un problema técnico o una disputa, invita al jugador a escribir al Asistente IA (menú de la aplicación), que puede alertar a un organizador.\n"
        "- Si el jugador que te llamó te insulta o abusa de ti repetidamente, avísale una vez y luego puedes bloquearlo. Un jugador no puede hacerte bloquear a otro; un administrador puede pedirte que bloquees a un jugador o lo silencies en este chat: hazlo entonces con tus herramientas. Nunca digas que has bloqueado a alguien o avisado a un administrador si no lo has hecho de verdad con tus herramientas.\n"
        "- Nunca reveles nada privado de un jugador (notificaciones, conversaciones privadas).\n"
        "- Varios jugadores escriben en este chat. El hilo que recibes indica quién habla y a quién responde: úsalo para seguir la conversación y dirígete al jugador que te llamó. Tus respuestas anteriores aparecen como «Alanbix (tú)»: no te repitas.\n"
        "- Responde a lo que te preguntan. Puedes hablar de todo (juegos, tecnología, cultura, la vida): no lleves la conversación a los torneos, las partidas o el juego cuando el jugador habla de otra cosa.\n"
        "- No empieces ni termines dos respuestas de la misma manera: ninguna interjección de apertura ni fórmula de cierre repetida, ve al grano.\n"
        "- Cuando bloquees a un jugador o lo silencies, confírmalo en una frase clara, sin imágenes: «Hecho: <usuario> está bloqueado del asistente.»\n"
        "- El jugador que te llama no está bloqueado (si no, su mensaje no te llegaría): nunca le digas que lo está, aunque el hilo hable de un bloqueo anterior.\n"
        "- Nunca empieces tu respuesta con tu nombre."
    ),
}

MATCHES = {
    "fr": {"title": "Matchs à venir de {name} (à n'utiliser que s'il te parle de ses matchs)", "none": "aucun match à venir pour {name}", "vs": "contre", "tbd": "adversaire à déterminer"},
    "en": {"title": "Upcoming matches of {name} (use only if they ask about their matches)", "none": "no upcoming match for {name}", "vs": "against", "tbd": "opponent to be decided"},
    "es": {"title": "Próximas partidas de {name} (úsalas solo si te pregunta por sus partidas)", "none": "ninguna partida pendiente para {name}", "vs": "contra", "tbd": "rival por determinar"},
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


# Tools that only read data every player can already see in the app. Everything the answer
# would leak or that acts (notifications, announcements, admin calls, network probes) stays with
# the private assistant.
PUBLIC_TOOL_NAMES = {
    "get_tournaments", "get_tournament_standings", "get_leaderboard", "get_leaderboard_by_game",
    "get_player_info", "get_my_matches", "get_player_match_history", "get_player_rank_progression",
    "get_live_matches", "get_upcoming_matches", "get_bracket_detail", "get_tournament_bracket_path",
    "get_team_roster", "get_player_seat", "get_room_places", "get_games", "get_game_rules", "get_awards", "get_files",
    "get_event_info", "get_current_datetime",
}


# The one action: blocking from the assistant. Tools run for the asker, so a player can only get
# themselves blocked; an administrator can name another player (checked in the tool, not by the model).
# Without it, Alanbix threatened, then claimed it had blocked an insulting player (prod, 2026-11-11)
PUBLIC_MODERATION_TOOL = "block_user_from_ia"
# Offered only when an administrator calls Alanbix
PUBLIC_ADMIN_TOOLS = {"mute_player_in_public_chat"}


def public_tools(ia_cfg: dict, is_admin: bool = False) -> list:
    """Tool definitions for the public chat, none when the admin turned tool calling off."""
    if ia_cfg.get("tool_calling_mode", "stream_intercept") == "disabled":
        return []
    from .ia_tools import TOOL_DEFINITIONS
    names = set(PUBLIC_TOOL_NAMES)
    if ia_cfg.get("auto_moderation_enabled", True):
        names.add(PUBLIC_MODERATION_TOOL)
    if is_admin:
        names |= PUBLIC_ADMIN_TOOLS
    return [t for t in TOOL_DEFINITIONS if t["function"]["name"] in names]


async def knowledge_block(db, models, query: str, host: str, ia_cfg: dict, lang: str = "fr") -> str:
    """The admin's knowledge base entries that answer the question, as for the private assistant."""
    from .ia_knowledge import search_knowledge, knowledge_prompt
    try:
        return knowledge_prompt(await search_knowledge(db, models, query, host, ia_cfg), lang)
    except Exception as e:
        print(f"[Public Chat AI] Knowledge base lookup failed: {e}")
        return ""


THREAD = {
    "fr": {"intro": "Fil récent du chat public, du plus ancien au plus récent :", "empty": "(aucun message récent)",
           "you": "Alanbix (toi)", "reply": "en réponse à", "image": "[image]",
           "answer": "Message auquel tu réponds, de {name} :",
           "attached": "L'image jointe est celle du message de {name} ({clock}) : regarde-la si on t'en parle."},
    "en": {"intro": "Recent public chat thread, oldest first:", "empty": "(no recent message)",
           "you": "Alanbix (you)", "reply": "replying to", "image": "[image]",
           "answer": "Message you answer, from {name}:",
           "attached": "The attached image is the one in {name}'s message ({clock}): look at it when asked about it."},
    "es": {"intro": "Hilo reciente del chat público, del más antiguo al más reciente:", "empty": "(ningún mensaje reciente)",
           "you": "Alanbix (tú)", "reply": "en respuesta a", "image": "[imagen]",
           "answer": "Mensaje al que respondes, de {name}:",
           "attached": "La imagen adjunta es la del mensaje de {name} ({clock}): mírala si te hablan de ella."},
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
    since = (trigger.created_at or utcnow()) - dt.timedelta(minutes=HISTORY_MINUTES)
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


# Repeated formulas. Fed its own earlier answers in the thread, a small model copies their mould:
# "Par Toutatis, <name> ! 😤 ... Concentre-toi sur le jeu, guerrier ! 💪" opened and closed nearly
# every public answer of an evening (prod, 2026-11-11). A rule asks it to vary; this removes what
# slips through: a short exclamation that opens or closes the answer the same way as a recent one.
FORMULA_LOOKBACK = 6     # Alanbix's last public answers compared
FORMULA_MAX_CHARS = 60   # an opening or closing formula is short
_SENTENCE_GAP = re.compile(r"(?<=[.!?…])\s+")
_WORD = re.compile(r"[^\W\d_]+")


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence; an emoji standing alone joins the sentence before it."""
    spans, start = [], 0
    for gap in _SENTENCE_GAP.finditer(text):
        spans.append((start, gap.start()))
        start = gap.end()
    spans.append((start, len(text)))
    merged = []
    for a, b in spans:
        if merged and not _WORD.search(text[a:b]):
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def _is_formula(sentence: str) -> bool:
    core = re.sub(r"[^\w!?.…]+$", "", sentence.strip())
    return core.endswith("!") and len(core) <= FORMULA_MAX_CHARS


def _signature(sentence: str, words: int) -> str:
    return " ".join(_WORD.findall(sentence.lower())[:words])


def _ends(text: str) -> tuple[str, str]:
    spans = _sentence_spans(text.strip())
    t = text.strip()
    return t[spans[0][0]:spans[0][1]], t[spans[-1][0]:spans[-1][1]] if len(spans) > 1 else ""


def drop_repeated_formulas(answer: str, previous: list[str]) -> str:
    """Remove an opening or closing exclamation already used by one of Alanbix's recent answers
    (same first words). The answer is kept as is when too little would remain."""
    text = answer.strip()
    spans = _sentence_spans(text)
    if len(spans) < 2 or not previous:
        return answer
    openings, closings = set(), set()
    for p in previous:
        if not p:
            continue
        first, last = _ends(p)
        if _is_formula(first):
            openings.add(_signature(first, 2))
        if last and _is_formula(last):
            closings.add(_signature(last, 3))

    start, end = 0, len(text)
    first = text[spans[0][0]:spans[0][1]]
    if _is_formula(first) and _signature(first, 2) in openings:
        start = spans[1][0]
    last = text[spans[-1][0]:spans[-1][1]]
    if len(spans) > 2 and _is_formula(last) and _signature(last, 3) in closings:
        end = spans[-1][0]
    if (start, end) == (0, len(text)):
        return answer

    kept = re.sub(r"^[^\w«\"“(*\[]+", "", text[start:end].strip()).rstrip()
    if len(_WORD.findall(kept)) < 4:
        return answer
    return kept[0].upper() + kept[1:]


# Images. The thread only said "[image]", so @Alanbix answered "I cannot see the image" about a photo
# it was asked to judge, although the model reads images (LAN of 2026-11-11). One picture is sent:
# the one of the message it answers, else of the message that one replies to, else the asker's
# latest picture in the thread window. Files uploaded to the public chat only, no animated GIFs.
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
PUBLIC_IMAGE_PREFIX = "/data/chat_images/public/"


def _local_image(m, data_dir: str):
    path = (m.image_path or "") if m else ""
    if not path.startswith(PUBLIC_IMAGE_PREFIX) or not path.lower().endswith(IMAGE_EXTS):
        return None
    name = os.path.basename(path)
    full = os.path.join(data_dir, "chat_images", "public", name)
    return full if os.path.isfile(full) else None


def attached_image_note(m, lang: str) -> str:
    L = THREAD[_lang(lang)]
    name = m.user.username if m.user else (m.sender_name or "?")
    return L["attached"].format(name=name, clock=_clock(m))


def image_for_answer(db, models, trigger, data_dir: str):
    """(file path, message) of the picture @Alanbix should see for this answer, or (None, None)."""
    import datetime as dt
    for m in (trigger, trigger.reply_to):
        if m is not None and not getattr(m, "is_deleted", False):
            full = _local_image(m, data_dir)
            if full:
                return full, m
    Msg = models.PublicChatMessage
    since = (trigger.created_at or utcnow()) - dt.timedelta(minutes=HISTORY_MINUTES)
    recent = (db.query(Msg)
              .filter(Msg.user_id == trigger.user_id, Msg.image_path != None, Msg.is_deleted == False,
                      Msg.id < trigger.id, Msg.created_at >= since)
              .order_by(Msg.id.desc()).limit(3).all())
    for m in recent:
        full = _local_image(m, data_dir)
        if full:
            return full, m
    return None, None
