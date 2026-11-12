"""The AI dispatcher: which waiting request a free server takes, and the queue built on it."""
import asyncio
import time
from unittest.mock import patch

import pytest

from app.ia_dispatch import pick, bind, estimated_wait, serial_key
from app.ia_queue import IAQueueManager, QueueEntry

FAST = {"url": "http://fast:11434", "model": "gemma4:e4b", "label": "Fast"}
SLOW = {"url": "http://slow:11434", "model": "mimo-v2.6:9b", "label": "Slow"}
NAMES = ["gemma4:e4b", "mimo-v2.6:9b"]


def chat(priority=10, user=1, conv=1, host=SLOW["url"], model="mimo-v2.6:9b", fixed=False, age=0.0):
    return QueueEntry(priority=priority, created_at=time.time() - age, user_id=user, conversation_id=conv,
                      task_type="chat", payload={"ollama_host": host, "model_fixed": fixed,
                                                 "req_data": {"model": model}, "model_info": {}})


def test_the_free_server_takes_the_most_urgent_request_and_is_pointed_at():
    player = chat(priority=10, user=1, age=5)
    admin = chat(priority=0, user=2, conv=2)
    background = QueueEntry(priority=20, created_at=time.time() - 9, task_type="auto_title",
                            payload={"ollama_host": SLOW["url"], "model": "mimo-v2.6:9b"})
    e, model = pick([player, background, admin], FAST, "", NAMES, set(), {})
    assert e is admin and model == "gemma4:e4b"
    bind(e, FAST, model)
    # Sent to the slow server at enqueue time, answered by the free fast one, with its model
    assert e.payload["ollama_host"] == FAST["url"]
    assert e.payload["req_data"]["model"] == "gemma4:e4b" and e.payload["model_info"]["instance"] == "Fast"


def test_a_chosen_model_only_goes_to_a_server_that_has_it():
    e = chat(model="mimo-v2.6:9b", fixed=True)
    assert pick([e], FAST, "", ["gemma4:e4b"], set(), {}) == (None, None)
    assert pick([e], FAST, "", NAMES, set(), {})[1] == "mimo-v2.6:9b"


def test_one_answer_at_a_time_per_player_public_chat_included():
    first, second = chat(user=7, conv=1, age=3), chat(user=7, conv=1)
    assert pick([first, second], FAST, "", NAMES, {7}, {}) == (None, None)
    public = QueueEntry(priority=10, created_at=time.time(), user_id=0, task_type="public_chat",
                        payload={"ollama_host": FAST["url"], "model": "gemma4:e4b", "asker_id": 9})
    assert serial_key(public) == 9
    assert pick([public], FAST, "", NAMES, {9}, {}) == (None, None)


def test_a_conversation_prefers_its_last_server_only_when_it_is_free():
    older = chat(user=1, conv=1, age=10)
    mine = chat(user=2, conv=2, age=1)
    # Same urgency: the conversation this server answered last goes first (its prompt is cached there)
    assert pick([older, mine], FAST, "", NAMES, set(), {2: FAST["url"]})[0] is mine
    # Never ahead of a more urgent request
    urgent = chat(priority=0, user=3, conv=3)
    assert pick([older, mine, urgent], FAST, "", NAMES, set(), {2: FAST["url"]})[0] is urgent


def test_no_crossing_between_ollama_and_openai_servers_but_the_callers_server_always_works():
    openai = {"url": "https://api.example.com/v1", "model": "gpt-x"}
    assert pick([chat()], openai, "", [], set(), {}) == (None, None)
    # The server the caller chose takes it even with an unknown model list
    e = chat(host=FAST["url"], model="gemma4:e4b")
    assert pick([e], FAST, "", [], set(), {})[1] == "gemma4:e4b"


def test_the_wait_counts_servers_working_side_by_side():
    assert estimated_wait(4, [5.0, 20.0], 15.0) == 16   # 4 / (1/5 + 1/20)
    assert estimated_wait(3, [None], 10.0) == 30
    assert estimated_wait(0, [5.0], 15.0) == 0


@pytest.mark.asyncio
async def test_a_fast_and_a_slow_server_share_the_queue_by_speed():
    """Ten player requests, all assigned to the slow server at enqueue (the old round-robin could do
    that): the fast server takes most of them and nobody waits behind the slow one while it is free."""
    q = IAQueueManager()
    served = {FAST["url"]: 0, SLOW["url"]: 0}
    speed = {FAST["url"]: 0.02, SLOW["url"]: 0.12}

    async def fake_process(entry, _worker):
        host = entry.payload["ollama_host"]
        served[host] += 1
        await asyncio.sleep(speed[host])
        return 0.0, speed[host]

    async def healthy(url, timeout=2.0):
        return True, 1, NAMES

    with patch.object(IAQueueManager, "_enabled_instances", return_value=[FAST, SLOW]), \
         patch.object(IAQueueManager, "load_persisted_durations"), \
         patch.object(IAQueueManager, "persist_durations"), \
         patch.object(q, "_process_entry", side_effect=fake_process), \
         patch.object(q, "_default_model", return_value=""), \
         patch("app.routers.ia._check_instance_health", side_effect=healthy):
        await q.start()
        entries = [chat(user=i + 1, conv=i + 1) for i in range(10)]
        started = time.monotonic()
        for e in entries:
            await q.enqueue(e)
        await asyncio.wait_for(asyncio.gather(*(e.done_event.wait() for e in entries)), timeout=10)
        took = time.monotonic() - started
        await q.stop()

    assert served[FAST["url"]] + served[SLOW["url"]] == 10
    assert served[FAST["url"]] >= 6
    # All on the slow server, one by one, would take 1.2 s
    assert took < 0.8


@pytest.mark.asyncio
async def test_the_real_request_goes_to_the_server_that_took_it():
    """End to end through _process_chat: assigned to the slow server, taken by the fast one, the HTTP
    call goes to the fast server with its model, and the answer is labelled with it."""
    from unittest.mock import MagicMock, AsyncMock
    import json

    calls = []

    def stream(method, url, json=None, **kw):
        calls.append((url, json["model"]))
        res = MagicMock(status_code=200)

        async def lines():
            import json as j
            yield j.dumps({"message": {"content": "Bonjour !"}})
            yield j.dumps({"done": True})
        res.aiter_lines = lines

        class Ctx:
            async def __aenter__(self):
                return res

            async def __aexit__(self, *a):
                return False
        return Ctx()

    client = MagicMock()
    client.stream = MagicMock(side_effect=stream)
    client.aclose = AsyncMock()
    q = IAQueueManager()
    e = chat(host=SLOW["url"], model="mimo-v2.6:9b")
    e.payload.update(conversation_id=0, req_data={"model": "mimo-v2.6:9b", "stream": True, "options": {},
                                                  "messages": [{"role": "user", "content": "Salut"}]})
    q._pending[e.id] = e
    with patch.object(q, "_default_model", return_value=""):
        taken = q._take(FAST, True, NAMES)
    assert taken is e
    with patch("httpx.AsyncClient", return_value=client):
        await q._process_chat(e, e.payload)
    assert calls and calls[0][0].startswith(FAST["url"]) and calls[0][1] == "gemma4:e4b"
    items = []
    while not e.result_stream.empty():
        items.append(e.result_stream.get_nowait())
    done = [i for i in items if i.get("done")][0]
    assert done["full_response"] == "Bonjour !"
