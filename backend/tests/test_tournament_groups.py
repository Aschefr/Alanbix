"""Groups followed by a knockout bracket (config.phases == "double")."""
import random

import pytest

from tests.test_tournaments import (
    _close,
    _create_game,
    _create_tournament,
    _get_bracket,
    _get_user_ids,
    _join_players,
    _score,
    _start,
)


def _setup(client, db_session, n, ko="single_elim", group_size=4, advancers=2, **extra):
    game = _create_game(db_session, f"g-{n}-{ko}", ko)
    cfg = {"bracket_type": ko, "phases": "double", "group_size": group_size, "advancers_count": advancers,
           "pts_winner": 10, "pts_second": 6, "pts_third": 4, "pts_participation": 1, "pts_per_match": 1}
    cfg.update(extra)
    t_id = _create_tournament(client, "Groups Cup", game.id, cfg)
    ids = _get_user_ids(db_session, n)
    _join_players(client, t_id, ids)
    _start(client, t_id)
    return t_id, ids


def _play_groups(client, t_id, rng):
    for m in [m for m in _get_bracket(client, t_id) if m["id"]["s"] >= 100]:
        a, b = rng.randint(0, 5), rng.randint(0, 5)
        if a == b:
            a += 1
        _score(client, t_id, m, [a, b])


def _play_knockout(client, t_id, rng):
    for _ in range(200):
        todo = [m for m in _get_bracket(client, t_id)
                if m["id"]["s"] < 100 and 0 not in m["p"] and not (m["score"][0] or m["score"][1])]
        if not todo:
            return
        a, b = rng.randint(1, 5), rng.randint(0, 4)
        if a == b:
            a += 1
        _score(client, t_id, todo[0], [a, b])
    pytest.fail("knockout never finished")


def test_groups_stage_creates_only_group_matches(client, db_session):
    t_id, ids = _setup(client, db_session, 8)
    bracket = _get_bracket(client, t_id)
    assert all(m["id"]["s"] >= 100 for m in bracket)
    assert len(bracket) == 12  # two groups of four, six matches each
    assert {m["id"]["s"] for m in bracket} == {101, 102}
    state = client.get(f"/tournaments/{t_id}").json()
    assert state["config"]["bracket_type"] == "round_robin"
    assert state["config"]["ko_type"] == "single_elim"
    assert state["config"]["stage"] == "groups"


def test_knockout_cannot_start_before_groups_are_over(client, db_session):
    t_id, _ = _setup(client, db_session, 8)
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 400
    assert client.get(f"/tournaments/{t_id}/group-stage").json()["complete"] is False


@pytest.mark.parametrize("n,group_size,advancers,ko", [
    (8, 4, 2, "single_elim"),
    (7, 4, 2, "single_elim"),
    (10, 5, 2, "single_elim"),
    (9, 3, 1, "single_elim"),
    (12, 4, 2, "double_elim"),
    (6, 3, 2, "double_elim"),
])
def test_groups_then_knockout_full_lifecycle(client, db_session, n, group_size, advancers, ko):
    rng = random.Random(n)
    t_id, ids = _setup(client, db_session, n, ko, group_size, advancers)
    _play_groups(client, t_id, rng)

    gs = client.get(f"/tournaments/{t_id}/group-stage").json()
    assert gs["complete"] is True
    qualifiers_expected = sum(min(advancers, len(g["table"])) for g in gs["groups"])

    res = client.post(f"/tournaments/{t_id}/start-knockout")
    assert res.status_code == 200, res.text
    qualifiers = res.json()["qualifiers"]
    assert len(qualifiers) == qualifiers_expected
    assert len(set(qualifiers)) == qualifiers_expected

    state = client.get(f"/tournaments/{t_id}").json()
    assert state["config"]["bracket_type"] == ko and state["config"]["stage"] == "knockout"
    ko_players = {pid for m in state["bracket"] if m["id"]["s"] < 100 for pid in m["p"] if pid}
    assert ko_players <= set(qualifiers) and len(ko_players) >= 1

    # group results are frozen once the knockout started
    group_match = next(m for m in state["bracket"] if m["id"]["s"] >= 100)
    r = client.put(f"/tournaments/{t_id}/score", json={
        "match_s": group_match["id"]["s"], "match_r": group_match["id"]["r"],
        "match_m": group_match["id"]["m"], "score": [9, 0]})
    assert r.status_code == 409

    _play_knockout(client, t_id, rng)
    assert client.get(f"/tournaments/{t_id}").json()["status"] == "DONE"

    results = _close(client, t_id)["results"]
    assert {r["entity_id"] for r in results} == set(ids)
    assert len([r for r in results if r["rank"] == 1]) == 1
    qualified_ranks = [r["rank"] for r in results if r["entity_id"] in set(qualifiers) and r["rank"]]
    out_ranks = [r["rank"] for r in results if r["entity_id"] not in set(qualifiers) and r["rank"]]
    if out_ranks and qualified_ranks:
        assert min(out_ranks) > max(qualified_ranks), "players out after the groups must rank behind the knockout"


def test_group_winners_are_seeded_first_and_split(client, db_session):
    t_id, ids = _setup(client, db_session, 8)
    rng = random.Random(3)
    _play_groups(client, t_id, rng)
    gs = client.get(f"/tournaments/{t_id}/group-stage").json()
    top = {g["group"]: [row["entity_id"] for row in g["table"][:2]] for g in gs["groups"]}
    res = client.post(f"/tournaments/{t_id}/start-knockout").json()
    assert res["qualifiers"] == [top[1][0], top[2][0], top[1][1], top[2][1]]
    # first round: the winner of one group meets the runner-up of the other
    r1 = [m for m in _get_bracket(client, t_id) if m["id"]["s"] == 1 and m["id"]["r"] == 1]
    for m in r1:
        groups = {next(g for g, ps in top.items() if pid in ps) for pid in m["p"]}
        assert len(groups) == 2, "first knockout round must not repeat a group match-up"


def test_groups_rollback_before_and_after_knockout_play(client, db_session):
    rng = random.Random(5)
    t_id, _ = _setup(client, db_session, 8)
    _play_groups(client, t_id, rng)
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 200
    assert client.post(f"/tournaments/{t_id}/groups-rollback").status_code == 200
    state = client.get(f"/tournaments/{t_id}").json()
    assert state["config"]["stage"] == "groups" and state["config"]["bracket_type"] == "round_robin"
    assert all(m["id"]["s"] >= 100 for m in state["bracket"])

    # fix a score, replay the knockout, then the rollback is refused
    m = state["bracket"][0]
    client.put(f"/tournaments/{t_id}/score", json={
        "match_s": m["id"]["s"], "match_r": m["id"]["r"], "match_m": m["id"]["m"], "score": [5, 2]})
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 200
    first = next(x for x in _get_bracket(client, t_id) if x["id"]["s"] == 1 and 0 not in x["p"])
    _score(client, t_id, first, [3, 1])
    assert client.post(f"/tournaments/{t_id}/groups-rollback").status_code == 409


def test_reset_restores_the_knockout_format(client, db_session):
    t_id, _ = _setup(client, db_session, 8, "double_elim")
    res = client.put(f"/tournaments/{t_id}", json={"status": "OPEN", "bracket": None})
    assert res.status_code == 200
    cfg = client.get(f"/tournaments/{t_id}").json()["config"]
    assert cfg["bracket_type"] == "double_elim"
    assert "stage" not in cfg and "ko_type" not in cfg
    _start(client, t_id)
    assert client.get(f"/tournaments/{t_id}").json()["config"]["stage"] == "groups"


def test_editing_keeps_the_server_side_group_settings(client, db_session):
    t_id, _ = _setup(client, db_session, 8)
    # an edit dialog sending a config without the keys the server wrote (or a wrong format)
    res = client.put(f"/tournaments/{t_id}", json={"name": "Renamed", "config": {
        "bracket_type": "round_robin", "phases": "double", "group_size": 4, "advancers_count": 2}})
    assert res.status_code == 200, res.text
    cfg = client.get(f"/tournaments/{t_id}").json()["config"]
    assert cfg["stage"] == "groups" and cfg["ko_type"] == "single_elim" and cfg["bracket_type"] == "round_robin"
    assert client.get(f"/tournaments/{t_id}/group-stage").json()["enabled"] is True


def test_lost_group_settings_are_repaired():
    from app.routers.tournaments import _heal_two_phase_config
    groups = [{"id": {"s": 101, "r": 1, "m": 1}, "p": [1, 2], "score": [None, None]}]
    cfg = {"bracket_type": "round_robin", "phases": "double"}
    assert _heal_two_phase_config(cfg, groups) is True
    assert cfg["stage"] == "groups" and cfg["ko_type"] == "single_elim" and cfg["bracket_type"] == "round_robin"

    with_lb = groups + [{"id": {"s": 2, "r": 1, "m": 1}, "p": [0, 0], "score": [None, None]}]
    cfg2 = {"bracket_type": "round_robin", "phases": "double"}
    assert _heal_two_phase_config(cfg2, with_lb) is True
    assert cfg2["stage"] == "knockout" and cfg2["ko_type"] == "double_elim" and cfg2["bracket_type"] == "double_elim"

    assert _heal_two_phase_config({"bracket_type": "round_robin"}, groups) is False
