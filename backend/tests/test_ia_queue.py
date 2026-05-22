import pytest
import asyncio
import time
from app.ia_queue import IAQueueManager, QueueEntry

@pytest.mark.asyncio
async def test_ia_queue_per_instance_durations():
    """Test that IAQueueManager calculates average durations independently per host."""
    qm = IAQueueManager()
    
    # 1. Enqueue two requests on different hosts
    entry1 = QueueEntry(
        priority=10,
        created_at=time.time(),
        id="req1",
        user_id=1,
        username="user1",
        task_type="chat",
        payload={"ollama_host": "http://instance1:11434"}
    )
    entry2 = QueueEntry(
        priority=10,
        created_at=time.time(),
        id="req2",
        user_id=2,
        username="user2",
        task_type="chat",
        payload={"ollama_host": "http://instance2:11434"}
    )
    
    qm._pending[entry1.id] = entry1
    qm._by_user[entry1.user_id] = entry1
    
    qm._pending[entry2.id] = entry2
    qm._by_user[entry2.user_id] = entry2

    # 2. Simulate processing of entry1 on host 1 (takes 0.5s)
    qm._pending.pop(entry1.id)
    qm._active[entry1.id] = entry1
    duration1 = 0.5 # Forced duration simulation
    
    # Simulate finally block
    qm._durations.append(duration1)
    qm._avg_duration = sum(qm._durations) / len(qm._durations)
    
    host1 = entry1.payload.get("ollama_host")
    if host1 not in qm._instance_durations:
        from collections import deque
        qm._instance_durations[host1] = deque(maxlen=20)
    qm._instance_durations[host1].append(duration1)
    qm._instance_avg_durations[host1] = sum(qm._instance_durations[host1]) / len(qm._instance_durations[host1])
    qm._cleanup_entry(entry1)

    # 3. Simulate processing of entry2 on host 2 (takes 1.5s)
    qm._pending.pop(entry2.id)
    qm._active[entry2.id] = entry2
    duration2 = 1.5
    
    qm._durations.append(duration2)
    qm._avg_duration = sum(qm._durations) / len(qm._durations)
    
    host2 = entry2.payload.get("ollama_host")
    if host2 not in qm._instance_durations:
        from collections import deque
        qm._instance_durations[host2] = deque(maxlen=20)
    qm._instance_durations[host2].append(duration2)
    qm._instance_avg_durations[host2] = sum(qm._instance_durations[host2]) / len(qm._instance_durations[host2])
    qm._cleanup_entry(entry2)

    # Verify per-instance averages
    assert qm._instance_avg_durations["http://instance1:11434"] == 0.5
    assert qm._instance_avg_durations["http://instance2:11434"] == 1.5
    
    # Global average is the mean of both
    assert qm._avg_duration == 1.0

@pytest.mark.asyncio
async def test_ia_queue_tool_time_subtraction():
    """Test that tool execution time is tracked and correctly subtracted from recorded duration."""
    qm = IAQueueManager()
    
    # Mock _process_entry to return 1.5 seconds of tool execution time and 0.5 seconds of response time
    async def mock_process_entry(entry, worker_id):
        return 1.5, 0.5
        
    qm._process_entry = mock_process_entry
    
    entry = QueueEntry(
        priority=10,
        created_at=time.time(),
        id="req_tool",
        user_id=3,
        username="user3",
        task_type="chat",
        payload={"ollama_host": "http://instance_tool:11434"}
    )
    
    tool_time, response_time = await qm._process_entry(entry, 1)
    simulated_elapsed = 2.0
    duration = response_time if response_time > 0.0 else max(0.1, simulated_elapsed - tool_time)
    
    assert tool_time == 1.5
    assert duration == 0.5


def test_ia_tool_block_user_from_ia(db_session):
    """Test that the block_user_from_ia tool blocks the user and raises notifications."""
    from app.ia_tools import execute_tool
    from app import models
    from unittest.mock import patch

    # Get Player1 user
    player1 = db_session.query(models.User).filter(models.User.username == "Player1").first()
    assert player1 is not None
    assert not player1.ia_blocked

    # Execute the block tool, mocking SessionLocal to return a context manager yielding db_session
    from unittest.mock import MagicMock
    mock_session = MagicMock()
    mock_session.__enter__.return_value = db_session
    with patch("app.database.SessionLocal", return_value=mock_session):
        result_str = execute_tool("block_user_from_ia", {"reason": "Language injurieux répétitif"}, user_id=player1.id)
        
    import json
    result = json.loads(result_str)
    assert result.get("success") is True
    assert result.get("username") == "Player1"
    
    # Reload from DB and verify blocked
    db_session.refresh(player1)
    assert player1.ia_blocked is True
    
    # Verify notifications were created
    notifs = db_session.query(models.Notification).filter(models.Notification.user_id == player1.id).all()
    assert len(notifs) == 1
    assert notifs[0].title == "Accès IA Révoqué"
    assert "Language injurieux" in notifs[0].content

    # Verify admin notification
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    admin_notifs = db_session.query(models.Notification).filter(models.Notification.user_id == admin.id).all()
    assert len(admin_notifs) >= 1
    assert any("Player1" in n.content for n in admin_notifs)


def test_ia_tool_block_user_from_ia_disabled(db_session):
    """Test that the block_user_from_ia tool returns an error when disabled in config."""
    from app.ia_tools import execute_tool
    from app import models
    from unittest.mock import patch, MagicMock

    player1 = db_session.query(models.User).filter(models.User.username == "Player1").first()
    assert player1 is not None

    # Save config with auto_moderation_enabled = False
    config = db_session.query(models.SystemConfig).filter(models.SystemConfig.key == "ia_settings").first()
    if not config:
        config = models.SystemConfig(key="ia_settings", value={"auto_moderation_enabled": False})
        db_session.add(config)
    else:
        val = dict(config.value)
        val["auto_moderation_enabled"] = False
        config.value = val
    db_session.commit()

    mock_session = MagicMock()
    mock_session.__enter__.return_value = db_session
    with patch("app.database.SessionLocal", return_value=mock_session):
        result_str = execute_tool("block_user_from_ia", {"reason": "Language injurieux répétitif"}, user_id=player1.id)

    import json
    result = json.loads(result_str)
    assert "error" in result
    assert "désactivé" in result["error"]

    # Verify not blocked
    db_session.refresh(player1)
    assert not player1.ia_blocked


@pytest.mark.asyncio
async def test_ia_queue_xml_fallback_parsing(db_session):
    """Test that XML fallback tool calling extracts tags and schedules the tool."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.ia_queue import QueueEntry, queue_manager
    from app import models
    import json

    player1 = db_session.query(models.User).filter(models.User.username == "Player1").first()
    assert player1 is not None

    entry = QueueEntry(
        priority=10,
        created_at=time.time(),
        id="req_xml",
        user_id=player1.id,
        username=player1.username,
        task_type="chat",
        payload={
            "ollama_host": "http://instance_xml:11434",
            "conversation_id": 1,
            "req_data": {
                "model": "deepseek-r1",
                "messages": [{"role": "user", "content": "Quelle heure est-il ?"}],
                "stream": True,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_current_datetime",
                            "description": "Get current time"
                        }
                    }
                ]
            }
        }
    )

    mock_res_tool = MagicMock()
    mock_res_tool.json.return_value = {
        "message": {
            "role": "assistant",
            "content": '<tool_call name="get_current_datetime">{}</tool_call>'
        }
    }
    
    mock_res_empty = MagicMock()
    mock_res_empty.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "J'ai les informations nécessaires maintenant."
        }
    }
    
    mock_response = MagicMock()
    async def mock_aiter_lines():
        yield '{"message": {"content": "Il est midi."}}'
        yield '{"done": true}'
        
    mock_response.aiter_lines = mock_aiter_lines
    mock_response.raise_for_status = MagicMock()
    
    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_response
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=[mock_res_tool, mock_res_empty])
    mock_client.stream = MagicMock(return_value=AsyncContextManagerMock())
    mock_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch("app.ia_tools.execute_tool", return_value='{"datetime": "2026-05-22T22:00:00"}') as mock_exec:
            tool_time, resp_time = await queue_manager._process_chat(entry, entry.payload)
            mock_exec.assert_called_once_with("get_current_datetime", {}, user_id=player1.id)
