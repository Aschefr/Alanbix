from unittest.mock import patch

import pytest

from app.routers import users


@pytest.fixture(autouse=True)
def fresh_guard():
    users._login_failures.clear()
    yield
    users._login_failures.clear()


def login(client, username, password):
    return client.post("/token", data={"username": username, "password": password})


def test_account_locked_after_five_wrong_passwords(client):
    for _ in range(4):
        assert login(client, "Player1", "wrong").status_code == 401
    res = login(client, "Player1", "wrong")
    assert res.status_code == 429
    assert res.json()["detail"]["code"] == "too_many_attempts"
    assert 0 < int(res.headers["Retry-After"]) <= users._LOGIN_LOCK + 1
    # Even the right password waits: the guesser cannot tell when it found it
    assert login(client, "Player1", "pass").status_code == 429
    # Another account from the same address is not blocked by these 5 failures
    assert login(client, "Player2", "pass").status_code == 200


def test_lock_expires(client):
    for _ in range(5):
        login(client, "Player1", "wrong")
    later = users._time.monotonic() + users._LOGIN_LOCK + 1
    with patch.object(users._time, "monotonic", return_value=later):
        assert login(client, "Player1", "pass").status_code == 200


def test_success_clears_account_failures(client):
    for _ in range(4):
        login(client, "Player1", "wrong")
    assert login(client, "Player1", "pass").status_code == 200
    assert login(client, "Player1", "wrong").status_code == 401


def test_address_locked_when_trying_many_accounts(client):
    for i in range(users._LOGIN_MAX_PER_ADDRESS):
        login(client, f"Player{i % 21 + 1}x", "wrong")
    assert login(client, "Player1", "pass").status_code == 429
