import jwt
import pytest

from app import auth
from app.main import app


@pytest.fixture
def client(client):
    # The shared client logs every request in as an admin; check real tokens here
    app.dependency_overrides.pop(auth.get_current_user, None)
    return client


def login(client, username="Player1", password="pass"):
    return client.post("/token", data={"username": username, "password": password}).json()["access_token"]


def claims(token):
    return jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])


def test_session_lasts_three_days(client):
    c = claims(login(client))
    assert c["exp"] - c["iat"] == 3 * 24 * 3600


def test_refresh_gives_a_working_session(client):
    token = login(client)
    res = client.post("/token/refresh", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    fresh = res.json()["access_token"]
    assert claims(fresh)["sub"] == "Player1"
    assert client.get("/me", headers={"Authorization": f"Bearer {fresh}"}).json()["username"] == "Player1"


def test_refresh_needs_a_valid_session(client):
    assert client.post("/token/refresh").status_code == 401
    assert client.post("/token/refresh", headers={"Authorization": "Bearer nope"}).status_code == 401
