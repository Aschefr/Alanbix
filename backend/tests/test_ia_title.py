# -*- coding: utf-8 -*-
import pytest
from app.ia_title_utils import _is_default_title, _build_title_prompt, _clean_title

def test_is_default_title():
    # Built-in fallbacks
    assert _is_default_title("Nouvelle conversation") is True
    assert _is_default_title("New conversation") is True
    assert _is_default_title("Nueva conversación") is True
    assert _is_default_title("  New discussion  ") is True
    assert _is_default_title("") is True
    assert _is_default_title(None) is True
    
    # Custom titles (should not be detected as default)
    assert _is_default_title("Stratégie Rocket League") is False
    assert _is_default_title("Aide configuration réseau") is False

def test_build_title_prompt():
    excerpt = "User: Comment configurer Searxng ?\nBot: C'est facile..."
    prompt = _build_title_prompt(excerpt)
    # Verify prompt is in English and requests the same language
    assert "Generate a short title" in prompt
    assert "same language as the conversation" in prompt
    assert excerpt in prompt

def test_clean_title():
    # Surround quotes cleanup
    assert _clean_title('"Mon Super Titre"') == "Mon Super Titre"
    assert _clean_title("'Mon Super Titre'") == "Mon Super Titre"
    assert _clean_title("`Mon Super Titre`") == "Mon Super Titre"
    assert _clean_title("**Mon Super Titre**") == "Mon Super Titre"
    
    # Prefix removal
    assert _clean_title("Title: Rocket League Tactics") == "Rocket League Tactics"
    assert _clean_title("Titre: Tactiques de jeu") == "Tactiques de jeu"
    assert _clean_title("Titre de la conversation : Aide DNS") == "Aide DNS"
    
    # Stray punctuation removal
    assert _clean_title("   - Mon Titre...   ") == "Mon Titre"
    assert _clean_title("Mon Titre.") == "Mon Titre"
    assert _clean_title("Mon Titre!?") == "Mon Titre"
    
    # Length truncation
    long_title = "Un titre de conversation beaucoup trop long et verbeux qui depasse la limite de cinquante caracteres"
    cleaned = _clean_title(long_title)
    assert len(cleaned) <= 50
    # Check that it truncated at word boundary
    assert cleaned.endswith("qui") or cleaned.endswith("depasse") or len(cleaned) <= 50
    
    # Rejection of unusable titles
    assert _clean_title("Ok") is None
    assert _clean_title("  ") is None
