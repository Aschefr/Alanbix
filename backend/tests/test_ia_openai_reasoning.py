"""OpenAI reasoning models get max_completion_tokens and no temperature; nothing else changes."""
import asyncio
import json

import httpx

from app.ia_utils import adapt_openai_payload, ia_client

OPENAI = "https://api.openai.com/v1/chat/completions"
BASE = {"messages": [], "temperature": 0.2, "max_tokens": 30}


def test_reasoning_model_on_openai_is_adapted():
    out = adapt_openai_payload(OPENAI, {**BASE, "model": "o4-mini"})
    assert "temperature" not in out and "max_tokens" not in out
    assert out["max_completion_tokens"] == 4096  # room for the hidden reasoning
    assert out["reasoning_effort"] == "low"
    big = adapt_openai_payload(OPENAI, {**BASE, "model": "gpt-5-mini", "max_tokens": 16384})
    assert big["max_completion_tokens"] == 16384


def test_chat_variant_gets_no_reasoning_effort():
    out = adapt_openai_payload(OPENAI, {**BASE, "model": "gpt-5-chat-latest"})
    assert "reasoning_effort" not in out and "max_tokens" not in out


def test_other_models_and_services_are_untouched():
    for url, model in [(OPENAI, "gpt-4o-mini"), (OPENAI, "gpt-4.1"),
                       ("https://openrouter.ai/api/v1/chat/completions", "openai/o3-mini"),
                       ("http://192.168.1.20:1234/v1/chat/completions", "o3-local")]:
        payload = {**BASE, "model": model}
        assert adapt_openai_payload(url, payload) == payload, (url, model)


def test_client_sends_the_adapted_body():
    sent = {}

    def handler(request):
        sent[request.url.path] = json.loads(request.content)
        return httpx.Response(200, json={})

    async def run():
        async with ia_client(transport=httpx.MockTransport(handler)) as c:
            await c.post(OPENAI, json={**BASE, "model": "o3"})
            await c.post("https://api.openai.com/v1/embeddings", json={"model": "o3", "max_tokens": 5})

    asyncio.run(run())
    assert "max_tokens" not in sent["/v1/chat/completions"]
    assert sent["/v1/embeddings"]["max_tokens"] == 5
