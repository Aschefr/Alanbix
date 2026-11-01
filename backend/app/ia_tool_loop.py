"""Non-streaming tool rounds shared by the private assistant (legacy mode) and the public chat.

Each round asks the model for an answer with the tools available. Native tool calls (Ollama or
OpenAI format) and the XML fallback (<tool_call name="...">{json}</tool_call>, for models without
native tool support) are both understood. The tools run and their results go back to the model,
until it stops calling tools or the round limit is reached.
"""
import json
import re
import time

import httpx

from .ia_utils import is_openai_host

XML_TOOL_CALL = re.compile(r'<tool_call name="([^"]+)">\s*(.*?)\s*</tool_call>', re.DOTALL)


def parse_tool_args(raw) -> dict:
    """Tool arguments as a dict: OpenAI sends a JSON string, Ollama a dict, small models sometimes single quotes."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    for text in (raw, str(raw).replace("'", '"')):
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else {}
        except Exception:
            continue
    return {}


def parse_xml_tool_calls(text: str) -> list:
    """Tool calls written as XML in the answer text."""
    return [
        {"function": {"name": name, "arguments": parse_tool_args(args)}}
        for name, args in XML_TOOL_CALL.findall(text or "")
    ]


async def run_tool_rounds(
    client,
    host: str,
    req_data: dict,
    messages: list,
    user_id: int = 0,
    conversation_id: int = 0,
    max_rounds: int = 3,
    allowed_tools: set | None = None,
    on_tool_call=None,
) -> dict:
    """Run the tool rounds and return what they added to the conversation.

    messages: the conversation as sent to the model (it may hold an extra tool instruction).
    allowed_tools: names the model may run; any other call gets an error result instead.
    on_tool_call: optional async callback(name) called before each tool runs.

    Returns {"added": [...messages to append...], "used_tools": [...], "tool_time": s, "rounds": n,
    "final": the answer text when the last round called no tool, else None}.
    """
    from .ia_tools import execute_tool

    added = []
    used_tools = []
    tool_time = 0.0
    rounds = 0
    final = None
    is_openai = is_openai_host(host)
    options = req_data.get("options", {})

    while rounds < max_rounds:
        rounds += 1
        if is_openai:
            url = f"{host.rstrip('/')}/chat/completions"
            body = {
                "model": req_data.get("model"),
                "messages": messages + added,
                "stream": False,
                "temperature": options.get("temperature", 0.2),
                "max_tokens": options.get("num_predict", 4096),
            }
            if req_data.get("tools"):
                body["tools"] = req_data["tools"]
        else:
            url = f"{host.rstrip('/')}/api/chat"
            body = {**req_data, "messages": messages + added, "stream": False}

        try:
            res = await client.post(url, json=body, timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0))
            data = res.json()
        except Exception as e:
            print(f"[ToolCall] Non-streaming call failed: {e}", flush=True)
            break

        msg = (data.get("choices") or [{}])[0].get("message", {}) if is_openai else data.get("message", {})
        content = msg.get("content") or ""
        calls = msg.get("tool_calls")
        is_xml = False
        if not calls:
            calls = parse_xml_tool_calls(content + "\n" + (msg.get("thinking") or ""))
            is_xml = bool(calls)
        if not calls:
            final = content
            break

        if is_xml:
            added.append({"role": "assistant", "content": content})
        else:
            added.append({"role": "assistant", "content": content, "tool_calls": calls})

        for call in calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            args = parse_tool_args(fn.get("arguments"))
            if on_tool_call:
                await on_tool_call(name)
            if name not in used_tools:
                used_tools.append(name)
            started = time.time()
            if allowed_tools is not None and name not in allowed_tools:
                result = json.dumps({"error": f"Tool '{name}' is not available here."})
            else:
                try:
                    result = await execute_tool(name, args, user_id=user_id, conversation_id=conversation_id)
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            tool_time += time.time() - started

            if is_xml:
                added.append({"role": "user", "content": f"Résultat de l'outil {name}: {result}"})
            else:
                reply = {"role": "tool", "content": result}
                if call.get("id"):
                    reply["tool_call_id"] = call["id"]
                added.append(reply)

    return {"added": added, "used_tools": used_tools, "tool_time": tool_time, "rounds": rounds, "final": final}
