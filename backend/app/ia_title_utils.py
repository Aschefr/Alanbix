"""
ia_title_utils.py — Shared utilities for AI conversation title generation.

These functions are used by both:
- routers/ia.py  (auto-title endpoint and _bg_title background task)
- ia_queue.py    (_process_title_suggestion worker)

Keeping them here avoids circular imports between ia.py and ia_queue.py.
"""
import os
import re
import json


def _is_default_title(title: str) -> bool:
    """Return True if the conversation title is still a default/untouched placeholder.
    Reads all i18n files dynamically to detect every language's default title.
    """
    if not title or not title.strip():
        return True
    # Hard-coded fallback values (DB model default + historical legacy)
    defaults = {
        "nouvelle conversation", "new conversation", "nueva conversación",
        "nouvelle discussion", "new discussion", "nueva discusión", "",
    }
    # Dynamically load `ai_default_chat_title` from all available i18n JSON files
    _this_dir = os.path.dirname(__file__)
    i18n_dirs = [
        os.path.normpath(os.path.join(_this_dir, "..", "static", "i18n")),
        os.path.normpath(os.path.join(_this_dir, "..", "data", "i18n")),
    ]
    for d in i18n_dirs:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fname), "r", encoding="utf-8-sig") as fh:
                    data = json.load(fh)
                v = data.get("ai_default_chat_title", "")
                if v:
                    defaults.add(v.strip().lower())
            except Exception:
                pass
    res = title.strip().lower() in defaults
    print(f"[BG_TITLE] Title '{title}' is default? {res} (Checked against: {defaults})", flush=True)
    return res


def _build_title_prompt(excerpt: str) -> str:
    """Build the prompt string for a title-generation Ollama call via /api/generate.
    Uses simple, direct instruction in French without complex Unicode characters.
    """
    return (
        "Genere un titre court (maximum 5 mots) pour synthetiser cette conversation.\n"
        "Le titre doit etre dans la meme langue que l'echange.\n"
        "Reponds UNIQUEMENT avec le titre brut, sans introduction, sans guillemets ni ponctuation finale.\n\n"
        f"Echange :\n{excerpt}"
    )


def _clean_title(raw: str, max_len: int = 50) -> str | None:
    """Clean and normalise a raw title returned by an LLM.
    Returns None if the result is unusable (empty or too short).
    """
    t = raw.strip()
    # Strip surrounding quotes / backticks / markdown bold-italic
    t = t.strip('"\'`')
    t = re.sub(r'^\*{1,2}|\*{1,2}$', '', t).strip()
    t = re.sub(r'^_{1,2}|_{1,2}$', '', t).strip()
    # Remove common LLM prefixes (multilingual)
    prefixes = (
        "titre :", "title :", "título :", "titel :",
        "titre:", "title:", "título:", "titel:",
        "titre de la conversation :", "titre de la conversation:",
    )
    tl = t.lower()
    for p in prefixes:
        if tl.startswith(p):
            t = t[len(p):].strip()
            tl = t.lower()
            break
    # Strip leading/trailing stray punctuation
    t = re.sub(r'^[\s\-–—:]+|[\s.!?]+$', '', t)
    # Smart truncation at word boundary
    if len(t) > max_len:
        truncated = t[:max_len].rsplit(' ', 1)[0]
        t = truncated if len(truncated) >= 3 else t[:max_len]
    # Reject if result is too short to be meaningful
    if not t or len(t) < 3:
        return None
    return t


