from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_browser_opening_info_page_gets_the_app_not_json(tmp_path, monkeypatch):
    # A stand-in frontend build, so the test does not depend on `npm run build`
    (tmp_path / "index.html").write_text("<!doctype html><title>Alanbix</title>", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(tmp_path))
    res = client.get("/dashboard/info", headers={"sec-fetch-mode": "navigate", "accept": "text/html"})
    assert "text/html" in res.headers.get("content-type", "")


def test_page_navigation_without_frontend_build_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(tmp_path))
    with monkeypatch.context() as m:
        m.setattr("os.path.isdir", lambda d: d == str(tmp_path))
        res = client.get("/dashboard/info", headers={"sec-fetch-mode": "navigate"})
    assert res.status_code == 404


def test_api_call_to_info_still_returns_json():
    res = client.get("/dashboard/info", headers={"sec-fetch-mode": "cors"})
    assert "application/json" in res.headers.get("content-type", "")
