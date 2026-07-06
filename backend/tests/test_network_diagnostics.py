import pytest
import json
import asyncio
from unittest.mock import patch, AsyncMock
from app.ia_tools import execute_tool, pending_client_calls

@pytest.mark.asyncio
async def test_network_diagnostics_client_delegation():
    client_calls = []
    async def on_client_call(name, args, call_id):
        client_calls.append((name, args, call_id))
        
        # Simulate the client responding shortly after
        async def respond_later():
            await asyncio.sleep(0.01)
            if call_id in pending_client_calls:
                event, _ = pending_client_calls[call_id]
                pending_client_calls[call_id] = (event, {"success": True, "latency": 15})
                event.set()
                
        asyncio.create_task(respond_later())

    # Call execute_tool (which will now be async def)
    res = await execute_tool("ping_host", {"host": "192.168.22.1"}, on_client_call=on_client_call)
    
    assert len(client_calls) == 1
    assert client_calls[0][0] == "ping_host"
    assert client_calls[0][1]["host"] == "192.168.22.1"
    
    data = json.loads(res)
    assert data["success"] is True
    assert data["latency"] == 15

@pytest.mark.asyncio
async def test_network_diagnostics_client_timeout():
    # If the client does not respond, it should timeout
    async def dummy_on_client_call(name, args, call_id):
        pass

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        res = await execute_tool("ping_host", {"host": "192.168.30.100"}, on_client_call=dummy_on_client_call)
        data = json.loads(res)
        assert "error" in data
        assert any(x in data["error"].lower() for x in ["timeout", "déla", "délai", "expir", "temps"])
