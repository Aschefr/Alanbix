import pytest

def test_i18n_config_defaults(client):
    # Get dashboard stats
    res = client.get("/dashboard/stats")
    assert res.status_code == 200
    data = res.json()
    assert "lan_multilingual" in data
    assert "lan_default_language" in data
    assert data["lan_multilingual"] is False
    assert data["lan_default_language"] == "fr"

def test_update_i18n_config(client):
    # Update lan_multilingual
    res = client.put("/admin/config/lan_multilingual", json={"value": True})
    assert res.status_code == 200
    assert res.json()["value"] is True

    # Update lan_default_language
    res = client.put("/admin/config/lan_default_language", json={"value": "en"})
    assert res.status_code == 200
    assert res.json()["value"] == "en"

    # Verify changes in stats
    res = client.get("/dashboard/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["lan_multilingual"] is True
    assert data["lan_default_language"] == "en"

def test_list_languages(client):
    res = client.get("/i18n/languages")
    assert res.status_code == 200
    langs = res.json().get("languages")
    assert isinstance(langs, list)
    assert "fr" in langs
    assert "en" in langs
