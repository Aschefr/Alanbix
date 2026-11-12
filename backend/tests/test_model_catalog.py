import asyncio
import json

import httpx
import pytest

from app import ia_model_catalog as catalog

OLLAMA = "http://ollama:11434"
MODEL = "gemma4:e4b"


@pytest.fixture(autouse=True)
def clean_state():
    catalog._pulls.clear()
    catalog._tasks.clear()
    yield
    catalog._pulls.clear()
    catalog._tasks.clear()


def serve(monkeypatch, handler):
    """Route the catalog's HTTP calls to a fake server."""
    def client():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(catalog, "ia_client", client)


def ollama_handler(pull_lines=None, status=200, installed=()):
    def handler(request):
        path = request.url.path
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.13"})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n} for n in installed]})
        if path == "/api/pull":
            assert json.loads(request.content)["model"] == MODEL
            if status != 200:
                return httpx.Response(status, json={"error": "pull model manifest: file does not exist"})
            return httpx.Response(200, content="\n".join(json.dumps(line) for line in pull_lines))
        return httpx.Response(404)
    return handler


def test_catalog_marks_installed_models(monkeypatch):
    serve(monkeypatch, ollama_handler(installed=[MODEL, "other:1b"]))
    res = asyncio.run(catalog.catalog_for(OLLAMA))
    assert res["supported"] is True
    by_name = {m["name"]: m for m in res["models"]}
    assert by_name[MODEL]["installed"] is True
    assert by_name["nemotron-3.5-bolt:e4b"]["installed"] is False
    assert res["comparison"]["labels"]["recommended"] == MODEL


def test_every_recommended_model_says_its_temperature_and_speed():
    for model in catalog.CATALOG:
        assert model["temperature"] == catalog.RECOMMENDED_TEMPERATURE
        assert model["typical_seconds"] > 0
        assert "moe" not in model["name"] and model["name"] != "qwen3.5:35b"


def test_openai_service_is_not_supported_without_any_call(monkeypatch):
    def handler(request):
        raise AssertionError("no call expected")
    serve(monkeypatch, handler)
    assert asyncio.run(catalog.catalog_for("https://api.openai.com/v1"))["supported"] is False


def test_llama_cpp_answers_tags_but_is_not_ollama(monkeypatch):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        return httpx.Response(404)
    serve(monkeypatch, handler)
    assert asyncio.run(catalog.catalog_for("http://llama:8080"))["supported"] is False


def test_unreachable_server_is_not_supported(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down")
    serve(monkeypatch, handler)
    assert asyncio.run(catalog.catalog_for(OLLAMA))["supported"] is False


def test_only_web_addresses_are_accepted(monkeypatch):
    def handler(request):
        raise AssertionError("no call expected")
    serve(monkeypatch, handler)
    assert asyncio.run(catalog.is_ollama("file:///etc/passwd")) is False


def run_pull(url=OLLAMA, model=MODEL):
    done = []
    async def go():
        state = catalog.start_pull(url, model, on_done=done.append)
        await catalog._tasks[catalog._key(url, model)]
        return state
    return asyncio.run(go()), done


def test_download_reports_success_and_refreshes(monkeypatch):
    serve(monkeypatch, ollama_handler(pull_lines=[
        {"status": "pulling manifest"},
        {"status": "pulling a", "digest": "a", "total": 4_000_000_000, "completed": 2_000_000_000},
        {"status": "pulling a", "digest": "a", "total": 4_000_000_000, "completed": 4_000_000_000},
        {"status": "verifying sha256 digest"},
        {"status": "success"},
    ]))
    state, done = run_pull()
    assert state == {"downloading": False, "percent": 100, "error": None}
    assert done == [OLLAMA]


def test_error_line_from_ollama_is_reported(monkeypatch):
    serve(monkeypatch, ollama_handler(pull_lines=[
        {"status": "pulling a", "digest": "a", "total": 100, "completed": 10},
        {"error": "no space left on device"},
    ]))
    state, done = run_pull()
    assert state["downloading"] is False
    assert state["error"] == "no space left on device"
    assert done == []


def test_http_error_is_reported(monkeypatch):
    serve(monkeypatch, ollama_handler(status=500))
    state, _ = run_pull()
    assert "file does not exist" in state["error"]


def test_stream_ending_without_success_is_a_failure(monkeypatch):
    serve(monkeypatch, ollama_handler(pull_lines=[{"status": "pulling a", "digest": "a", "total": 100, "completed": 10}]))
    state, done = run_pull()
    assert state["error"] == "download interrupted"
    assert done == []


def test_percent_does_not_go_backwards_when_a_new_layer_starts():
    layers = {"a": (4_000_000_000, 4_000_000_000)}
    first = catalog._percent(layers, 4.6)
    layers["b"] = (0, 600_000_000)
    assert catalog._percent(layers, 4.6) >= first
    assert catalog._percent({"a": (9_000_000_000, 9_000_000_000)}, 4.6) == 99


def test_model_outside_the_list_is_refused():
    with pytest.raises(ValueError):
        catalog.start_pull(OLLAMA, "evil/model:latest")


def test_second_request_joins_the_running_download(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, content=json.dumps({"status": "success"}))
    serve(monkeypatch, handler)
    async def go():
        first = catalog.start_pull(OLLAMA, MODEL)
        second = catalog.start_pull(OLLAMA + "/", MODEL)
        assert first is second
        await catalog._tasks[catalog._key(OLLAMA, MODEL)]
    asyncio.run(go())
    assert calls == ["/api/pull"]


def test_endpoint_refuses_a_model_outside_the_list(client):
    res = client.post("/ia/model-catalog/pull", json={"url": OLLAMA, "model": "evil:latest"})
    assert res.status_code == 400


def test_endpoints_are_for_admins_only(client):
    from app.auth import get_current_admin, get_current_user
    from app.main import app
    app.dependency_overrides.pop(get_current_admin)
    app.dependency_overrides.pop(get_current_user)
    assert client.get("/ia/model-catalog", params={"url": OLLAMA}).status_code == 401
    assert client.post("/ia/model-catalog/pull", json={"url": OLLAMA, "model": MODEL}).status_code == 401
