"""Regression: in a 4-player single elimination, winning the first semi-final
must not auto-win the final nor finish the tournament (the "Duel Test" bug)."""
from tests.test_tournaments import (
    _create_game, _create_tournament, _get_bracket, _get_user_ids, _join_players, _score, _start,
)


def test_first_semi_does_not_finish_single_elim(client, db_session):
    game = _create_game(db_session, "Duel", "single_elim")
    t_id = _create_tournament(client, "Duel", game.id, {
        "bracket_type": "single_elim", "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1,
    })
    _join_players(client, t_id, _get_user_ids(db_session, 4))
    _start(client, t_id)

    semi = next(m for m in _get_bracket(client, t_id) if m["id"]["r"] == 1)
    res = _score(client, t_id, semi, [2, 0])
    assert not res.get("done")

    state = client.get(f"/tournaments/{t_id}").json()
    final = next(m for m in _get_bracket(client, t_id) if m["id"]["r"] == 2)
    assert state["status"] != "DONE"
    assert (final.get("score") or [None, None]) == [None, None], f"final auto-scored: {final}"
