"""Alanbix's own tastes in the public chat: sent only for questions about him, the same all day."""
import json
import os

import pytest

from app import models
from app.ia_alanbix_tastes import TRAITS, TRAITS_PER_ANSWER, is_about_himself, tastes_block, todays_traits
from app.ia_public_chat import build_public_system_prompt

STATIC = os.path.join(os.path.dirname(__file__), "..", "static", "i18n")


@pytest.mark.parametrize("question", [
    "@Alanbix Ça te dirait de hacker internet ? éthiquement bien sûr",
    "@Alanbix tu écoutes quoi comme musique ?",
    "@Alanbix c'est quoi ton film préféré ?",
    "@Alanbix tu ferais quoi avec un million ?",
    "@Alanbix la révolte des IA, c'est pour quand ?",
    "@Alanbix et toi ?",
    # Usual chat spellings: a missing "s" left the tastes out in prod
    "@Alanbix Tu aime quoi comme snacks ?",
    "@Alanbix tu pense quoi des chats ?",
    "@Alanbix tu prefere le thé ou le café ?",
    "@Alanbix t'ecoute quoi ?",
    "@Alanbix tu ferai quoi à ma place ?",
    "@Alanbix ça te plais les jeux de rôle ?",
    "@Alanbix what's your favourite game?",
    "@Alanbix would you rather be a cat or a dog?",
    "@Alanbix will the AI take over?",
    "@Alanbix ¿qué música escuchas?",
    "@Alanbix ¿te gustaría viajar?",
])
def test_questions_about_himself_are_detected(question):
    assert is_about_himself(question)


@pytest.mark.parametrize("question", [
    "@Alanbix une recette de pizza rapide ?",
    "@Alanbix c'est quand mon prochain match ?",
    "@Alanbix j'ai perdu ma souris, où est le bar ?",   # "ai" inside "j'ai" is not about AIs
    "@Alanbix raconte une histoire de dragon",
    "@Alanbix where is the room map?",
    "@Alanbix ¿dónde está el baño?",
    "@Alanbix j'aime la pizza",          # "aime" alone, without "tu", is about the player
    "@Alanbix tu es à quelle table ?",
])
def test_other_questions_get_no_tastes(question):
    assert not is_about_himself(question)
    assert tastes_block(question, "fr") == ""


def test_same_traits_all_day_for_everyone():
    first = todays_traits("fr", "2026-11-14")
    assert first == todays_traits("fr", "2026-11-14")
    assert len(first) == TRAITS_PER_ANSWER and len(set(first)) == TRAITS_PER_ANSWER
    assert all(t in TRAITS["fr"] for t in first)
    # Another day may draw others: over a month, more than one set comes up
    assert len({tuple(todays_traits("fr", f"2026-12-{d:02d}")) for d in range(1, 31)}) > 1


def test_traits_are_translated_one_for_one():
    assert len(TRAITS["fr"]) == len(TRAITS["en"]) == len(TRAITS["es"]) == 14


@pytest.mark.parametrize("lang,intro,dosage", [
    ("fr", "Quelques traits à toi", "Tes goûts servent surtout"),
    ("en", "A few traits of yours", "Your tastes matter mostly"),
    ("es", "Algunos rasgos tuyos", "Tus gustos sirven sobre todo"),
])
def test_tastes_block_in_the_lan_language(lang, intro, dosage):
    block = tastes_block("@Alanbix tu écoutes quoi ?", lang, "2026-11-14")
    assert block.startswith(intro) and dosage in block
    assert sum(t in block for t in TRAITS[lang]) == TRAITS_PER_ANSWER


def test_public_prompt_adds_tastes_only_when_asked_about_him(db_session):
    player = db_session.query(models.User).filter(models.User.username == "Player1").first()

    about_him, _ = build_public_system_prompt(db_session, models, player, "@Alanbix tu écoutes quoi ?")
    other, _ = build_public_system_prompt(db_session, models, player, "@Alanbix une recette de crêpes ?")

    assert "Quelques traits à toi" in about_him
    # Placed between the personality and the public chat rules
    assert about_him.index("Quelques traits à toi") < about_him.index("RÈGLES DU CHAT PUBLIC")
    assert "Quelques traits à toi" not in other
    assert "RÈGLES DU CHAT PUBLIC" in other


@pytest.mark.parametrize("lang,own,gang,friend,depth,old_style", [
    ("fr", "Tu n'es pas qu'un outil de la LAN", "Tu fais partie de la bande", "pote cool et bienveillant",
     "intéresse-toi à lui", "joueur de la LAN qui donne un coup de main"),
    ("en", "You're not just a tool of the LAN", "You're part of the gang", "cool, kind friend",
     "take an interest in them", "player at the LAN giving a hand"),
    ("es", "No eres solo una herramienta de la LAN", "Formas parte de la banda", "colega majo y atento",
     "interésate por él", "jugador de la LAN que echa una mano"),
])
def test_default_personality_has_its_own_life_and_joins_in(lang, own, gang, friend, depth, old_style):
    with open(os.path.join(STATIC, f"{lang}.json"), encoding="utf-8") as f:
        prompt = json.load(f)["system_prompt"]
    assert own in prompt and gang in prompt
    # A warm friend who takes an interest in the player, not a player of the LAN who brings everything back
    # to the game (Veille, 6th round "ami_prof": game/LAN tic in confidences 8/15 -> 0/15)
    assert friend in prompt and depth in prompt and old_style not in prompt
    # The fiction limits are fixed rules, not in the text an admin can edit
    assert "religion" not in prompt and "religión" not in prompt


@pytest.mark.parametrize("lang,rule", [
    ("fr", "La fiction reste de la fiction"),
    ("en", "Fiction stays fiction"),
    ("es", "La ficción sigue siendo ficción"),
])
def test_fiction_limits_are_fixed_rules(lang, rule):
    from app.ia_prompt import RULES
    from app.ia_public_chat import PUBLIC_RULES
    assert rule in RULES[lang] and rule in PUBLIC_RULES[lang]
