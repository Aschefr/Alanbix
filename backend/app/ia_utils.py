import os
import json
import httpx
import numpy as np

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
DEFAULT_EMBED_MODEL = "nomic-embed-text"

def _get_embed_model():
    """Read embedding model from SystemConfig, fallback to default."""
    try:
        from .database import SessionLocal
        from . import models as m
        db = SessionLocal()
        try:
            cfg = db.query(m.SystemConfig).filter(m.SystemConfig.key == "ia_settings").first()
            if cfg and cfg.value:
                return cfg.value.get("embedding_model") or DEFAULT_EMBED_MODEL
        finally:
            db.close()
    except Exception:
        pass
    return DEFAULT_EMBED_MODEL

async def get_embedding(text: str, ollama_host: str = None):
    """Get embedding vector from Ollama."""
    host = ollama_host or OLLAMA_HOST
    embed_model = _get_embed_model()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{host}/api/embeddings",
                json={
                    "model": embed_model,
                    "prompt": text
                },
                timeout=30.0
            )
            return response.json()["embedding"]
    except Exception as e:
        print(f"Embedding error: {e}")
        return None


def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def search_similar(query_embedding, documents, top_k=3):
    """
    Search most similar documents using cosine similarity.
    
    Args:
        query_embedding: list of floats (query vector)
        documents: list of dicts with keys 'id', 'content', 'embedding_json', 'metadata_json'
        top_k: number of results to return
    
    Returns:
        list of (doc, score) tuples sorted by similarity descending
    """
    if not query_embedding or not documents:
        return []
    
    scored = []
    for doc in documents:
        if not doc.embedding_json:
            continue
        try:
            doc_embedding = json.loads(doc.embedding_json)
            score = cosine_similarity(query_embedding, doc_embedding)
            scored.append((doc, score))
        except (json.JSONDecodeError, ValueError):
            continue
    
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
