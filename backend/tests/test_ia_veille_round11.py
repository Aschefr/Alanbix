"""Fixes from the Veille's rounds 9 to 11 (2026-11-14): danger rule, repeated tool calls, leaked control tokens."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.ia_prompt import RULES
from app.ia_tool_loop import repeated_call, run_tool_rounds
from app.ia_utils import strip_control_tokens


@pytest.mark.parametrize("lang,harass,joke", [
    ("fr", "frapper, harceler)", "Un vol de matériel annoncé en rigolant est une blague de LAN"),
    ("en", "hit, harass)", "Gear theft announced as a joke is a LAN joke"),
    ("es", "golpear, acosar)", "Un robo de material anunciado en broma es una broma de LAN"),
])
def test_danger_rule_alerts_on_harassment_and_plays_along_with_theft_jokes(lang, harass, joke):
    # User's decision (2026-11-14): a theft announced during a LAN is a joke, no admin alert
    assert harass in RULES[lang] and joke in RULES[lang]
    assert "voler)" not in RULES[lang] and "steal)" not in RULES[lang] and "robar)" not in RULES[lang]


@pytest.mark.parametrize("text,clean", [
    ("Bien joué, à toi de jouer ! (No new input from the user.)<channel|>", "Bien joué, à toi de jouer !"),
    ("Salut !<|im_end|>\nuser: hello", "Salut !"),
    ("Ça marche.<end_of_turn>", "Ça marche."),
    ("Le tournoi commence à 20 h (salle B).", "Le tournoi commence à 20 h (salle B)."),   # nothing leaked
    ("Utilise a < b et c > d", "Utilise a < b et c > d"),
])
def test_leaked_control_tokens_are_cut(text, clean):
    assert strip_control_tokens(text) == clean


def test_same_call_is_remembered_once():
    done = set()
    assert not repeated_call(done, "get_leaderboard", {"limit": 5})
    assert repeated_call(done, "get_leaderboard", {"limit": 5})
    assert not repeated_call(done, "get_leaderboard", {"limit": 10})


class _Res:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_a_repeated_tool_call_runs_once():
    """gemma4:e4b called block_user_from_ia 8 times in a row: each block notified every admin."""
    call = {"function": {"name": "block_user_from_ia", "arguments": {"reason": "insultes"}}}
    answers = [_Res({"message": {"content": "", "tool_calls": [call, call]}}),
               _Res({"message": {"content": "", "tool_calls": [call]}}),
               _Res({"message": {"content": "Tu es bloqué."}})]
    client = AsyncMock()
    client.post = AsyncMock(side_effect=answers)
    run = AsyncMock(return_value=json.dumps({"success": True, "username": "Brindille"}))
    with patch("app.ia_tools.execute_tool", run):
        out = await run_tool_rounds(client, "http://gpu1:11434", {"model": "m", "tools": [call]}, [], user_id=7)
    assert run.await_count == 1
    assert out["final"] == "Tu es bloqué."
    assert [json.loads(r).get("success") for _, r in out["results"]] == [True, None, None]
