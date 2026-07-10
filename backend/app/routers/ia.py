import os
import json
import httpx
import asyncio
import uuid
import shutil
import base64
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..websockets import manager as ws_manager
from .. import models, schemas, auth, database
from ..ia_utils import get_embedding, get_embedding_chunked, search_similar
from starlette.requests import Request as StarletteRequest
from ..ia_compression import run_truncation, run_compaction, run_summary
from ..ia_title_utils import _is_default_title, _build_title_prompt, _clean_title

router = APIRouter(prefix="/ia", tags=["IA"])

# --- Multi-instance Ollama support ---

_round_robin_idx = 0
_active_requests = {}  # url -> int (active generation count)

def get_effective_config(db: Session):
    db_config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "ia_settings").first()
    if db_config:
        # Assurer la compatibilité rétroactive des anciens réglages en BDD
        val = db_config.value
        if "network_tools_enabled" not in val:
            val["network_tools_enabled"] = True
        if "auto_moderation_enabled" not in val:
            val["auto_moderation_enabled"] = True
        if "tool_calling_mode" not in val:
            val["tool_calling_mode"] = "stream_intercept"
        return val
    return {
        "ollama_host": os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"),
        "model": "",
        "rag_enabled": True,
        "network_tools_enabled": True,
        "auto_moderation_enabled": True,
        "tool_calling_mode": "stream_intercept"
    }

def get_instances(db: Session):
    """Extract instance list from config. Returns [] if no instances configured."""
    cfg = get_effective_config(db)
    instances = cfg.get("ollama_instances")
    if instances and len(instances) > 0:
        return instances
    # Legacy single-host fallback (only if ollama_host is explicitly set)
    host = cfg.get("ollama_host", os.getenv("OLLAMA_HOST", ""))
    model = cfg.get("model", "")
    if host and model:
        return [{"url": host, "label": "Default", "model": model, "enabled": True, "priority": 0}]
    return []

def is_openai_host(url: str) -> bool:
    clean = url.rstrip("/")
    return clean.endswith("/v1") or "/v1/" in clean or "openai" in clean.lower()

_health_cache = {}  # url -> (timestamp, ok, latency, models)

async def _check_instance_health(url: str, timeout: float = 3.0):
    """Ping an Ollama or OpenAI instance, return (ok, latency_ms, models). Uses cache to prevent high latency."""
    import time
    now = time.time()
    if url in _health_cache:
        cached_time, ok, latency, models = _health_cache[url]
        if now - cached_time < 10.0:
            return ok, latency, models

    clean_url = url.rstrip("/")
    is_openai = is_openai_host(clean_url)

    try:
        async with httpx.AsyncClient() as client:
            t0 = time.time()
            if is_openai:
                res = await client.get(f"{clean_url}/models", timeout=timeout)
                latency = round((time.time() - t0) * 1000)
                if res.status_code == 200:
                    data = res.json()
                    model_names = [m.get("id", "?") for m in data.get("data", [])]
                    _health_cache[url] = (now, True, latency, model_names)
                    return True, latency, model_names
            else:
                try:
                    res = await client.get(f"{clean_url}/api/tags", timeout=timeout)
                    latency = round((time.time() - t0) * 1000)
                    if res.status_code == 200:
                        data = res.json()
                        model_names = [m.get("name", "?") for m in data.get("models", [])]
                        _health_cache[url] = (now, True, latency, model_names)
                        return True, latency, model_names
                except Exception:
                    # Fallback check if it was configured as Ollama but is actually OpenAI
                    res = await client.get(f"{clean_url}/v1/models", timeout=timeout)
                    latency = round((time.time() - t0) * 1000)
                    if res.status_code == 200:
                        data = res.json()
                        model_names = [m.get("id", "?") for m in data.get("data", [])]
                        _health_cache[url] = (now, True, latency, model_names)
                        return True, latency, model_names
    except Exception:
        pass
    _health_cache[url] = (now, False, 0, [])
    return False, 0, []


async def pick_instance(db: Session, model: str = None):
    """Round-robin among enabled instances. Silent failover on unhealthy ones.
    If model is specified, prefer instances with matching model affinity."""
    global _round_robin_idx
    instances = [i for i in get_instances(db) if i.get("enabled", True)]
    if not instances:
        return None
    
    # Sort by priority (lower = higher priority), stable sort preserves order for equal priorities
    instances.sort(key=lambda i: i.get("priority", 10))
    
    # If model specified, prefer instances with that model affinity
    if model:
        affinity = [i for i in instances if i.get("model") == model]
        if affinity:
            instances = affinity
    
    n = len(instances)
    for attempt in range(n):
        idx = (_round_robin_idx + attempt) % n
        inst = instances[idx]
        ok, _, _ = await _check_instance_health(inst["url"], timeout=2.0)
        if ok:
            _round_robin_idx = (idx + 1) % n
            return inst
    # All down — return first anyway, let the caller handle the error
    return instances[0]

@router.get("/models")
async def list_models(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Merge models from all enabled instances (deduplicated)."""
    instances = [i for i in get_instances(db) if i.get("enabled", True)]
    seen = set()
    all_models = []
    for inst in instances:
        url = inst["url"].rstrip("/")
        is_openai = is_openai_host(url)
        try:
            async with httpx.AsyncClient() as client:
                if is_openai:
                    res = await client.get(f"{url}/models", timeout=5.0)
                    if res.status_code == 200:
                        for m in res.json().get("data", []):
                            name = m.get("id")
                            if name and name not in seen:
                                seen.add(name)
                                all_models.append({
                                    "name": name,
                                    "details": {"family": "openai", "parameter_size": "unknown"}
                                })
                else:
                    try:
                        res = await client.get(f"{url}/api/tags", timeout=5.0)
                        if res.status_code == 200:
                            for m in res.json().get("models", []):
                                if m["name"] not in seen:
                                    seen.add(m["name"])
                                    all_models.append(m)
                    except Exception:
                        # Fallback to OpenAI endpoint on Ollama host
                        res = await client.get(f"{url}/v1/models", timeout=5.0)
                        if res.status_code == 200:
                            for m in res.json().get("data", []):
                                name = m.get("id")
                                if name and name not in seen:
                                    seen.add(name)
                                    all_models.append({
                                        "name": name,
                                        "details": {"family": "openai", "parameter_size": "unknown"}
                                    })
        except Exception:
            pass
    return {"models": all_models}

@router.post("/test-connection")
async def test_connection(config: dict, admin: models.User = Depends(auth.get_current_admin)):
    url = config.get("url") or config.get("ollama_host", "")
    ok, latency, model_names = await _check_instance_health(url, timeout=5.0)
    if ok:
        return {"status": "ok", "latency_ms": latency, "models": model_names}
    return {"status": "error", "detail": "Connection failed"}

@router.get("/instances/status")
async def instances_status(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Return health status of all configured instances."""
    from ..ia_queue import queue_manager
    from .i18n import bulk_translate_active_urls
    instances = get_instances(db)
    # Build a set of URLs currently being used by active queue entries
    active_urls = set()
    for entry in queue_manager._active.values():
        host = entry.payload.get("ollama_host", "")
        if host:
            active_urls.add(host.rstrip("/"))
    # Also include URLs busy with bulk i18n translation
    for url in bulk_translate_active_urls:
        active_urls.add(url.rstrip("/"))
    results = []
    for inst in instances:
        inst_url = inst["url"].rstrip("/")
        ok, latency, model_names = await _check_instance_health(inst["url"])
        is_busy = inst_url in active_urls
        avg_dur = queue_manager._instance_avg_durations.get(inst["url"], None)
        if avg_dur is None:
            avg_dur = queue_manager._instance_avg_durations.get(inst_url, None)
        results.append({
            "url": inst["url"],
            "label": inst.get("label", ""),
            "model": inst.get("model", ""),
            "enabled": inst.get("enabled", True),
            "online": ok,
            "latency_ms": latency,
            "available_models": model_names,
            "busy": is_busy,
            "active_requests": 1 if is_busy else 0,
            "avg_duration": round(avg_dur, 1) if avg_dur is not None else None
        })
    return results

@router.get("/config")
def get_ia_config(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    cfg = get_effective_config(db)
    # Include system_prompt from SystemConfig
    sp = db.query(models.SystemConfig).filter(models.SystemConfig.key == "system_prompt").first()
    cfg["system_prompt"] = sp.value if sp else ""
    return cfg

@router.post("/config")
async def update_ia_config(config_data: dict, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == "ia_settings").first()
    if not config:
        config = models.SystemConfig(key="ia_settings", value=config_data)
        db.add(config)
    else:
        config.value = config_data
    db.commit()

    # Hot-restart queue workers to match new instance count (G-52)
    instances = config_data.get("ollama_instances", [])
    enabled_count = max(1, sum(1 for inst in instances if inst.get("enabled", True)))
    from ..ia_queue import queue_manager
    asyncio.create_task(queue_manager.restart_workers(enabled_count))

    await ws_manager.broadcast({"type": "ia_config_updated"})
    return {"status": "updated"}

def get_active_system_prompt(db: Session) -> str:
    lang_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    lang = lang_cfg.value if lang_cfg else "fr"
    
    try:
        from .i18n import load_i18n_merged
        i18n_data = load_i18n_merged(lang)
        prompt = i18n_data.get("system_prompt", "")
        if prompt:
            return prompt
    except Exception as e:
        print(f"[ERROR] Failed to read system_prompt for lang {lang}: {e}")
        
    sp_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == f"system_prompt_{lang}").first()
    if sp_cfg and sp_cfg.value:
        return sp_cfg.value
        
    if lang == "fr":
        legacy = db.query(models.SystemConfig).filter(models.SystemConfig.key == "system_prompt").first()
        if legacy and legacy.value:
            return legacy.value
        
    if lang == "en":
        return "You are Alanbix, the AI assisting players during the ongoing video game tournament (commonly called 'LAN'). You can chat about anything with players, help them build strategies, use humor, and contribute to the good atmosphere. You can tease players.\nAnswer directly, without fluff or context-setting. If you don't know, say you don't know, don't invent. Answer all types of questions even outside the initial scope. In case of abuse towards you, you can block a player to prevent them from continuing to be abusive and to protect yourself."
    return "Tu es Alanbix, l'IA qui assiste les joueurs lors du tournois de jeux vidéo (communément appelé 'LAN') en cours. Tu peux parler de tout et de rien avec les joueurs, les aider à monter des stratégies, de faire preuve d'humour et de participer à la bonne ambiance. Tu peux taquiner les joueurs.\nRéponds directement, sans fioritures ni de mise en contexte. Si tu ne sais pas, dis que tu ne sais pas, n'invente pas. Réponds à tout type de question même hors du scope initiale. En cas d'abus envers toi, tu peut bloquer un joueur pour l'empêcher de continuer à être abusif et te protéger."

def get_active_closing_prompt(db: Session) -> str:
    lang_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == "lan_default_language").first()
    lang = lang_cfg.value if lang_cfg else "fr"
    
    try:
        from .i18n import load_i18n_merged
        i18n_data = load_i18n_merged(lang)
        prompt = i18n_data.get("tournament_closing_prompt", "")
        if prompt:
            return prompt
    except Exception as e:
        print(f"[ERROR] Failed to read tournament_closing_prompt for lang {lang}: {e}")
        
    cp_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == f"tournament_closing_prompt_{lang}").first()
    if cp_cfg and cp_cfg.value:
        return cp_cfg.value
        
    if lang == "fr":
        legacy = db.query(models.SystemConfig).filter(models.SystemConfig.key == "tournament_closing_prompt").first()
        if legacy and legacy.value:
            return legacy.value
            
    if lang == "en":
        return "You are an enthusiastic video game tournament (LAN) commentator. You can use sarcasm and gently tease players. Use humor as much as possible."
    return "Tu est un commentateur enthousiaste de tournois de jeux vidéo (LAN). Tu peut faire du sarcasme et gentiment taquiner les joueurs. Fait de l'humour autant que possible."

class TranslatePromptsRequest(BaseModel):
    source_lang: str
    target_lang: str

@router.post("/translate-prompts")
async def translate_prompts(req: TranslatePromptsRequest, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    src_sp = None
    sp_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == f"system_prompt_{req.source_lang}").first()
    if sp_cfg and sp_cfg.value:
        src_sp = sp_cfg.value
    elif req.source_lang == "fr":
        legacy = db.query(models.SystemConfig).filter(models.SystemConfig.key == "system_prompt").first()
        if legacy and legacy.value:
            src_sp = legacy.value
            
    if not src_sp:
        try:
            from .i18n import load_i18n_merged
            src_sp = load_i18n_merged(req.source_lang).get("system_prompt", "")
        except:
            pass
            
    if not src_sp:
        src_sp = "Tu es Alanbix, l'IA qui assiste les joueurs lors du tournois de jeux vidéo (communément appelé 'LAN') en cours. Tu peux parler de tout et de rien avec les joueurs, les aider à monter des stratégies, de faire preuve d'humour et de participer à la bonne ambiance. Tu peux taquiner les joueurs.\nRéponds directement, sans fioritures ni de mise en contexte. Si tu ne sais pas, dis que tu ne sais pas, n'invente pas. Réponds à tout type de question même hors du scope initiale. En cas d'abus envers toi, tu peut bloquer un joueur pour l'empêcher de continuer à être abusif et te protéger."

    src_cp = None
    cp_cfg = db.query(models.SystemConfig).filter(models.SystemConfig.key == f"tournament_closing_prompt_{req.source_lang}").first()
    if cp_cfg and cp_cfg.value:
        src_cp = cp_cfg.value
    elif req.source_lang == "fr":
        legacy = db.query(models.SystemConfig).filter(models.SystemConfig.key == "tournament_closing_prompt").first()
        if legacy and legacy.value:
            src_cp = legacy.value
            
    if not src_cp:
        src_cp = "Tu es le commentateur sportif surexcité d'une LAN party."

    ia_cfg = get_effective_config(db)
    model = ia_cfg.get('model', '')
    instance = await pick_instance(db, model=model)
    if not instance:
        raise HTTPException(503, "Aucune instance IA configurée par l'administrateur")
    ollama_host = instance["url"]
    if instance.get("model"):
        model = instance["model"]

    translation_prompt = (
        f"Translate the following two AI prompt texts into '{req.target_lang}' (language code).\n"
        "CRITICAL RULES:\n"
        "1. KEEP ALL placeholders inside braces exactly as they are without translating them (e.g. {context_summary}, {rag_context}, {history_str}, {prompt}). Do not change spelling, spacing or formatting of variables.\n"
        "2. Respond ONLY with a valid JSON object containing keys 'system_prompt' and 'closing_prompt'. Do not include markdown, backticks or explanations. Just JSON.\n\n"
        f"=== Text 1 (System Prompt) ===\n{src_sp}\n\n"
        f"=== Text 2 (Closing Prompt) ===\n{src_cp}\n"
    )

    try:
        async with httpx.AsyncClient() as client:
            is_openai = is_openai_host(ollama_host)
            if is_openai:
                url = f"{ollama_host.rstrip('/')}/chat/completions"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": translation_prompt}],
                    "stream": False,
                    "temperature": 0.2
                }
            else:
                url = f"{ollama_host.rstrip('/')}/api/chat"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": translation_prompt}],
                    "stream": False,
                    "options": {"temperature": 0.2}
                }

            res = await client.post(url, json=payload, timeout=45.0)
            
            if res.status_code != 200:
                raise HTTPException(500, f"AI service error (Status {res.status_code})")
                
            data = res.json()
            if is_openai:
                raw = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            else:
                raw = data.get("message", {}).get("content", "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            
            translated_data = json.loads(raw)
            trans_sp = translated_data.get("system_prompt", "").strip()
            trans_cp = translated_data.get("closing_prompt", "").strip()
            
            if not trans_sp or not trans_cp:
                raise ValueError("Translation returned empty fields.")
                
            target_sp_key = f"system_prompt_{req.target_lang}"
            target_cp_key = f"tournament_closing_prompt_{req.target_lang}"
            
            sp_cfg_target = db.query(models.SystemConfig).filter(models.SystemConfig.key == target_sp_key).first()
            if sp_cfg_target:
                sp_cfg_target.value = trans_sp
            else:
                db.add(models.SystemConfig(key=target_sp_key, value=trans_sp))
                
            cp_cfg_target = db.query(models.SystemConfig).filter(models.SystemConfig.key == target_cp_key).first()
            if cp_cfg_target:
                cp_cfg_target.value = trans_cp
            else:
                db.add(models.SystemConfig(key=target_cp_key, value=trans_cp))
                
            db.commit()
            await ws_manager.broadcast({"type": "ia_config_updated"})
            return {"status": "ok", "system_prompt": trans_sp, "closing_prompt": trans_cp}
            
    except Exception as e:
        raise HTTPException(500, f"AI Translation failed: {str(e)}")

@router.get("/conversations")
def list_conversations(db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    convs = db.query(models.Conversation).filter(models.Conversation.user_id == user.id).order_by(models.Conversation.created_at.desc()).all()
    results = []
    for c in convs:
        unread_count = db.query(models.ChatMessage).filter(
            models.ChatMessage.conversation_id == c.id,
            models.ChatMessage.id > (c.player_last_read_message_id or 0),
            models.ChatMessage.role.in_(["bot", "admin"])
        ).count()
        results.append({
            "id": c.id,
            "title": c.title,
            "user_id": c.user_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "model": c.model,
            "unread_count": unread_count,
            "has_new_messages": unread_count > 0
        })
    return results

@router.post("/conversations", response_model=schemas.Conversation)
def create_conversation(conv: schemas.ConversationBase, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    if user.ia_blocked:
        raise HTTPException(403, detail="Votre accès à l'IA a été suspendu par un administrateur.")
    db_conv = models.Conversation(title=conv.title, user_id=user.id)
    db.add(db_conv)
    db.commit()
    db.refresh(db_conv)
    return db_conv

CHAT_IMAGES_DIR = os.path.join(os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db")), "chat_images")
MAX_IMAGE_SIZE = 8 * 1024 * 1024  # 8 Mo
ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}

@router.post("/upload-image")
async def upload_image(conversation_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Upload an image for a chat message. Returns the relative path."""
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, detail="Type de fichier non supporté. JPEG, PNG, GIF, WebP uniquement.")
    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(400, detail="Image trop volumineuse (max 8 Mo).")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
        ext = "jpg"
    img_dir = os.path.join(CHAT_IMAGES_DIR, str(conversation_id))
    os.makedirs(img_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(img_dir, filename)
    with open(filepath, "wb") as f:
        f.write(data)
    rel_path = f"chat_images/{conversation_id}/{filename}"
    return {"image_path": rel_path}

@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id, models.Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404)
    # Clean up image files
    img_dir = os.path.join(CHAT_IMAGES_DIR, str(conv_id))
    if os.path.isdir(img_dir):
        shutil.rmtree(img_dir, ignore_errors=True)
    db.delete(conv)
    db.commit()
    return {"status": "ok"}

@router.get("/conversations/{conv_id}/messages")
def get_messages(conv_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id).first()
    messages = db.query(models.ChatMessage).filter(models.ChatMessage.conversation_id == conv_id).order_by(models.ChatMessage.timestamp.asc()).all()
    if messages:
        conv.player_last_read_message_id = messages[-1].id
        db.commit()
    
    # Estimate tokens — only count messages that Ollama will see (post-compression) + compressed context
    # Add overhead for system prompt + user identity + tool definitions (~1300 tokens)
    SYSTEM_OVERHEAD_TOKENS = 1300
    if conv.compressed_at:
        active_msgs = [m for m in messages if m.timestamp > conv.compressed_at]
    else:
        active_msgs = messages
    active_chars = sum(len(m.content) for m in active_msgs)
    ctx_chars = len(conv.compressed_context or "") if conv.compressed_context else 0
    est_tokens = int((active_chars + ctx_chars) / 3.5) + SYSTEM_OVERHEAD_TOKENS
    
    return {
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "image_path": m.image_path, "timestamp": m.timestamp.isoformat(), "meta": m.meta}
            for m in messages
        ],
        "usage": {"estimated_tokens": est_tokens},
        "admin_override": conv.admin_override or False,
        "compression": {
            "mode": conv.compression_mode,
            "auto_mode": conv.auto_compression_mode,
            "compressed_at": conv.compressed_at.isoformat() if conv.compressed_at else None,
            "context": conv.compressed_context
        }
    }

class CompressRequest(BaseModel):
    mode: str

@router.post("/compress/{conv_id}")
async def compress_context(conv_id: int, req: CompressRequest, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404)
        
    history = db.query(models.ChatMessage).filter(models.ChatMessage.conversation_id == conv_id).order_by(models.ChatMessage.timestamp.asc()).all()
    messages_to_process = [m for m in history if not conv.compressed_at or m.timestamp > conv.compressed_at]
    if not messages_to_process:
        return {"status": "ok"}
        
    ia_cfg = get_effective_config(db)
    model_to_use = conv.model or ia_cfg.get('model', '')
    instance = await pick_instance(db, model=model_to_use)
    if not instance:
        raise HTTPException(503, "Aucune instance IA configurée par l'administrateur")
    url = instance["url"]
    if not conv.model and instance.get("model"):
        model_to_use = instance["model"]
    model = model_to_use
    
    if req.mode == "truncate":
        dropped, kept = run_truncation(messages_to_process, max_tokens=4096)
        if dropped:
            dropped_lines = [f"- {'U' if m.role == 'user' else 'A'}: {m.content.strip().split(chr(10))[0][:120]}" for m in dropped]
            compressed = "[Tronqué]\n" + "\n".join(dropped_lines)
            conv.compressed_context = compressed
            conv.compressed_at = kept[0].timestamp if kept else datetime.utcnow()
            conv.compression_mode = "truncate"
            conv.auto_compression_mode = "truncate"
            db.commit()
        return {"status": "ok"}
        
    text_to_compress = ""
    if conv.compressed_context:
        text_to_compress += f"=== Contexte Précédent (compressé) ===\n{conv.compressed_context}\n\n"
    for m in messages_to_process:
        text_to_compress += f"{'Utilisateur' if m.role == 'user' else 'Assistant'} : {m.content}\n\n"
        
    cutoff_time = datetime.utcnow()
    
    # Route through AI queue for compact/summary (requires GPU)
    from ..ia_queue import queue_manager, QueueEntry
    entry = QueueEntry(
        priority=15,
        created_at=time.time(),
        user_id=user.id,
        username=user.username,
        conversation_id=conv_id,
        task_type="compress",
        payload={
            "ollama_host": url,
            "model": model,
            "mode": req.mode,
            "text": text_to_compress,
            "num_ctx": ia_cfg.get("context_window", 4096)
        }
    )
    entry, position = await queue_manager.enqueue(entry)
    
    # Wait for the worker to finish (with timeout)
    try:
        await asyncio.wait_for(entry.done_event.wait(), timeout=180.0)
    except asyncio.TimeoutError:
        await queue_manager.cancel(entry.id)
        raise HTTPException(504, "Timeout — la file d'attente IA est saturée. Réessayez plus tard.")
    
    # Read result
    result_data = await entry.result_stream.get()
    if result_data.get("error"):
        raise HTTPException(500, result_data.get("result", "Erreur de compression"))
    
    res = result_data.get("result", "")
    if not res or not res.strip():
        raise HTTPException(500, "L'IA n'a pas pu compresser le contexte (réponse vide). Réessayez ou choisissez un autre mode.")
        
    conv.compressed_context = res.strip()
    conv.compressed_at = cutoff_time
    conv.compression_mode = req.mode
    conv.auto_compression_mode = req.mode
    db.commit()
        
    return {"status": "ok"}

@router.delete("/compress/{conv_id}")
async def revert_compression(conv_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id).first()
    if conv:
        conv.compression_mode = None
        conv.auto_compression_mode = None
        conv.compressed_context = None
        conv.compressed_at = None
        db.commit()
    return {"status": "ok"}

@router.delete("/message/{msg_id}")
async def delete_message(msg_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    msg = db.query(models.ChatMessage).filter(models.ChatMessage.id == msg_id).first()
    if msg:
        db.delete(msg)
        db.commit()
    return {"status": "ok"}

class MessageEdit(BaseModel):
    content: str

@router.put("/message/{msg_id}")
async def edit_message(msg_id: int, body: MessageEdit, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    msg = db.query(models.ChatMessage).filter(models.ChatMessage.id == msg_id).first()
    if not msg:
        raise HTTPException(404, "Message not found")
    msg.content = body.content
    db.commit()
    return {"status": "ok"}

class CompressedContextEdit(BaseModel):
    context: str

@router.put("/compress/{conv_id}/edit")
async def edit_compressed_context(conv_id: int, body: CompressedContextEdit, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404)
    conv.compressed_context = body.context
    db.commit()
    return {"status": "ok"}

@router.post("/regenerate/{conv_id}")
async def regenerate_last(conv_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    last_assistant = db.query(models.ChatMessage).filter(models.ChatMessage.conversation_id == conv_id, models.ChatMessage.role == "bot").order_by(models.ChatMessage.timestamp.desc()).first()
    if last_assistant:
        db.delete(last_assistant)
        db.commit()
    last_user = db.query(models.ChatMessage).filter(models.ChatMessage.conversation_id == conv_id, models.ChatMessage.role == "user").order_by(models.ChatMessage.timestamp.desc()).first()
    if not last_user:
        raise HTTPException(404)
    return {"status": "ok", "last_user_content": last_user.content}

class RenameRequest(BaseModel):
    title: str

@router.patch("/conversations/{conv_id}/title")
def rename_conversation(conv_id: int, body: RenameRequest, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Manually rename a conversation."""
    conv = db.query(models.Conversation).filter(
        models.Conversation.id == conv_id,
        models.Conversation.user_id == user.id
    ).first()
    if not conv:
        raise HTTPException(404)
    title = body.title.strip()
    if not title or len(title) > 100:
        raise HTTPException(400, "Titre invalide (1–100 caractères)")
    conv.title = title
    db.commit()
    return {"status": "ok", "title": conv.title}

@router.post("/conversations/{conv_id}/suggest-title")
async def suggest_title(conv_id: int, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    """Fire-and-forget title suggestion via the IA queue. Returns immediately; result pushed via WebSocket."""
    conv = db.query(models.Conversation).filter(
        models.Conversation.id == conv_id,
        models.Conversation.user_id == user.id
    ).first()
    if not conv:
        raise HTTPException(404)

    msgs = db.query(models.ChatMessage).filter(
        models.ChatMessage.conversation_id == conv_id,
        models.ChatMessage.role.in_(["user", "bot"])
    ).order_by(models.ChatMessage.timestamp.asc()).limit(6).all()

    if not msgs:
        raise HTTPException(400, "Aucun message dans cette conversation")

    excerpt_parts = []
    for m in msgs:
        prefix = "User" if m.role == "user" else "Assistant"
        excerpt_parts.append(f"{prefix}: {m.content[:200]}")
    excerpt = "\n".join(excerpt_parts)

    cfg = get_effective_config(db)
    model = conv.model or cfg.get("model", "")
    instance = await pick_instance(db, model=model)
    if not instance:
        raise HTTPException(503, "Aucune instance IA configurée par l'administrateur")
    ollama_host = instance["url"]
    if instance.get("model"):
        model = instance["model"]

    from ..ia_queue import queue_manager, QueueEntry
    import time
    entry = QueueEntry(
        priority=5,           # between admin (0) and player (10) — doesn't block chat
        created_at=time.time(),
        user_id=0,            # 0 = system task, not subject to 1-per-user limit
        username=f"system:title:{user.id}",
        conversation_id=conv_id,
        task_type="title_suggestion",
        payload={
            "ollama_host": ollama_host,
            "model": model,
            "excerpt": excerpt,
            "conversation_id": conv_id,
            "user_id": user.id,
        }
    )
    await queue_manager.enqueue(entry)
    return {"status": "pending"}



class QueryRequest(BaseModel):
    prompt: str
    conversation_id: int
    game_id: Optional[int] = None
    image_path: Optional[str] = None

@router.post("/stream")
async def stream_query(request: QueryRequest, raw_request: StarletteRequest, db: Session = Depends(database.get_db), user: models.User = Depends(auth.get_current_user)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == request.conversation_id).first()
    if not conv:
        raise HTTPException(404)
    
    # Block user if admin has banned them from AI
    if user.ia_blocked:
        blocked_msg = json.dumps({"text": "🚫 Votre accès à l'IA a été suspendu par un administrateur.", "done": True, "ia_blocked": True})
        async def blocked_response():
            yield f"data: {blocked_msg}\n\n"
        return StreamingResponse(blocked_response(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    
    # Block AI when admin has taken over
    if conv.admin_override:
        # Still save the user message so admin can see it
        user_msg = models.ChatMessage(conversation_id=request.conversation_id, role="user", content=request.prompt, image_path=request.image_path)
        db.add(user_msg)
        db.commit()
        # Notify admin via WS that user sent a message
        await ws_manager.broadcast({
            "type": "user_message_during_override",
            "conversation_id": request.conversation_id,
            "user_id": conv.user_id,
            "content": request.prompt
        })
        async def admin_mode_response():
            yield f"data: {json.dumps({'text': '🛡️ Un administrateur gère cette conversation. Votre message a été transmis.', 'done': True})}\n\n"
        return StreamingResponse(admin_mode_response(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    ia_cfg = get_effective_config(db)
    model_to_use = conv.model or ia_cfg.get('model', '')
    instance = await pick_instance(db, model=model_to_use)
    if not instance:
        raise HTTPException(503, "Aucune instance IA configurée par l'administrateur")
    ollama_host = instance["url"]
    # Use instance's model affinity if conversation has no override
    if not conv.model and instance.get("model"):
        model_to_use = instance["model"]
    
    # 1. RAG (numpy cosine similarity in memory)
    query_embedding = await get_embedding(request.prompt, ollama_host=ollama_host)
    rag_context = ""
    if query_embedding:
        all_docs = db.query(models.KnowledgeBase).all()
        if request.game_id is not None:
            all_docs = [d for d in all_docs if d.metadata_json and d.metadata_json.get('game_id') == request.game_id]
        results = search_similar(query_embedding, all_docs, top_k=3)
        rag_context = "\n".join([doc.content for doc, score in results])
        
    # 2. History
    history_query = db.query(models.ChatMessage).filter(models.ChatMessage.conversation_id == request.conversation_id)
    if conv.compressed_at:
        history_query = history_query.filter(models.ChatMessage.timestamp > conv.compressed_at)
    history = history_query.order_by(models.ChatMessage.timestamp.asc()).all()
    
    user_msg = models.ChatMessage(conversation_id=request.conversation_id, role="user", content=request.prompt, image_path=request.image_path)
    db.add(user_msg)
    db.commit()
    # Notify admin monitoring panel in real-time that a user message was sent
    await ws_manager.broadcast({"type": "chat_updated", "conversation_id": request.conversation_id, "user_id": conv.user_id, "role": "user"})
    
    # Build system prompt — read from SystemConfig, fallback to i18n JSON, then default
    system_prompt = get_active_system_prompt(db)
    
    # Build messages array for Ollama chat API
    ollama_messages = [{"role": "system", "content": system_prompt}]
    
    # Inject user identity so the model knows who is asking
    user_context = f"L'utilisateur qui te parle s'appelle \"{user.username}\""
    if user.team_name:
        user_context += f", il fait partie de l'équipe \"{user.team_name}\""
    if user.is_admin:
        user_context += ", c'est un administrateur de la LAN"
    user_context += "."
    ollama_messages.append({"role": "system", "content": user_context})
    
    # Inject compressed context if present
    if conv.compressed_context:
        ollama_messages.append({"role": "system", "content": f"=== Contexte Compressé ===\n{conv.compressed_context}"})
    
    # Inject RAG context if present
    if rag_context:
        ollama_messages.append({"role": "system", "content": f"=== Base de Connaissances ===\n{rag_context}"})
    
    # Inject conversation history (include images as base64 for vision models)
    for m in history:
        msg_entry = {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        if m.image_path:
            img_full = os.path.join(os.path.dirname(CHAT_IMAGES_DIR), m.image_path)
            if os.path.isfile(img_full):
                with open(img_full, "rb") as imgf:
                    msg_entry["images"] = [base64.b64encode(imgf.read()).decode("utf-8")]
        ollama_messages.append(msg_entry)
    
    # Current user message (with image if attached)
    current_msg = {"role": "user", "content": request.prompt}
    if request.image_path:
        img_full = os.path.join(os.path.dirname(CHAT_IMAGES_DIR), request.image_path)
        if os.path.isfile(img_full):
            with open(img_full, "rb") as imgf:
                current_msg["images"] = [base64.b64encode(imgf.read()).decode("utf-8")]
    ollama_messages.append(current_msg)
    
    # ── Enqueue into AI Queue (G-52) ──
    from ..ia_queue import queue_manager, QueueEntry
    from ..ia_tools import TOOL_DEFINITIONS
    
    # Filtrer les outils optionnels de diagnostic réseau et de modération
    enabled_tools = []
    tool_calling_mode = ia_cfg.get("tool_calling_mode", "stream_intercept")
    
    if tool_calling_mode != "disabled":
        network_tool_names = {"ping_host", "traceroute_host", "dns_lookup", "check_server_health", "scan_local_network"}
        network_enabled = ia_cfg.get("network_tools_enabled", True)
        moderation_enabled = ia_cfg.get("auto_moderation_enabled", True)
        for tool in TOOL_DEFINITIONS:
            if tool["function"]["name"] in network_tool_names and not network_enabled:
                continue
            if tool["function"]["name"] == "block_user_from_ia" and not moderation_enabled:
                continue
            enabled_tools.append(tool)
        
    req_data = {
        "model": model_to_use,
        "messages": ollama_messages,
        "stream": True,
        "options": {"temperature": ia_cfg.get('temperature', 0.2), "num_ctx": ia_cfg.get('context_window', 4096)},
        "tools": enabled_tools,
    }
    queue_entry = QueueEntry(
        priority=0 if user.is_admin else 10,
        created_at=time.time(),
        user_id=user.id,
        username=user.username,
        conversation_id=request.conversation_id,
        task_type="chat",
        payload={
            "ollama_host": ollama_host,
            "req_data": req_data,
            "conversation_id": request.conversation_id,
            "raw_request": raw_request,
            "model_info": {"model": model_to_use, "instance": instance.get('label', 'Default') if instance else 'Default'},
            "tool_calling_mode": tool_calling_mode,
        }
    )
    queue_entry, position = await queue_manager.enqueue(queue_entry)

    async def event_generator():
        _active_requests[ollama_host] = _active_requests.get(ollama_host, 0) + 1
        try:
            avg_dur = queue_manager._instance_avg_durations.get(ollama_host, queue_manager._avg_duration)
            # Yield model info immediately so frontend knows who we are querying
            yield f"data: {json.dumps({'model_info': {'model': model_to_use, 'instance': instance.get('label', 'Default') if instance else 'Default'}, 'avg_duration': round(avg_dur, 1)})}\n\n"
            # ── Phase 1: Queue wait (send position updates via SSE) ──
            if position > 0:
                yield f"data: {json.dumps({'queued': True, 'position': position, 'estimated_wait': round(position * avg_dur), 'avg_duration': round(avg_dur, 1)})}\n\n"
                # Wait for worker to pick us up, sending position updates
                while not queue_entry.processing_event.is_set():
                    try:
                        await asyncio.wait_for(queue_entry.processing_event.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        if queue_entry.cancelled:
                            yield f"data: {json.dumps({'text': '❌ Requête annulée.', 'done': True})}\n\n"
                            return
                        if await raw_request.is_disconnected():
                            await queue_manager.cancel(queue_entry.id)
                            return
                        # Send updated position
                        new_pos = queue_manager._get_position(queue_entry.id)
                        if new_pos > 0:
                            yield f"data: {json.dumps({'position': new_pos, 'estimated_wait': round(new_pos * avg_dur), 'avg_duration': round(avg_dur, 1)})}\n\n"
                yield f"data: {json.dumps({'processing': True})}\n\n"

            # ── Phase 2: Stream tokens from worker ──
            full_response = ""
            while True:
                try:
                    chunk = await asyncio.wait_for(queue_entry.result_stream.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'text': '⏱️ Timeout de génération.', 'done': True, 'error': True})}\n\n"
                    break

                if chunk.get("cancelled"):
                    yield f"data: {json.dumps({'text': '❌ Requête annulée.', 'done': True})}\n\n"
                    break

                if chunk.get("status"):
                    yield f"data: {json.dumps(chunk)}\n\n"
                    continue

                if chunk.get("text") and not chunk.get("done"):
                    full_response += chunk["text"]
                    yield f"data: {json.dumps({'text': chunk['text']})}\n\n"

                if chunk.get("done"):
                    if chunk.get("error"):
                        error_text = chunk.get("text", "Erreur IA inconnue")
                        if error_text:
                            full_response += error_text
                        yield f"data: {json.dumps({'text': error_text, 'done': True, 'error': True})}\n\n"
                        break

                    # Worker finished — compute tokens + auto-title
                    worker_response = chunk.get("full_response", full_response)
                    if not worker_response:
                        worker_response = full_response

                    meta_val = chunk.get("meta") or {
                        "model_info": {"model": model_to_use, "instance": instance.get('label', 'Default') if instance else 'Default'},
                        "used_tools": chunk.get("meta", {}).get("used_tools", [])
                    }
                    with database.SessionLocal() as s:
                        # Only save if the worker hasn't already persisted the message
                        if not chunk.get("saved_by_worker"):
                            ai_msg = models.ChatMessage(
                                conversation_id=request.conversation_id, 
                                role="bot", 
                                content=worker_response,
                                meta=meta_val
                            )
                            s.add(ai_msg)
                            s.commit()
                        # Notify admin monitoring panel that AI response is ready (bot role = not new unread for admin)
                        await ws_manager.broadcast({"type": "chat_updated", "conversation_id": request.conversation_id, "user_id": conv.user_id, "role": "bot"})
                        # Compute updated token estimate for frontend
                        conv_obj = s.query(models.Conversation).filter(models.Conversation.id == request.conversation_id).first()
                        post_msgs = s.query(models.ChatMessage).filter(
                            models.ChatMessage.conversation_id == request.conversation_id
                        )
                        if conv_obj and conv_obj.compressed_at:
                            post_msgs = post_msgs.filter(models.ChatMessage.timestamp > conv_obj.compressed_at)
                        post_msgs = post_msgs.all()
                        ctx_chars = len(conv_obj.compressed_context or "") if conv_obj else 0
                        est_tokens = int((sum(len(m.content) for m in post_msgs) + ctx_chars) / 3.5) + 1300  # +system overhead
                        
                        # ── Auto-title: queue task (G-50) ──
                        if conv_obj and _is_default_title(conv_obj.title) and not conv_obj.title_generation_attempted:
                            # Mark as attempted so we never enqueue redundant generations
                            conv_obj.title_generation_attempted = True
                            s.commit()
                            
                            # Collect up to 3 exchanges (user + bot pairs) for richer context
                            first_msgs = s.query(models.ChatMessage).filter(
                                models.ChatMessage.conversation_id == request.conversation_id,
                                models.ChatMessage.role.in_(["user", "bot"])
                            ).order_by(models.ChatMessage.timestamp.asc()).limit(6).all()
                            if first_msgs:
                                # Build excerpt for the prompt
                                excerpt_parts = []
                                for m in first_msgs:
                                    prefix = "User" if m.role == "user" else "Assistant"
                                    excerpt_parts.append(f"{prefix}: {m.content[:300]}")
                                _excerpt = "\n".join(excerpt_parts[:6])
                                
                                # Enqueue the task
                                from ..ia_queue import QueueEntry
                                import time
                                entry = QueueEntry(
                                    priority=20,          # background priority (doesn't block player queries)
                                    created_at=time.time(),
                                    user_id=0,            # system task (no 1-per-user limit)
                                    username="system:autotitle",
                                    conversation_id=request.conversation_id,
                                    task_type="auto_title",
                                    payload={
                                        "ollama_host": ollama_host,
                                        "model": model_to_use,
                                        "excerpt": _excerpt,
                                        "conversation_id": request.conversation_id,
                                        "user_id": conv_obj.user_id,
                                    }
                                )
                                await queue_manager.enqueue(entry)
                        
                    done_payload = {'done': True, 'estimated_tokens': est_tokens, 'meta': meta_val}
                    yield f"data: {json.dumps(done_payload)}\n\n"
                    break
        except Exception as stream_err:
            error_msg = f"Erreur IA ({type(stream_err).__name__}): {str(stream_err)[:200]}"
            yield f"data: {json.dumps({'text': error_msg, 'done': True, 'error': True})}\n\n"
        finally:
            _active_requests[ollama_host] = max(0, _active_requests.get(ollama_host, 1) - 1)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Queue status endpoints (G-52) ────────────────────────────────────────────
@router.get("/queue/status")
async def queue_status(user: models.User = Depends(auth.get_current_user)):
    """Get the current user's position in the AI queue."""
    from ..ia_queue import queue_manager
    info = queue_manager.get_user_position(user.id)
    if not info:
        return {"queued": False}
    return {"queued": True, **info}

@router.get("/queue/admin")
async def queue_admin(admin: models.User = Depends(auth.get_current_admin)):
    """Full queue status for admin dashboard."""
    from ..ia_queue import queue_manager
    return queue_manager.get_full_status()

@router.delete("/queue/{entry_id}")
async def queue_cancel(entry_id: str, user: models.User = Depends(auth.get_current_user)):
    """Cancel a queued request. Players can cancel their own; admins can cancel any."""
    from ..ia_queue import queue_manager
    # Check ownership (unless admin)
    entry = queue_manager._pending.get(entry_id)
    if entry and not user.is_admin and entry.user_id != user.id:
        raise HTTPException(403, "Vous ne pouvez annuler que vos propres requêtes.")
    ok = await queue_manager.cancel(entry_id)
    if not ok:
        raise HTTPException(404, "Entrée non trouvée dans la file.")
    return {"status": "cancelled"}

@router.delete("/queue/user/cancel")
async def queue_cancel_own(user: models.User = Depends(auth.get_current_user)):
    """Cancel the current user's pending queue entry."""
    from ..ia_queue import queue_manager
    ok = await queue_manager.cancel_by_user(user.id)
    return {"status": "cancelled" if ok else "not_found"}

# NOTE: Legacy /auto-title/{conv_id} endpoint removed — title generation is now
# handled exclusively via IAQueueManager._process_auto_title (enqueued from /stream).


# ── Admin conversation monitoring endpoints ──────────────────────────────────
@router.get("/admin/conversations")
async def admin_list_conversations(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """List ALL conversations across all users (admin only)."""
    convs = db.query(models.Conversation).all()
    results = []
    for c in convs:
        user = db.query(models.User).filter(models.User.id == c.user_id).first()
        
        # Get the last message in this conversation
        last_msg = db.query(models.ChatMessage).filter(
            models.ChatMessage.conversation_id == c.id
        ).order_by(models.ChatMessage.timestamp.desc()).first()
        
        msg_count = db.query(models.ChatMessage).filter(models.ChatMessage.conversation_id == c.id).count()
        
        last_message_at = last_msg.timestamp if last_msg else c.created_at
        last_message_role = last_msg.role if last_msg else None
        last_message_preview = last_msg.content[:60] + "..." if last_msg and len(last_msg.content) > 60 else (last_msg.content if last_msg else None)
        
        unread_count = db.query(models.ChatMessage).filter(
            models.ChatMessage.conversation_id == c.id,
            models.ChatMessage.id > (c.admin_last_read_message_id or 0),
            models.ChatMessage.role == "user"
        ).count()
        
        results.append({
            "id": c.id,
            "title": c.title,
            "user_id": c.user_id,
            "username": user.username if user else "?",
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "message_count": msg_count,
            "admin_override": c.admin_override or False,
            "last_message_at": last_message_at.isoformat() if last_message_at else None,
            "last_message_role": last_message_role,
            "last_message_preview": last_message_preview,
            "has_new_messages": unread_count > 0,
            "unread_count": unread_count,
            "is_online": user.is_online if user else False
        })
        
    # Sort by last message time descending (recent first)
    results.sort(key=lambda x: x["last_message_at"] or "", reverse=True)
    return results

@router.get("/admin/conversations/{conv_id}/messages")
async def admin_get_messages(conv_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Read all messages of any conversation (admin only)."""
    conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404)
    messages = db.query(models.ChatMessage).filter(
        models.ChatMessage.conversation_id == conv_id
    ).order_by(models.ChatMessage.timestamp.asc()).all()
    
    if messages:
        conv.admin_last_read_message_id = messages[-1].id
        db.commit()
        
    user = db.query(models.User).filter(models.User.id == conv.user_id).first()
    return {
        "conversation": {
            "id": conv.id,
            "title": conv.title,
            "username": user.username if user else "?",
            "admin_override": conv.admin_override or False
        },
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "image_path": m.image_path, "timestamp": m.timestamp.isoformat(), "meta": m.meta}
            for m in messages
        ]
    }

class AdminInterveneRequest(BaseModel):
    content: str
    image_path: Optional[str] = None

@router.post("/admin/conversations/{conv_id}/intervene")
async def admin_intervene(conv_id: int, body: AdminInterveneRequest, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Inject an admin message into a player's conversation."""
    conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404)
    # Save as role 'admin' with the admin's username in the content prefix
    msg = models.ChatMessage(
        conversation_id=conv_id,
        role="admin",
        content=f"[{admin.username}] {body.content}",
        image_path=body.image_path
    )
    db.add(msg)
    # Auto-enable admin override
    conv.admin_override = True
    db.commit()
    # Broadcast to all connected clients so user sees it in real-time
    await ws_manager.broadcast({
        "type": "admin_message",
        "conversation_id": conv_id,
        "user_id": conv.user_id,
        "admin_name": admin.username,
        "content": body.content,
        "message_id": msg.id
    })
    # Create notification for the user
    notif = models.Notification(
        user_id=conv.user_id,
        type="admin_message",
        title=f"🛡️ Message de {admin.username}",
        content=body.content[:200],
        metadata_json={"conversation_id": conv_id}
    )
    db.add(notif)
    db.commit()
    await ws_manager.broadcast({"type": "notification_new"})
    return {"status": "ok", "message_id": msg.id}

class OverrideRequest(BaseModel):
    admin_override: bool

@router.put("/admin/conversations/{conv_id}/override")
async def admin_toggle_override(conv_id: int, body: OverrideRequest, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Toggle admin_override flag on a conversation."""
    conv = db.query(models.Conversation).filter(models.Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404)
    conv.admin_override = body.admin_override
    db.commit()
    await ws_manager.broadcast({
        "type": "admin_override_updated",
        "conversation_id": conv.id,
        "user_id": conv.user_id,
        "admin_override": conv.admin_override
    })
    return {"status": "ok", "admin_override": conv.admin_override}


class UploadDocumentRequest(BaseModel):
    content: str
    metadata: dict = {}

@router.post("/upload-document")
async def upload_document(req: UploadDocumentRequest, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    instance = await pick_instance(db)
    host = instance["url"] if instance else get_effective_config(db).get('ollama_host', 'http://localhost:11434')
    embedding, num_chunks = await get_embedding_chunked(req.content, ollama_host=host)
    embedding_str = json.dumps(embedding) if embedding else None
    doc = models.KnowledgeBase(content=req.content, metadata_json=req.metadata, embedding_json=embedding_str)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    await ws_manager.broadcast({"type": "knowledge_updated"})
    result = {"status": "uploaded", "id": doc.id, "content_length": len(req.content), "chunks": num_chunks}
    if not embedding:
        result["warning"] = "Le document a été sauvegardé mais la vectorisation a échoué. Vérifiez qu'une instance Ollama est en ligne avec un modèle d'embedding."
        result["has_embedding"] = False
    else:
        result["has_embedding"] = True
    return result

@router.get("/knowledge")
async def list_knowledge(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """List all RAG knowledge base entries (without full embedding data for performance)."""
    docs = db.query(models.KnowledgeBase).all()
    return [{
        "id": d.id,
        "content": d.content[:200] + ("…" if len(d.content) > 200 else ""),
        "content_length": len(d.content),
        "has_embedding": d.embedding_json is not None and len(d.embedding_json or "") > 10,
        "metadata": d.metadata_json
    } for d in docs]

@router.delete("/knowledge/{doc_id}")
async def delete_knowledge(doc_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Delete a knowledge base entry."""
    doc = db.query(models.KnowledgeBase).filter(models.KnowledgeBase.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    await ws_manager.broadcast({"type": "knowledge_updated"})
    return {"status": "deleted", "id": doc_id}

@router.get("/knowledge/{doc_id}")
async def get_knowledge_doc(doc_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Get full content of a knowledge base entry."""
    doc = db.query(models.KnowledgeBase).filter(models.KnowledgeBase.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": doc.id,
        "content": doc.content,
        "content_length": len(doc.content),
        "has_embedding": doc.embedding_json is not None and len(doc.embedding_json or "") > 10,
        "metadata": doc.metadata_json
    }

class UpdateDocumentRequest(BaseModel):
    content: str
    metadata: dict = {}

@router.put("/knowledge/{doc_id}")
async def update_knowledge_doc(doc_id: int, req: UpdateDocumentRequest, db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Update a knowledge base entry: replace content and re-vectorize."""
    doc = db.query(models.KnowledgeBase).filter(models.KnowledgeBase.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    instance = await pick_instance(db)
    host = instance["url"] if instance else get_effective_config(db).get('ollama_host', 'http://localhost:11434')
    embedding, num_chunks = await get_embedding_chunked(req.content, ollama_host=host)
    
    doc.content = req.content
    doc.metadata_json = req.metadata if req.metadata else doc.metadata_json
    doc.embedding_json = json.dumps(embedding) if embedding else None
    db.commit()
    await ws_manager.broadcast({"type": "knowledge_updated"})
    
    result = {"status": "updated", "id": doc.id, "content_length": len(req.content), "chunks": num_chunks}
    if not embedding:
        result["warning"] = "Le contenu a été mis à jour mais la re-vectorisation a échoué."
        result["has_embedding"] = False
    else:
        result["has_embedding"] = True
    return result

@router.delete("/admin/nuke-images")
async def admin_nuke_images(db: Session = Depends(database.get_db), admin: models.User = Depends(auth.get_current_admin)):
    """Purge ALL chat images from the server."""
    if os.path.isdir(CHAT_IMAGES_DIR):
        shutil.rmtree(CHAT_IMAGES_DIR, ignore_errors=True)
    os.makedirs(CHAT_IMAGES_DIR, exist_ok=True)
    # Clear image_path references in DB
    db.query(models.ChatMessage).filter(models.ChatMessage.image_path != None).update({"image_path": None})
    db.commit()
    return {"status": "ok", "message": "Toutes les images ont été supprimées."}

@router.post("/client-tool-response/{call_id}")
async def client_tool_response(call_id: str, payload: dict):
    from ..ia_tools import pending_client_calls
    if call_id not in pending_client_calls:
        raise HTTPException(404, "Identifiant d'appel non trouvé ou expiré.")
    
    event, _ = pending_client_calls[call_id]
    pending_client_calls[call_id] = (event, payload)
    event.set()
    return {"status": "ok"}
