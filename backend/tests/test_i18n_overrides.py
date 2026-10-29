import os
import json
import tempfile
from unittest.mock import patch

import pytest


def _write(path, data):
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(data, f, ensure_ascii=False)


def _read(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


@pytest.fixture
def i18n_dirs():
    with tempfile.TemporaryDirectory() as static_dir, \
         tempfile.TemporaryDirectory() as data_dir, \
         tempfile.TemporaryDirectory() as history_dir:
        _write(os.path.join(static_dir, "fr.json"), {"greet": "Bonjour vous", "title": "Tableau de bord", "prompt": "Défaut"})
        _write(os.path.join(history_dir, "fr.json"), {"greet": ["Salut toi"]})
        with patch("app.routers.i18n.STATIC_I18N_DIR", static_dir), \
             patch("app.routers.i18n.DATA_I18N_DIR", data_dir), \
             patch("app.routers.i18n.STATIC_I18N_HISTORY_DIR", history_dir):
            yield static_dir, data_dir


def test_startup_cleanup_drops_seeded_copies_keeps_customisations(i18n_dirs):
    from app.routers.i18n import cleanup_user_overrides
    _, data_dir = i18n_dirs
    # Full copy seeded by an older version, plus one real admin customisation
    _write(os.path.join(data_dir, "fr.json"), {"greet": "Salut toi", "title": "Tableau de bord", "prompt": "Mon prompt"})

    cleanup_user_overrides()

    assert _read(os.path.join(data_dir, "fr.json")) == {"prompt": "Mon prompt"}


def test_update_stores_only_changed_keys(client, i18n_dirs):
    _, data_dir = i18n_dirs
    merged = client.get("/api/i18n/fr").json()
    merged["prompt"] = "Mon prompt"

    assert client.put("/api/i18n/fr", json=merged).status_code == 200

    assert _read(os.path.join(data_dir, "fr.json")) == {"prompt": "Mon prompt"}
    assert client.get("/api/i18n/fr").json()["greet"] == "Bonjour vous"
