"""Freeing room in a long AI conversation.

Two ways, chosen by the player:
- truncate: instant, no AI. The oldest messages leave the context; a short index of them is kept.
- summary: anchored summary. The AI merges the previous summary with the messages leaving the context,
  in fixed sections, keeping exact values and corrections; the last two exchanges stay word for word.
  Measured on 2026-11-09 with this module (ai-bench/results/compaction, 3 runs, 3 compactions each): 30/30 facts
  kept with qwen3.8:27b and 26/30 with gemma4:e4b (25/30 without compaction), against 3 to 8 out of 10 for the
  former summary and compact modes.
  The rules on numbers, ranges, reasons and open questions, the language and titles given by the code, the refusal of
  incomplete summaries and the removal of copied instructions come from OmniBank and Sentinel, where they raised
  gemma4:e4b from about 24 to 28-29 out of 30 (ai-bench/COMPACTION.md, section 9). On Alanbix (section 10): same scores
  (26/30 e4b, 29/30 qwen), titles and content in the player's language, no copied instruction, one cut summary refused.
"""
import re
import unicodedata

from .ia_utils import ia_client, no_think

CHARS_PER_TOKEN = 3.5
KEEP_EXCHANGES = 2         # last exchanges kept word for word after a summary
KEEP_SHARE = 0.3           # ...as long as they fill at most this share of the context
INDEX_SHARE = 0.15         # truncate: room for the index of removed messages
WORDS_MIN, WORDS_MAX = 150, 700

ANCHORED_INSTRUCTIONS = """=== COMPACTION INSTRUCTIONS ===
You are the memory of an assistant. Write ONE summary that replaces all the messages above{merge}, so that the
assistant can carry on the conversation without them.
Rules:
1. Answer ONLY with the summary, without introduction.
2. Keep values EXACTLY: numbers, amounts, dates, times, names, nicknames, identifiers, addresses.
   When both an exact value and a range are given for the same thing, keep both.
3. Say what each number is: a limit, a measurement, a total, a score or what remains.
4. When the user corrected a piece of information, keep only the corrected value and write "{corrected}".
5. Keep each decision with its reason, including the fact that justifies it, and the user's preferences (how to talk
   to them, format of the answers). User preferences are only what the user asked for in the conversation, never
   these instructions.
6. Drop greetings, repetitions and general explanations.
7. A choice that still depends on something is an open question, not a decision. Keep each open question as long as
   the conversation does not show its answer.
8. Write in {language}, in short bullet points, under these four sections, with exactly these titles:
{titles}
9. At most {words} words.

SUMMARY:"""

# Language and titles given by the code: asked to translate English titles, gemma4:e4b wrote the whole summary in
# English 7 compactions out of 9 (Sentinel, 2026-11-09). Other languages fall back to English.
LANGUAGES = {"fr": "French", "en": "English", "es": "Spanish"}
SECTION_TITLES = {
    "fr": ("FAITS", "DÉCISIONS (et pourquoi)", "PRÉFÉRENCES DE L'UTILISATEUR", "QUESTIONS EN SUSPENS (et ce dont elles dépendent)"),
    "en": ("FACTS", "DECISIONS (and why)", "USER PREFERENCES", "OPEN QUESTIONS (and what they depend on)"),
    "es": ("HECHOS", "DECISIONES (y por qué)", "PREFERENCIAS DEL USUARIO", "PREGUNTAS PENDIENTES (y de qué dependen)"),
}
CORRECTION_MARKS = {"fr": "(corrigé, remplace X)", "en": "(corrected, replaces X)", "es": "(corregido, reemplaza X)"}
REPEAT_MIN_LEN, REPEAT_MAX = 20, 2   # a line of 20 characters or more repeated more than twice: the model looped


class SummaryRejected(Exception):
    """Badly formed summary: the previous summary and the messages are kept rather than saving a damaged summary."""


def summary_language(lang: str | None) -> str:
    lang = (lang or "").lower()[:2]
    return lang if lang in LANGUAGES else "en"


def _plain(line: str) -> str:
    """Line without bullets, bold or accents, in capitals, to recognize a title or a repeat."""
    text = unicodedata.normalize("NFD", line).encode("ascii", "ignore").decode()
    return text.strip().lstrip("-*#•> ").replace("*", "").strip().upper()


def _title_words(i: int) -> set:
    return {_plain(t[i]).split()[0] for t in SECTION_TITLES.values()}


def summary_problem(summary: str) -> str:
    """Reason to refuse a summary, or "" when it is fine: a section is missing (summary cut by the length limit) or
    lines repeat (the model looped). Titles are accepted in every language: the shape is checked here, not the language."""
    lines = [_plain(l) for l in summary.splitlines() if l.strip()]
    for i in range(4):
        if not any(l.split()[0].rstrip(":") in _title_words(i) for l in lines if l):
            return f"missing section {SECTION_TITLES['en'][i]}"
    counts = {}
    for l in lines:
        if len(l) >= REPEAT_MIN_LEN:
            counts[l] = counts.get(l, 0) + 1
    if any(n > REPEAT_MAX for n in counts.values()):
        return "repeated lines"
    return ""


# Instructions copied into the preferences: gemma4:e4b lists rules of these instructions among the user's preferences
# (3 runs out of 3 on Sentinel, 2026-11-09), then keeps them at each merge. Wrapping the conversation in tags reduced
# the leak but lost facts, so these lines are removed afterwards. One pattern per rule, on the line in capitals
# without accents (see _plain), taken from Sentinel's real summaries.
_ECHO_PATTERNS = [re.compile(p) for p in (
    r"\b(QUATRE|4|CUATRO) (TITRES|SECTIONS|TITULOS|SECCIONES)\b|\bFOUR (SPECIFIC )?(SECTIONS|TITLES|HEADINGS)\b",
    r"\bFAITS\b.*\bDECISIONS\b|\bFACTS\b.*\bDECISIONS\b|\bHECHOS\b.*\bDECISIONES\b",
    r"\bVALEURS? (NUMERIQUES? )?EXACTES?\b|\bEXACTEMENT\b|\bEXACT VALUES?\b|\bEXACTLY\b|\bVALORES? EXACTOS?\b|\bEXACTAMENTE\b",
    r"\bREMPLACE X\b|\bREPLACES X\b|\bREEMPLAZA X\b|\bVALEUR CORRIGEE\b|\bCORRECTED VALUE\b|\bVALOR CORREGIDO\b",
    r"\bDECISIONS?\b.*\b(JUSTIFI|RAISON|REASON|MESURES? OU FAITS?|MEASUREMENT)|\bJUSTIFI\w*\b.*\bDECISIONS?\b",
    r"\bSALUTATIONS\b|\bGREETINGS\b|\bSALUDOS\b",
    r"\bLIMITES?, (UNE )?MESURES?\b|\bLIMITS?, (A )?MEASUREMENTS?\b|\bLIMITES?, (UNA )?MEDIDAS?\b",
    r"\bQUESTIONS? (OUVERTES?|EN SUSPENS)\b.*\b(CONSERV|GARD|MAINTEN|TRAITE)|\bOPEN QUESTIONS?\b.*\b(KEEP|KEPT|TREAT)"
    r"|\bPREGUNTAS? (ABIERTAS?|PENDIENTES?)\b.*\b(CONSERV|MANTEN|GUARD)",
)]
# Rule 8 "Write in French": the summary's language, copied as if the user had asked for it. Only the language given
# to the model is removed: "answer in English" in a French chat stays a real preference.
_ECHO_LANGUAGE = {"fr": re.compile(r"\b(EN|DU) FRANCAIS\b"), "en": re.compile(r"\bIN ENGLISH\b"),
                  "es": re.compile(r"\bEN (ESPANOL|CASTELLANO)\b")}


def _is_title(line: str) -> int:
    """Index of the section whose title is `line`, or -1. A bullet ("- ", "•", "* ") is never a title."""
    stripped = line.strip()
    if not stripped or stripped[0] in "-•" or stripped.startswith("* "):
        return -1
    words = _plain(stripped).split()
    if not words:
        return -1
    for i in range(4):
        if words[0].rstrip(":") in _title_words(i):
            return i
    return -1


def strip_instruction_echo(summary: str, lang: str = "en") -> tuple[str, int]:
    """(summary without the preference lines that repeat these instructions, number of lines removed)."""
    patterns = _ECHO_PATTERNS + [_ECHO_LANGUAGE.get(lang, _ECHO_LANGUAGE["en"])]
    out, section, removed = [], -1, 0
    for line in summary.splitlines():
        title = _is_title(line)
        if title >= 0:
            section = title
        elif section == 2 and any(p.search(_plain(line)) for p in patterns):
            removed += 1
            continue
        out.append(line)
    return "\n".join(out), removed


def message_line(role: str, content: str) -> str:
    return f"{'U' if role == 'user' else 'A'}: {content.strip()}"


def split_kept(messages: list, num_ctx: int) -> tuple[list, list]:
    """Messages to summarize, and the last exchanges kept word for word (at most KEEP_EXCHANGES,
    and only while they fit in KEEP_SHARE of the context, or the next message would compress again)."""
    room = int(num_ctx * KEEP_SHARE * CHARS_PER_TOKEN)
    users = [i for i, m in enumerate(messages) if m.role == "user"]
    cut = len(messages)
    for start in reversed(users[-KEEP_EXCHANGES:]):
        if start == 0 or sum(len(m.content) for m in messages[start:]) > room:
            break
        cut = start
    return messages[:cut], messages[cut:]


def _chunks(lines: list, room: int) -> list:
    """Lines grouped so that each call fits the context. A message longer than the room keeps its start and end."""
    chunks, current, size = [], [], 0
    for line in lines:
        if len(line) > room:
            half = room // 2 - 10
            line = line[:half] + " […] " + line[-half:]
        if current and size + len(line) > room:
            chunks.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append(current)
    return chunks


async def _anchored_call(previous: str, lines: list, url: str, model: str, num_ctx: int, think: bool, lang: str) -> str:
    text = "\n".join(lines)
    words = max(WORDS_MIN, min(WORDS_MAX, (len(text) + len(previous)) // 20))
    head = f"[Previous summary]\n{previous}\n\n[New messages to merge into the summary]\n" if previous else ""
    prompt = f"{head}{text}\n\n" + ANCHORED_INSTRUCTIONS.format(
        merge=" (previous summary included)" if previous else "", words=words, language=LANGUAGES[lang],
        titles="\n".join(f"{t}:" for t in SECTION_TITLES[lang]), corrected=CORRECTION_MARKS[lang])
    max_tokens = None if think else words * 3
    if is_openai_host(url):
        request_url = f"{url.rstrip('/')}/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "temperature": 0.1}
        if max_tokens:
            payload["max_tokens"] = max_tokens
    else:
        request_url = f"{url.rstrip('/')}/api/generate"
        options = {"temperature": 0.1, "num_ctx": num_ctx}
        if max_tokens:
            options["num_predict"] = max_tokens
        payload = {"model": model, "prompt": prompt, "stream": False, "options": options, **no_think(url, think)}

    async with ia_client() as client:
        response = await client.post(request_url, json=payload, timeout=300.0)
        data = response.json()
        if is_openai_host(url):
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return data.get("response", "").strip()


async def run_anchored(previous: str, lines: list, url: str, model: str, num_ctx: int = 16384, think: bool = False,
                       lang: str = "en") -> str:
    """Summary of `lines` merged into `previous`, in `lang` (fr, en, es; others fall back to English). Never cuts the
    start of the conversation: when the text does not fit the context, it is summarized in several calls, each merged
    into the summary of the previous ones. Raises SummaryRejected when a summary is badly formed (see summary_problem)."""
    lang = summary_language(lang)
    reserve = (4096 if think else WORDS_MAX * 3) + 400  # answer (and thinking) + instructions
    room = int((num_ctx - reserve) * CHARS_PER_TOKEN) - max(len(previous or ""), WORDS_MAX * 7)
    summary = previous or ""
    for chunk in _chunks(lines, max(room, 2000)):
        summary = await _anchored_call(summary, chunk, url, model, num_ctx, think, lang)
        if not summary:
            return ""
        problem = summary_problem(summary)
        if problem:
            raise SummaryRejected(problem)
        summary, _ = strip_instruction_echo(summary, lang)
    return summary


def run_truncation(messages: list, num_ctx: int) -> tuple[list, list]:
    """Oldest messages dropped, newest kept: these fill at most half of the context."""
    if not messages:
        return [], []
    max_chars = int(num_ctx * CHARS_PER_TOKEN * 0.5)
    kept, total = [], 0
    for m in reversed(messages):
        size = len(m.content) + 20
        if total + size > max_chars and kept:
            break
        kept.insert(0, m)
        total += size
    kept_ids = {m.id for m in kept}
    return [m for m in messages if m.id not in kept_ids], kept


def truncation_index(previous: str, dropped: list, num_ctx: int) -> str:
    """Index of the removed messages, added to the previous one: the start of each message (300 characters for
    the player, 200 for the assistant). Over INDEX_SHARE of the context, the oldest lines go first."""
    lines = [l for l in (previous or "").splitlines() if l.startswith("- ")]
    for m in dropped:
        flat = " ".join(m.content.split())
        limit = 300 if m.role == "user" else 200
        lines.append("- " + message_line(m.role, flat if len(flat) <= limit else flat[:limit] + "…"))
    room = int(num_ctx * INDEX_SHARE * CHARS_PER_TOKEN)
    while len(lines) > 1 and sum(len(l) + 1 for l in lines) > room:
        lines.pop(0)
    return "[Tronqué]\n" + "\n".join(lines)


def is_openai_host(url: str) -> bool:
    clean = url.rstrip("/")
    return clean.endswith("/v1") or "/v1/" in clean or "openai" in clean.lower()
