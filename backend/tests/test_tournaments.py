"""
Automated Tournament Scoring Test Suite
========================================
Stress-tests scoring logic across all tournament modes:
- FFA (21 players, multi-round with ffa-advance)
- Round Robin (6 players, all 15 matches scored)
- Single Elimination (8 players, full bracket to finale)
- Double Elimination (8 players, WB→LB dropout + Grand Final)
- Team Round Robin (5 teams × 4 players, all 10 matches)

Each test validates score integrity at multiple progression points.
"""
import pytest
from app import models


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_game(db, name, bracket_type):
    game = models.Game(name=name, default_config={"bracket_type": bracket_type})
    db.add(game)
    db.commit()
    return game


def _create_tournament(client, name, game_id, config):
    res = client.post("/tournaments", json={"name": name, "game_id": game_id, "config": config})
    assert res.status_code == 200, f"Create tournament failed: {res.text}"
    return res.json()["id"]


def _join_players(client, t_id, user_ids):
    for uid in user_ids:
        res = client.post(f"/tournaments/{t_id}/join", json={"user_id": uid})
        assert res.status_code == 200, f"Join failed for user {uid}: {res.text}"


def _start(client, t_id):
    res = client.post(f"/tournaments/{t_id}/start")
    assert res.status_code == 200, f"Start failed: {res.text}"
    return res.json()


def _get_bracket(client, t_id):
    res = client.get(f"/tournaments/{t_id}")
    assert res.status_code == 200
    return res.json()["bracket"]


def _score(client, t_id, match, scores):
    mid = match["id"]
    res = client.put(f"/tournaments/{t_id}/score", json={
        "match_s": mid["s"], "match_r": mid["r"], "match_m": mid["m"],
        "score": scores
    })
    assert res.status_code == 200, f"Score failed: {res.text}"
    return res.json()


def _standings(client, t_id):
    res = client.get(f"/tournaments/{t_id}/standings")
    assert res.status_code == 200
    return res.json()["standings"]


def _close(client, t_id):
    res = client.post(f"/tournaments/{t_id}/close")
    assert res.status_code == 200, f"Close failed: {res.text}"
    return res.json()


def _find(bracket, s, r, m):
    return next((x for x in bracket if x["id"]["s"] == s and x["id"]["r"] == r and x["id"]["m"] == m), None)


def _get_user_ids(db, count=21):
    return [u.id for u in db.query(models.User).filter(
        models.User.username.startswith("Player")
    ).order_by(models.User.id).limit(count).all()]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1 — FFA 21 joueurs, multi-manche, close + point distribution
# ═══════════════════════════════════════════════════════════════════════════

def test_ffa_21_players_full_lifecycle(client, db_session):
    """FFA: 21 players → score manche 1 → advance to 11 → score manche 2 → finish → close."""
    game = _create_game(db_session, "Golf FFA", "ffa")
    t_id = _create_tournament(client, "Mega FFA", game.id, {
        "bracket_type": "ffa",
        "lower_score_is_better": True,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 21)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    # ── Manche 1: all 21 players ──
    bracket = _get_bracket(client, t_id)
    assert len(bracket) == 1, "FFA should have 1 match per round"

    match = bracket[0]
    match_p = match["p"]
    assert len(match_p) == 21

    # Score: each player gets their position index as score (lower = better)
    # Player at index 0 gets 1 (best), index 20 gets 21 (worst)
    scores = list(range(1, 22))
    _score(client, t_id, match, scores)

    # ── Verify standings after manche 1 ──
    lb = _standings(client, t_id)
    assert len(lb) == 21, f"Expected 21 entries, got {len(lb)}"

    # No H2H wins in FFA
    for p in lb:
        assert p["wins"] == 0, f"H2H bug: {p['name']} has {p['wins']} wins in FFA"

    # Best player (score=1) should be ranked first
    best_pid = match_p[0]  # scored 1
    worst_pid = match_p[20]  # scored 21
    best = next(p for p in lb if p["entity_id"] == best_pid)
    worst = next(p for p in lb if p["entity_id"] == worst_pid)
    assert best["total"] > worst["total"], "Best score should yield highest points"
    assert best["rank"] == 1, f"Best player should be rank 1, got {best['rank']}"

    # ── Advance to 11 players ──
    res = client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 11})
    assert res.status_code == 200
    assert res.json()["round"] == 2

    # ── Manche 2: 11 players ──
    bracket = _get_bracket(client, t_id)
    manche2 = _find(bracket, 1, 2, 1)
    assert manche2 is not None, "Manche 2 should exist"
    assert len(manche2["p"]) == 11, f"Expected 11 advancing players, got {len(manche2['p'])}"

    scores2 = list(range(1, 12))
    _score(client, t_id, manche2, scores2)

    # ── Finish + Close ──
    res = client.post(f"/tournaments/{t_id}/ffa-finish")
    assert res.status_code == 200

    close_res = _close(client, t_id)
    results = close_res["results"]
    assert len(results) > 0, "Close should produce results"

    # Verify placement points
    first = next((r for r in results if r["rank"] == 1), None)
    assert first is not None, "Should have a rank 1"
    assert first["placement_pts"] == 10, f"1st should get 10 pts, got {first['placement_pts']}"

    # Verify User.points were persisted
    db_session.expire_all()
    first_user = db_session.query(models.User).filter(models.User.id == first["entity_id"]).first()
    assert first_user.points > 0, "User.points should be credited after close"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2 — Round Robin 6 joueurs, 15 matchs scorés, standings progression
# ═══════════════════════════════════════════════════════════════════════════

def test_round_robin_6_players_full(client, db_session):
    """RR: 6 players = 15 matches, all scored. Check standings + close distribution."""
    game = _create_game(db_session, "Fighter RR", "round_robin")
    t_id = _create_tournament(client, "Fighter League", game.id, {
        "bracket_type": "round_robin",
        "lower_score_is_better": False,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 6)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    bracket = _get_bracket(client, t_id)
    assert len(bracket) == 15, f"Expected 15 RR matches for 6 players, got {len(bracket)}"

    # ── Score all 15 matches ──
    # p[0] always wins with score [3, 1]
    for i, match in enumerate(bracket):
        _score(client, t_id, match, [3, 1])

    # ── Verify standings after all matches ──
    lb = _standings(client, t_id)
    assert len(lb) == 6, f"Expected 6 entries, got {len(lb)}"

    # All players should have played 5 matches each
    for p in lb:
        assert p["matches_played"] == 5, f"{p['name']} played {p['matches_played']}, expected 5"

    # Total wins across all players should be 15 (one winner per match)
    total_wins = sum(p["wins"] for p in lb)
    assert total_wins == 15, f"Total wins should be 15, got {total_wins}"

    # ── Close and verify distribution ──
    close_res = _close(client, t_id)
    results = close_res["results"]

    # Verify that rank 1 gets pts_winner
    first = next((r for r in results if r["rank"] == 1), None)
    assert first is not None, "Should have a rank 1"
    assert first["placement_pts"] == 10

    # Verify all participants got participation points
    for r in results:
        assert r["participation_pts"] > 0, f"{r['name']} should have participation pts"

    # Verify User.points persistence
    db_session.expire_all()
    for r in results:
        user = db_session.query(models.User).filter(models.User.id == r["entity_id"]).first()
        assert user.points > 0, f"{user.username} should have points after close"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3 — Single Elimination 8 joueurs, bracket complet → finale
# ═══════════════════════════════════════════════════════════════════════════

def test_single_elim_8_players_full_bracket(client, db_session):
    """SE: 8 players = perfect bracket (no BYE). Play R1→R2→Finale, verify DONE + close."""
    game = _create_game(db_session, "Duel SE", "single_elim")
    t_id = _create_tournament(client, "Elim Cup", game.id, {
        "bracket_type": "single_elim",
        "lower_score_is_better": False,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 8)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    bracket = _get_bracket(client, t_id)
    # 8 players = 4 + 2 + 1 = 7 matches
    assert len(bracket) == 7, f"Expected 7 SE matches, got {len(bracket)}"

    # No BYEs with 8 players
    r1 = [m for m in bracket if m["id"]["r"] == 1]
    assert len(r1) == 4
    for m in r1:
        assert m["p"][0] != 0 and m["p"][1] != 0, "No BYEs expected in 8-player bracket"

    # ── Score Round 1 (4 matches) ──
    for m in r1:
        _score(client, t_id, m, [3, 1])  # p[0] always wins

    # Refetch bracket — winners should have advanced to R2
    bracket = _get_bracket(client, t_id)
    r2 = [m for m in bracket if m["id"]["r"] == 2]
    assert len(r2) == 2

    for m in r2:
        assert m["p"][0] != 0 and m["p"][1] != 0, "R2 slots should be filled after R1"

    # ── Score Round 2 (Semi-finals) ──
    for m in r2:
        _score(client, t_id, m, [3, 1])

    # ── Score Finale ──
    bracket = _get_bracket(client, t_id)
    finale = _find(bracket, 1, 3, 1)
    assert finale is not None
    assert finale["p"][0] != 0 and finale["p"][1] != 0, "Finale should have 2 players"

    result = _score(client, t_id, finale, [5, 2])
    assert result["done"] is True, "Tournament should be DONE after final scored"

    # ── Verify standings before close ──
    lb = _standings(client, t_id)
    ranked = [p for p in lb if p["rank"] is not None]
    assert len(ranked) >= 2, "At least 1st and 2nd should be ranked"

    # ── Close and verify ──
    close_res = _close(client, t_id)
    results = close_res["results"]

    first = next((r for r in results if r["rank"] == 1), None)
    second = next((r for r in results if r["rank"] == 2), None)
    assert first is not None and second is not None
    assert first["placement_pts"] == 10
    assert second["placement_pts"] == 6
    assert first["total"] > second["total"], "1st should have more points than 2nd"

    # 3rd place: semi-final losers
    thirds = [r for r in results if r["rank"] == 3]
    assert len(thirds) == 2, "Both semi-final losers should get 3rd"
    for t in thirds:
        assert t["placement_pts"] == 4


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4 — Double Elimination 8 joueurs, WB→LB dropout + Grand Final
# ═══════════════════════════════════════════════════════════════════════════

def test_double_elim_8_players_lb_dropout(client, db_session):
    """DE: 8 players. Score WB R1, verify losers go to LB. Play through GF."""
    game = _create_game(db_session, "Duel DE", "double_elim")
    t_id = _create_tournament(client, "DE Cup", game.id, {
        "bracket_type": "double_elim",
        "lower_score_is_better": False,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 8)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    bracket = _get_bracket(client, t_id)

    # DE 8 players: WB has 7 matches (s=1), LB has several (s=2)
    wb = [m for m in bracket if m["id"]["s"] == 1]
    lb = [m for m in bracket if m["id"]["s"] == 2]
    assert len(wb) > 0, "Should have WB matches"
    assert len(lb) > 0, "Should have LB matches"

    # ── Score WB R1 (4 matches) ──
    wb_r1 = [m for m in wb if m["id"]["r"] == 1]
    assert len(wb_r1) == 4

    losers_r1 = []
    for m in wb_r1:
        _score(client, t_id, m, [3, 1])
        losers_r1.append(m["p"][1])  # p[1] loses (score 1 < 3)

    # Refetch — verify losers dropped to LB
    bracket = _get_bracket(client, t_id)
    lb_updated = [m for m in bracket if m["id"]["s"] == 2]
    lb_players = set()
    for m in lb_updated:
        for pid in m["p"]:
            if pid != 0:
                lb_players.add(pid)

    for loser in losers_r1:
        assert loser in lb_players, f"Loser {loser} should be in LB"

    # ── Play through remaining WB + LB until GF ──
    # Score all unscored matches iteratively until GF is ready
    max_iters = 30
    for _ in range(max_iters):
        bracket = _get_bracket(client, t_id)
        unscored = [
            m for m in bracket
            if m["p"][0] != 0 and m["p"][1] != 0
            and (m["score"][0] is None or m["score"][0] == 0)
            and (m["score"][1] is None or m["score"][1] == 0)
        ]
        if not unscored:
            break
        for m in unscored:
            _score(client, t_id, m, [3, 1])
            break  # re-fetch after each score (advancement changes bracket)

    # Tournament should be DONE
    res = client.get(f"/tournaments/{t_id}")
    assert res.json()["status"] == "DONE", f"Expected DONE, got {res.json()['status']}"

    # ── Close and verify ──
    close_res = _close(client, t_id)
    results = close_res["results"]

    first = next((r for r in results if r["rank"] == 1), None)
    second = next((r for r in results if r["rank"] == 2), None)
    assert first is not None, "Should have a winner"
    assert second is not None, "Should have a runner-up"
    assert first["placement_pts"] == 10
    assert second["placement_pts"] == 6
    assert first["total"] > second["total"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5 — Team Round Robin, 5 équipes × 4 joueurs
# ═══════════════════════════════════════════════════════════════════════════

def test_team_rr_5_teams_point_distribution(client, db_session):
    """Team RR: 5 teams (4 members each) = 10 matches. Verify points go to all members."""
    game = _create_game(db_session, "Team Game", "round_robin")
    t_id = _create_tournament(client, "Team League", game.id, {
        "bracket_type": "round_robin",
        "lower_score_is_better": False,
        "use_teams": True,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 21)

    # Join all 20 players first (requirement: must be participant before joining team)
    _join_players(client, t_id, user_ids[:20])

    # Create 5 teams, 4 members each
    team_ids = []
    for i in range(5):
        res = client.post(f"/tournaments/{t_id}/teams", json={"name": f"Team {chr(65 + i)}"})
        assert res.status_code == 200, f"Create team failed: {res.text}"
        team_ids.append(res.json()["id"])

    for i, tid in enumerate(team_ids):
        members = user_ids[i * 4:(i + 1) * 4]
        for uid in members:
            res = client.post(f"/tournaments/{t_id}/teams/{tid}/members", json={"user_id": uid})
            assert res.status_code == 200, f"Add member {uid} to team {tid} failed: {res.text}"

    _start(client, t_id)

    bracket = _get_bracket(client, t_id)
    # 5 teams RR = C(5,2) = 10 matches
    assert len(bracket) == 10, f"Expected 10 team RR matches, got {len(bracket)}"

    # Verify teams are negative IDs
    for m in bracket:
        for pid in m["p"]:
            if pid != 0:
                assert pid < 0, f"Team IDs should be negative, got {pid}"

    # ── Score all 10 matches ──
    # Alternate winners: odd matches p[0] wins, even matches p[1] wins
    for i, match in enumerate(bracket):
        if i % 2 == 0:
            _score(client, t_id, match, [3, 1])
        else:
            _score(client, t_id, match, [1, 3])

    # ── Verify standings ──
    lb = _standings(client, t_id)
    assert len(lb) >= 5, f"Expected at least 5 team entries, got {len(lb)}"

    total_wins = sum(p["wins"] for p in lb if p["entity_id"] < 0)
    assert total_wins == 10, f"Total wins should be 10, got {total_wins}"

    # ── Close and verify member point distribution ──
    close_res = _close(client, t_id)
    results = close_res["results"]

    # Verify that User.points were distributed to team members
    db_session.expire_all()
    credited_count = 0
    for uid in user_ids[:20]:
        user = db_session.query(models.User).filter(models.User.id == uid).first()
        if user.points and user.points > 0:
            credited_count += 1

    assert credited_count == 20, f"Expected all 20 team members to get points, got {credited_count}"

    # Player21 (not in any team, not joined) should have 0 points
    p21 = db_session.query(models.User).filter(models.User.id == user_ids[20]).first()
    assert (p21.points or 0) == 0, "Player21 should have 0 points (not in tournament)"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6 — Score Correction SE: re-score R1 → rollback + re-advance
# ═══════════════════════════════════════════════════════════════════════════

def test_single_elim_score_correction(client, db_session):
    """SE: Score R1 match, then re-score with opposite winner. Old winner must be
    removed from R2, new winner placed instead."""
    game = _create_game(db_session, "Correction SE", "single_elim")
    t_id = _create_tournament(client, "Correction Cup", game.id, {
        "bracket_type": "single_elim",
        "lower_score_is_better": False,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 8)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    bracket = _get_bracket(client, t_id)
    r1_m1 = _find(bracket, 1, 1, 1)
    p0, p1 = r1_m1["p"][0], r1_m1["p"][1]

    # ── Initial score: p[0] wins ──
    _score(client, t_id, r1_m1, [3, 1])

    bracket = _get_bracket(client, t_id)
    r2_m1 = _find(bracket, 1, 2, 1)
    assert p0 in r2_m1["p"], f"p0 ({p0}) should have advanced to R2"
    assert p1 not in r2_m1["p"], f"p1 ({p1}) should NOT be in R2"

    # ── Correction: p[1] wins instead ──
    r1_m1_fresh = _find(bracket, 1, 1, 1)
    _score(client, t_id, r1_m1_fresh, [1, 3])

    bracket = _get_bracket(client, t_id)
    r2_m1 = _find(bracket, 1, 2, 1)
    assert p1 in r2_m1["p"], f"After correction, p1 ({p1}) should be in R2"
    assert p0 not in r2_m1["p"], f"After correction, p0 ({p0}) should be removed from R2"

    # ── Play through to finale with corrected bracket ──
    # Score remaining R1 matches
    for m in [_find(bracket, 1, 1, i) for i in range(2, 5)]:
        if m and (m["score"][0] is None or m["score"][0] == 0):
            _score(client, t_id, m, [3, 1])

    # Score R2
    bracket = _get_bracket(client, t_id)
    for m in [_find(bracket, 1, 2, i) for i in range(1, 3)]:
        if m and m["p"][0] != 0 and m["p"][1] != 0 and (m["score"][0] is None or m["score"][0] == 0):
            _score(client, t_id, m, [3, 1])

    # Score Finale
    bracket = _get_bracket(client, t_id)
    finale = _find(bracket, 1, 3, 1)
    if finale and finale["p"][0] != 0 and finale["p"][1] != 0:
        result = _score(client, t_id, finale, [5, 2])
        assert result["done"] is True

    # Close — the corrected winner (p1) should NOT be champion
    # (p1 won R1M1 but lost in later rounds if p[0] of R2 is the convention)
    close_res = _close(client, t_id)
    results = close_res["results"]
    assert len(results) > 0

    # The key assertion: p0 should NOT be 1st (he lost R1M1 after correction)
    first = next((r for r in results if r["rank"] == 1), None)
    assert first is not None
    assert first["entity_id"] != p0, "p0 lost R1M1 after correction, should not be champion"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7 — Reopen after Close: points rollback
# ═══════════════════════════════════════════════════════════════════════════

def test_reopen_after_close_rollback_points(client, db_session):
    """Close a RR tournament (points distributed), then reopen → User.points must go back to 0."""
    game = _create_game(db_session, "Reopen RR", "round_robin")
    t_id = _create_tournament(client, "Reopen League", game.id, {
        "bracket_type": "round_robin",
        "lower_score_is_better": False,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 6)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    bracket = _get_bracket(client, t_id)

    # Score all 15 matches
    for match in bracket:
        _score(client, t_id, match, [3, 1])

    # ── Close ──
    _close(client, t_id)

    # Verify points were credited
    db_session.expire_all()
    points_after_close = {}
    for uid in user_ids:
        user = db_session.query(models.User).filter(models.User.id == uid).first()
        points_after_close[uid] = user.points or 0
        assert points_after_close[uid] > 0, f"{user.username} should have points after close"

    # ── Reopen ──
    res = client.post(f"/tournaments/{t_id}/reopen")
    assert res.status_code == 200
    assert res.json()["rolled_back_users"] == 6

    # Verify tournament is DONE again (not CLOSED)
    t_res = client.get(f"/tournaments/{t_id}")
    assert t_res.json()["status"] == "DONE"

    # Verify points were rolled back to 0
    db_session.expire_all()
    for uid in user_ids:
        user = db_session.query(models.User).filter(models.User.id == uid).first()
        assert (user.points or 0) == 0, \
            f"{user.username}: expected 0 after reopen, got {user.points} (was {points_after_close[uid]})"

    # ── Re-close should re-distribute same points ──
    _close(client, t_id)
    db_session.expire_all()
    for uid in user_ids:
        user = db_session.query(models.User).filter(models.User.id == uid).first()
        assert (user.points or 0) == points_after_close[uid], \
            f"{user.username}: re-close points mismatch (got {user.points}, expected {points_after_close[uid]})"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8 — RR Score Correction: re-score changes wins count
# ═══════════════════════════════════════════════════════════════════════════

def test_rr_score_correction_wins_update(client, db_session):
    """RR: Score a match (p0 wins), check standings. Re-score (p1 wins). Verify wins swap."""
    game = _create_game(db_session, "Correction RR", "round_robin")
    t_id = _create_tournament(client, "Fix League", game.id, {
        "bracket_type": "round_robin",
        "lower_score_is_better": False,
        "pts_winner": 0, "pts_second": 0, "pts_third": 0,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 6)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    bracket = _get_bracket(client, t_id)
    match = bracket[0]
    p0, p1 = match["p"][0], match["p"][1]

    # ── Initial score: p0 wins ──
    _score(client, t_id, match, [5, 2])

    lb = _standings(client, t_id)
    w0 = next(p for p in lb if p["entity_id"] == p0)
    w1 = next(p for p in lb if p["entity_id"] == p1)
    assert w0["wins"] == 1, f"p0 should have 1 win, got {w0['wins']}"
    assert w1["wins"] == 0, f"p1 should have 0 wins, got {w1['wins']}"
    assert w0["total"] > w1["total"], "p0 should have more total points"

    # ── Correction: p1 wins instead ──
    bracket = _get_bracket(client, t_id)
    match_fresh = bracket[0]
    _score(client, t_id, match_fresh, [1, 4])

    lb = _standings(client, t_id)
    w0 = next(p for p in lb if p["entity_id"] == p0)
    w1 = next(p for p in lb if p["entity_id"] == p1)
    assert w0["wins"] == 0, f"After correction, p0 should have 0 wins, got {w0['wins']}"
    assert w1["wins"] == 1, f"After correction, p1 should have 1 win, got {w1['wins']}"
    assert w1["total"] > w0["total"], "After correction, p1 should have more total points"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9 — FFA multi-manche: éliminés doivent être classés après survivants
# ═══════════════════════════════════════════════════════════════════════════

def test_ffa_multiround_eliminated_ranked(client, db_session):
    """FFA 8 players → advance 4 → advance 2 → finish. Verify:
    - Last-round players get ranks 1-2
    - Round 2 eliminated get ranks 3-4 (above round 1 eliminated)
    - Round 1 eliminated get ranks 5-8
    - No duplicate ranks at #1 (the old bug)
    """
    game = _create_game(db_session, "FFA Ranking", "ffa")
    t_id = _create_tournament(client, "Ranking FFA", game.id, {
        "bracket_type": "ffa",
        "lower_score_is_better": True,
        "pts_winner": 10, "pts_second": 6, "pts_third": 4,
        "pts_participation": 1, "pts_per_match": 1
    })

    user_ids = _get_user_ids(db_session, 8)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    # ── Round 1: 8 players, scores = placements 1-8 ──
    bracket = _get_bracket(client, t_id)
    m1 = bracket[0]
    scores_r1 = list(range(1, 9))  # player[0]=1st, player[7]=8th
    _score(client, t_id, m1, scores_r1)

    # Advance top 4
    res = client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 4})
    assert res.status_code == 200

    # ── Round 2: 4 players ──
    bracket = _get_bracket(client, t_id)
    m2 = _find(bracket, 1, 2, 1)
    assert len(m2["p"]) == 4
    scores_r2 = [1, 2, 3, 4]
    _score(client, t_id, m2, scores_r2)

    # Advance top 2
    res = client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 2})
    assert res.status_code == 200

    # ── Round 3 (final): 2 players ──
    bracket = _get_bracket(client, t_id)
    m3 = _find(bracket, 1, 3, 1)
    assert len(m3["p"]) == 2
    _score(client, t_id, m3, [1, 2])

    # Finish + Close
    res = client.post(f"/tournaments/{t_id}/ffa-finish")
    assert res.status_code == 200
    close_res = _close(client, t_id)
    results = close_res["results"]

    # ── Verify rankings ──
    # Only ONE player should be rank 1
    rank1 = [r for r in results if r["rank"] == 1]
    assert len(rank1) == 1, f"Expected exactly 1 player at rank 1, got {len(rank1)}: {[r['name'] for r in rank1]}"

    # Rank 2 should exist (final loser)
    rank2 = [r for r in results if r["rank"] == 2]
    assert len(rank2) == 1, f"Expected 1 player at rank 2, got {len(rank2)}"

    # Eliminated in round 2 should be ranked 3-4
    rank3_4 = [r for r in results if r["rank"] in (3, 4)]
    assert len(rank3_4) == 2, f"Expected 2 players at rank 3-4, got {len(rank3_4)}"

    # Eliminated in round 1 should be ranked 5+
    rank5_plus = [r for r in results if r["rank"] is not None and r["rank"] >= 5]
    assert len(rank5_plus) == 4, f"Expected 4 players at rank 5+, got {len(rank5_plus)}"

    # Points should decrease with rank
    assert rank1[0]["total"] > rank2[0]["total"], "1st should have more points than 2nd"

    # Verify placement points
    assert rank1[0]["placement_pts"] == 10, f"1st: expected 10 placement pts, got {rank1[0]['placement_pts']}"
    assert rank2[0]["placement_pts"] == 6, f"2nd: expected 6 placement pts, got {rank2[0]['placement_pts']}"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10 — Live Leaderboard: Zero Scores count towards wins
# ═══════════════════════════════════════════════════════════════════════════

def test_live_leaderboard_zero_scores(client, db_session):
    """Verify that matches ending in a zero score (e.g. 1-0) correctly count wins in live leaderboard."""
    game = _create_game(db_session, "Live Zero RR", "round_robin")
    t_id = _create_tournament(client, "Zero League", game.id, {
        "bracket_type": "round_robin",
        "lower_score_is_better": False,
        "pts_winner": 3, "pts_second": 0, "pts_third": 0,
        "pts_participation": 0, "pts_per_match": 0,
        "pts_per_win": 3, "pts_per_goal": 1
    })

    user_ids = _get_user_ids(db_session, 2)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    # Score the first match as 1 - 0
    bracket = _get_bracket(client, t_id)
    match = bracket[0]
    p0, p1 = match["p"][0], match["p"][1]
    
    _score(client, t_id, match, [1, 0])

    # Call the /dashboard/stats endpoint to verify wins and goals
    res = client.get("/dashboard/stats")
    assert res.status_code == 200
    stats = res.json()
    
    # Check that leaderboard stats contain players and count the win
    leaderboard = stats.get("leaderboard", [])
    assert len(leaderboard) > 0, "Leaderboard should not be empty"
    
    # p0 should have 1 win and 0 goal/match points (points = 3 (win) + 0 (score bonus) = 3)
    p0_user = db_session.query(models.User).filter(models.User.id == p0).first()
    p0_entry = next((e for e in leaderboard if e["username"] == p0_user.username), None)
    assert p0_entry is not None, "p0 should be in the leaderboard"
    assert p0_entry["points"] == 3, f"p0 should have 3 points (3 for win, 0 for goal), got {p0_entry['points']}"

    # Also verify that projected standings count 1 win for p0
    standings = _standings(client, t_id)
    p0_standing = next((s for s in standings if s["entity_id"] == p0), None)
    assert p0_standing is not None
    assert p0_standing["wins"] == 1, "Projected standings should count 1 win for p0"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 11 — FFA Rollback Round
# ═══════════════════════════════════════════════════════════════════════════

def test_ffa_rollback_round(client, db_session):
    """Verify that we can rollback an advanced FFA round."""
    game = _create_game(db_session, "FFA Rollback", "ffa")
    t_id = _create_tournament(client, "Rollback FFA", game.id, {
        "bracket_type": "ffa",
        "lower_score_is_better": True
    })

    user_ids = _get_user_ids(db_session, 8)
    _join_players(client, t_id, user_ids)
    _start(client, t_id)

    # Round 1
    bracket = _get_bracket(client, t_id)
    m1 = bracket[0]
    _score(client, t_id, m1, list(range(1, 9)))

    # Advance
    res = client.post(f"/tournaments/{t_id}/ffa-advance", json={"keep_count": 4})
    assert res.status_code == 200

    # Verify Round 2 exists
    bracket = _get_bracket(client, t_id)
    assert len(bracket) == 2, "Should have 2 rounds"
    assert any(m["id"]["r"] == 2 for m in bracket)

    # Rollback
    res = client.post(f"/tournaments/{t_id}/ffa-rollback")
    assert res.status_code == 200
    assert res.json()["round"] == 1

    # Verify Round 2 is deleted
    bracket = _get_bracket(client, t_id)
    assert len(bracket) == 1, "Round 2 should be deleted"
    assert all(m["id"]["r"] == 1 for m in bracket)



