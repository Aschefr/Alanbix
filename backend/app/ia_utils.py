import os
import json
import httpx
import numpy as np

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
DEFAULT_EMBED_MODEL = "nomic-embed-text"

# Chunking config
CHUNK_SIZE = 2000       # ~500 tokens per chunk
CHUNK_OVERLAP = 200     # overlap between consecutive chunks for context continuity
CHUNK_THRESHOLD = 3000  # texts shorter than this are embedded as-is (no chunking)

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


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for embedding.
    
    Tries to split on paragraph/sentence boundaries when possible.
    Returns a list of text chunks.
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        
        if end < len(text):
            # Try to break at a paragraph boundary first
            para_break = text.rfind('\n\n', start + chunk_size // 2, end)
            if para_break > start:
                end = para_break + 2  # include the double newline
            else:
                # Try sentence boundary (. ! ? followed by space/newline)
                best_break = -1
                for sep in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
                    pos = text.rfind(sep, start + chunk_size // 2, end)
                    if pos > best_break:
                        best_break = pos
                if best_break > start:
                    end = best_break + 2
                else:
                    # Try word boundary
                    space = text.rfind(' ', start + chunk_size // 2, end)
                    if space > start:
                        end = space + 1
        else:
            end = len(text)
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Next chunk starts with overlap
        start = max(start + 1, end - overlap)
    
    return chunks


def is_openai_host(url: str) -> bool:
    clean = url.rstrip("/")
    return clean.endswith("/v1") or "/v1/" in clean or "openai" in clean.lower()

async def get_embedding(text: str, ollama_host: str = None, timeout: float = 60.0):
    """Get embedding vector from Ollama or OpenAI for a single text."""
    host = ollama_host or OLLAMA_HOST
    embed_model = _get_embed_model()
    try:
        is_openai = is_openai_host(host)
        if is_openai:
            url = f"{host.rstrip('/')}/embeddings"
            payload = {
                "model": embed_model,
                "input": text
            }
        else:
            url = f"{host.rstrip('/')}/api/embeddings"
            payload = {
                "model": embed_model,
                "prompt": text
            }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                timeout=timeout
            )
            data = response.json()
            if is_openai:
                return data["data"][0]["embedding"]
            return data["embedding"]
    except Exception as e:
        print(f"Embedding error: {e}")
        return None


async def get_embedding_chunked(text: str, ollama_host: str = None) -> tuple[list | None, int]:
    """Get embedding for a text, chunking if necessary.
    
    For short texts (< CHUNK_THRESHOLD), embeds directly.
    For long texts, splits into chunks, embeds each, and averages the vectors.
    
    Returns:
        (embedding_vector, num_chunks) — embedding is None on failure.
    """
    if not text or not text.strip():
        return None, 0
    
    text = text.strip()
    
    # Short text: embed directly
    if len(text) < CHUNK_THRESHOLD:
        emb = await get_embedding(text, ollama_host=ollama_host)
        return emb, 1
    
    # Long text: chunk and average
    chunks = chunk_text(text)
    if not chunks:
        return None, 0
    
    print(f"RAG chunking: {len(text)} chars → {len(chunks)} chunks")
    
    embeddings = []
    for i, chunk in enumerate(chunks):
        emb = await get_embedding(chunk, ollama_host=ollama_host, timeout=120.0)
        if emb:
            embeddings.append(emb)
        else:
            print(f"  Chunk {i+1}/{len(chunks)} failed to embed ({len(chunk)} chars)")
    
    if not embeddings:
        return None, len(chunks)
    
    # Average all chunk embeddings (normalized)
    avg = np.mean(np.array(embeddings, dtype=np.float32), axis=0)
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg = avg / norm  # L2 normalize the averaged vector
    
    return avg.tolist(), len(chunks)


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
