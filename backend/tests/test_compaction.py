"""Freeing room in a long AI conversation: anchored summary and truncation (ai-bench/COMPACTION.md, 2026-11-08)."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app import models
from app.ia_compression import split_kept, run_anchored, run_truncation, truncation_index


def msg(i, role, content):
    return SimpleNamespace(id=i, role=role, content=content)


def exchanges(n, size=40):
    out = []
    for k in range(n):
        out += [msg(2 * k, "user", f"question {k} " + "q" * size), msg(2 * k + 1, "assistant", f"answer {k} " + "a" * size)]
    return out


def test_last_two_exchanges_stay_word_for_word():
    to_summarize, kept = split_kept(exchanges(5), 16384)
    assert [m.id for m in kept] == [6, 7, 8, 9]
    assert [m.id for m in to_summarize] == [0, 1, 2, 3, 4, 5]


def test_long_last_exchanges_are_summarized_too():
    """Kept word for word, a huge last exchange would fill the context again and compress at every message."""
    convo = exchanges(4)
    convo[-2].content = "x" * 30000  # last question: more than 30 % of a 16K context
    to_summarize, kept = split_kept(convo, 16384)
    assert kept == []
    assert len(to_summarize) == 8


def test_something_is_always_summarized():
    to_summarize, kept = split_kept(exchanges(2), 16384)
    assert [m.id for m in to_summarize] == [0, 1]
    assert [m.id for m in kept] == [2, 3]


def ollama(*answers):
    res = [MagicMock(json=MagicMock(return_value={"response": a})) for a in answers]
    c = AsyncMock()
    c.post = AsyncMock(side_effect=res)
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    return c


@pytest.mark.asyncio
async def test_summary_merges_the_previous_one():
    c = ollama("FACTS:\n- Lyra joins at 21:00")
    with patch("httpx.AsyncClient", return_value=c):
        out = await run_anchored("FACTS:\n- team Kiwi", ["U: Lyra joins at 21:00", "A: Noted"],
                                 "http://gpu:11434", "m", num_ctx=32768, think=False)
    assert out == "FACTS:\n- Lyra joins at 21:00"
    sent = c.post.call_args.kwargs["json"]
    assert sent["prompt"].startswith("[Previous summary]\nFACTS:\n- team Kiwi\n\n[New messages to merge into the summary]\nU: Lyra")
    for section in ("FACTS:", "DECISIONS (and why):", "USER PREFERENCES:", "OPEN QUESTIONS"):
        assert section in sent["prompt"]
    assert sent["options"] == {"temperature": 0.1, "num_ctx": 32768, "num_predict": 450}
    assert sent["think"] is False


@pytest.mark.asyncio
async def test_a_text_too_long_is_summarized_in_parts_without_losing_its_start():
    """The former modes cut the start of a text that did not fit the context."""
    lines = [f"U: fact {k} " + "z" * 3000 for k in range(20)]  # 60 000 characters for an 8K context
    c = ollama("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12")
    with patch("httpx.AsyncClient", return_value=c):
        out = await run_anchored("", lines, "http://gpu:11434", "m", num_ctx=8192, think=False)
    prompts = [call.kwargs["json"]["prompt"] for call in c.post.call_args_list]
    assert len(prompts) > 1
    assert "U: fact 0 " in prompts[0]
    assert prompts[1].startswith("[Previous summary]\nS1\n")
    assert all(f"U: fact {k} " in "".join(prompts) for k in range(20))
    assert all(len(p) / 3.5 < 8192 for p in prompts)
    assert out == f"S{len(prompts)}"


def test_truncation_follows_the_context_size():
    convo = exchanges(40, size=1000)  # 80 messages of about 1 000 characters
    dropped_small, kept_small = run_truncation(convo, 8192)
    dropped_big, kept_big = run_truncation(convo, 32768)
    assert len(kept_big) > 2 * len(kept_small)
    assert sum(len(m.content) for m in kept_big) <= 32768 * 3.5 * 0.5


def test_truncation_index_adds_to_the_previous_one():
    first = truncation_index("", [msg(1, "user", "Team Kiwi:\nZephyr, Orbit"), msg(2, "assistant", "OK")], 16384)
    assert first == "[Tronqué]\n- U: Team Kiwi: Zephyr, Orbit\n- A: OK"  # the whole message, not only its first line
    second = truncation_index(first, [msg(3, "user", "Lyra joins")], 16384)
    assert second.splitlines() == ["[Tronqué]", "- U: Team Kiwi: Zephyr, Orbit", "- A: OK", "- U: Lyra joins"]
    big = truncation_index("", [msg(k, "user", f"n{k} " + "y" * 400) for k in range(200)], 8192)
    assert len(big) <= 8192 * 3.5 * 0.15 + 400
    assert "n199 " in big and "n0 " not in big  # the oldest lines go first


@pytest.fixture
def conversation(db_session):
    user = db_session.query(models.User).filter(models.User.username == "admin").first()
    conv = models.Conversation(user_id=user.id, title="t", compression_mode="compact",
                               compressed_context="FACTS:\n- old", compressed_at=datetime(2026, 11, 8, 10, 0))
    db_session.add(conv)
    db_session.commit()
    start = datetime(2026, 11, 8, 10, 0)
    for k, m in enumerate(exchanges(4)):
        db_session.add(models.ChatMessage(conversation_id=conv.id, role="user" if m.role == "user" else "assistant",
                                          content=m.content, timestamp=start + timedelta(minutes=k)))
    db_session.commit()
    return conv


def test_compress_route_summarizes_all_but_the_last_exchanges(client, db_session, conversation):
    """A conversation compressed by the former "compact" mode goes on with the summary, merged with the old one."""
    sent = {}

    async def enqueue(entry):
        sent.update(entry.payload)
        await entry.result_stream.put({"done": True, "result": "FACTS:\n- new"})
        entry.done_event.set()
        return entry, 0

    with patch("app.routers.ia.pick_instance", AsyncMock(return_value={"url": "http://gpu:11434"})), \
            patch("app.ia_queue.queue_manager.enqueue", enqueue):
        assert client.post(f"/ia/compress/{conversation.id}", json={"mode": "compact"}).status_code == 200

    assert sent["previous"] == "FACTS:\n- old"
    assert [l.split()[2] for l in sent["lines"]] == ["0", "0", "1", "1"]
    db_session.refresh(conversation)
    assert conversation.compressed_context == "FACTS:\n- new"
    assert conversation.compression_mode == "summary"
    assert conversation.compressed_at == datetime(2026, 11, 8, 10, 4)  # the last two exchanges stay in the chat
