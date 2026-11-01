"""A player may correct a finished match while the bracket has not moved on from it."""
from app.routers.tournaments import _player_can_correct


def _m(s, r, m, p, score):
    return {"id": {"s": s, "r": r, "m": m}, "p": p, "score": score}


def _single_elim(final_p, final_score=None):
    return [
        _m(1, 1, 1, [1, 2], [3, 1]),
        _m(1, 1, 2, [3, 4], [None, None]),
        _m(1, 2, 1, final_p, final_score or [None, None]),
    ]


def test_correctable_while_next_opponent_unknown():
    bracket = _single_elim([1, 0])
    assert _player_can_correct(bracket, bracket[0], "single_elim")


def test_locked_once_next_opponent_known():
    bracket = _single_elim([1, 3])
    bracket[1]["score"] = [2, 0]
    assert not _player_can_correct(bracket, bracket[0], "single_elim")


def test_locked_once_next_match_scored():
    bracket = _single_elim([1, 0], [1, 0])
    assert not _player_can_correct(bracket, bracket[0], "single_elim")


def test_round_robin_always_correctable():
    bracket = [_m(1, 1, 1, [1, 2], [2, 1]), _m(2, 1, 1, [1, 3], [1, 0])]
    assert _player_can_correct(bracket, bracket[0], "round_robin")


def test_ffa_locked_after_next_round():
    r1 = _m(1, 1, 1, [1, 2, 3], [10, 5, 1])
    assert _player_can_correct([r1], r1, "ffa")
    assert not _player_can_correct([r1, _m(1, 2, 1, [1, 2], [None, None])], r1, "ffa")
