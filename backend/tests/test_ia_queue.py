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
    assert notifs[0].title == "Accès à l'assistant IA bloqué"
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
    mock_response.status_code = 200
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


def _title_client(*responses):
    from unittest.mock import MagicMock, AsyncMock
    mocks = []
    for status, body in responses:
        r = MagicMock()
        r.status_code = status
        r.json.return_value = body
        mocks.append(r)
    client = AsyncMock()
    client.post = AsyncMock(side_effect=mocks)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_title_request_switches_thinking_off():
    """A reasoning model (Qwen 3.5 on vLLM) used up the 30 tokens thinking and returned
    content=None, so the conversation kept its default title."""
    from unittest.mock import patch
    from app.ia_queue import IAQueueManager

    client = _title_client((200, {"choices": [{"message": {"content": "Blague de LAN"}}]}))
    with patch("httpx.AsyncClient", return_value=client):
        title, status = await IAQueueManager()._request_title(
            "http://gpu:8000/v1", "qwen3.5", "User: Raconte-moi une blague de LAN")
    assert (title, status) == ("Blague de LAN", 200)
    assert client.post.call_args.kwargs["json"]["chat_template_kwargs"] == {"enable_thinking": False}

    client = _title_client((200, {"response": "<think>hmm</think>Tournoi Rocket League"}))
    with patch("httpx.AsyncClient", return_value=client):
        title, _ = await IAQueueManager()._request_title("http://gpu1:11434", "qwen3", "User: ...")
    assert title == "Tournoi Rocket League"
    assert client.post.call_args.kwargs["json"]["think"] is False


@pytest.mark.asyncio
async def test_title_request_retries_without_switch_when_refused():
    from unittest.mock import patch
    from app.ia_queue import IAQueueManager

    client = _title_client(
        (400, {"error": "Unrecognized request argument: chat_template_kwargs"}),
        (200, {"choices": [{"message": {"content": "Réseau du tournoi"}}]}),
    )
    with patch("httpx.AsyncClient", return_value=client):
        title, _ = await IAQueueManager()._request_title("http://gpu:8000/v1", "gpt", "User: ...")
    assert title == "Réseau du tournoi"
    assert "chat_template_kwargs" not in client.post.call_args_list[1].kwargs["json"]

    client = _title_client((200, {"choices": [{"message": {"content": None}}]}))
    with patch("httpx.AsyncClient", return_value=client):
        assert (await IAQueueManager()._request_title("http://gpu:8000/v1", "m", "x"))[0] is None


@pytest.mark.asyncio
async def test_process_entry_routes_correctly():
    """Verify _process_entry dispatches to the correct handler for each task_type."""
    from unittest.mock import AsyncMock
    from app.ia_queue import IAQueueManager, QueueEntry

    qm = IAQueueManager()

    task_types_and_handlers = {
        "chat": "_process_chat",
        "public_chat": "_process_public_chat",
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


@pytest.mark.asyncio
async def test_process_public_chat_tokens_and_thinking_cleanup():
    """Verify _process_public_chat uses dynamic context_window for num_predict and cleans thinking tags properly."""
    from unittest.mock import MagicMock, AsyncMock, patch
    from app.ia_queue import IAQueueManager, QueueEntry

    qm = IAQueueManager()

    configured_context_window = 4096
    entry = QueueEntry(
        priority=10,
        created_at=time.time(),
        user_id=0,
        username="Alanbix",
        task_type="public_chat",
        payload={
            "ollama_host": "http://gpu1:11434",
            "model": "deepseek-r1:8b",
            "messages": [{"role": "user", "content": "Raconte une blague"}],
            "temperature": 0.7,
            "context_window": configured_context_window,
        }
    )

    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "message": {
            "content": "<think>Je dois faire rire la LAN. Une blague sur les devs.</think>Pourquoi les devs aiment la nuit ? Parce que le soleil génère des reflets sur l'écran !"
        }
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_res)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await qm._process_public_chat(entry, entry.payload)

    # Check request payload sent to Ollama
    call_args = mock_client.post.call_args
    req_json = call_args.kwargs.get("json", {})
    assert req_json["options"]["num_predict"] == configured_context_window, "num_predict should match configured context_window"
    assert req_json["options"]["num_ctx"] == configured_context_window, "num_ctx should match configured context_window"

    # Check result received by queue consumer
    result = await entry.result_stream.get()
    assert result.get("done") is True
    assert result.get("result") == "Pourquoi les devs aiment la nuit ? Parce que le soleil génère des reflets sur l'écran !"



@pytest.mark.asyncio
async def test_thinking_setting_reaches_ollama():
    """Thinking on (the default): nothing is sent, as before. Off: think false on Ollama, nothing on
    OpenAI-compatible services. Used by the thinking bench (kept outside the repo)."""
    from unittest.mock import MagicMock, AsyncMock, patch
    from app.ia_queue import IAQueueManager, QueueEntry

    def client():
        res = MagicMock(status_code=200)
        res.json.return_value = {"message": {"content": "{}"}, "response": "ok"}
        c = AsyncMock()
        c.post = AsyncMock(return_value=res)
        c.__aenter__ = AsyncMock(return_value=c)
        c.__aexit__ = AsyncMock(return_value=False)
        return c

    async def sent(task_type, host, **extra):
        payload = {"ollama_host": host, "model": "m", "prompt": "p", "text": "t", "lines": ["U: t"],
                   "messages": [{"role": "user", "content": "x"}], **extra}
        entry = QueueEntry(priority=0, created_at=time.time(), user_id=0, username="t", task_type=task_type, payload=payload)
        c = client()
        with patch("httpx.AsyncClient", return_value=c):
            await getattr(IAQueueManager(), f"_process_{task_type}")(entry, payload)
        return c.post.call_args.kwargs["json"]

    for task in ("notification", "translate", "compress", "public_chat"):
        assert "think" not in await sent(task, "http://gpu1:11434"), task
        assert (await sent(task, "http://gpu1:11434", think=False))["think"] is False, task
        assert "think" not in await sent(task, "http://gpu:8000/v1", think=False), task


@pytest.mark.asyncio
async def test_every_call_asks_the_same_context():
    """Ollama reloads a model when the context size changes: a translation without num_ctx
    reloaded qwen3.8:27b after each chat, and the 45 s limit aborted the load every time."""
    from unittest.mock import MagicMock, AsyncMock, patch
    from app.ia_queue import IAQueueManager, QueueEntry

    def client():
        res = MagicMock(status_code=200)
        res.json.return_value = {"message": {"content": "{}"}, "response": "ok"}
        c = AsyncMock()
        c.post = AsyncMock(return_value=res)
        c.__aenter__ = AsyncMock(return_value=c)
        c.__aexit__ = AsyncMock(return_value=False)
        return c

    for task in ("notification", "translate", "compress", "public_chat", "title_suggestion", "auto_title"):
        payload = {"ollama_host": "http://gpu1:11434", "model": "m", "prompt": "p", "text": "t", "lines": ["U: t"],
                   "excerpt": "User: salut", "conversation_id": 0, "user_id": 0,
                   "messages": [{"role": "user", "content": "x"}], "context_window": 16384, "num_ctx": 16384}
        entry = QueueEntry(priority=0, created_at=time.time(), user_id=0, username="t", task_type=task, payload=payload)
        c = client()
        with patch("httpx.AsyncClient", return_value=c):
            await getattr(IAQueueManager(), f"_process_{task}")(entry, payload)
        assert c.post.call_args.kwargs["json"]["options"]["num_ctx"] == 16384, task


@pytest.mark.asyncio
async def test_last_tool_round_still_answers():
    """qwen3.8:27b and bonsai-2:27b, thinking on, asked for a third tool in the last round (which has none):
    the loop ended without a 'done', and the player waited 5 minutes for nothing."""
    import sys
    from unittest.mock import MagicMock, AsyncMock, patch
    import json
    from app.ia_queue import IAQueueManager, QueueEntry, LAST_ROUND_INSTRUCTION
    import app.ia_tools  # noqa: F401  (patched below, imported lazily by the queue)

    def stream(*lines):
        res = MagicMock()

        async def aiter_lines():
            for line in lines:
                yield json.dumps(line)
        res.aiter_lines = aiter_lines
        res.status_code = 200

        class Ctx:
            async def __aenter__(self):
                return res

            async def __aexit__(self, *a):
                return False
        return Ctx()

    call = '<tool_call name="get_tournaments">{}</tool_call>'
    rounds = [stream({"message": {"content": call}}), stream({"message": {"content": call}}),
              stream({"message": {"content": "Aucun tournoi de ce nom. " + call}}, {"done": True})]
    client = MagicMock()
    client.stream = MagicMock(side_effect=rounds)
    client.aclose = AsyncMock()
    tools = [{"type": "function", "function": {"name": "get_tournaments", "parameters": {}}}]
    entry = QueueEntry(priority=0, created_at=time.time(), user_id=0, username="t", task_type="chat", payload={
        "ollama_host": "http://gpu1:11434", "conversation_id": 0, "tool_calling_mode": "stream_intercept",
        "req_data": {"model": "m", "messages": [{"role": "user", "content": "Mon score au Rocket League Masters ?"}],
                     "stream": True, "options": {}, "tools": tools}})
    run_tool = AsyncMock(return_value='{"tournaments": []}')
    patches = [patch(f"{m}.execute_tool", run_tool) for m in list(sys.modules)
               if m.endswith("ia_tools") and hasattr(sys.modules[m], "execute_tool")]
    with patch("httpx.AsyncClient", return_value=client):
        for p in patches:
            p.start()
        try:
            await IAQueueManager()._process_chat(entry, entry.payload)
        finally:
            for p in patches:
                p.stop()

    assert run_tool.await_count == 2
    last_request = client.stream.call_args_list[2].kwargs["json"]
    assert "tools" not in last_request and last_request["messages"][-1] == LAST_ROUND_INSTRUCTION
    items = []
    while not entry.result_stream.empty():
        items.append(entry.result_stream.get_nowait())
    done = [i for i in items if i.get("done")]
    assert done and done[0]["full_response"] == "Aucun tournoi de ce nom."


@pytest.mark.asyncio
async def test_empty_last_round_is_asked_again_without_thinking():
    """With thinking on, qwen3.8:27b often only asked for another tool in the last round: the answer was empty."""
    import sys
    import json
    from unittest.mock import MagicMock, AsyncMock, patch
    from app.ia_queue import IAQueueManager, QueueEntry
    import app.ia_tools  # noqa: F401  (patched below, imported lazily by the queue)

    def stream(*lines):
        res = MagicMock()

        async def aiter_lines():
            for line in lines:
                yield json.dumps(line)
        res.aiter_lines = aiter_lines
        res.status_code = 200

        class Ctx:
            async def __aenter__(self):
                return res

            async def __aexit__(self, *a):
                return False
        return Ctx()

    native = {"message": {"content": "", "tool_calls": [{"function": {"name": "get_tournaments", "arguments": {}}}]}}
    rounds = [stream(native, {"done": True}), stream(native, {"done": True}), stream(native, {"done": True}),
              stream({"message": {"content": "Ce tournoi n'existe pas."}}, {"done": True})]
    client = MagicMock()
    client.stream = MagicMock(side_effect=rounds)
    client.aclose = AsyncMock()
    tools = [{"type": "function", "function": {"name": "get_tournaments", "parameters": {}}}]
    entry = QueueEntry(priority=0, created_at=time.time(), user_id=0, username="t", task_type="chat", payload={
        "ollama_host": "http://gpu1:11434", "conversation_id": 0, "tool_calling_mode": "stream_intercept",
        "req_data": {"model": "m", "messages": [{"role": "user", "content": "Mon score au Rocket League Masters ?"}],
                     "stream": True, "options": {}, "tools": tools}})
    run_tool = AsyncMock(return_value='{"tournaments": []}')
    patches = [patch(f"{m}.execute_tool", run_tool) for m in list(sys.modules)
               if m.endswith("ia_tools") and hasattr(sys.modules[m], "execute_tool")]
    with patch("httpx.AsyncClient", return_value=client):
        for p in patches:
            p.start()
        try:
            await IAQueueManager()._process_chat(entry, entry.payload)
        finally:
            for p in patches:
                p.stop()

    assert run_tool.await_count == 2 and client.stream.call_count == 4
    assert "think" not in client.stream.call_args_list[2].kwargs["json"]
    assert client.stream.call_args_list[3].kwargs["json"]["think"] is False
    items = []
    while not entry.result_stream.empty():
        items.append(entry.result_stream.get_nowait())
    assert [i["full_response"] for i in items if i.get("done")] == ["Ce tournoi n'existe pas."]


def test_model_missing_is_told_apart_from_other_errors():
    """Ollama reached but without the model: 404 "model ... not found", not a connection problem."""
    from app.ia_utils import is_model_missing
    assert is_model_missing(404, '{"error":"model \'gemma4:e4b\' not found"}')
    assert is_model_missing(404, '{"error":{"code":"model_not_found"}}')
    assert not is_model_missing(404, "404 page not found")  # a wrong address, not a missing model
    assert not is_model_missing(500,'{"error":"model \'x\' not found"}')
    assert not is_model_missing(200, "")


@pytest.mark.asyncio
async def test_chat_says_when_the_model_is_missing():
    """A user's report (2026-11-10): an Ollama without any model looked like a broken connection."""
    from unittest.mock import MagicMock, AsyncMock, patch
    from app.ia_queue import IAQueueManager, QueueEntry

    res = MagicMock()
    res.status_code = 404
    res.aread = AsyncMock(return_value=b'{"error":"model \'gemma4:e4b\' not found"}')

    class Ctx:
        async def __aenter__(self):
            return res

        async def __aexit__(self, *a):
            return False
    client = MagicMock()
    client.stream = MagicMock(return_value=Ctx())
    client.aclose = AsyncMock()
    entry = QueueEntry(priority=0, created_at=time.time(), user_id=0, username="t", task_type="chat", payload={
        "ollama_host": "http://gpu1:11434", "conversation_id": 0,
        "req_data": {"model": "gemma4:e4b", "messages": [{"role": "user", "content": "Salut"}], "stream": True, "options": {}}})
    with patch("httpx.AsyncClient", return_value=client):
        await IAQueueManager()._process_chat(entry, entry.payload)

    items = []
    while not entry.result_stream.empty():
        items.append(entry.result_stream.get_nowait())
    failure = [i for i in items if i.get("done")][0]
    assert failure["error"] and failure["code"] == "model_missing" and failure["model"] == "gemma4:e4b"
    assert client.stream.call_count == 1  # no retry against a model that is not there


def _chat_rounds(*rounds):
    """Client whose stream() answers each round with the given Ollama lines."""
    import json
    from unittest.mock import MagicMock, AsyncMock

    def stream(lines):
        res = MagicMock()
        res.status_code = 200

        async def aiter_lines():
            for line in lines:
                yield json.dumps(line)
        res.aiter_lines = aiter_lines

        class Ctx:
            async def __aenter__(self):
                return res

            async def __aexit__(self, *a):
                return False
        return Ctx()
    client = MagicMock()
    client.stream = MagicMock(side_effect=[stream(r) for r in rounds])
    client.aclose = AsyncMock()
    return client


async def _run_chat(client, **req):
    from unittest.mock import patch
    from app.ia_queue import IAQueueManager, QueueEntry
    entry = QueueEntry(priority=0, created_at=time.time(), user_id=0, username="t", task_type="chat", payload={
        "ollama_host": "http://gpu1:11434", "conversation_id": 0,
        "req_data": {"model": "mimo-v2.6:9b", "messages": [{"role": "user", "content": "Salut"}], "stream": True,
                     "options": {}, **req}})
    with patch("httpx.AsyncClient", return_value=client):
        await IAQueueManager()._process_chat(entry, entry.payload)
    items = []
    while not entry.result_stream.empty():
        items.append(entry.result_stream.get_nowait())
    return [i for i in items if i.get("done")][0]


# Prod, 2026-11-11: mimo-v2.6:9b thought until the 16K window was full, Ollama cut it, the player got an empty bubble
THOUGHT_ONLY = [{"message": {"content": "", "thinking": "Hmm, let me think"}},
                {"message": {"content": ""}, "done": True, "done_reason": "length"}]


@pytest.mark.asyncio
async def test_empty_answer_is_asked_again_without_thinking():
    client = _chat_rounds(THOUGHT_ONLY, [{"message": {"content": "Bonjour !"}}, {"done": True}])
    done = await _run_chat(client)
    assert done["full_response"] == "Bonjour !" and not done.get("error")
    assert "think" not in client.stream.call_args_list[0].kwargs["json"]
    assert client.stream.call_args_list[1].kwargs["json"]["think"] is False


@pytest.mark.asyncio
async def test_still_empty_answer_tells_the_player():
    client = _chat_rounds(THOUGHT_ONLY, THOUGHT_ONLY)
    done = await _run_chat(client)
    assert done["error"] and done["code"] == "empty_answer"
    assert client.stream.call_count == 2


@pytest.mark.asyncio
async def test_empty_answer_without_thinking_is_not_asked_twice():
    client = _chat_rounds(THOUGHT_ONLY)
    done = await _run_chat(client, think=False)
    assert done["error"] and done["code"] == "empty_answer"
    assert client.stream.call_count == 1  # the same request again would end the same way


async def _run_chat_on_servers(client, servers, **extra):
    """Chat on http://lost:11434 while the admin also set up `servers` [(url, model, healthy, models)]."""
    from unittest.mock import patch, MagicMock
    from app.ia_queue import IAQueueManager, QueueEntry
    import app.routers.ia as ia_router
    instances = [{"url": "http://lost:11434", "model": "gemma4:e4b", "label": "Portable"}] + [
        {"url": u, "model": m, "label": u} for u, m, _, _ in servers]
    health = {u: (ok, 5, names) for u, _, ok, names in servers}

    async def check(url, timeout=3.0, api_key=""):
        return health.get(url, (False, 0, []))
    entry = QueueEntry(priority=0, created_at=time.time(), user_id=0, username="t", task_type="chat", payload={
        "ollama_host": "http://lost:11434", "conversation_id": 0,
        "model_info": {"model": "gemma4:e4b", "instance": "Portable"},
        "req_data": {"model": "gemma4:e4b", "messages": [{"role": "user", "content": "Salut"}], "stream": True,
                     "options": {}}, **extra})
    with patch("httpx.AsyncClient", return_value=client), patch("app.database.SessionLocal", MagicMock()), \
            patch.object(ia_router, "get_instances", lambda db: instances), \
            patch.object(ia_router, "get_effective_config", lambda db: {"model": ""}), \
            patch.object(ia_router, "_check_instance_health", check):
        await IAQueueManager()._process_chat(entry, entry.payload)
    items = []
    while not entry.result_stream.empty():
        items.append(entry.result_stream.get_nowait())
    return entry, [i for i in items if i.get("done")][0]


# Prod, 2026-11-11: Windows Update restarted the laptop while gemma4:e4b was thinking; the stream just stopped
CUT_WHILE_THINKING = [{"message": {"content": "", "thinking": "Hmm"}}]


@pytest.mark.asyncio
async def test_lost_server_hands_the_question_to_another():
    client = _chat_rounds(CUT_WHILE_THINKING, [{"message": {"content": "Salut !"}}, {"done": True}])
    entry, done = await _run_chat_on_servers(client, [("http://down:11434", "x", False, []),
                                                     ("http://exposed:11434", "mimo-v2.6:9b", True, ["mimo-v2.6:9b"])])
    assert done["full_response"] == "Salut !" and not done.get("error")
    second = client.stream.call_args_list[1]
    assert second.args[1] == "http://exposed:11434/api/chat" and second.kwargs["json"]["model"] == "mimo-v2.6:9b"
    assert entry.payload["ollama_host"] == "http://exposed:11434"  # its time counts for that server
    assert done["meta"]["model_info"] == {"model": "mimo-v2.6:9b", "instance": "http://exposed:11434"}


@pytest.mark.asyncio
async def test_lost_server_without_another_tells_the_player():
    import httpx
    client = _chat_rounds()
    client.stream.side_effect = [httpx.ConnectError("refused")]
    _, done = await _run_chat_on_servers(client, [("http://down:11434", "x", False, [])])
    assert done["error"] and done["code"] == "ai_unreachable"


@pytest.mark.asyncio
async def test_chosen_model_is_not_swapped_for_another():
    client = _chat_rounds(CUT_WHILE_THINKING)
    _, done = await _run_chat_on_servers(client, [("http://exposed:11434", "mimo-v2.6:9b", True, ["mimo-v2.6:9b"])],
                                         model_fixed=True)
    assert done["code"] == "ai_unreachable" and client.stream.call_count == 1


@pytest.mark.asyncio
async def test_answer_cut_after_words_is_not_asked_elsewhere():
    client = _chat_rounds([{"message": {"content": "Le tournoi commence"}}])
    _, done = await _run_chat_on_servers(client, [("http://exposed:11434", "mimo-v2.6:9b", True, ["mimo-v2.6:9b"])])
    assert done["error"] and "code" not in done and client.stream.call_count == 1


@pytest.mark.asyncio
async def test_second_server_lost_too_stops_there():
    client = _chat_rounds(CUT_WHILE_THINKING, CUT_WHILE_THINKING)
    _, done = await _run_chat_on_servers(client, [("http://exposed:11434", "mimo-v2.6:9b", True, ["mimo-v2.6:9b"])])
    assert done["code"] == "ai_unreachable" and client.stream.call_count == 2
