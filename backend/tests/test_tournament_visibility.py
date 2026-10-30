"""Hiding a tournament from the players (admins keep seeing it)."""
from app import models
from app.auth import get_optional_user
from app.main import app

from tests.test_tournaments import _create_game, _create_tournament, _get_user_ids, _join_players, _start


def _as(player_or_none):
    app.dependency_overrides[get_optional_user] = lambda: player_or_none


def test_hidden_tournament_is_invisible_to_players_not_to_admins(client, db_session):
    game = _create_game(db_session, "Hide", "single_elim")
    shown = _create_tournament(client, "Visible Cup", game.id, {"bracket_type": "single_elim"})
    hidden = _create_tournament(client, "Hidden Cup", game.id, {"bracket_type": "single_elim"})
    ids = _get_user_ids(db_session, 4)
    _join_players(client, hidden, ids)
    _start(client, hidden)

    res = client.put(f"/tournaments/{hidden}", json={"is_hidden": True})
    assert res.status_code == 200 and res.json()["is_hidden"] is True

    # admin: everything stays reachable
    assert {t["id"] for t in client.get("/tournaments").json()} == {shown, hidden}
    assert client.get(f"/tournaments/{hidden}").status_code == 200

    # a player and the (anonymous) projector only see the visible one
    player = db_session.query(models.User).filter(models.User.username == "Player1").first()
    for who in (player, None):
        _as(who)
        assert {t["id"] for t in client.get("/tournaments").json()} == {shown}
        assert client.get(f"/tournaments/{hidden}").status_code == 404
        assert client.get(f"/tournaments/{hidden}/standings").status_code == 404
        assert client.get(f"/tournaments/{hidden}/participants").status_code == 404
        assert client.get(f"/tournaments/{shown}").status_code == 200

    # showing it again restores it for everybody
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    _as(admin)
    assert client.put(f"/tournaments/{hidden}", json={"is_hidden": False}).status_code == 200
    _as(player)
    assert {t["id"] for t in client.get("/tournaments").json()} == {shown, hidden}


def test_hidden_tournaments_do_not_feed_the_public_numbers(client, db_session):
    game = _create_game(db_session, "Hide2", "single_elim")
    t_id = _create_tournament(client, "Secret", game.id, {"bracket_type": "single_elim"})
    _join_players(client, t_id, _get_user_ids(db_session, 4))
    _start(client, t_id)
    before = client.get("/dashboard/stats").json()
    assert before["active"] == 1
    client.put(f"/tournaments/{t_id}", json={"is_hidden": True})
    after = client.get("/dashboard/stats").json()
    assert after["active"] == 0 and after["tournaments"] == 0
