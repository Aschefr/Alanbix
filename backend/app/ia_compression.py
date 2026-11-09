"""Freeing room in a long AI conversation.

Two ways, chosen by the player:
- truncate: instant, no AI. The oldest messages leave the context; a short index of them is kept.
- summary: anchored summary. The AI merges the previous summary with the messages leaving the context,
  in fixed sections, keeping exact values and corrections; the last two exchanges stay word for word.
  Measured on 2026-11-09 with this module (ai-bench/results/compaction, 3 runs, 3 compactions each): 30/30 facts
  kept with qwen3.8:27b and 23/30 with gemma4:e4b (25/30 without compaction), against 3 to 8 out of 10 for the
  former summary and compact modes.
"""
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
3. When the user corrected a piece of information, keep only the corrected value and write "(corrected, replaces X)".
4. Keep decisions with their reason, and the user's preferences (how to talk to them, format of the answers).
5. Drop greetings, repetitions and general explanations.
6. Write in the language of the conversation, in short bullet points, under these sections:
FACTS:
DECISIONS (and why):
USER PREFERENCES:
OPEN QUESTIONS (and what they depend on):
7. At most {words} words.

SUMMARY:"""


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


async def _anchored_call(previous: str, lines: list, url: str, model: str, num_ctx: int, think: bool) -> str:
    text = "\n".join(lines)
    words = max(WORDS_MIN, min(WORDS_MAX, (len(text) + len(previous)) // 20))
    head = f"[Previous summary]\n{previous}\n\n[New messages to merge into the summary]\n" if previous else ""
    prompt = f"{head}{text}\n\n" + ANCHORED_INSTRUCTIONS.format(
        merge=" (previous summary included)" if previous else "", words=words)
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


async def run_anchored(previous: str, lines: list, url: str, model: str, num_ctx: int = 16384, think: bool = False) -> str:
    """Summary of `lines` merged into `previous`. Never cuts the start of the conversation: when the text does not fit
    the context, it is summarized in several calls, each merged into the summary of the previous ones."""
    reserve = (4096 if think else WORDS_MAX * 3) + 400  # answer (and thinking) + instructions
    room = int((num_ctx - reserve) * CHARS_PER_TOKEN) - max(len(previous or ""), WORDS_MAX * 7)
    summary = previous or ""
    for chunk in _chunks(lines, max(room, 2000)):
        summary = await _anchored_call(summary, chunk, url, model, num_ctx, think)
        if not summary:
            return ""
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
