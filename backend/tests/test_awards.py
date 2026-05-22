import pytest
from app import models
from app.main import app

def test_awards_automated_flow(client, db_session):
    # 1. Clear any existing awards / configs
    client.delete("/admin/nuke/awards")

    # 2. Verify we have 12 categories returned from GET /admin/awards
    res = client.get("/admin/awards")
    assert res.status_code == 200
    awards_data = res.json()
    assert len(awards_data) == 12
    # Check default keys are present
    keys = [item["key"] for item in awards_data]
    assert "premier" in keys
    assert "bourreau" in keys
    assert "team" in keys

    # 3. Check custom override PUT /admin/awards/{category_key}
    res = client.put("/admin/awards/premier", json={
        "title": "🏆 Grand Champion",
        "description": "Le meilleur joueur de la LAN avec {points} points."
    })
    assert res.status_code == 200
    assert res.json()["status"] == "updated"

    # Verify custom text is returned from GET
    res = client.get("/admin/awards")
    premier_award = next(item for item in res.json() if item["key"] == "premier")
    assert premier_award["title"] == "🏆 Grand Champion"
    assert premier_award["description"] == "Le meilleur joueur de la LAN avec {points} points."
    assert premier_award["custom_title"] == "🏆 Grand Champion"

    # 4. Restore defaults via DELETE
    res = client.delete("/admin/awards/premier/text")
    assert res.status_code == 200
    assert res.json()["status"] == "restored"

    res = client.get("/admin/awards")
    premier_award_restored = next(item for item in res.json() if item["key"] == "premier")
    assert premier_award_restored["title"] == premier_award_restored["default_title"]
    assert premier_award_restored["custom_title"] is None

def test_awards_nuke(client, db_session):
    # Nuke configurations and awards
    res = client.delete("/admin/nuke/awards")
    assert res.status_code == 200
    assert res.json()["status"] == "nuked"
