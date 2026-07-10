import pytest
import json
import httpx
from unittest.mock import patch, MagicMock, AsyncMock
from app.routers.ia import _check_instance_health, list_models, pick_instance
from app.ia_utils import get_embedding
from app.ia_queue import IAQueueManager, QueueEntry
from app.ia_compression import run_compaction, run_summary

# ---------------------------------------------------------------------------
# Mock Response Helpers
# ---------------------------------------------------------------------------
class AsyncContextManagerMock:
    def __init__(self, response):
        self.response = response
    async def __aenter__(self):
        return self.response
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

# Helper to mock httpx responses cleanly using a real class
def mock_httpx_client(requests_map):
    """
    requests_map: dict of { (method, url_part): (status_code, json_data_or_iterator) }
    """
    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url, *args, **kwargs):
            for (m, path), (status, data) in requests_map.items():
                if m == "GET" and path in url:
                    res = MagicMock(spec=httpx.Response)
                    res.status_code = status
                    res.json = lambda: data
                    res.text = json.dumps(data)
                    return res
            res = MagicMock(spec=httpx.Response)
            res.status_code = 404
            res.json = lambda: {}
            return res

        async def post(self, url, *args, **kwargs):
            for (m, path), (status, data) in requests_map.items():
                if m == "POST" and path in url:
                    res = MagicMock(spec=httpx.Response)
                    res.status_code = status
                    res.json = lambda: data
                    res.text = json.dumps(data)
                    return res
            res = MagicMock(spec=httpx.Response)
            res.status_code = 404
            res.json = lambda: {}
            return res

        def stream(self, method, url, *args, **kwargs):
            for (m, path), (status, iterator) in requests_map.items():
                if m == method and path in url:
                    res = MagicMock()
                    res.status_code = status
                    async def aiter_lines():
                        for line in iterator:
                            yield line
                    res.aiter_lines = aiter_lines
                    return AsyncContextManagerMock(res)
            res = MagicMock()
            res.status_code = 404
            return AsyncContextManagerMock(res)

        async def aclose(self):
            pass

    return MockClient()

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_detect_and_check_health_ollama():
    """Verify health check and model listing on Ollama endpoint format."""
    requests_map = {
        ("GET", "/api/tags"): (200, {
            "models": [
                {"name": "llama3.2:1b", "details": {"family": "llama", "parameter_size": "1B"}}
            ]
        })
    }
    
    with patch("httpx.AsyncClient", return_value=mock_httpx_client(requests_map)):
        ok, latency, models = await _check_instance_health("http://localhost:11434")
        assert ok is True
        assert "llama3.2:1b" in models

@pytest.mark.asyncio
async def test_detect_and_check_health_openai():
    """Verify health check and model listing on OpenAI endpoint format."""
    requests_map = {
        ("GET", "/api/tags"): (404, {}),
        ("GET", "/v1/models"): (200, {
            "data": [
                {"id": "llama3.2:1b", "object": "model"}
            ]
        })
    }
    
    with patch("httpx.AsyncClient", return_value=mock_httpx_client(requests_map)):
        ok, latency, models = await _check_instance_health("http://localhost:12345/v1")
        assert ok is True
        assert "llama3.2:1b" in models

@pytest.mark.asyncio
async def test_list_models_merged(db_session):
    """Verify list_models merges both Ollama and OpenAI model tags successfully."""
    requests_map = {
        ("GET", "http://instance-ollama/api/tags"): (200, {
            "models": [{"name": "ollama-model:latest"}]
        }),
        ("GET", "http://instance-openai/v1/models"): (200, {
            "data": [{"id": "openai-model:latest"}]
        }),
        ("GET", "http://instance-openai/api/tags"): (404, {}),
    }

    # Setup instances in DB
    from app.models import SystemConfig
    cfg = db_session.query(SystemConfig).filter(SystemConfig.key == "ia_settings").first()
    config_val = {
        "ollama_instances": [
            {"url": "http://instance-ollama", "label": "Ollama", "model": "", "enabled": True, "priority": 0},
            {"url": "http://instance-openai/v1", "label": "OpenAI", "model": "", "enabled": True, "priority": 1}
        ]
    }
    if cfg:
        cfg.value = config_val
    else:
        db_session.add(SystemConfig(key="ia_settings", value=config_val))
    db_session.commit()

    with patch("httpx.AsyncClient", return_value=mock_httpx_client(requests_map)):
        res = await list_models(db=db_session)
        model_names = [m["name"] for m in res["models"]]
        assert "ollama-model:latest" in model_names
        assert "openai-model:latest" in model_names

@pytest.mark.asyncio
async def test_get_embedding_openai():
    """Verify get_embedding works with OpenAI API format."""
    requests_map = {
        ("POST", "http://instance-openai/v1/embeddings"): (200, {
            "data": [{"embedding": [0.9, 0.8, 0.7]}]
        })
    }
    
    with patch("httpx.AsyncClient", return_value=mock_httpx_client(requests_map)), \
         patch("app.ia_utils._get_embed_model", return_value="text-embedding-ada-002"):
        emb = await get_embedding("test text", ollama_host="http://instance-openai/v1")
        assert emb == [0.9, 0.8, 0.7]

@pytest.mark.asyncio
async def test_run_compaction_and_summary_openai():
    """Verify compression tasks route to OpenAI chat completions when using OpenAI endpoints."""
    requests_map = {
        ("POST", "http://instance-openai/v1/chat/completions"): (200, {
            "choices": [{"message": {"content": "Compressed Context Text"}}]
        })
    }

    with patch("httpx.AsyncClient", return_value=mock_httpx_client(requests_map)):
        compacted = await run_compaction("long context text", "http://instance-openai/v1", "llama3.2")
        assert compacted == "Compressed Context Text"

        summarized = await run_summary("long text to summarize", "http://instance-openai/v1", "llama3.2")
        assert summarized == "Compressed Context Text"

@pytest.mark.asyncio
async def test_chat_streaming_openai():
    """Verify chat streaming loop processes OpenAI server-sent events (SSE) chunks correctly."""
    sse_chunks = [
        'data: {"choices": [{"delta": {"content": "Hello"}}]}\n',
        'data: {"choices": [{"delta": {"content": " world"}}]}\n',
        'data: [DONE]\n'
    ]
    
    requests_map = {
        ("POST", "http://instance-openai/v1/chat/completions"): (200, sse_chunks)
    }

    qm = IAQueueManager()
    entry = QueueEntry(
        priority=10,
        created_at=0.0,
        user_id=1,
        username="player1",
        task_type="chat",
        payload={
            "ollama_host": "http://instance-openai/v1",
            "conversation_id": 1,
            "req_data": {
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True
            }
        }
    )

    with patch("httpx.AsyncClient", return_value=mock_httpx_client(requests_map)):
        # Run chat processing directly
        await qm._process_chat(entry, entry.payload)
        
        # Read from result stream queue
        tokens = []
        while not entry.result_stream.empty():
            chunk = await entry.result_stream.get()
            if "text" in chunk:
                tokens.append(chunk["text"])
        
        assert "".join(tokens) == "Hello world"
