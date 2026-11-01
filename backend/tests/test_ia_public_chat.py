"""@Alanbix in the public chat: prompt layers and answer length."""
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import models
from app.ia_public_chat import asker_matches_block, build_public_system_prompt


def test_public_prompt_has_public_rules_and_asker_card(db_session):
    player = db_session.query(models.User).filter(models.User.username == "Player1").first()
    player.team_name = "Les Rapides"
    db_session.commit()

    prompt, lang = build_public_system_prompt(db_session, models, player)

    assert lang == "fr"
    assert "RÈGLES DU CHAT PUBLIC" in prompt
    # The private assistant's rules (alerts, notifications, blocking) do not apply here
    assert "RÈGLES DE FONCTIONNEMENT" not in prompt
    assert '"Player1"' in prompt and "Les Rapides" in prompt
    assert "aucun match à venir pour Player1" in prompt


def test_asker_matches_block_lists_a_few_pending_matches(db_session):
    player = db_session.query(models.User).filter(models.User.username == "Player1").first()
    pending = [{"tournament": f"Cup {i}", "round": "WB Round 1", "opponent": "Player2", "status": "À venir"} for i in range(4)]
    pending[0]["opponent"] = "À déterminer (BYE)"
    data = json.dumps({"player": "Player1", "pending_matches": pending})
    with patch("app.ia_tools._tool_get_my_matches", return_value=data):
        block = asker_matches_block(db_session, models, player, "en")

    lines = block.splitlines()
    assert lines[0] == "- Upcoming matches of Player1:"
    assert lines[1] == "  - Cup 0, WB Round 1, opponent to be decided"
    assert lines[2] == "  - Cup 1, WB Round 1, against Player2"
    assert len(lines) == 4  # title + 3 matches


@pytest.mark.asyncio
async def test_public_answer_length_is_capped_below_the_context():
    from app.ia_queue import IAQueueManager, QueueEntry, PUBLIC_CHAT_MAX_ANSWER_TOKENS

    entry = QueueEntry(
        priority=10, created_at=time.time(), user_id=0, username="Alanbix", task_type="public_chat",
        payload={"ollama_host": "http://gpu1:11434", "model": "m", "messages": [{"role": "user", "content": "?"}],
                 "context_window": 32768},
    )
    res = MagicMock(status_code=200)
    res.json.return_value = {"message": {"content": "ok"}}
    client = AsyncMock()
    client.post = AsyncMock(return_value=res)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        await IAQueueManager()._process_public_chat(entry, entry.payload)

    options = client.post.call_args.kwargs["json"]["options"]
    assert options["num_predict"] == PUBLIC_CHAT_MAX_ANSWER_TOKENS
    assert options["num_ctx"] == 32768
