"""One question, one answer: a non-streaming request to an AI server (Ollama or OpenAI-compatible).

Used by the queue for its background jobs (translation, tournament notification, chat review).
Split out of ia_queue.py.
"""
from .ia_tool_loop import AI_READ_TIMEOUT
from .ia_utils import ia_client, is_openai_host, no_think


async def ask_once(host: str, model: str, messages: list, *, temperature: float, think: bool = True,
                   num_ctx: int | None = None, max_tokens: int | None = None, json_format: bool = False,
                   timeout: float = AI_READ_TIMEOUT) -> str:
    """The raw answer text. Raises when the server does not answer 200."""
    base = host.rstrip("/")
    if is_openai_host(host):
        url = f"{base}/chat/completions"
        req_json = {"model": model, "messages": messages, "stream": False, "temperature": temperature}
        if json_format:
            req_json["response_format"] = {"type": "json_object"}
        if max_tokens:
            req_json["max_tokens"] = max_tokens
    else:
        url = f"{base}/api/chat"
        options = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        if num_ctx:
            # Same context as every other call: another size makes Ollama reload the model
            options["num_ctx"] = num_ctx
        req_json = {"model": model, "messages": messages, "stream": False}
        if json_format:
            req_json["format"] = "json"
        req_json = {**req_json, "options": options, **no_think(host, think)}

    async with ia_client() as client:
        res = await client.post(url, json=req_json, timeout=timeout)

    if res.status_code != 200:
        raise Exception(f"AI service returned HTTP {res.status_code}: {res.text[:200]}")
    if is_openai_host(host):
        return res.json().get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    return res.json().get("message", {}).get("content", "") or ""
