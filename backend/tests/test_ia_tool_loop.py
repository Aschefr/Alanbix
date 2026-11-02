"""Shared non-streaming tool rounds (ia_tool_loop.run_tool_rounds)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ia_tool_loop import parse_tool_args, parse_xml_tool_calls, run_tool_rounds


def _response(payload):
    res = MagicMock()
    res.json.return_value = payload
    return res


def test_parse_tool_args_accepts_every_format():
    assert parse_tool_args({"a": 1}) == {"a": 1}
    assert parse_tool_args('{"a": 1}') == {"a": 1}
    assert parse_tool_args("{'a': 1}") == {"a": 1}
    assert parse_tool_args("not json") == {}
    assert parse_tool_args(None) == {}


def test_parse_xml_tool_calls_reads_every_call():
    text = 'ok <tool_call name="get_games">{}</tool_call> then <tool_call name="get_leaderboard">{"limit": 3}</tool_call>'
    calls = parse_xml_tool_calls(text)
    assert [c["function"]["name"] for c in calls] == ["get_games", "get_leaderboard"]
    assert calls[1]["function"]["arguments"] == {"limit": 3}


@pytest.mark.asyncio
async def test_openai_native_call_gets_its_id_back():
    client = MagicMock()
    client.post = AsyncMock(side_effect=[
        _response({"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "get_games", "arguments": '{"q": "cs"}'}}
        ]}}]}),
        _response({"choices": [{"message": {"content": "Voilà."}}]}),
    ])
    with patch("app.ia_tools.execute_tool", AsyncMock(return_value='{"games": []}')) as run:
        out = await run_tool_rounds(client, "https://api.openai.com/v1", {"model": "m", "tools": [{}]},
                                    [{"role": "user", "content": "jeux ?"}], user_id=7)
    run.assert_called_once_with("get_games", {"q": "cs"}, user_id=7, conversation_id=0)
    assert out["used_tools"] == ["get_games"]
    assert out["added"][-1] == {"role": "tool", "content": '{"games": []}', "tool_call_id": "call_1"}
    assert out["rounds"] == 2


@pytest.mark.asyncio
async def test_xml_fallback_and_disallowed_tool():
    client = MagicMock()
    client.post = AsyncMock(side_effect=[
        _response({"message": {"content": '<tool_call name="announce_to_all">{"message": "hi"}</tool_call>'}}),
        _response({"message": {"content": "Fini."}}),
    ])
    with patch("app.ia_tools.execute_tool", AsyncMock()) as run:
        out = await run_tool_rounds(client, "http://ollama:11434", {"model": "m"},
                                    [{"role": "user", "content": "annonce"}], allowed_tools={"get_games"})
    run.assert_not_called()
    result = out["added"][-1]
    assert result["role"] == "user" and "not available" in result["content"]
    assert json.loads(result["content"].split(": ", 1)[1])["error"]


def test_merge_stream_tool_calls_rebuilds_openai_pieces():
    from app.ia_tool_loop import merge_stream_tool_calls
    pieces = [
        {"index": 0, "id": "call_1", "type": "function", "function": {"name": "get_player_seat", "arguments": ""}},
        {"index": 0, "function": {"arguments": '{"user'}},
        {"index": 0, "function": {"arguments": 'name": "Obelix"}'}},
        {"index": 1, "id": "call_2", "function": {"name": "get_games", "arguments": "{}"}},
    ]
    calls = merge_stream_tool_calls(pieces)
    assert [c["function"]["name"] for c in calls] == ["get_player_seat", "get_games"]
    assert calls[0]["id"] == "call_1" and calls[0]["type"] == "function"
    assert parse_tool_args(calls[0]["function"]["arguments"]) == {"username": "Obelix"}
    assert calls[1]["type"] == "function"


def test_merge_stream_tool_calls_keeps_whole_ollama_calls():
    from app.ia_tool_loop import merge_stream_tool_calls
    whole = [
        {"function": {"name": "get_games", "arguments": {}}},
        {"function": {"name": "get_player_seat", "arguments": {"username": "Obelix"}}},
    ]
    calls = merge_stream_tool_calls(whole)
    assert [c["function"] for c in calls] == [w["function"] for w in whole]
    assert "id" not in calls[0]
