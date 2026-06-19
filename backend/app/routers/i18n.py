import os
import json
import httpx
import asyncio
import time
from fastapi import APIRouter, HTTPException, Body, Depends, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .. import models, database, auth
from .ia import get_effective_config, get_instances, _check_instance_health, pick_instance

router = APIRouter(prefix="/api/i18n", tags=["i18n"])

# Track which instance URLs are actively used by bulk translation
bulk_translate_active_urls: set = set()

# Reference files shipped with the app (read-only in standalone/Docker)
STATIC_I18N_DIR = "static/i18n"
# User-editable files persisted in the data volume
DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
DATA_I18N_DIR = os.path.join(DATA_DIR, "i18n")
os.makedirs(DATA_I18N_DIR, exist_ok=True)

RESERVED_LANGS = {"bulk-translate", "auto-translate"}

def _sanitize_lang(lang: str) -> str:
    cleaned = lang.replace("/", "").replace("\\", "").replace(".", "")
    if cleaned in RESERVED_LANGS:
        raise HTTPException(status_code=400, detail="Invalid language code")
    return cleaned

def get_i18n_path(lang: str) -> str:
    """Return the best path for reading a language file.
    Priority: data/i18n/ (user edits) > static/i18n/ (shipped defaults).
    """
    lang = _sanitize_lang(lang)
    data_path = os.path.join(DATA_I18N_DIR, f"{lang}.json")
    if os.path.exists(data_path):
        return data_path
    static_path = os.path.join(STATIC_I18N_DIR, f"{lang}.json")
    if os.path.exists(static_path):
        return static_path
    return data_path  # will be used for creation

def get_i18n_write_path(lang: str) -> str:
    """Return path where user edits should be written (always in data volume)."""
    lang = _sanitize_lang(lang)
    return os.path.join(DATA_I18N_DIR, f"{lang}.json")

def load_i18n_merged(lang: str) -> dict:
    """Load a language file with merge logic.
    For all languages: data/i18n/ overrides static/i18n/ key-by-key.
    New keys from static/ (app updates) are added automatically.
    """
    lang = _sanitize_lang(lang)
    static_path = os.path.join(STATIC_I18N_DIR, f"{lang}.json")
    data_path = os.path.join(DATA_I18N_DIR, f"{lang}.json")

    if not os.path.exists(static_path) and not os.path.exists(data_path):
        return None

    static_data = {}
    if os.path.exists(static_path):
        try:
            with open(static_path, "r", encoding="utf-8-sig") as f:
                static_data = json.load(f)
        except Exception:
            pass

    data_data = {}
    if os.path.exists(data_path):
        try:
            with open(data_path, "r", encoding="utf-8-sig") as f:
                data_data = json.load(f)
        except Exception:
            pass

    # Merge: start with static defaults, overlay user edits
    merged = {**static_data, **data_data}
    return merged

def list_all_languages() -> list:
    """List language codes from both static and data directories."""
    codes = set()
    for d in [STATIC_I18N_DIR, DATA_I18N_DIR]:
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.endswith(".json") and not f.endswith(".bak"):
                    code = f.split(".")[0]
                    if code not in RESERVED_LANGS:
                        codes.add(code)
    return sorted(codes)

class AutoTranslateRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str

@router.post("/auto-translate")
async def auto_translate(
    req: AutoTranslateRequest,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    if not req.text.strip():
        return {"translated_text": ""}
        
    try:
        ia_cfg = get_effective_config(db)
        model = ia_cfg.get('model', 'llama3')
        instance = await pick_instance(db, model=model)
        ollama_host = instance["url"] if instance else ia_cfg.get('ollama_host', 'http://localhost:11434')
        if instance and instance.get("model"):
            model = instance["model"]
            
        translation_prompt = (
            f"Translate the following text from language code '{req.source_lang}' to '{req.target_lang}'.\n"
            "CRITICAL RULES:\n"
            "1. KEEP ALL placeholders inside braces exactly as they are without translating them (e.g. {waiting}, {position}, {user}, {team_name}). Do not change spelling, spacing, or formatting of variables.\n"
            "2. Respond with ONLY the translated text. Do not include markdown formatting, backticks, quotes, introductory or explanatory text. Just the raw translation.\n\n"
            f"Text to translate:\n{req.text}"
        )
        
        print(f"[DEBUG] Enqueueing translation task for text: {req.text[:50]}")
        import time
        from ..ia_queue import queue_manager, QueueEntry
        entry = QueueEntry(
            priority=0, # Admin priority
            created_at=time.time(),
            user_id=admin.id,
            username=admin.username,
            task_type="translate",
            payload={
                "ollama_host": ollama_host,
                "model": model,
                "prompt": translation_prompt
            }
        )
        entry, _ = await queue_manager.enqueue(entry)
        
        print(f"[DEBUG] Task enqueued. Waiting for done_event...")
        while not entry.done_event.is_set():
            await asyncio.sleep(0.1)
            
        print(f"[DEBUG] done_event set. Reading result stream...")
        result = None
        while not entry.result_stream.empty():
            res_item = entry.result_stream.get_nowait()
            print(f"[DEBUG] Result stream item: {res_item}")
            if isinstance(res_item, dict):
                # Accept both "result" and "text" as translation output keys
                if "result" in res_item or "text" in res_item:
                    result = res_item
                
        if not result or result.get("error"):
            error_detail = "No response from queue"
            if result:
                error_detail = result.get("result") or result.get("text") or "Unknown error"
            print(f"[DEBUG] Translation task failed: {error_detail}")
            raise HTTPException(500, f"AI Translation failed: {error_detail}")
            
        raw = (result.get("result") or result.get("text", "")).strip()
        print(f"[DEBUG] Translation success! Raw response: {raw[:50]}")
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1].strip()
        elif raw.startswith("'") and raw.endswith("'"):
            raw = raw[1:-1].strip()
            
        return {"translated_text": raw}
    except Exception as e:
        import traceback
        traceback.print_exc()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(500, f"AI Translation failed: {str(e)}")

# ---------------------------------------------------------------------------
# Bulk-translate: parallel across all available instances via SSE
# ---------------------------------------------------------------------------
class BulkTranslateRequest(BaseModel):
    keys: List[str]
    source_lang: str
    target_lang: str
    source_data: Dict[str, str]  # key -> source text


@router.post("/bulk-translate")
async def bulk_translate(
    req: BulkTranslateRequest,
    request: Request,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(auth.get_current_admin)
):
    """Translate keys in parallel across all available AI instances.
    Returns SSE stream with each translated key as a JSON event.
    """
    ia_cfg = get_effective_config(db)
    default_model = ia_cfg.get('model', 'llama3')

    # Discover healthy instances
    instances = [i for i in get_instances(db) if i.get("enabled", True)]
    healthy = []
    for inst in instances:
        ok, _, _ = await _check_instance_health(inst["url"], timeout=2.0)
        if ok:
            healthy.append(inst)
    if not healthy:
        raise HTTPException(503, "No AI instances available")

    # Build async queue of keys to translate
    key_queue: asyncio.Queue = asyncio.Queue()
    for key in req.keys:
        source_text = req.source_data.get(key, "")
        if source_text and source_text.strip():
            await key_queue.put(key)

    total = key_queue.qsize()
    if total == 0:
        raise HTTPException(400, "No translatable keys provided")

    # Shared result queue for SSE output
    result_queue: asyncio.Queue = asyncio.Queue()
    active_workers = len(healthy)
    workers_done = asyncio.Event()

    async def translate_worker(inst: dict, worker_id: int):
        """Worker: consume keys from queue, translate via assigned instance."""
        nonlocal active_workers
        url = inst["url"]
        model = inst.get("model") or default_model
        label = inst.get("label", url)
        consecutive_errors = 0

        while not key_queue.empty():
            try:
                key = key_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            source_text = req.source_data.get(key, "")
            prompt = (
                f"Translate the following text from language code '{req.source_lang}' to '{req.target_lang}'.\n"
                "CRITICAL RULES:\n"
                "1. KEEP ALL placeholders inside braces exactly as they are without translating them "
                "(e.g. {waiting}, {position}, {user}, {team_name}). Do not change spelling, spacing, or formatting of variables.\n"
                "2. Respond with ONLY the translated text. Do not include markdown formatting, backticks, "
                "quotes, introductory or explanatory text. Just the raw translation.\n\n"
                f"Text to translate:\n{source_text}"
            )

            try:
                bulk_translate_active_urls.add(url)
                async with httpx.AsyncClient() as client:
                    res = await client.post(f"{url}/api/chat", json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {"temperature": 0.1}
                    }, timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0))

                if res.status_code != 200:
                    raise Exception(f"HTTP {res.status_code}")

                raw = res.json().get("message", {}).get("content", "").strip()
                # Clean up common AI artifacts
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                if raw.startswith('"') and raw.endswith('"'):
                    raw = raw[1:-1].strip()
                elif raw.startswith("'") and raw.endswith("'"):
                    raw = raw[1:-1].strip()

                await result_queue.put({"type": "result", "key": key, "translation": raw, "instance": label})
                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                print(f"[BulkTranslate] Worker {worker_id} ({label}) error on key '{key}': {e}")
                await result_queue.put({"type": "error", "key": key, "error": str(e), "instance": label})

                # If 3 consecutive errors, instance is likely down — stop worker
                if consecutive_errors >= 3:
                    print(f"[BulkTranslate] Worker {worker_id} ({label}) removed after 3 consecutive errors")
                    await result_queue.put({"type": "instance_lost", "instance": label})
                    break

        active_workers -= 1
        if active_workers <= 0:
            workers_done.set()
        bulk_translate_active_urls.discard(url)

    async def sse_generator():
        """Generate SSE events from results."""
        # Start header event with instance count
        yield f"data: {json.dumps({'type': 'start', 'total': total, 'instances': len(healthy), 'instance_labels': [i.get('label', i['url']) for i in healthy]})}\n\n"

        # Launch all workers
        tasks = []
        for i, inst in enumerate(healthy):
            tasks.append(asyncio.create_task(translate_worker(inst, i)))

        completed = 0
        while not workers_done.is_set() or not result_queue.empty():
            # Check client disconnect
            if await request.is_disconnected():
                # Cancel all workers
                for t in tasks:
                    t.cancel()
                yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                return

            try:
                item = await asyncio.wait_for(result_queue.get(), timeout=0.5)
                completed += 1
                item["progress"] = completed
                item["total"] = total
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive
                yield f": keepalive\n\n"
                continue

        # Drain any remaining
        while not result_queue.empty():
            item = result_queue.get_nowait()
            completed += 1
            item["progress"] = completed
            item["total"] = total
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'completed': completed, 'total': total})}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@router.get("/{lang}")
def get_language(lang: str):
    lang = _sanitize_lang(lang)
    data = load_i18n_merged(lang)
    if data is None:
        raise HTTPException(status_code=404, detail="Language not found")
    return data

@router.post("/{lang}")
def create_language(lang: str, admin: models.User = Depends(auth.get_current_admin)):
    lang = _sanitize_lang(lang)
    data_path = get_i18n_write_path(lang)
    static_path = os.path.join(STATIC_I18N_DIR, f"{lang}.json")
    if os.path.exists(data_path) or os.path.exists(static_path):
        raise HTTPException(status_code=400, detail="Language already exists")
    
    try:
        os.makedirs(DATA_I18N_DIR, exist_ok=True)
        with open(data_path, "w", encoding="utf-8-sig") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
        return {"message": f"Language {lang} created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{lang}")
def update_language(lang: str, translations: Dict[str, str] = Body(...), admin: models.User = Depends(auth.get_current_admin)):
    lang = _sanitize_lang(lang)
    # Verify the language exists somewhere
    data = load_i18n_merged(lang)
    if data is None:
        raise HTTPException(status_code=404, detail="Language not found")
    
    try:
        write_path = get_i18n_write_path(lang)
        os.makedirs(DATA_I18N_DIR, exist_ok=True)
        with open(write_path, "w", encoding="utf-8-sig") as f:
            json.dump(translations, f, indent=4, ensure_ascii=False)
        return {"message": "Translations updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{lang}")
def delete_language(lang: str, admin: models.User = Depends(auth.get_current_admin)):
    if lang in ["fr", "en"]:
        raise HTTPException(status_code=400, detail="Cannot delete default languages")
    
    lang = _sanitize_lang(lang)
    data_path = get_i18n_write_path(lang)
    static_path = os.path.join(STATIC_I18N_DIR, f"{lang}.json")
    
    if not os.path.exists(data_path) and not os.path.exists(static_path):
        raise HTTPException(status_code=404, detail="Language not found")
    
    try:
        if os.path.exists(data_path):
            os.remove(data_path)
        # Note: don't delete static files (shipped with app)
        return {"message": f"Language {lang} deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{lang}/sync")
def sync_language(lang: str, admin: models.User = Depends(auth.get_current_admin)):
    """Detect missing keys in a language file compared to the reference (fr.json).
    Returns the list of missing keys and adds them with empty values.
    """
    lang = _sanitize_lang(lang)
    ref_data = load_i18n_merged("fr")
    target_data = load_i18n_merged(lang)
    
    if not ref_data:
        raise HTTPException(status_code=404, detail="Reference language (fr) not found")
    if target_data is None:
        raise HTTPException(status_code=404, detail=f"Language {lang} not found")
    
    missing_keys = [k for k in ref_data if k not in target_data]
    
    if missing_keys:
        for k in missing_keys:
            target_data[k] = ""
        # Write the updated file
        write_path = get_i18n_write_path(lang)
        os.makedirs(DATA_I18N_DIR, exist_ok=True)
        with open(write_path, "w", encoding="utf-8-sig") as f:
            json.dump(target_data, f, indent=4, ensure_ascii=False)
    
    return {
        "missing_count": len(missing_keys),
        "missing_keys": missing_keys,
        "total_keys": len(ref_data)
    }
