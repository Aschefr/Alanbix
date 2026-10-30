from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_browser_opening_info_page_gets_the_app_not_json():
    res = client.get("/dashboard/info", headers={"sec-fetch-mode": "navigate", "accept": "text/html"})
    assert "application/json" not in res.headers.get("content-type", "")


def test_api_call_to_info_still_returns_json():
    res = client.get("/dashboard/info", headers={"sec-fetch-mode": "cors"})
    assert "application/json" in res.headers.get("content-type", "")
