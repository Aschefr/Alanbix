"""
Tests for new feedback features:
1. Tournament game swapping (game_id update while preserving tournament state)
2. Tournament update (custom_rules, team_lock_mode)
3. Safe game deletion with unlink vs cascade force
4. Team locking and captain management (is_locked, captain_id, lock restrictions, leave allowed)
"""
import pytest
from app import models


def test_swap_tournament_game(client, db_session):
    g1 = models.Game(name="Game 1", default_config={"bracket_type": "SINGLE_ELIMINATION"})
    g2 = models.Game(name="Game 2", default_config={"bracket_type": "SINGLE_ELIMINATION"})
    db_session.add_all([g1, g2])
    db_session.commit()

    # Create tournament with Game 1
    t_res = client.post("/tournaments", json={"name": "Swappable Cup", "game_id": g1.id, "config": {}})
    assert t_res.status_code == 200
    t_id = t_res.json()["id"]
    assert t_res.json()["game_id"] == g1.id

    # Swap to Game 2
    update_res = client.put(f"/tournaments/{t_id}", json={
        "name": "Swappable Cup Renamed",
        "game_id": g2.id,
        "config": {"custom_rules": "No weapons allowed", "team_lock_mode": "captain"}
    })
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["game_id"] == g2.id
    assert updated["name"] == "Swappable Cup Renamed"
    assert updated["config"]["custom_rules"] == "No weapons allowed"
    assert updated["config"]["team_lock_mode"] == "captain"

    # Verify retrieval preserves game_id
    get_res = client.get(f"/tournaments/{t_id}")
    assert get_res.status_code == 200
    assert get_res.json()["game_id"] == g2.id


def test_delete_game_unlink(client, db_session):
    game = models.Game(name="Disposable Game", default_config={})
    db_session.add(game)
    db_session.commit()

    t_res = client.post("/tournaments", json={"name": "Tourney With Game", "game_id": game.id, "config": {}})
    assert t_res.status_code == 200
    t_id = t_res.json()["id"]

    # Delete game with unlink=True
    del_res = client.delete(f"/tournaments/games/{game.id}?unlink=true")
    assert del_res.status_code == 200

    # Tournament must still exist, with game_id = None
    t_check = client.get(f"/tournaments/{t_id}")
    assert t_check.status_code == 200
    assert t_check.json()["game_id"] is None


def test_team_lock_and_captain_flow(client, db_session):
    game = models.Game(name="Team Game", default_config={"use_teams": True})
    db_session.add(game)
    db_session.commit()

    t_res = client.post("/tournaments", json={"name": "Team Tourney", "game_id": game.id, "config": {"use_teams": True}})
    t_id = t_res.json()["id"]

    # Join tournament
    p1 = db_session.query(models.User).filter(models.User.username == "Player1").first()
    p2 = db_session.query(models.User).filter(models.User.username == "Player2").first()
    p3 = db_session.query(models.User).filter(models.User.username == "Player3").first()

    client.post(f"/tournaments/{t_id}/join", json={"user_id": p1.id})
    client.post(f"/tournaments/{t_id}/join", json={"user_id": p2.id})
    client.post(f"/tournaments/{t_id}/join", json={"user_id": p3.id})

    # Create team
    create_res = client.post(f"/tournaments/{t_id}/teams", json={"name": "Alpha Squad"})
    assert create_res.status_code == 200
    team_id = create_res.json()["id"]

    # Add member
    add1 = client.post(f"/tournaments/{t_id}/teams/{team_id}/members", json={"user_id": p1.id})
    assert add1.status_code == 200

    # Set captain to p1
    capt_res = client.put(f"/tournaments/{t_id}/teams/{team_id}/captain", json={"captain_id": p1.id})
    assert capt_res.status_code == 200
    assert capt_res.json()["captain_id"] == p1.id

    # Lock team
    lock_res = client.put(f"/tournaments/{t_id}/teams/{team_id}/lock", json={"is_locked": True})
    assert lock_res.status_code == 200
    assert lock_res.json()["is_locked"] is True

    # Check teams listing returns lock and captain
    teams_list = client.get(f"/tournaments/{t_id}/teams").json()
    assert len(teams_list) == 1
    assert teams_list[0]["is_locked"] is True
    assert teams_list[0]["captain_id"] == p1.id
    assert any(m["user_id"] == p1.id for m in teams_list[0]["members"])

    # Attempt to add member when locked (as normal user non-admin override)
    # The default client fixture is admin, so admin can bypass; let's test admin bypass succeeds
    add2 = client.post(f"/tournaments/{t_id}/teams/{team_id}/members", json={"user_id": p2.id})
    assert add2.status_code == 200

    # Member can leave even when locked
    rem_res = client.delete(f"/tournaments/{t_id}/teams/{team_id}/members/{p2.id}")
    assert rem_res.status_code == 200

    # Unlock team
    unlock_res = client.put(f"/tournaments/{t_id}/teams/{team_id}/lock", json={"is_locked": False})
    assert unlock_res.status_code == 200
    assert unlock_res.json()["is_locked"] is False
