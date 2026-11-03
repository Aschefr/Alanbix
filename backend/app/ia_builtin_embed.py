"""Built-in embedding model: knowledge base search by meaning without any AI server.

A small multilingual model (paraphrase-multilingual-MiniLM-L12-v2, Apache 2.0, quantized ONNX) run on the
CPU by ONNX Runtime. The libraries are in the image; the model (135 MB) is downloaded on demand by the
admin into the data folder, so it stays through updates and works offline afterwards. It is loaded at
the first search only.
"""
import asyncio
import hashlib
import os
import threading

import httpx

MODEL_ID = "paraphrase-multilingual-MiniLM-L12-v2"
NAME = f"builtin:{MODEL_ID}"
# This model's own threshold (a similarity score only means something for one model). Measured on real
# entries: right ones scored 0.37-0.67, unrelated ones mostly under 0.33. Better one entry too many, which
# the assistant is told to ignore, than the entry that held the answer.
MIN_SCORE = 0.35
MAX_TOKENS = 256

_REPO = "https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/2c4055b12046f11709e9df2c122e59ffbdc2f900"
FILES = {
    "model_quantized.onnx": (f"{_REPO}/onnx/model_quantized.onnx", 118308126, "66fc00f5f29afcaff34092e1bdd20008ca3918265a82fb9695a551e510cc4ebc"),
    "tokenizer.json": (f"{_REPO}/tokenizer.json", 17082913, "b60b6b43406a48bf3638526314f3d232d97058bc93472ff2de930d43686fa441"),
}
TOTAL_BYTES = sum(size for _, size, _ in FILES.values())

_install = {"downloading": False, "downloaded": 0, "error": None}
_runtime = {"session": None, "tokenizer": None}
_lock = threading.Lock()


def model_dir() -> str:
    data_dir = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
    return os.path.join(data_dir, "models", MODEL_ID)


def is_installed() -> bool:
    return all(
        os.path.isfile(os.path.join(model_dir(), name)) and os.path.getsize(os.path.join(model_dir(), name)) == size
        for name, (_, size, _) in FILES.items()
    )


def install_state() -> dict:
    return {
        "installed": is_installed(),
        "downloading": _install["downloading"],
        "downloaded": _install["downloaded"],
        "total": TOTAL_BYTES,
        "error": _install["error"],
    }


async def _download(client, url: str, path: str, sha256: str):
    digest = hashlib.sha256()
    tmp = path + ".part"
    try:
        async with client.stream("GET", url) as res:
            if res.status_code != 200:
                raise RuntimeError(f"HTTP {res.status_code}")
            with open(tmp, "wb") as f:
                async for chunk in res.aiter_bytes(1024 * 1024):
                    f.write(chunk)
                    digest.update(chunk)
                    _install["downloaded"] += len(chunk)
        if digest.hexdigest() != sha256:
            raise RuntimeError("checksum mismatch")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


async def install() -> bool:
    """Download the model (once, verified). Progress and errors are read through install_state()."""
    if _install["downloading"] or is_installed():
        return is_installed()
    _install.update(downloading=True, downloaded=0, error=None)
    try:
        os.makedirs(model_dir(), exist_ok=True)
        timeout = httpx.Timeout(connect=20.0, read=120.0, write=20.0, pool=20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for name, (url, size, sha256) in FILES.items():
                path = os.path.join(model_dir(), name)
                if os.path.isfile(path) and os.path.getsize(path) == size:
                    _install["downloaded"] += size
                    continue
                await _download(client, url, path, sha256)
        return True
    except Exception as e:
        _install["error"] = str(e) or type(e).__name__
        print(f"[Built-in embedding] Download failed: {_install['error']}", flush=True)
        return False
    finally:
        _install["downloading"] = False


def _load():
    with _lock:
        if _runtime["session"] is None:
            # Imported here: no memory used until the first search by meaning
            import onnxruntime as ort
            from tokenizers import Tokenizer
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2  # leave the CPU to the game server next to it
            options.inter_op_num_threads = 1
            tokenizer = Tokenizer.from_file(os.path.join(model_dir(), "tokenizer.json"))
            tokenizer.enable_truncation(MAX_TOKENS)
            _runtime["session"] = ort.InferenceSession(
                os.path.join(model_dir(), "model_quantized.onnx"), options, providers=["CPUExecutionProvider"]
            )
            _runtime["tokenizer"] = tokenizer
    return _runtime["session"], _runtime["tokenizer"]


def _embed_sync(text: str) -> list:
    import numpy as np
    session, tokenizer = _load()
    encoded = tokenizer.encode(text)
    ids = np.array([encoded.ids], dtype=np.int64)
    mask = np.array([encoded.attention_mask], dtype=np.int64)
    feed = {"input_ids": ids, "attention_mask": mask}
    if any(i.name == "token_type_ids" for i in session.get_inputs()):
        feed["token_type_ids"] = np.zeros_like(ids)
    hidden = session.run(None, feed)[0]
    # Mean of the token vectors (without padding), then unit length: what the model was trained with
    weights = mask[..., None]
    vector = (hidden * weights).sum(axis=1)[0] / weights.sum()
    norm = np.linalg.norm(vector)
    return (vector / norm if norm else vector).tolist()


async def embed(text: str) -> list:
    if not is_installed():
        raise RuntimeError("built-in model not installed")
    return await asyncio.to_thread(_embed_sync, text)
