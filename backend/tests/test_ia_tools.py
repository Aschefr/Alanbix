import pytest
import json
import os
import asyncio
from unittest.mock import patch
from app import models
from app.ia_tools import execute_tool, _find_best_match

class MockSessionManager:
    def __init__(self, session):
        self.session = session
    def __enter__(self):
        return self.session
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

@pytest.fixture
def mock_db_session(db_session):
    return MockSessionManager(db_session)

def test_find_best_match():
    possibilities = ["PlayerOne", "TeamAwesome", "Rocket League", "Trackmania"]
    
    # Exact case-insensitive match
    assert _find_best_match("playerone", possibilities) == "PlayerOne"
    # Substring match
    assert _find_best_match("awesome", possibilities) == "TeamAwesome"
    # Fuzzy match
    assert _find_best_match("rocket legue", possibilities) == "Rocket League"
    # Cutoff guard (too different)
    assert _find_best_match("league of legends", possibilities) is None
    # Empty query
    assert _find_best_match("", possibilities) is None

@pytest.mark.asyncio
async def test_get_player_info_fuzzy(db_session, mock_db_session):
    # Ensure player exists in mock DB
    user = db_session.query(models.User).filter(models.User.username == "Player1").first()
    assert user is not None
    
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        # Misspelled username
        res = await execute_tool("get_player_info", {"username": "playr1"})
        data = json.loads(res)
        assert "username" in data
        assert data["username"] == "Player1"

@pytest.mark.asyncio
async def test_get_live_matches_and_upcoming(db_session, mock_db_session):
    # Create tournament, bracket and players
    game = models.Game(name="Test Game")
    db_session.add(game)
    db_session.commit()
    
    # Add tournament with RUNNING status
    t = models.Tournament(
        name="Tournoi Test",
        status="RUNNING",
        game_id=game.id,
        config={"bracket_type": "single_elim", "use_teams": False},
        bracket=[
            {
                "id": {"s": 1, "r": 1, "m": 1},
                "p": [1, 2],  # Player1 vs Player2
                "score": [None, None]  # Unplayed (upcoming/live)
            },
            {
                "id": {"s": 1, "r": 1, "m": 2},
                "p": [3, 0],  # Player3 vs TBD
                "score": [None, None]
            }
        ]
    )
    db_session.add(t)
    db_session.commit()
    
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        # Test live matches (must list Player1 vs Player2)
        res_live = await execute_tool("get_live_matches", {})
        data_live = json.loads(res_live)
        assert data_live["count"] == 1
        assert data_live["live_matches"][0]["player1"] == "Player1"
        assert data_live["live_matches"][0]["player2"] == "Player2"

        # Test upcoming matches (same list for standard 1v1 bracket)
        res_up = await execute_tool("get_upcoming_matches", {})
        data_up = json.loads(res_up)
        assert data_up["count"] == 1
        assert data_up["upcoming_matches"][0]["player1"] == "Player1"
        assert data_up["upcoming_matches"][0]["player2"] == "Player2"

@pytest.mark.asyncio
async def test_get_files(mock_db_session):
    from app.routers.dashboard import INFO_FILES_DIR
    os.makedirs(INFO_FILES_DIR, exist_ok=True)
    test_file = os.path.join(INFO_FILES_DIR, "test_config.txt")
    with open(test_file, "w") as f:
        f.write("test content")
        
    try:
        with patch("app.database.SessionLocal", return_value=mock_db_session):
            res = await execute_tool("get_files", {})
            data = json.loads(res)
            assert data["count"] > 0
            file_names = [f["name"] for f in data["files"]]
            assert "test_config.txt" in file_names
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

@pytest.mark.asyncio
async def test_get_bracket_detail(db_session, mock_db_session):
    game = models.Game(name="CS:GO")
    db_session.add(game)
    db_session.commit()
    
    t = models.Tournament(
        name="CS:GO Tournament",
        status="RUNNING",
        game_id=game.id,
        config={"bracket_type": "single_elim", "use_teams": False},
        bracket=[
            {
                "id": {"s": 1, "r": 1, "m": 1},
                "p": [1, 2],
                "score": [16, 12]  # Played
            }
        ]
    )
    db_session.add(t)
    db_session.commit()
    
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        res = await execute_tool("get_bracket_detail", {"tournament_name": "cs"})
        data = json.loads(res)
        assert data["tournament_name"] == "CS:GO Tournament"
        assert "Tableau Principal / Winners Bracket" in data["bracket_details"]
        rounds = data["bracket_details"]["Tableau Principal / Winners Bracket"]
        assert "Round 1" in rounds
        match = rounds["Round 1"][0]
        assert match["players"] == ["Player1", "Player2"]
        assert match["score"] == [16, 12]
        assert match["completed"] is True

@pytest.mark.asyncio
async def test_get_player_rank_progression(db_session, mock_db_session):
    game = models.Game(name="Trackmania")
    db_session.add(game)
    db_session.commit()
    
    # Add a closed tournament distributing points
    t = models.Tournament(
        name="Trackmania Cup",
        status="CLOSED",
        game_id=game.id,
        config={"bracket_type": "single_elim", "use_teams": False},
        results=[
            {"rank": 1, "entity_id": 1, "name": "Player1", "total": 10},
            {"rank": 2, "entity_id": 2, "name": "Player2", "total": 6}
        ]
    )
    db_session.add(t)
    db_session.commit()
    
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        res = await execute_tool("get_player_rank_progression", {"username": "playr1"})
        data = json.loads(res)
        assert data["username"] == "Player1"
        assert len(data["progression"]) == 2  # Start + 1 tournament
        assert data["progression"][1]["tournament_name"] == "Trackmania Cup"
        assert data["progression"][1]["points_gained"] == 10
        assert data["progression"][1]["total_points"] == 10


@pytest.mark.asyncio
async def test_get_leaderboard_by_game(db_session, mock_db_session):
    game = models.Game(name="Golfit!")
    db_session.add(game)
    db_session.commit()
    
    t = models.Tournament(
        name="Golf Open",
        status="CLOSED",
        game_id=game.id,
        config={"bracket_type": "single_elim", "use_teams": False},
        results=[
            {"rank": 1, "entity_id": 1, "name": "Player1", "total": 15},
            {"rank": 2, "entity_id": 2, "name": "Player2", "total": 8}
        ]
    )
    db_session.add(t)
    db_session.commit()
    
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        res = await execute_tool("get_leaderboard_by_game", {"game_name": "golf"})
        data = json.loads(res)
        assert data["game"] == "Golfit!"
        assert data["leaderboard"][0]["name"] == "Player1"
        assert data["leaderboard"][0]["points"] == 15


@pytest.mark.asyncio
async def test_get_tournament_bracket_path(db_session, mock_db_session):
    game = models.Game(name="FIFA")
    db_session.add(game)
    db_session.commit()
    
    t = models.Tournament(
        name="FIFA Cup",
        status="RUNNING",
        game_id=game.id,
        config={"bracket_type": "single_elim", "use_teams": False},
        bracket=[
            {
                "id": {"s": 1, "r": 1, "m": 1},
                "p": [1, 2],
                "score": [3, 1]
            }
        ]
    )
    db_session.add(t)
    db_session.commit()
    
    with patch("app.database.SessionLocal", return_value=mock_db_session):
        res = await execute_tool("get_tournament_bracket_path", {"tournament_name": "fifa", "username": "Player1"})
        data = json.loads(res)
        assert data["player"] == "Player1"
        assert data["tournament"] == "FIFA Cup"
        assert data["path"][0]["opponent"] == "Player2"
        assert data["path"][0]["outcome"] == "Victoire"


@pytest.mark.asyncio
async def test_send_notification_to_player(db_session, mock_db_session):
    with patch("app.database.SessionLocal", return_value=mock_db_session), \
         patch("app.websockets.manager.broadcast") as mock_broadcast:
        res = await execute_tool("send_notification_to_player", {"username": "playr2", "content": "Ton match commence !"})
        data = json.loads(res)
        assert data["success"] is True
        assert data["recipient"] == "Player2"
        
        # Verify db insert
        notif = db_session.query(models.Notification).filter(models.Notification.content == "Ton match commence !").first()
        assert notif is not None
        assert notif.user_id == 2
        
        # Verify WS broadcast was scheduled/called
        await asyncio.sleep(0.01)
        assert mock_broadcast.called


@pytest.mark.asyncio
async def test_announce_to_all_admin_vs_user(db_session, mock_db_session):
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    player1 = db_session.query(models.User).filter(models.User.username == "Player1").first()
    assert admin is not None
    assert player1 is not None
    
    with patch("app.database.SessionLocal", return_value=mock_db_session), \
         patch("app.websockets.manager.broadcast") as mock_broadcast:
         
        # 1. Non-admin user try: must fail
        res_fail = await execute_tool("announce_to_all", {"content": "Pause repas !"}, user_id=player1.id)
        data_fail = json.loads(res_fail)
        assert "error" in data_fail
        
        # 2. Admin user try: must succeed
        res_ok = await execute_tool("announce_to_all", {"content": "Pause pizza !"}, user_id=admin.id)
        data_ok = json.loads(res_ok)
        assert data_ok["success"] is True
        
        # Verify notifications created for all users
        notif_count = db_session.query(models.Notification).filter(models.Notification.content == "Pause pizza !").count()
        assert notif_count > 1
        
        await asyncio.sleep(0.01)
        assert mock_broadcast.called
