"""
Clearing a result
=================
The "reset" button of a win/loss match sends an empty score for both sides.
The match must go back to "not played" and what followed from it must be undone.
"""
import pytest

from tests.test_tournament_rejections import _make, _ready, _state
from tests.test_tournaments import _get_bracket, _score


def _find(bracket, mid):
    return next(m for m in bracket if m["id"] == mid)


@pytest.mark.parametrize("bracket_type", ["single_elim", "double_elim"])
def test_reset_undoes_the_win_and_what_followed(client, db_session, bracket_type):
    t_id, _ = _make(client, db_session, 4, bracket_type=bracket_type, boolean_mode=True)
    fresh = _get_bracket(client, t_id)
    match = _ready(fresh, section=1)
    _score(client, t_id, match, [1, 0])
    assert _get_bracket(client, t_id) != fresh

    res = client.put(f"/tournaments/{t_id}/score", json={
        "match_s": match["id"]["s"], "match_r": match["id"]["r"], "match_m": match["id"]["m"], "score": [None, None]})
    assert res.status_code == 200, res.text
    assert _get_bracket(client, t_id) == fresh, "the reset left the result or its consequences in place"


def test_reset_in_a_championship(client, db_session):
    t_id, _ = _make(client, db_session, 4, bracket_type="round_robin", boolean_mode=True)
    match = _ready(_get_bracket(client, t_id))
    _score(client, t_id, match, [0, 1])
    res = client.put(f"/tournaments/{t_id}/score", json={
        "match_s": match["id"]["s"], "match_r": match["id"]["r"], "match_m": match["id"]["m"], "score": [None, None]})
    assert res.status_code == 200, res.text
    assert _find(_get_bracket(client, t_id), match["id"])["score"] == [None, None]


def test_reset_of_the_final_reopens_the_tournament(client, db_session):
    t_id, _ = _make(client, db_session, 2, bracket_type="single_elim", boolean_mode=True)
    final = _ready(_get_bracket(client, t_id))
    _score(client, t_id, final, [1, 0])
    assert _state(client, t_id)[0] == "DONE"
    res = client.put(f"/tournaments/{t_id}/score", json={
        "match_s": final["id"]["s"], "match_r": final["id"]["r"], "match_m": final["id"]["m"], "score": [None, None]})
    assert res.status_code == 200, res.text
    status, bracket, _ = _state(client, t_id)
    assert _find(bracket, final["id"])["score"] == [None, None]
    assert status == "RUNNING", "a final with no result cannot leave the tournament finished"
