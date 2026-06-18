import os
import json
import pytest
import tempfile
import asyncio
from unittest.mock import patch, AsyncMock
from app.ia_queue import QueueEntry

@pytest.fixture(autouse=True)
def mock_i18n_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create initial files
        with open(os.path.join(tmp_dir, "fr.json"), "w", encoding="utf-8-sig") as f:
            json.dump({"test_key": "Bonjour"}, f, ensure_ascii=False, indent=4)
        with open(os.path.join(tmp_dir, "en.json"), "w", encoding="utf-8-sig") as f:
            json.dump({"test_key": "Hello"}, f, ensure_ascii=False, indent=4)
            
        with patch("app.routers.i18n.I18N_DIR", tmp_dir):
            yield tmp_dir

def test_get_language_success(client):
    res = client.get("/api/i18n/fr")
    assert res.status_code == 200
    assert res.json() == {"test_key": "Bonjour"}

def test_get_language_not_found(client):
    res = client.get("/api/i18n/de")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

def test_create_language_success(client):
    res = client.post("/api/i18n/de")
    assert res.status_code == 200
    assert "created" in res.json()["message"].lower()
    
    # Verify file exists and is empty dict
    res_get = client.get("/api/i18n/de")
    assert res_get.status_code == 200
    assert res_get.json() == {}

def test_create_language_already_exists(client):
    res = client.post("/api/i18n/fr")
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"].lower()

def test_update_language_success(client):
    res = client.put("/api/i18n/fr", json={"test_key": "Bonjour Modifié", "new_key": "Nouveau"})
    assert res.status_code == 200
    
    # Verify update
    res_get = client.get("/api/i18n/fr")
    assert res_get.status_code == 200
    assert res_get.json() == {"test_key": "Bonjour Modifié", "new_key": "Nouveau"}

def test_update_language_not_found(client):
    res = client.put("/api/i18n/de", json={"key": "val"})
    assert res.status_code == 404

def test_delete_language_success(client):
    # First create
    client.post("/api/i18n/de")
    
    # Delete
    res = client.delete("/api/i18n/de")
    assert res.status_code == 200
    assert "deleted" in res.json()["message"].lower()
    
    # Verify deleted
    res_get = client.get("/api/i18n/de")
    assert res_get.status_code == 404

def test_delete_language_defaults_forbidden(client):
    res = client.delete("/api/i18n/fr")
    assert res.status_code == 400
    assert "cannot delete default" in res.json()["detail"].lower()
    
    res_en = client.delete("/api/i18n/en")
    assert res_en.status_code == 400

@pytest.mark.asyncio
async def test_auto_translate_success(client):
    from app.ia_queue import queue_manager
    
    async def mock_enqueue(entry):
        entry.done_event.set()
        await entry.result_stream.put({"done": True, "result": "Hello Translated"})
        return entry, 0
        
    with patch.object(queue_manager, "enqueue", side_effect=mock_enqueue):
        res = client.post("/api/i18n/auto-translate", json={
            "text": "Bonjour",
            "source_lang": "fr",
            "target_lang": "en"
        })
        assert res.status_code == 200
        assert res.json() == {"translated_text": "Hello Translated"}
