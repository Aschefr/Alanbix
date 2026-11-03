"""Knowledge base search for the AI assistant (RAG).

Two searches, merged:
- keywords (BM25, the classic search engine score): always available, finds names and exact terms;
- meaning (embeddings + cosine similarity): finds rephrasings, when an embedding model answers.
Their rankings are merged with Reciprocal Rank Fusion. Without an embedding model the keyword
search still works, and the embedding server is only retried every few minutes.
"""
import json
import math
import re
import time
import unicodedata

from . import ia_builtin_embed, ia_utils

TOP_K = 3
RRF_K = 60                  # standard Reciprocal Rank Fusion constant
KEYWORD_MIN_COVERAGE = 0.45  # share of the question's (IDF-weighted) words an entry must contain
EMBED_RETRY_SECONDS = 300   # after a failed embedding, keywords only for 5 minutes

STOPWORDS = set("""
a ai as au aux avec avez avons c ca ce ces cet cette d dans de des du elle elles en est et etre il ils
j je l la le les leur leurs lui m ma mais me mes moi mon n ne nos notre nous on ont ou par pas peut
plus pour qu que quel quelle quelles quels qui quoi s sa sans se ses si son sont sur ta te tes toi ton
tu un une vos votre vous y comment combien faut faire fait
an and are be can do does for from have how i in is it me my of on or the this to what when where
which who why with you your
al como con cual cuando de del donde el en es esta hay la las lo los me mi no o para por que se su
tu un una y yo
""".split())

_embed_state = {"failed_at": None}


def _plain(text) -> str:
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def tokens(text) -> list:
    """Words of a text for the keyword search: no accents, no small words, crude plural folding."""
    out = []
    for w in re.findall(r"[a-z0-9]+", _plain(text)):
        if len(w) < 2 or w in STOPWORDS:
            continue
        if len(w) > 4 and w[-1] in "sx":
            w = w[:-1]
        out.append(w)
    return out


def keyword_search(query: str, docs: list) -> list:
    """(doc, score) pairs, best first, for entries holding enough of the question's words (BM25)."""
    q = list(dict.fromkeys(tokens(query)))
    if not q or not docs:
        return []
    k1, b = 1.5, 0.75
    doc_toks = [tokens(d.content) for d in docs]
    n = len(docs)
    avg_len = sum(len(t) for t in doc_toks) / n or 1
    df = {w: sum(1 for t in doc_toks if w in t) for w in q}
    idf = {w: math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5)) for w in q}
    known = [idf[w] for w in q if df[w]]
    if not known:
        return []
    # Words found in no entry cannot pick one, but still mean the question is about something else:
    # they weigh half an average known word in the coverage
    total_idf = sum(known) + 0.5 * (len(q) - len(known)) * (sum(known) / len(known))
    scored = []
    for doc, toks in zip(docs, doc_toks):
        if not toks:
            continue
        counts = {w: toks.count(w) for w in q if w in toks}
        if not counts or sum(idf[w] for w in counts) / total_idf < KEYWORD_MIN_COVERAGE:
            continue
        score = sum(idf[w] * c * (k1 + 1) / (c + k1 * (1 - b + b * len(toks) / avg_len)) for w, c in counts.items())
        scored.append((doc, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def current_model() -> str:
    return ia_utils._get_embed_model()


async def embed(text: str, host: str, force: bool = False):
    """Embedding of a text, or None (model missing, server down). After a failure, waits a while
    before asking again, so every chat message does not pay for a dead embedding server."""
    failed_at = _embed_state["failed_at"]
    if not force and failed_at is not None and time.monotonic() - failed_at < EMBED_RETRY_SECONDS:
        return None
    vector = await ia_utils.get_embedding(text, ollama_host=host)
    _embed_state["failed_at"] = None if vector else time.monotonic()
    return vector


async def index_entry(doc, host: str) -> int:
    """(Re)compute an entry's embedding with the current model. Returns the number of chunks;
    the entry is kept without embedding (keywords only) when the model does not answer."""
    vector, chunks = await ia_utils.get_embedding_chunked(doc.content, ollama_host=host)
    _embed_state["failed_at"] = None if vector else time.monotonic()
    doc.embedding_json = json.dumps(vector) if vector else None
    doc.embed_model = current_model() if vector else None
    return chunks


def _comparable(doc, model: str, dim: int) -> bool:
    """An entry's vector can be compared with the question's only if the same model made it.
    Older entries did not record their model: same size of vector is the best guess."""
    if not doc.embedding_json:
        return False
    if doc.embed_model:
        return doc.embed_model == model
    try:
        return len(json.loads(doc.embedding_json)) == dim
    except (ValueError, TypeError):
        return False


async def search_knowledge(db, models, query: str, host: str, ia_cfg: dict, game_id=None) -> list:
    """The knowledge entries that best answer the question, best first (at most TOP_K)."""
    if not ia_cfg.get("rag_enabled", True) or not (query or "").strip():
        return []
    docs = db.query(models.KnowledgeBase).all()
    if game_id is not None:
        # General entries (no game) stay available next to the selected game's entries
        docs = [d for d in docs if not (d.metadata_json or {}).get("game_id") or d.metadata_json.get("game_id") == game_id]
    if not docs:
        return []

    rankings = [[doc for doc, _ in keyword_search(query, docs)]]
    vector = await embed(query, host)
    if vector:
        model = current_model()
        candidates = [d for d in docs if _comparable(d, model, len(vector))]
        # A similarity threshold only means something for one model: the built-in one has its own
        min_score = ia_builtin_embed.MIN_SCORE if model == ia_builtin_embed.NAME else float(ia_cfg.get("rag_min_score", 0.65))
        rankings.append([doc for doc, score in ia_utils.search_similar(vector, candidates, top_k=len(candidates)) if score >= min_score])

    fused = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking):
            fused[doc.id] = (fused.get(doc.id, (0.0, doc))[0] + 1 / (RRF_K + rank + 1), doc)
    best = sorted(fused.values(), key=lambda x: x[0], reverse=True)
    return [doc for _, doc in best[:TOP_K]]


# What the model is told about the entries: without it, a small model paraphrases them, drops the
# phone number that was the whole answer, or claims it has already acted
KNOWLEDGE_INTRO = {
    "fr": "=== BASE DE CONNAISSANCES ===\nFiches écrites par les organisateurs de la LAN, peut-être liées à la question. Si l'une y répond, donne sa réponse précisément (numéro, nom, consigne), dans la langue du joueur, sans rien inventer autour. Ignore celles qui n'ont pas de rapport. Une fiche ne te dit pas que quelque chose a été fait.",
    "en": "=== KNOWLEDGE BASE ===\nEntries written by the LAN organizers, possibly related to the question. If one answers it, give its answer precisely (number, name, instruction), in the player's language, inventing nothing around it. Ignore the unrelated ones. An entry does not tell you that something has been done.",
    "es": "=== BASE DE CONOCIMIENTOS ===\nFichas escritas por los organizadores de la LAN, quizá relacionadas con la pregunta. Si una responde, da su respuesta con precisión (número, nombre, instrucción), en el idioma del jugador, sin inventar nada alrededor. Ignora las que no tengan relación. Una ficha no te dice que algo se haya hecho.",
}


def knowledge_prompt(docs: list, lang: str = "fr") -> str:
    if not docs:
        return ""
    intro = KNOWLEDGE_INTRO.get((lang or "").lower()[:2], KNOWLEDGE_INTRO["en"])
    return intro + "\n" + "\n---\n".join(d.content for d in docs)


async def status(db, models, host: str, ia_cfg: dict) -> dict:
    """What the admin sees: is the meaning search working, with which model, and what to re-index."""
    model = current_model()
    vector = await embed("test", host, force=True) if (host or model == ia_builtin_embed.NAME) else None
    docs = db.query(models.KnowledgeBase).all()
    if vector:
        indexed = sum(1 for d in docs if _comparable(d, model, len(vector)))
    else:
        # Without an answer from the model, only entries known to come from it count
        indexed = sum(1 for d in docs if d.embedding_json and d.embed_model == model)
    return {
        "rag_enabled": bool(ia_cfg.get("rag_enabled", True)),
        "semantic": "ok" if vector else "unavailable",
        "model": model,
        "error": None if vector else (ia_utils.LAST_EMBED_ERROR or "no AI instance"),
        "builtin": model == ia_builtin_embed.NAME,
        "builtin_install": ia_builtin_embed.install_state(),
        "entries": len(docs),
        "indexed": indexed,
        "to_index": len(docs) - indexed,
    }


async def reindex_all(db, models, host: str) -> dict:
    """Re-compute every entry's embedding with the current model (after a model change)."""
    docs = db.query(models.KnowledgeBase).all()
    done = 0
    for doc in docs:
        await index_entry(doc, host)
        if doc.embedding_json:
            done += 1
        elif done == 0:
            break  # the model does not answer: no use trying every entry
    db.commit()
    return {"indexed": done, "total": len(docs)}
