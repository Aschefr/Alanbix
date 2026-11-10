"""When @Alanbix cannot answer in the public chat (user's request, 2026-11-10).

Everyone sees a light-hearted "Alanbix is unavailable" line, picked among a few variants, in the LAN's
language. The admins get an alert with the reason, at most once every ADMIN_ALERT_EVERY seconds: a
server that stays down must not bury them under one alert per mention.
"""
import random
import time

import httpx

from .ia_utils import ModelMissing

# Number of public_chat_alanbix_down_N keys in every language file
VARIANTS = 5
ADMIN_ALERT_EVERY = 30 * 60

_last_alert = 0.0
_failures = 0  # since the last alert, this one included


def reason_of(error) -> str:
    """Short code of a failure, from the exception raised or the queue's code."""
    if isinstance(error, str):
        return error
    if isinstance(error, ModelMissing):
        return "model_missing"
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "unreachable"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    return "error"


def _lan_texts(db, models) -> dict:
    from .routers.awards import get_i18n_dict
    row = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    return get_i18n_dict(row.value if row and row.value else "fr")


def public_line(db, models) -> str:
    """One of the variants, in the LAN's language (French when a key is missing)."""
    from .routers.awards import get_i18n_dict
    key = f"public_chat_alanbix_down_{random.randint(1, VARIANTS)}"
    return _lan_texts(db, models).get(key) or get_i18n_dict("fr").get(key) or "Alanbix est indisposé."


def should_alert(now: float | None = None) -> int:
    """Count this failure; return how many failures the alert covers, or 0 when it is too soon."""
    global _last_alert, _failures
    now = time.time() if now is None else now
    _failures += 1
    if now - _last_alert < ADMIN_ALERT_EVERY:
        return 0
    count, _failures, _last_alert = _failures, 0, now
    return count


async def alert_admins(db, models, reason: str, detail: str = "", model: str = "") -> bool:
    """The admins' alert, when the anti-spam window allows it. Returns whether one was sent.
    One text per reason (notif_public_ai_down_<reason>), so each admin reads it in their own language."""
    count = should_alert()
    if not count:
        return False
    from .routers.notifications import localized_text, notify_user
    params = {"count": count, "model": model or "?", "minutes": ADMIN_ALERT_EVERY // 60, "detail": detail[:300]}
    title, body, meta = localized_text(db, "notif_public_ai_down_title", f"notif_public_ai_down_{reason}", params, icon="🤖")
    for admin in db.query(models.User).filter(models.User.is_admin == True).all():  # noqa: E712
        await notify_user(db, admin.id, "system", title, body, link="/dashboard/admin", data=meta)
    return True
