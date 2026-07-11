import pytest
from app.main import app

def test_get_changelog(client):
    res = client.get("/changelog")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "tag_name" in first
    assert "published_at" in first
    assert "name" in first
    assert "body" in first
    assert first["tag_name"].startswith("v")
    # Verify that the latest version from VERSION is parsed correctly
    import os
    version = "1.29.0"
    for path in ["VERSION", "../VERSION"]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                version = f.read().strip()
                break
    assert any(r["tag_name"] == f"v{version}" for r in data)
