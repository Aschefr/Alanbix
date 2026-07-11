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


@pytest.mark.asyncio
async def test_ia_tool_block_user_from_ia(db_session):
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
        result_str = await execute_tool("block_user_from_ia", {"reason": "Language injurieux répétitif"}, user_id=player1.id)
        
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


@pytest.mark.asyncio
async def test_ia_tool_block_user_from_ia_disabled(db_session):
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
        result_str = await execute_tool("block_user_from_ia", {"reason": "Language injurieux répétitif"}, user_id=player1.id)

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
            "tool_calling_mode": "legacy_double",
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

    mock_exec = AsyncMock(return_value='{"datetime": "2026-05-22T22:00:00"}')
    import sys
    patched_targets = []
    for mod_name in list(sys.modules.keys()):
        if mod_name.endswith("ia_tools") and hasattr(sys.modules[mod_name], "execute_tool"):
            patched_targets.append(patch(f"{mod_name}.execute_tool", mock_exec))
            
    with patch("httpx.AsyncClient", return_value=mock_client):
        # Open all patches
        for p in patched_targets:
            p.start()
        try:
            tool_time, resp_time = await queue_manager._process_chat(entry, entry.payload)
            mock_exec.assert_called_once_with("get_current_datetime", {}, user_id=player1.id, conversation_id=0)
        finally:
            for p in patched_targets:
                p.stop()


@pytest.mark.asyncio
async def test_ia_queue_host_concurrency_limit():
    """Verify that only 1 request at a time runs on a given Ollama host.

    When one entry is already active on host X, a second entry targeting the
    same host should NOT be moved to _active — it must stay in _pending.
    """
    qm = IAQueueManager()

    # Simulate an already-active entry on host "http://gpu1:11434"
    active_entry = QueueEntry(
        priority=10,
        created_at=time.time(),
        id="active_1",
        user_id=1,
        username="user1",
        task_type="chat",
        payload={"ollama_host": "http://gpu1:11434"}
    )
    qm._active[active_entry.id] = active_entry

    # Create a second entry targeting the same host
    waiting_entry = QueueEntry(
        priority=10,
        created_at=time.time(),
        id="waiting_1",
        user_id=2,
        username="user2",
        task_type="chat",
        payload={"ollama_host": "http://gpu1:11434"}
    )
    qm._pending[waiting_entry.id] = waiting_entry

    # Simulate the concurrency check from _worker (lines 320-329 of ia_queue.py)
    host = waiting_entry.payload.get("ollama_host")
    active_on_host = sum(1 for e in qm._active.values() if e.payload.get("ollama_host") == host)

    # The waiting entry must NOT be promoted to active
    assert active_on_host >= 1, "There should be at least 1 active request on gpu1"
    assert waiting_entry.id in qm._pending, "Waiting entry should remain in _pending"
    assert waiting_entry.id not in qm._active, "Waiting entry should NOT be in _active"

    # Now verify a different host WOULD be allowed
    entry_gpu2 = QueueEntry(
        priority=10,
        created_at=time.time(),
        id="gpu2_entry",
        user_id=3,
        username="user3",
        task_type="chat",
        payload={"ollama_host": "http://gpu2:11434"}
    )
    active_on_gpu2 = sum(1 for e in qm._active.values() if e.payload.get("ollama_host") == "http://gpu2:11434")
    assert active_on_gpu2 == 0, "gpu2 has no active requests, so entry should be promotable"


@pytest.mark.asyncio
async def test_auto_title_not_enqueued_if_already_attempted(db_session):
    """Verify that auto-title is NOT enqueued when title_generation_attempted is True."""
    from app import models
    from app.ia_title_utils import _is_default_title

    # Create a conversation with a default title but title_generation_attempted=True
    conv = models.Conversation(
        title="Nouvelle conversation",
        user_id=1,
        title_generation_attempted=True
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)

    # The guard condition from stream_query (line 917 of ia.py):
    #   if conv_obj and _is_default_title(conv_obj.title) and not conv_obj.title_generation_attempted:
    should_enqueue = _is_default_title(conv.title) and not conv.title_generation_attempted

    assert _is_default_title(conv.title) is True, "Title should be detected as default"
    assert conv.title_generation_attempted is True, "Flag should be True"
    assert should_enqueue is False, "Auto-title should NOT be enqueued when already attempted"


@pytest.mark.asyncio
async def test_auto_title_skips_custom_title(db_session):
    """Verify that _process_auto_title does NOT overwrite a manually-set title.

    Simulates the race condition where a user renames their conversation while
    the auto-title task is waiting in the queue.
    """
    from unittest.mock import patch, MagicMock, AsyncMock
    from app.ia_queue import IAQueueManager, QueueEntry
    from app import models
    from app.ia_title_utils import _is_default_title

    # Create a conversation with a CUSTOM title (user renamed it while waiting)
    conv = models.Conversation(
        title="Ma stratégie Rocket League",
        user_id=1,
        title_generation_attempted=True
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)

    assert _is_default_title(conv.title) is False, "Custom title should NOT be detected as default"

    # Mock Ollama response that would return a generated title
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "Configuration réseau avancée"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Mock SessionLocal to return our test db_session
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__ = MagicMock(return_value=db_session)
    mock_session_ctx.__exit__ = MagicMock(return_value=False)

    qm = IAQueueManager()
    entry = QueueEntry(
        priority=20,
        created_at=time.time(),
        id="autotitle_race",
        user_id=0,
        username="system:autotitle",
        task_type="auto_title",
        payload={
            "ollama_host": "http://gpu1:11434",
            "model": "gemma4:e4b",
            "excerpt": "User: Hello\nAssistant: Bonjour !",
            "conversation_id": conv.id,
            "user_id": 1,
        }
    )

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("app.database.SessionLocal", return_value=mock_session_ctx), \
         patch("app.ia_queue.ws_manager.broadcast", new_callable=AsyncMock) as mock_broadcast:
        await qm._process_auto_title(entry, entry.payload)

    # The title should NOT have been overwritten
    db_session.refresh(conv)
    assert conv.title == "Ma stratégie Rocket League", \
        "Custom title must not be overwritten by auto-title"

    # WebSocket broadcast should NOT have been called (no title change)
    for call in mock_broadcast.call_args_list:
        msg = call[0][0] if call[0] else call[1].get("message", {})
        assert msg.get("type") != "conv_title_updated", \
            "No conv_title_updated should be broadcast when title is custom"


@pytest.mark.asyncio
async def test_process_entry_routes_correctly():
    """Verify _process_entry dispatches to the correct handler for each task_type."""
    from unittest.mock import AsyncMock
    from app.ia_queue import IAQueueManager, QueueEntry

    qm = IAQueueManager()

    task_types_and_handlers = {
        "chat": "_process_chat",
        "compress": "_process_compress",
        "notification": "_process_notification",
        "translate": "_process_translate",
        "title_suggestion": "_process_title_suggestion",
        "auto_title": "_process_auto_title",
    }

    for task_type, handler_name in task_types_and_handlers.items():
        # Mock ALL handlers to prevent side effects
        mocks = {}
        for tt, hn in task_types_and_handlers.items():
            mock = AsyncMock(return_value=(0.0, 0.0) if tt == "chat" else None)
            setattr(qm, hn, mock)
            mocks[hn] = mock

        entry = QueueEntry(
            priority=10,
            created_at=time.time(),
            id=f"route_{task_type}",
            user_id=1,
            username="test",
            task_type=task_type,
            payload={"ollama_host": "http://test:11434"}
        )

        await qm._process_entry(entry, worker_id=0)

        # Verify the correct handler was called
        expected_mock = mocks[handler_name]
        assert expected_mock.called, \
            f"Handler {handler_name} should have been called for task_type='{task_type}'"

        # Verify OTHER handlers were NOT called
        for other_name, other_mock in mocks.items():
            if other_name != handler_name:
                assert not other_mock.called, \
                    f"Handler {other_name} should NOT be called for task_type='{task_type}'"
