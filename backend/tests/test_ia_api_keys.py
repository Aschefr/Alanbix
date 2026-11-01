"""API keys of online AI services: sent to the service, never back to the browser."""
import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from app import models
from app import ia_utils


def _post_config(client, instances):
    with patch("app.ia_queue.queue_manager.restart_workers", new_callable=AsyncMock):
        return client.post("/ia/config", json={"ollama_instances": instances})


def _saved_instances(db):
    db.expire_all()
    cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "ia_settings").first()
    return cfg.value["ollama_instances"]


def test_key_is_saved_but_never_returned(client, db_session):
    assert _post_config(client, [{"url": "https://api.mistral.ai/v1", "model": "m", "api_key": " sk-123 "}]).status_code == 200
    assert _saved_instances(db_session)[0]["api_key"] == "sk-123"
    inst = client.get("/ia/config").json()["ollama_instances"][0]
    assert "api_key" not in inst and inst["has_api_key"] is True


def test_key_kept_when_sent_back_empty_and_removed_on_request(client, db_session):
    _post_config(client, [{"url": "https://api.mistral.ai/v1", "model": "m", "api_key": "sk-123"}])
    # The settings page sends the instance back as it received it (no key)
    _post_config(client, [{"url": "https://api.mistral.ai/v1/", "model": "m2", "has_api_key": True}])
    saved = _saved_instances(db_session)[0]
    assert saved["api_key"] == "sk-123" and "has_api_key" not in saved
    _post_config(client, [{"url": "https://api.mistral.ai/v1", "model": "m2", "clear_api_key": True}])
    assert "api_key" not in _saved_instances(db_session)[0]


def test_client_adds_the_key_of_the_matching_instance():
    ia_utils.register_instance_keys([
        {"url": "https://api.example.com/v1/", "api_key": "k-long"},
        {"url": "https://api.example.com", "api_key": "k-short"},
        {"url": "http://ollama:11434", "api_key": ""},
    ])
    seen = {}

    def handler(request):
        seen[str(request.url)] = request.headers.get("authorization")
        return httpx.Response(200, json={})

    async def run():
        async with ia_utils.ia_client(transport=httpx.MockTransport(handler)) as c:
            await c.post("https://api.example.com/v1/chat/completions", json={})
            await c.get("https://api.example.com/other")
            await c.get("http://ollama:11434/api/tags")

    asyncio.run(run())
    assert seen["https://api.example.com/v1/chat/completions"] == "Bearer k-long"
    assert seen["https://api.example.com/other"] == "Bearer k-short"
    assert seen["http://ollama:11434/api/tags"] is None
    ia_utils.register_instance_keys([])


def test_context_window_never_below_16k(client, db_session):
    with patch("app.ia_queue.queue_manager.restart_workers", new_callable=AsyncMock):
        client.post("/ia/config", json={"context_window": 4096})
    assert client.get("/ia/config").json()["context_window"] == 16384
    with patch("app.ia_queue.queue_manager.restart_workers", new_callable=AsyncMock):
        client.post("/ia/config", json={"context_window": 65536})
    assert client.get("/ia/config").json()["context_window"] == 65536
