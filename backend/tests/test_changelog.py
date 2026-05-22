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
    # Verify that the latest version 1.13.0 is parsed correctly
    assert first["tag_name"] == "v1.13.0"
