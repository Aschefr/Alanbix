"""Which waiting AI request a free server takes, and how the request is pointed at that server.

Before, each request got its server when it entered the queue (round-robin, blind to load), so a
request could wait behind the slow server while the fast one sat idle. Now each server has its own
worker; when it is free it takes the most urgent request it can serve. The fast server frees up
more often, so it naturally serves more. A conversation goes back to the server that served it last
only when that server is free at that moment: the Ollama prompt cache is a bonus, never a wait.
"""
from .ia_utils import is_openai_host


def _url(u: str) -> str:
    return (u or "").rstrip("/")


def current_model(entry) -> str:
    p = entry.payload
    if entry.task_type == "chat":
        return (p.get("req_data") or {}).get("model") or ""
    return p.get("model") or ""


def serial_key(entry):
    """Who the request is for: one request at a time per player (public chat answers are queued as
    Alanbix, user 0, with the player in asker_id)."""
    return entry.user_id or entry.payload.get("asker_id") or None


def model_for(entry, inst: dict, default_model: str, names: list) -> str | None:
    """The model this server would answer with, or None when it cannot take the request."""
    p = entry.payload
    host = p.get("ollama_host")
    if p.get("pin_host") and _url(host) != _url(inst["url"]):
        return None
    # Request fields differ between Ollama and OpenAI-style servers: never cross over
    if host and is_openai_host(host) != is_openai_host(inst["url"]):
        return None
    current = current_model(entry)
    if _url(host) == _url(inst["url"]) and current:
        return current  # the server its caller picked: always allowed, as before
    want = current if p.get("model_fixed") else (inst.get("model") or default_model or current)
    if not want:
        return None
    if names and want not in names and f"{want}:latest" not in names:
        return None
    return want


def pick(pending: list, inst: dict, default_model: str, names: list, busy: set, last_host: dict):
    """(entry, model) for the free server `inst`, or (None, None).

    pending: waiting entries; most urgent first (priority, then age). busy: serial keys of players
    already being answered. last_host: conversation id -> server that answered it last. Among the
    requests of the most urgent level this server can take, one whose conversation it served last
    goes first; otherwise the oldest."""
    url = _url(inst["url"])
    chosen, level = None, None
    for e in sorted(pending, key=lambda e: (e.priority, e.created_at)):
        if e.cancelled:
            continue
        key = serial_key(e)
        if key and key in busy:
            continue
        model = model_for(e, inst, default_model, names)
        if not model:
            continue
        sticky = e.conversation_id and _url(last_host.get(e.conversation_id)) == url
        if chosen is None:
            chosen, level = (e, model), e.priority
            if sticky:
                break
            continue
        if e.priority != level:
            break
        if sticky:
            chosen = (e, model)
            break
    return chosen if chosen else (None, None)


def bind(entry, inst: dict, model: str):
    """Point the request at this server and model, as the failover already does for a lost server."""
    p = entry.payload
    p["ollama_host"] = inst["url"]
    if entry.task_type == "chat":
        p["req_data"] = {**(p.get("req_data") or {}), "model": model}
        p["model_info"] = {"model": model, "instance": inst.get("label", "Default")}
    else:
        p["model"] = model


def estimated_wait(position: int, averages: list, fallback: float) -> int:
    """Seconds before a request at this position starts: the servers work side by side, so the
    queue drains at the sum of their speeds (one answer every `average` seconds each)."""
    if position <= 0:
        return 0
    speeds = [1.0 / a for a in averages if a and a > 0]
    if not speeds:
        speeds = [1.0 / max(fallback, 0.1)]
    return round(position / sum(speeds))
