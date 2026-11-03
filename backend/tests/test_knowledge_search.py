import json
from unittest.mock import AsyncMock, patch

import pytest

from app import ia_knowledge, models
from app.ia_knowledge import keyword_search, search_knowledge, tokens

CFG = {"rag_enabled": True, "rag_min_score": 0.65}


@pytest.fixture(autouse=True)
def fresh_embed_state():
    ia_knowledge._embed_state["failed_at"] = None
    yield
    ia_knowledge._embed_state["failed_at"] = None


def add(db, content, vector=None, model=None, meta=None):
    doc = models.KnowledgeBase(content=content, metadata_json=meta or {},
                               embedding_json=json.dumps(vector) if vector else None, embed_model=model)
    db.add(doc)
    db.commit()
    return doc


def seed(db):
    return [
        add(db, "Q: Qui contacter pour réparer la serrure de la porte des WC ? R: Le serrurier, au 06 00 00 00 00.", [1, 0, 0], "nomic"),
        add(db, "Les jeux crackés Goldberg ont un raccourci pour configurer son pseudo.", [0, 1, 0], "nomic"),
        add(db, "Le wifi de la LAN s'appelle Lanomalie_5G, mot de passe affiché à l'accueil.", [0, 0, 1], "nomic"),
    ]


def test_tokens_drop_accents_small_words_and_plurals():
    assert tokens("Où sont les toilettes de la salle ?") == ["toilette", "salle"]
    assert tokens("Les jeux crackés") == ["jeux", "cracke"]


def test_keyword_search_needs_enough_of_the_question():
    docs = [type("D", (), {"content": c})() for c in (
        "Le mot de passe du wifi est affiché à l'accueil.",
        "Le match de Rocket League commence à 20h.",
    )]
    assert [d.content[:6] for d, _ in keyword_search("mot de passe wifi ?", docs)] == ["Le mot"]
    assert [d.content[:6] for d, _ in keyword_search("c'est quoi mon prochain match", docs)] == ["Le mat"]
    # One word out of four is not enough to inject an entry
    assert keyword_search("comment régler la latence du match en ligne", docs) == []
    assert keyword_search("salut", docs) == []


@pytest.mark.asyncio
async def test_meaning_works_right_after_the_machine_started():
    # The monotonic clock counts from boot: "no failure yet" must not look like a recent failure
    with patch("app.ia_knowledge.time.monotonic", return_value=10.0),          patch("app.ia_utils.get_embedding", AsyncMock(return_value=[1.0])) as emb:
        assert await ia_knowledge.embed("question", "http://ai") == [1.0]
    assert emb.await_count == 1


@pytest.mark.asyncio
async def test_keywords_alone_when_no_embedding_model(db_session):
    lock, goldberg, wifi = seed(db_session)
    with patch("app.ia_utils.get_embedding", AsyncMock(return_value=None)) as emb:
        found = await search_knowledge(db_session, models, "la serrure des WC est cassée", "http://ai", CFG)
        assert [d.id for d in found] == [lock.id]
        # The dead embedding server is not asked again on the next message
        await search_knowledge(db_session, models, "pseudo Goldberg", "http://ai", CFG)
        assert emb.await_count == 1


@pytest.mark.asyncio
async def test_meaning_and_keywords_are_merged(db_session):
    lock, goldberg, wifi = seed(db_session)
    with patch("app.ia_utils.get_embedding", AsyncMock(return_value=[0, 0.1, 1])), \
         patch("app.ia_utils._get_embed_model", return_value="nomic"):
        # No shared word with the wifi entry, but close in meaning; "Goldberg" found by keyword
        found = await search_knowledge(db_session, models, "réseau sans fil et Goldberg", "http://ai", CFG)
    assert {d.id for d in found} == {wifi.id, goldberg.id}


@pytest.mark.asyncio
async def test_vectors_of_another_model_are_not_compared(db_session):
    lock, goldberg, wifi = seed(db_session)
    with patch("app.ia_utils.get_embedding", AsyncMock(return_value=[0, 0, 1])), \
         patch("app.ia_utils._get_embed_model", return_value="bge-m3"):
        assert await search_knowledge(db_session, models, "réseau sans fil", "http://ai", CFG) == []


@pytest.mark.asyncio
async def test_index_entry_records_the_model_or_keeps_keywords_only(db_session):
    doc = models.KnowledgeBase(content="Le bar ferme à 2h.")
    with patch("app.ia_utils.get_embedding", AsyncMock(return_value=[0.5, 0.5])), \
         patch("app.ia_utils._get_embed_model", return_value="nomic"):
        await ia_knowledge.index_entry(doc, "http://ai")
    assert doc.embed_model == "nomic" and json.loads(doc.embedding_json) == [0.5, 0.5]
    with patch("app.ia_utils.get_embedding", AsyncMock(return_value=None)):
        await ia_knowledge.index_entry(doc, "http://ai")
    assert doc.embedding_json is None and doc.embed_model is None


@pytest.mark.asyncio
async def test_status_tells_what_works_and_what_to_reindex(db_session):
    seed(db_session)
    add(db_session, "Entrée sans vecteur")
    with patch("app.ia_utils.get_embedding", AsyncMock(return_value=None)), \
         patch("app.ia_utils.LAST_EMBED_ERROR", "HTTP 404 (nomic): model not found"):
        st = await ia_knowledge.status(db_session, models, "http://ai", CFG)
    assert st["semantic"] == "unavailable" and "404" in st["error"]
    assert (st["entries"], st["to_index"]) == (4, 4)  # nomic entries cannot be checked without the model
    with patch("app.ia_utils.get_embedding", AsyncMock(return_value=[1, 0, 0])), \
         patch("app.ia_utils._get_embed_model", return_value="nomic"):
        st = await ia_knowledge.status(db_session, models, "http://ai", CFG)
    assert (st["semantic"], st["indexed"], st["to_index"]) == ("ok", 3, 1)
