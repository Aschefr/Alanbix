"""
Tournament engine sweep
=======================
Plays complete tournaments for many player counts and format options, with
pseudo-random results, and checks the invariants a LAN organiser relies on:
the tournament finishes, every playable match can be scored, there is exactly
one champion, nobody is lost or duplicated, and closing distributes points.
"""
import random

import pytest

from app import models
from tests.test_tournaments import (
    _close,
    _create_game,
    _create_tournament,
    _find,
    _get_bracket,
    _get_user_ids,
    _join_players,
    _score,
    _standings,
    _start,
)


def _playable(match, bracket_type):
    p = match["p"]
    if len(p) < 2 or 0 in p:
        return False
    s = match.get("score") or [None, None]
    if bracket_type == "round_robin":
        return s[0] is None or s[1] is None or (s[0] == 0 and s[1] == 0)
    return s[0] is None or s[1] is None or (s[0] == 0 and s[1] == 0)


def _play_out(client, t_id, bracket_type, rng, allow_draws=False, max_steps=500):
    """Score playable matches until nothing is left. Returns True if the server said DONE."""
    done = False
    for _ in range(max_steps):
        bracket = _get_bracket(client, t_id)
        todo = [m for m in bracket if _playable(m, bracket_type)]
        if not todo:
            break
        m = todo[0]
        a, b = rng.randint(1, 5), rng.randint(0, 4)
        if a == b and not allow_draws:
            a += 1
        res = _score(client, t_id, m, [a, b])
        done = bool(res.get("done"))
    else:
        pytest.fail("tournament never ran out of playable matches")
    return done


@pytest.mark.parametrize("fmt", ["single_elim", "double_elim"])
@pytest.mark.parametrize("n", list(range(2, 18)))
def test_elimination_any_size(client, db_session, fmt, n):
    game = _create_game(db_session, f"{fmt}-{n}", fmt)
    t_id = _create_tournament(client, f"{fmt} {n}", game.id, {
        "bracket_type": fmt, "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1,
    })
    ids = _get_user_ids(db_session, n)
    _join_players(client, t_id, ids)
    _start(client, t_id)

    done = _play_out(client, t_id, fmt, random.Random(n))
    state = client.get(f"/tournaments/{t_id}").json()
    assert done or state["status"] == "DONE", f"not finished: status={state['status']}"

    ranks = _standings(client, t_id)
    assert [r for r in ranks if r.get("rank") == 1], "no champion in standings"
    assert len({r["entity_id"] if "entity_id" in r else r.get("name") for r in ranks}) == len(ranks), "duplicate in standings"

    results = _close(client, t_id)["results"]
    assert len(results) == n, f"{len(results)} results for {n} players"
    assert len([r for r in results if r["rank"] == 1]) == 1, "more than one champion"
    assert {r["entity_id"] for r in results} == set(ids), "a player is missing from the results"


@pytest.mark.parametrize("meet_twice", [False, True])
@pytest.mark.parametrize("group_size", [None, 3, 4])
@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7, 8, 9])
def test_round_robin_any_size(client, db_session, n, group_size, meet_twice):
    cfg = {"bracket_type": "round_robin", "pts_winner": 10, "pts_second": 6, "pts_third": 4,
           "pts_participation": 1, "pts_per_match": 1, "meet_twice": meet_twice, "allow_draws": True}
    if group_size:
        cfg["group_size"] = group_size
    game = _create_game(db_session, f"rr-{n}-{group_size}-{meet_twice}", "round_robin")
    t_id = _create_tournament(client, "RR", game.id, cfg)
    ids = _get_user_ids(db_session, n)
    _join_players(client, t_id, ids)
    _start(client, t_id)

    bracket = _get_bracket(client, t_id)
    # expected number of matches: sum over groups of C(size, 2), doubled when meeting twice
    gs = group_size or n
    sizes, left = [], n
    while left > 0:
        sizes.append(min(gs, left))
        left -= gs
    expected = sum(k * (k - 1) // 2 for k in sizes) * (2 if meet_twice else 1)
    assert len(bracket) == expected, f"{len(bracket)} matches, expected {expected} for groups {sizes}"

    done = _play_out(client, t_id, "round_robin", random.Random(n * 7), allow_draws=True)
    state = client.get(f"/tournaments/{t_id}").json()
    assert done or state["status"] == "DONE", f"not finished: {state['status']}"
    lb = _standings(client, t_id)
    assert len(lb) == n
    lonely = sizes.count(1)
    idle = [p for p in lb if p["matches_played"] == 0]
    assert len(idle) == lonely, f"{len(idle)} players never play (groups {sizes})"
    _close(client, t_id)


@pytest.mark.parametrize("n,group", [(5, 4), (9, 4), (13, 4), (8, 8), (10, 3)])
def test_ffa_round_one_any_size(client, db_session, n, group):
    game = _create_game(db_session, f"ffa-{n}-{group}", "ffa")
    t_id = _create_tournament(client, "FFA", game.id, {
        "bracket_type": "ffa", "ffa_group_size": group, "ffa_advancers": 2,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4, "pts_participation": 1, "pts_per_match": 1,
    })
    ids = _get_user_ids(db_session, n)
    _join_players(client, t_id, ids)
    _start(client, t_id)
    bracket = _get_bracket(client, t_id)
    assert sum(len(m["p"]) for m in bracket) == n, "every player must sit in exactly one R1 match"
    seen = [pid for m in bracket for pid in m["p"]]
    assert sorted(seen) == sorted(ids), "players duplicated or missing in FFA round 1"
    for m in bracket:
        k = len(m["p"])
        _score(client, t_id, m, list(range(1, k + 1)))
    r = client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 3})
    assert r.status_code == 200, r.text
    nxt = [m for m in _get_bracket(client, t_id) if m["id"]["r"] == 2]
    advanced = [pid for m in nxt for pid in m["p"]]
    assert len(advanced) == len(set(advanced)), "a player advanced twice"
    assert len(advanced) == 3, f"{len(advanced)} advanced, expected the 3 requested"


def test_ffa_higher_score_wins_by_default(client, db_session):
    """With the default direction (higher is better) the top score must rank first."""
    game = _create_game(db_session, "ffa-high", "ffa")
    t_id = _create_tournament(client, "FFA high", game.id, {
        "bracket_type": "ffa", "ffa_group_size": 4, "lower_score_is_better": False,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4, "pts_participation": 1, "pts_per_match": 1,
    })
    ids = _get_user_ids(db_session, 4)
    _join_players(client, t_id, ids)
    _start(client, t_id)
    match = _get_bracket(client, t_id)[0]
    scores = [10, 20, 5, 15]
    _score(client, t_id, match, scores)
    best = match["p"][scores.index(20)]
    worst = match["p"][scores.index(5)]
    results = {r["entity_id"]: r["rank"] for r in _close(client, t_id)["results"]}
    assert results[best] == 1, "the highest score must be first"
    assert results[worst] == 4, "the lowest score must be last"


def test_ffa_advance_per_match_keeps_the_best_of_each_lobby(client, db_session):
    game = _create_game(db_session, "ffa-lobby", "ffa")
    t_id = _create_tournament(client, "FFA lobbies", game.id, {
        "bracket_type": "ffa", "ffa_group_size": 4, "lower_score_is_better": True,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4, "pts_participation": 1, "pts_per_match": 1,
    })
    ids = _get_user_ids(db_session, 8)
    _join_players(client, t_id, ids)
    _start(client, t_id)
    bracket = _get_bracket(client, t_id)
    assert len(bracket) == 2
    for m in bracket:
        _score(client, t_id, m, [1, 2, 3, 4])
    res = client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 2, "per_match": True})
    assert res.status_code == 200, res.text
    advanced = {pid for m in _get_bracket(client, t_id) if m["id"]["r"] == 2 for pid in m["p"]}
    expected = {bracket[0]["p"][0], bracket[0]["p"][1], bracket[1]["p"][0], bracket[1]["p"][1]}
    assert advanced == expected
