"""Who the players named in a public chat question are, given to the model with their moderation status.

Asked whether a player banned days earlier could come back, @Alanbix took the (manga-like)
username for the manga character, then claimed to remember their talks (prod, 2026-11-14): he only sees the
last 30 minutes of the chat and nothing told him that the name is a player. So when a message names registered
players, the code says who they are and where their block or mute stands today (a ban can be lifted by an
administrator), so he can play on it without inventing. The reason of a block is never given: everyone reads
the public chat.
"""
import datetime as dt
import re
import unicodedata
import zoneinfo

from .clock import utcnow

MAX_NAMED = 3
MIN_NAME_CHARS = 3   # "le", "de"... as usernames would match ordinary words

TEXT = {
    "fr": {
        "intro": "Joueurs nommés dans le message (données de l'application, à jour) :",
        "player": "joueur inscrit à cette LAN",
        "admin": "administrateur de cette LAN",
        "blocked": "bloqué de l'assistant depuis le {date}, toujours bloqué",
        "blocked_no_date": "actuellement bloqué de l'assistant",
        "unblocked": "bloqué de l'assistant le {date}, débloqué depuis par un administrateur",
        "unblocked_on": "bloqué de l'assistant le {date}, débloqué par un administrateur le {end}",
        "muted": "muet dans le chat public jusqu'au {date}",
        # Asked, not just allowed: with "tu peux plaisanter" gemma4:e4b played on an unban 2 times in 30,
        # with this 27 in 30 (Veille, 14th round)
        "outro": ("Ce sont de vraies personnes de la LAN, pas des personnages. Si un joueur a été débloqué, dis-le et "
                  "taquine-le gentiment là-dessus (il est de retour, mais tu l'as à l'œil). Tu ne connais pas la raison "
                  "d'un blocage et tu ne te souviens pas de vos anciennes conversations : n'invente ni l'une ni les autres."),
    },
    "en": {
        "intro": "Players named in the message (app data, up to date):",
        "player": "a player registered at this LAN",
        "admin": "an administrator of this LAN",
        "blocked": "blocked from the assistant since {date}, still blocked",
        "blocked_no_date": "currently blocked from the assistant",
        "unblocked": "blocked from the assistant on {date}, unblocked since by an administrator",
        "unblocked_on": "blocked from the assistant on {date}, unblocked by an administrator on {end}",
        "muted": "muted in the public chat until {date}",
        "outro": ("They are real people at the LAN, not characters. If a player was unblocked, say so and tease them "
                  "kindly about it (they are back, but you are keeping an eye on them). You do not know the reason of "
                  "a block and you do not remember your past conversations with them: invent neither."),
    },
    "es": {
        "intro": "Jugadores nombrados en el mensaje (datos de la aplicación, al día):",
        "player": "jugador inscrito en esta LAN",
        "admin": "administrador de esta LAN",
        "blocked": "bloqueado del asistente desde el {date}, sigue bloqueado",
        "blocked_no_date": "actualmente bloqueado del asistente",
        "unblocked": "bloqueado del asistente el {date}, desbloqueado después por un administrador",
        "unblocked_on": "bloqueado del asistente el {date}, desbloqueado por un administrador el {end}",
        "muted": "silenciado en el chat público hasta el {date}",
        "outro": ("Son personas reales de la LAN, no personajes. Si un jugador ha sido desbloqueado, dilo y bromea "
                  "con cariño sobre ello (ha vuelto, pero lo tienes vigilado). No conoces el motivo de un bloqueo ni "
                  "recuerdas vuestras conversaciones pasadas: no inventes ni lo uno ni lo otro."),
    },
}
BLOCK_NOTIFICATION = "notif_ia_blocked_title"


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn")


def _when(stamp) -> str:
    local = stamp.replace(tzinfo=dt.timezone.utc).astimezone(zoneinfo.ZoneInfo("Europe/Paris"))
    return local.strftime("%d/%m %H:%M")


def named_players(db, models, question: str, asker) -> list:
    """Registered players whose username is written in the question, the asker and Alanbix aside."""
    text = _plain(question)
    found = []
    for user in db.query(models.User).order_by(models.User.id).all():
        name = _plain(user.username)
        if len(name) < MIN_NAME_CHARS or name == "alanbix" or (asker is not None and user.id == asker.id):
            continue
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text):
            found.append(user)
    return found[:MAX_NAMED]


EARLIER_MESSAGES = 2
EARLIER_MINUTES = 30   # the thread Alanbix sees


def asker_earlier_text(db, models, trigger) -> str:
    """The asker's last messages before this one in the thread, where a later "him" was named."""
    Msg = models.PublicChatMessage
    since = (trigger.created_at or utcnow()) - dt.timedelta(minutes=EARLIER_MINUTES)
    rows = (db.query(Msg.content)
            .filter(Msg.user_id == trigger.user_id, Msg.is_deleted == False, Msg.id < trigger.id,
                    Msg.created_at >= since)
            .order_by(Msg.id.desc()).limit(EARLIER_MESSAGES).all())
    return " ".join(r[0] or "" for r in rows)


def _last_block(db, models, user):
    """When the player was last blocked: the stored date, else the notification sent at the time
    (blocks older than the date column)."""
    if user.ia_blocked_at:
        return user.ia_blocked_at
    notes = (db.query(models.Notification)
             .filter(models.Notification.user_id == user.id, models.Notification.type == "system")
             .order_by(models.Notification.id.desc()).limit(50).all())
    for note in notes:
        if ((note.metadata_json or {}).get("i18n") or {}).get("title") == BLOCK_NOTIFICATION:
            return note.created_at
    return None


def _status(db, models, user, L) -> str:
    facts = [L["admin"] if user.is_admin else L["player"]]
    blocked_at = _last_block(db, models, user)
    if user.ia_blocked:
        facts.append(L["blocked"].format(date=_when(blocked_at)) if blocked_at else L["blocked_no_date"])
    elif blocked_at:
        if user.ia_unblocked_at and user.ia_unblocked_at >= blocked_at:
            facts.append(L["unblocked_on"].format(date=_when(blocked_at), end=_when(user.ia_unblocked_at)))
        else:
            facts.append(L["unblocked"].format(date=_when(blocked_at)))
    if user.public_chat_muted_until and user.public_chat_muted_until > utcnow():
        facts.append(L["muted"].format(date=_when(user.public_chat_muted_until)))
    return f"- {user.username} : {' ; '.join(facts)}."


def named_players_block(db, models, question: str, asker, lang: str) -> str:
    """The card of the players named in the question, or '' when it names none."""
    players = named_players(db, models, question, asker)
    if not players:
        return ""
    L = TEXT.get(lang) or TEXT["fr"]
    return "\n".join([L["intro"], *(_status(db, models, u, L) for u in players), L["outro"]])


def set_ia_blocked(user, blocked: bool) -> None:
    """Block or unblock a player from the assistant, keeping when, so Alanbix knows a ban was lifted."""
    blocked = bool(blocked)
    if blocked and not user.ia_blocked:
        user.ia_blocked_at, user.ia_unblocked_at = utcnow(), None
    elif not blocked and user.ia_blocked:
        user.ia_unblocked_at = utcnow()
    user.ia_blocked = blocked
