import hashlib
import json
import os
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from app import ia_builtin_embed as builtin
from app import ia_knowledge, ia_utils, models

MODEL = b"fake onnx model"
TOKENIZER = b"fake tokenizer"


def sha(b):
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def small_model(tmp_path, monkeypatch):
    """The two model files replaced by small ones, in a temporary data folder."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "alanbix.db"))
    monkeypatch.setattr(builtin, "FILES", {
        "model_quantized.onnx": ("http://hf/model", len(MODEL), sha(MODEL)),
        "tokenizer.json": ("http://hf/tokenizer", len(TOKENIZER), sha(TOKENIZER)),
    })
    builtin._install.update(downloading=False, downloaded=0, error=None)
    ia_knowledge._embed_state["failed_at"] = None
    yield tmp_path
    builtin._install.update(downloading=False, downloaded=0, error=None)
    builtin._runtime.update(session=None, tokenizer=None)
    ia_knowledge._embed_state["failed_at"] = None


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def aiter_bytes(self, _size):
        yield self.body


class FakeClient:
    def __init__(self, bodies):
        self.bodies, self.calls = bodies, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, _method, url):
        self.calls.append(url)
        return FakeResponse(*self.bodies[url])


def client_with(model=(MODEL, 200), tokenizer=(TOKENIZER, 200)):
    return FakeClient({"http://hf/model": model, "http://hf/tokenizer": tokenizer})


@pytest.mark.asyncio
async def test_install_downloads_and_verifies(small_model):
    assert not builtin.is_installed()
    with patch("httpx.AsyncClient", return_value=client_with()):
        assert await builtin.install() is True
    assert builtin.is_installed()
    assert builtin.install_state()["error"] is None


@pytest.mark.asyncio
async def test_corrupt_download_is_refused_and_left_nowhere(small_model):
    with patch("httpx.AsyncClient", return_value=client_with(tokenizer=(b"x" * len(TOKENIZER), 200))):
        assert await builtin.install() is False
    state = builtin.install_state()
    assert not state["installed"] and not state["downloading"]
    assert state["error"] == "checksum mismatch"
    assert not any(f.endswith(".part") for f in os.listdir(builtin.model_dir()))


@pytest.mark.asyncio
async def test_failed_download_can_resume_with_what_it_has(small_model):
    with patch("httpx.AsyncClient", return_value=client_with(tokenizer=(b"", 503))):
        assert await builtin.install() is False
    assert "503" in builtin.install_state()["error"]
    # The model file is kept: the second try only fetches the tokenizer
    client = client_with()
    with patch("httpx.AsyncClient", return_value=client):
        assert await builtin.install() is True
    assert client.calls == ["http://hf/tokenizer"]


def test_vector_is_mean_of_real_tokens_with_unit_length(small_model):
    class Input:
        name = "input_ids"

    class Session:
        def get_inputs(self):
            return [Input()]

        def run(self, _out, feed):
            assert list(feed) == ["input_ids", "attention_mask"]
            return [np.array([[[3.0, 0.0], [0.0, 4.0], [9.0, 9.0]]])]

    class Encoded:
        ids = [1, 2, 0]
        attention_mask = [1, 1, 0]  # the third token is padding

    class Tok:
        def encode(self, _text):
            return Encoded()

    builtin._runtime.update(session=Session(), tokenizer=Tok())
    vector = builtin._embed_sync("salut")
    assert vector == pytest.approx([0.6, 0.8])


def test_auto_uses_builtin_once_installed(small_model, db_session):
    assert ia_utils._get_embed_model() == ia_utils.DEFAULT_EMBED_MODEL
    with patch.object(builtin, "is_installed", return_value=True):
        assert ia_utils._get_embed_model() == builtin.NAME


@pytest.mark.asyncio
async def test_embedding_goes_to_builtin_without_any_server(small_model):
    with patch("app.ia_utils._get_embed_model", return_value=builtin.NAME), \
         patch.object(builtin, "embed", AsyncMock(return_value=[0.1, 0.2])) as emb, \
         patch("httpx.AsyncClient") as http:
        assert await ia_utils.get_embedding("salut") == [0.1, 0.2]
    emb.assert_awaited_once_with("salut")
    http.assert_not_called()


@pytest.mark.asyncio
async def test_not_installed_reports_why(small_model):
    with patch("app.ia_utils._get_embed_model", return_value=builtin.NAME):
        assert await ia_utils.get_embedding("salut") is None
    assert "not installed" in ia_utils.LAST_EMBED_ERROR


@pytest.mark.asyncio
async def test_builtin_has_its_own_threshold(small_model, db_session):
    # Scores 0.55: kept with the built-in model (0.5), dropped with an external one (0.65 by default)
    doc = models.KnowledgeBase(content="fiche sans mot en commun", metadata_json={}, embedding_json=json.dumps([0.55, 0.835]), embed_model=builtin.NAME)
    db_session.add(doc)
    db_session.commit()
    cfg = {"rag_enabled": True, "rag_min_score": 0.65}
    with patch("app.ia_utils._get_embed_model", return_value=builtin.NAME), \
         patch("app.ia_utils.get_embedding", AsyncMock(return_value=[1.0, 0.0])):
        assert [d.id for d in await ia_knowledge.search_knowledge(db_session, models, "question", "", cfg)] == [doc.id]
    doc.embed_model = "nomic"
    db_session.commit()
    with patch("app.ia_utils._get_embed_model", return_value="nomic"), \
         patch("app.ia_utils.get_embedding", AsyncMock(return_value=[1.0, 0.0])):
        assert await ia_knowledge.search_knowledge(db_session, models, "question", "", cfg) == []
