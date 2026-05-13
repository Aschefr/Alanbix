import re
import httpx
from datetime import datetime

def run_truncation(messages: list, max_tokens: int, chars_per_token: float = 3.5) -> tuple[list, list]:
    if not messages:
        return [], []
    max_chars = int(max_tokens * chars_per_token * 0.6)
    kept = []
    total_chars = 0
    for m in reversed(messages):
        msg_len = len(m.content) + 20
        if total_chars + msg_len > max_chars and kept:
            break
        kept.insert(0, m)
        total_chars += msg_len
    kept_ids = {m.id for m in kept}
    dropped = [m for m in messages if m.id not in kept_ids]
    return dropped, kept

def _estimate_tokens(text: str, chars_per_token: float = 3.5) -> int:
    return int(len(text) / chars_per_token)

_COMPACT_INSTRUCTIONS = (
    "\n\n=== INSTRUCTIONS (CRITICAL — READ CAREFULLY) ===\n"
    "You are a text compactor. Rewrite the text ABOVE using minimum characters.\n\n"
    "RULES:\n"
    "1. Output ONLY the compacted text. No commentary, no intro.\n"
    "2. Keep the SAME language as the input (French→French, English→English).\n"
    "3. Use U: for user, A: for assistant.\n"
    "4. Remove ALL greetings, politeness, filler, reformulations, repetitions.\n"
    "5. Convert verbose explanations to telegraphic notes.\n"
    "6. KEEP ALL technical details.\n"
    "7. KEEP conversation flow (who said what, in order).\n"
    "8. Target: ~50% of original size.\n\n"
    "NOW COMPACT THE TEXT ABOVE. Output ONLY the compacted result:"
)

_SUMMARY_INSTRUCTIONS = (
    "\n\n=== INSTRUCTIONS (CRITICAL — READ CAREFULLY) ===\n"
    "You are a conversation summarizer. Produce an ULTRA-COMPRESSED structured summary "
    "of the text ABOVE.\n\n"
    "CRITICAL RULES:\n"
    "1. Output ONLY the summary. No intro, no commentary.\n"
    "2. Use the SAME LANGUAGE as the conversation.\n"
    "3. You are NOT answering questions. You are SUMMARIZING what was discussed.\n"
    "4. DO NOT continue the conversation or provide new analysis.\n"
    "USE THIS FORMAT:\n"
    "SUJET: [1 line]\n"
    "FAITS:\n"
    "- [fact]\n"
    "RÉSOLU:\n"
    "- [resolved point]\n"
    "EN COURS:\n"
    "- [open question]\n\n"
    "STYLE: Telegraphic. Max 1 line per bullet. Target: ~30% of original size.\n\n"
    "NOW SUMMARIZE THE TEXT ABOVE. Output ONLY the structured summary:"
)

def _fit_text_to_context(text: str, instructions: str, num_ctx: int, chars_per_token: float = 3.5) -> tuple[str, bool]:
    instructions_tokens = _estimate_tokens(instructions)
    response_budget = 1024
    text_budget_tokens = num_ctx - instructions_tokens - response_budget
    text_budget_chars = int(text_budget_tokens * chars_per_token)
    if len(text) <= text_budget_chars:
        return text, False
    truncated = "...[tronqué]...\n" + text[-text_budget_chars:]
    return truncated, True

async def run_compaction(text: str, url: str, model: str, num_ctx: int = 4096) -> str:
    fitted_text, _ = _fit_text_to_context(text, _COMPACT_INSTRUCTIONS, num_ctx)
    prompt = fitted_text + _COMPACT_INSTRUCTIONS
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.1, "num_ctx": num_ctx}},
            timeout=180.0
        )
        return response.json().get("response", "").strip()

async def run_summary(text: str, url: str, model: str, num_ctx: int = 4096) -> str:
    fitted_text, _ = _fit_text_to_context(text, _SUMMARY_INSTRUCTIONS, num_ctx)
    prompt = fitted_text + _SUMMARY_INSTRUCTIONS
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.1, "num_ctx": num_ctx}},
            timeout=180.0
        )
        return response.json().get("response", "").strip()
