"""
Impossible matches and impossible moves
=======================================
Every way a score or an action can describe something that cannot happen in a
tournament: a refused request must leave the tournament exactly as it was.
The sweep tests play valid tournaments; this file only feeds the engine what it must refuse.
"""
import pytest
from fastapi import HTTPException

from app import models
from app.auth import get_current_admin, get_current_user, get_optional_user
from app.main import app
from tests.test_tournaments import (
    _create_game,
    _create_tournament,
    _get_bracket,
    _get_user_ids,
    _join_players,
    _score,
    _start,
)

BASE = {"pts_winner": 10, "pts_second": 6, "pts_third": 4, "pts_participation": 1, "pts_per_match": 1}


def _make(client, db_session, n, **cfg):
    game = _create_game(db_session, f"rej-{n}-{len(cfg)}-{sorted(cfg.items())}", cfg.get("bracket_type", "single_elim"))
    t_id = _create_tournament(client, "Rejections", game.id, dict(BASE, **cfg))
    ids = _get_user_ids(db_session, n)
    _join_players(client, t_id, ids)
    _start(client, t_id)
    return t_id, ids


def _state(client, t_id):
    t = client.get(f"/tournaments/{t_id}").json()
    return t["status"], t["bracket"], t["config"]


def _refused(client, t_id, match, score, codes=(400, 409)):
    """The score is refused and nothing changed."""
    before = _state(client, t_id)
    mid = match["id"]
    res = client.put(f"/tournaments/{t_id}/score", json={
        "match_s": mid["s"], "match_r": mid["r"], "match_m": mid["m"], "score": score})
    assert res.status_code in codes, f"{score} on {mid} accepted: {res.status_code} {res.text}"
    assert _state(client, t_id) == before, f"{score} on {mid} was refused but changed the tournament"


def _ready(bracket, section=None):
    """A match with all its players known and no score yet."""
    for m in bracket:
        if section is not None and m["id"]["s"] != section:
            continue
        if len(m["p"]) >= 2 and 0 not in m["p"] and not any(m["score"] or []):
            return m
    raise AssertionError("no ready match")


# ── Duel scores (elimination, championship, groups) ─────────────────────────

DUEL_FORMATS = {
    "single_elim": {"bracket_type": "single_elim"},
    "double_elim": {"bracket_type": "double_elim"},
    "round_robin": {"bracket_type": "round_robin"},
    "groups": {"bracket_type": "single_elim", "phases": "double", "group_size": 3, "advancers_count": 1},
}


@pytest.mark.parametrize("fmt", DUEL_FORMATS)
@pytest.mark.parametrize("score", [
    [3],             # one side only
    [3, 1, 2],       # a third side in a duel
    [],              # nothing
    [-1, 2],         # negative
    [2, -3],
    [3, None],       # half a score on a match not played yet
    [None, 0],
])
def test_a_duel_takes_exactly_two_scores_that_are_not_negative(client, db_session, fmt, score):
    t_id, _ = _make(client, db_session, 6, **DUEL_FORMATS[fmt])
    _refused(client, t_id, _ready(_get_bracket(client, t_id)), score)


@pytest.mark.parametrize("fmt", ["single_elim", "double_elim"])
@pytest.mark.parametrize("score", [[2, 2], [1, 1], [7, 7]])
def test_an_elimination_match_cannot_end_in_a_draw(client, db_session, fmt, score):
    t_id, _ = _make(client, db_session, 8, **DUEL_FORMATS[fmt])
    _refused(client, t_id, _ready(_get_bracket(client, t_id)), score)


def test_an_elimination_draw_is_refused_even_with_draws_allowed(client, db_session):
    t_id, _ = _make(client, db_session, 8, bracket_type="single_elim", allow_draws=True)
    _refused(client, t_id, _ready(_get_bracket(client, t_id)), [2, 2])


def test_a_knockout_match_cannot_end_in_a_draw_even_if_the_groups_allowed_it(client, db_session):
    t_id, _ = _make(client, db_session, 6, bracket_type="single_elim", phases="double",
                    group_size=3, advancers_count=2, allow_draws=True)
    groups = _get_bracket(client, t_id)
    _score(client, t_id, groups[0], [1, 1])  # a draw is fine in a group here
    for m in groups[1:]:
        _score(client, t_id, m, [2, 1])
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 200
    _refused(client, t_id, _ready(_get_bracket(client, t_id), section=1), [3, 3])


def test_a_championship_draw_needs_draws_allowed(client, db_session):
    t_id, _ = _make(client, db_session, 4, bracket_type="round_robin")
    _refused(client, t_id, _ready(_get_bracket(client, t_id)), [2, 2])
    t2, _ = _make(client, db_session, 4, bracket_type="round_robin", allow_draws=True, meet_twice=True)
    _score(client, t2, _ready(_get_bracket(client, t2)), [2, 2])


@pytest.mark.parametrize("score", [[2, 0], [0, 3], [1, 5], [-1, 0]])
def test_win_or_loss_mode_takes_only_one_and_zero(client, db_session, score):
    t_id, _ = _make(client, db_session, 4, bracket_type="round_robin", boolean_mode=True, allow_draws=True)
    _refused(client, t_id, _ready(_get_bracket(client, t_id)), score)


def test_win_or_loss_mode_draw_needs_draws_allowed(client, db_session):
    t_id, _ = _make(client, db_session, 4, bracket_type="round_robin", boolean_mode=True)
    _refused(client, t_id, _ready(_get_bracket(client, t_id)), [1, 1])


# ── Matches that cannot be played ───────────────────────────────────────────

def test_a_match_waiting_for_its_players_cannot_be_scored_even_by_an_admin(client, db_session):
    t_id, _ = _make(client, db_session, 8, bracket_type="single_elim")
    final = next(m for m in _get_bracket(client, t_id) if m["id"]["r"] == 3)
    assert final["p"] == [0, 0]
    _refused(client, t_id, final, [2, 1])
    semi = next(m for m in _get_bracket(client, t_id) if m["id"]["r"] == 2)
    _refused(client, t_id, semi, [2, 1])


def test_a_bye_cannot_be_scored(client, db_session):
    """6 players in an 8 bracket: two first-round matches have a single player, decided by the server."""
    t_id, _ = _make(client, db_session, 6, bracket_type="single_elim")
    bye = next(m for m in _get_bracket(client, t_id) if m["id"]["r"] == 1 and 0 in m["p"])
    _refused(client, t_id, bye, [0, 3])


def test_a_double_elimination_losers_match_waits_for_its_players(client, db_session):
    t_id, _ = _make(client, db_session, 8, bracket_type="double_elim")
    lb = next(m for m in _get_bracket(client, t_id) if m["id"]["s"] == 2 and 0 in m["p"])
    _refused(client, t_id, lb, [2, 1])


def test_a_match_that_does_not_exist(client, db_session):
    t_id, _ = _make(client, db_session, 4, bracket_type="single_elim")
    _refused(client, t_id, {"id": {"s": 1, "r": 9, "m": 1}}, [2, 1], codes=(404,))
    _refused(client, t_id, {"id": {"s": 7, "r": 1, "m": 1}}, [2, 1], codes=(404,))


def test_a_group_score_cannot_change_once_the_knockout_started(client, db_session):
    t_id, _ = _make(client, db_session, 6, bracket_type="single_elim", phases="double", group_size=3, advancers_count=2)
    for m in _get_bracket(client, t_id):
        _score(client, t_id, m, [2, 1])
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 200
    group_match = next(m for m in _get_bracket(client, t_id) if m["id"]["s"] >= 100)
    _refused(client, t_id, group_match, [0, 5])


def test_a_closed_tournament_takes_no_score(client, db_session):
    """Closing handed out the points: a score changed afterwards would not match them."""
    t_id, _ = _make(client, db_session, 2, bracket_type="single_elim")
    final = _get_bracket(client, t_id)[0]
    _score(client, t_id, final, [2, 1])
    assert client.post(f"/tournaments/{t_id}/close").status_code == 200
    _refused(client, t_id, final, [0, 3])


# ── Free-for-all ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score", [
    [5, 3, 2],          # one slot missing
    [5, 3, 2, 1, 4],    # one slot too many
    [5, -3, 2, 1],      # negative
])
def test_a_free_for_all_lobby_takes_one_score_per_player(client, db_session, score):
    t_id, _ = _make(client, db_session, 8, bracket_type="ffa", ffa_group_size=4)
    lobby = _get_bracket(client, t_id)[0]
    assert len(lobby["p"]) == 4
    _refused(client, t_id, lobby, score)


def _ffa_round_played(client, db_session, n=8):
    t_id, ids = _make(client, db_session, n, bracket_type="ffa", ffa_group_size=4)
    for m in _get_bracket(client, t_id):
        _score(client, t_id, m, list(range(1, len(m["p"]) + 1)))
    return t_id


@pytest.mark.parametrize("keep", [0, -1, 1, 8, 9])
def test_the_next_free_for_all_round_needs_fewer_players_but_at_least_two(client, db_session, keep):
    """Keep 1 would make a lobby of one, keep everyone would replay the same round forever."""
    t_id = _ffa_round_played(client, db_session)
    before = _state(client, t_id)
    res = client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": keep})
    assert res.status_code == 400, f"keep {keep} accepted: {res.text}"
    assert _state(client, t_id) == before


def test_per_lobby_advance_must_still_drop_someone(client, db_session):
    t_id = _ffa_round_played(client, db_session)
    before = _state(client, t_id)
    res = client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 4, "per_match": True})
    assert res.status_code == 400, res.text
    assert _state(client, t_id) == before


def test_the_next_round_needs_every_lobby_played(client, db_session):
    t_id, _ = _make(client, db_session, 8, bracket_type="ffa", ffa_group_size=4)
    _score(client, t_id, _get_bracket(client, t_id)[0], [1, 2, 3, 4])
    before = _state(client, t_id)
    assert client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 4}).status_code == 400
    assert _state(client, t_id) == before


# ── Moves that do not fit the tournament's state ────────────────────────────

def test_a_running_tournament_cannot_be_started_again(client, db_session):
    """Starting again would draw a new bracket and wipe every score."""
    t_id, _ = _make(client, db_session, 4, bracket_type="single_elim")
    _score(client, t_id, _ready(_get_bracket(client, t_id)), [2, 1])
    before = _state(client, t_id)
    assert client.post(f"/tournaments/{t_id}/start").status_code in (400, 409)
    assert _state(client, t_id) == before


def test_nobody_joins_a_tournament_already_drawn(client, db_session):
    """A player added after the draw is in no match: the interface only offers it while open."""
    t_id, ids = _make(client, db_session, 4, bracket_type="single_elim")
    late = _get_user_ids(db_session, 5)[-1]
    assert client.post(f"/tournaments/{t_id}/join", json={"user_id": late}).status_code == 400
    assert client.post(f"/tournaments/{t_id}/join-all").status_code == 400
    assert late not in [p["user_id"] for p in client.get(f"/tournaments/{t_id}/participants").json()]


def test_the_knockout_needs_the_groups_and_only_starts_once(client, db_session):
    t_id, _ = _make(client, db_session, 6, bracket_type="single_elim", phases="double", group_size=3, advancers_count=2)
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 400  # groups not played
    for m in _get_bracket(client, t_id):
        _score(client, t_id, m, [2, 1])
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 200
    before = _state(client, t_id)
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 400
    assert _state(client, t_id) == before


def test_free_for_all_moves_on_other_formats_are_refused(client, db_session):
    t_id, _ = _make(client, db_session, 4, bracket_type="single_elim")
    before = _state(client, t_id)
    assert client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 2}).status_code == 400
    assert client.post(f"/tournaments/{t_id}/start-knockout").status_code == 400
    assert _state(client, t_id) == before


# ── A player, not an admin ──────────────────────────────────────────────────

@pytest.fixture()
def as_player(db_session):
    def not_admin():
        raise HTTPException(status_code=403, detail="Admins only")

    def use(username):
        user = db_session.query(models.User).filter(models.User.username == username).first()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_user] = lambda: user
        app.dependency_overrides[get_current_admin] = not_admin
        return user
    yield use


def test_a_player_only_scores_their_own_ready_match(client, db_session, as_player):
    t_id, ids = _make(client, db_session, 8, bracket_type="single_elim")
    bracket = _get_bracket(client, t_id)
    names = {u.id: u.username for u in db_session.query(models.User).all()}
    mine = bracket[0]
    other = next(m for m in bracket if m["id"]["r"] == 1 and m is not mine)
    player = as_player(names[mine["p"][0]])
    _refused(client, t_id, other, [2, 1], codes=(403,))
    final = next(m for m in bracket if m["id"]["r"] == 3)
    _refused(client, t_id, final, [2, 1], codes=(403,))
    _refused(client, t_id, mine, [2, 2])      # the same rules as an admin
    _refused(client, t_id, mine, [-2, 1])
    outsider = as_player(names[_get_user_ids(db_session, 9)[-1]])
    assert outsider.id not in ids
    _refused(client, t_id, mine, [2, 1], codes=(403,))


def test_a_player_cannot_start_or_move_a_tournament(client, db_session, as_player):
    t_id, ids = _make(client, db_session, 4, bracket_type="ffa", ffa_group_size=4)
    _score(client, t_id, _get_bracket(client, t_id)[0], [1, 2, 3, 4])
    names = {u.id: u.username for u in db_session.query(models.User).all()}
    as_player(names[ids[0]])
    before = _state(client, t_id)
    for path, body in (("start", {}), ("ffa-advance", {"keep_count": 2}), ("ffa-finish", {}), ("close", {})):
        assert client.post(f"/tournaments/{t_id}/{path}", json=body).status_code in (401, 403), path
    assert _state(client, t_id) == before
