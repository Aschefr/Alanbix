"""Thumbnail endpoint: small cached WebP copies of game covers."""
import os

from fastapi.testclient import TestClient
from PIL import Image

from app import main


def _client():
    return TestClient(main.app)


def test_thumbnail_is_generated_small_and_cached():
    name = "thumbtest_cover.png"
    folder = os.path.join(main.DATA_DIR, "game_images")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    Image.new("RGB", (1200, 700), (200, 30, 30)).save(path)
    try:
        res = _client().get(f"/data/thumbs/96/game_images/{name}")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/webp"
        assert "max-age" in res.headers["cache-control"]
        assert len(res.content) < os.path.getsize(path)
        thumb = os.path.join(main.DATA_DIR, "thumbs", "96", "game_images", "thumbtest_cover.webp")
        assert os.path.isfile(thumb)
        with Image.open(thumb) as img:
            assert img.width <= 96
    finally:
        for p in (path, os.path.join(main.DATA_DIR, "thumbs", "96", "game_images", "thumbtest_cover.webp")):
            if os.path.exists(p):
                os.remove(p)


def test_thumbnail_rejects_unknown_width_kind_and_file():
    c = _client()
    assert c.get("/data/thumbs/97/game_images/x.png").status_code == 404
    assert c.get("/data/thumbs/96/secrets/x.png").status_code == 404
    assert c.get("/data/thumbs/96/game_images/missing.png").status_code == 404
    assert c.get("/data/thumbs/96/game_images/..%2f..%2falanbix.db").status_code == 404
