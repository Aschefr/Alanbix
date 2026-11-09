"""Freeing room in a long AI conversation: anchored summary and truncation (ai-bench/COMPACTION.md, 2026-11-08)."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app import models
from app.ia_compression import (split_kept, run_anchored, run_truncation, truncation_index, summary_problem,
                                strip_instruction_echo, SummaryRejected)


def msg(i, role, content):
    return SimpleNamespace(id=i, role=role, content=content)


def exchanges(n, size=40):
    out = []
    for k in range(n):
        out += [msg(2 * k, "user", f"question {k} " + "q" * size), msg(2 * k + 1, "assistant", f"answer {k} " + "a" * size)]
    return out


def full(facts, prefs="- talk to me with tu"):
    """A summary with the four sections, as the model must write it."""
    return "\n".join(["FAITS :", facts, "DÉCISIONS (et pourquoi) :", "- none", "PRÉFÉRENCES DE L'UTILISATEUR :", prefs,
                      "QUESTIONS EN SUSPENS (et ce dont elles dépendent) :", "- none"])


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
    c = ollama(full("- Lyra joins at 21:00"))
    with patch("httpx.AsyncClient", return_value=c):
        out = await run_anchored("FAITS :\n- team Kiwi", ["U: Lyra joins at 21:00", "A: Noted"],
                                 "http://gpu:11434", "m", num_ctx=32768, think=False, lang="fr")
    assert out == full("- Lyra joins at 21:00")
    sent = c.post.call_args.kwargs["json"]
    assert sent["prompt"].startswith("[Previous summary]\nFAITS :\n- team Kiwi\n\n[New messages to merge into the summary]\nU: Lyra")
    # language and titles given by the code, already translated: asked to translate them, gemma4:e4b wrote in English
    assert "Write in French" in sent["prompt"] and "(corrigé, remplace X)" in sent["prompt"]
    for section in ("FAITS:", "DÉCISIONS (et pourquoi):", "PRÉFÉRENCES DE L'UTILISATEUR:", "QUESTIONS EN SUSPENS"):
        assert section in sent["prompt"]
    assert sent["options"] == {"temperature": 0.1, "num_ctx": 32768, "num_predict": 450}
    assert sent["think"] is False


@pytest.mark.asyncio
async def test_other_languages_get_their_titles_or_english():
    for lang, word in (("es", "Write in Spanish"), ("en", "Write in English"), ("de", "Write in English"), (None, "Write in English")):
        c = ollama(full("- x"))
        with patch("httpx.AsyncClient", return_value=c):
            await run_anchored("", ["U: x"], "http://gpu:11434", "m", lang=lang)
        prompt = c.post.call_args.kwargs["json"]["prompt"]
        assert word in prompt
        assert ("HECHOS:" in prompt) == (lang == "es")


@pytest.mark.asyncio
async def test_a_text_too_long_is_summarized_in_parts_without_losing_its_start():
    """The former modes cut the start of a text that did not fit the context."""
    lines = [f"U: fact {k} " + "z" * 3000 for k in range(20)]  # 60 000 characters for an 8K context
    c = ollama(*[full(f"- S{k}") for k in range(1, 13)])
    with patch("httpx.AsyncClient", return_value=c):
        out = await run_anchored("", lines, "http://gpu:11434", "m", num_ctx=8192, think=False, lang="fr")
    prompts = [call.kwargs["json"]["prompt"] for call in c.post.call_args_list]
    assert len(prompts) > 1
    assert "U: fact 0 " in prompts[0]
    assert prompts[1].startswith("[Previous summary]\n" + full("- S1"))
    assert all(f"U: fact {k} " in "".join(prompts) for k in range(20))
    assert all(len(p) / 3.5 < 8192 for p in prompts)
    assert out == full(f"- S{len(prompts)}")


def test_incomplete_or_looping_summaries_are_refused():
    assert summary_problem(full("- a")) == ""
    assert summary_problem("FACTS:\n- a\nDECISIONS (and why):\n- b\nUSER PREFERENCES:\n- c\nOPEN QUESTIONS:\n- d") == ""
    assert summary_problem("**HECHOS:**\n- a\nDECISIONES:\n- b\nPREFERENCIAS DEL USUARIO:\n- c\nPREGUNTAS PENDIENTES:\n- d") == ""
    cut = full("- a").rsplit("QUESTIONS EN SUSPENS", 1)[0]  # cut by the length limit
    assert "OPEN QUESTIONS" in summary_problem(cut)
    loop = full("\n".join(["- Lyra joins team Kiwi at 21:00"] * 3))
    assert summary_problem(loop) == "repeated lines"


@pytest.mark.asyncio
async def test_a_refused_summary_raises_and_is_not_returned():
    c = ollama("FAITS :\n- a\nDÉCISIONS :\n- b")
    with patch("httpx.AsyncClient", return_value=c):
        with pytest.raises(SummaryRejected):
            await run_anchored("FAITS :\n- old", ["U: x"], "http://gpu:11434", "m", lang="fr")


def test_copied_instructions_leave_the_preferences_only():
    prefs = "\n".join(["- Tutoyer le joueur", "- Garder les valeurs exactes et les plages",
                       "- Écrire en français", "- Utiliser les quatre titres donnés"])
    clean, removed = strip_instruction_echo(full("- Garder les valeurs exactes : score 3-2", prefs), "fr")
    assert removed == 3
    assert "- Tutoyer le joueur" in clean
    assert "- Garder les valeurs exactes : score 3-2" in clean  # a fact, not a preference: kept
    # another language than the summary's is a real request of the player
    assert strip_instruction_echo(full("- a", "- Répondre en anglais"), "fr")[1] == 0


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


def queue_answering(sent, answer):
    async def enqueue(entry):
        sent.update(entry.payload)
        await entry.result_stream.put(answer)
        entry.done_event.set()
        return entry, 0
    return enqueue


def test_compress_route_summarizes_all_but_the_last_exchanges(client, db_session, conversation):
    """A conversation compressed by the former "compact" mode goes on with the summary, merged with the old one."""
    sent = {}
    with patch("app.routers.ia.pick_instance", AsyncMock(return_value={"url": "http://gpu:11434"})), \
            patch("app.ia_queue.queue_manager.enqueue", queue_answering(sent, {"done": True, "result": "FACTS:\n- new"})):
        assert client.post(f"/ia/compress/{conversation.id}", json={"mode": "compact", "lang": "es"}).status_code == 200

    assert sent["previous"] == "FACTS:\n- old"
    assert sent["lang"] == "es"  # the player's interface language
    assert [l.split()[2] for l in sent["lines"]] == ["0", "0", "1", "1"]
    db_session.refresh(conversation)
    assert conversation.compressed_context == "FACTS:\n- new"
    assert conversation.compression_mode == "summary"
    assert conversation.compressed_at == datetime(2026, 11, 8, 10, 4)  # the last two exchanges stay in the chat


def test_a_refused_summary_leaves_the_conversation_as_it_was(client, db_session, conversation):
    sent = {}
    refused = {"done": True, "error": True, "rejected": True, "result": "missing section OPEN QUESTIONS"}
    with patch("app.routers.ia.pick_instance", AsyncMock(return_value={"url": "http://gpu:11434"})), \
            patch("app.ia_queue.queue_manager.enqueue", queue_answering(sent, refused)):
        res = client.post(f"/ia/compress/{conversation.id}", json={"mode": "summary"})
    assert res.status_code == 500 and "incomplet" in res.json()["detail"]
    assert sent["lang"] == "fr"  # no language sent: the LAN's
    db_session.refresh(conversation)
    assert conversation.compressed_context == "FACTS:\n- old"
    assert conversation.compressed_at == datetime(2026, 11, 8, 10, 0)
