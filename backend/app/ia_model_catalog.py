"""Models recommended for Alanbix, and their download on an Ollama server.

Only Ollama has a download command (/api/pull): OpenAI-compatible services and llama.cpp do not, and
/api/version tells them apart, since llama.cpp also answers /api/tags. Only models of this list can be
requested. The list is what the rules of ia_model_comparison pick from a comparison on real Alanbix
questions; see docs/*/features/ai-assistant.md.
"""
import asyncio
import json

import httpx

from .ia_compression import is_openai_host
from .ia_model_comparison import comparison
from .ia_utils import ia_client

# Temperature: at 0.7 the small models act less reliably (alert an admin less often, answer in another
# language); the big ones were flawless at both 0.2 and 0.7.
RECOMMENDED_TEMPERATURE = 0.2

# The models the comparison's rules pick (test_model_comparison checks it). size_gb is what /api/tags
# reports once downloaded; typical_seconds is the median chat answer, tool calls included, on an RTX 3090
# with a 32K context; memory_gb is read on the card once loaded at 32K.
# No MoE model here (qwen3.5:35b...): loading one crashed a server with 32 GB of memory.
CATALOG = [
    {"name": "gemma4:e4b", "tier": "recommended", "size_gb": 6.6, "typical_seconds": 2.5, "memory_gb": 5.4, "temperature": RECOMMENDED_TEMPERATURE},
    {"name": "nemotron-3.5-bolt:e4b", "tier": "alternative", "size_gb": 7.9, "typical_seconds": 3.1, "memory_gb": 7.9, "temperature": RECOMMENDED_TEMPERATURE},
]
_NAMES = {m["name"] for m in CATALOG}

# Between two lines of progress: checking a big model on a slow disk can take minutes without any line
PULL_TIMEOUT = httpx.Timeout(connect=10.0, read=900.0, write=10.0, pool=10.0)

_pulls: dict = {}  # (url, model) -> {"downloading", "percent", "error"}
_tasks: dict = {}  # (url, model) -> running task, keeps it alive


def _key(url: str, model: str) -> tuple:
    return (url.rstrip("/"), model)


def pull_state(url: str, model: str) -> dict:
    return _pulls.get(_key(url, model)) or {"downloading": False, "percent": 0, "error": None}


async def is_ollama(url: str) -> bool:
    if not url.startswith(("http://", "https://")) or is_openai_host(url):
        return False
    try:
        async with ia_client() as client:
            res = await client.get(f"{url.rstrip('/')}/api/version", timeout=5.0)
        return res.status_code == 200 and "version" in res.json()
    except Exception:
        return False


async def installed_models(url: str) -> set:
    async with ia_client() as client:
        res = await client.get(f"{url.rstrip('/')}/api/tags", timeout=5.0)
    res.raise_for_status()
    return {m.get("name") for m in res.json().get("models", [])}


async def catalog_for(url: str) -> dict:
    """The list as seen from one server. supported is false when it cannot download models."""
    if not await is_ollama(url):
        return {"supported": False, "models": []}
    try:
        installed = await installed_models(url)
    except Exception:
        return {"supported": False, "models": []}
    return {
        "supported": True,
        "models": [{**m, "installed": m["name"] in installed, **pull_state(url, m["name"])} for m in CATALOG],
        "comparison": comparison(),
    }


def _percent(layers: dict, size_gb: float) -> int:
    """Ollama announces the layers one after the other: their total grows along the way. Dividing by
    the expected size keeps the bar from going backwards when a new layer starts."""
    done = sum(c for c, _ in layers.values())
    total = max(sum(t for _, t in layers.values()), size_gb * 1e9)
    return min(99, int(done * 100 / total))


async def _pull(url: str, model: str, on_done=None) -> None:
    state = _pulls[_key(url, model)]
    size_gb = next(m["size_gb"] for m in CATALOG if m["name"] == model)
    layers = {}
    try:
        async with ia_client() as client:
            async with client.stream("POST", f"{url.rstrip('/')}/api/pull", json={"model": model, "stream": True}, timeout=PULL_TIMEOUT) as res:
                if res.status_code != 200:
                    body = (await res.aread()).decode("utf-8", "replace")
                    try:
                        raise RuntimeError(json.loads(body).get("error") or f"HTTP {res.status_code}")
                    except ValueError:
                        raise RuntimeError(f"HTTP {res.status_code}") from None
                success = False
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise RuntimeError(data["error"])
                    if data.get("digest") and data.get("total"):
                        layers[data["digest"]] = (data.get("completed") or 0, data["total"])
                        state["percent"] = max(state["percent"], _percent(layers, size_gb))
                    success = data.get("status") == "success"
        if not success:
            raise RuntimeError("download interrupted")
        state.update(percent=100, error=None)
        if on_done:
            on_done(url)
    except Exception as e:
        print(f"[Models] Download of {model} on {url} failed: {e}", flush=True)
        state["error"] = str(e) or e.__class__.__name__
    finally:
        state["downloading"] = False
        _tasks.pop(_key(url, model), None)


def start_pull(url: str, model: str, on_done=None) -> dict:
    """Start the download in the background, or return the one already running. An interrupted
    download starts again where it stopped: Ollama keeps what it already has."""
    if model not in _NAMES:
        raise ValueError(model)
    key = _key(url, model)
    if key not in _tasks:
        _pulls[key] = {"downloading": True, "percent": 0, "error": None}
        _tasks[key] = asyncio.create_task(_pull(url, model, on_done))
    return _pulls[key]
