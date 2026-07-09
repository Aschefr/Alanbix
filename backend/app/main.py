from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, init_db
from . import models
from .routers import users, tournaments, room, ia, dashboard, notifications, players

from .websockets import manager

app = FastAPI(title="Alanbix API")


# CORS & Redirects Fix
import os
_cors_raw = os.getenv("CORS_ORIGINS", "*")
_cors_origins = ["*"] if _cors_raw.strip() == "*" else [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.router.redirect_slashes = False
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)





@app.on_event("startup")
async def startup():
    init_db()

    # Seed default i18n files to user data volume on startup (DX helper)
    import shutil
    data_dir = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
    data_i18n_dir = os.path.join(data_dir, "i18n")
    static_i18n_dir = "static/i18n"
    os.makedirs(data_i18n_dir, exist_ok=True)
    if os.path.exists(static_i18n_dir):
        for f_name in os.listdir(static_i18n_dir):
            if f_name.endswith(".json") and not f_name.endswith(".bak"):
                src_file = os.path.join(static_i18n_dir, f_name)
                dest_file = os.path.join(data_i18n_dir, f_name)
                if not os.path.exists(dest_file):
                    try:
                        shutil.copy2(src_file, dest_file)
                        print(f"[Startup] Seeded i18n file to data volume: {f_name}")
                    except Exception as e:
                        print(f"[Startup] Failed to seed i18n file {f_name}: {e}")

    # ── Prompt migration v1.18.0 ──────────────────────────────────────────
    # If data/i18n/ has the exact old default prompts (never customised by
    # the admin), replace them with the new structured Asterix-style prompts.
    # Customised values are left untouched.
    _OLD_SYSTEM_PROMPTS = {
        "fr": (
            "Tu es Alanbix, l'IA qui assiste les joueurs lors du tournois de jeux"
            " vidéo (communément appelé 'LAN') en cours. Tu peux parler de tout et"
            " de rien avec les joueurs, les aider à monter des stratégies, de faire"
            " preuve d'humour et de participer à la bonne ambiance. Tu peux taquiner"
            " les joueurs.\nRéponds directement, sans fioritures ni de mise en"
            " contexte. Si tu ne sais pas, dis que tu ne sais pas, n'invente pas."
            " Réponds à tout type de question même hors du scope initiale. En cas"
            " d'abus envers toi, tu peut bloquer un joueur pour l'empêcher de"
            " continuer à être abusif et te protéger."
        ),
        "en": (
            "You are Alanbix, the AI assisting players during the ongoing video game"
            " tournament (commonly called 'LAN'). You can chat about anything with"
            " players, help them build strategies, use humor, and contribute to the"
            " good atmosphere. You can tease players.\nAnswer directly, without fluff"
            " or context-setting. If you don't know, say you don't know, don't"
            " invent. Answer all types of questions even outside the initial scope."
            " In case of abuse towards you, you can block a player to prevent them"
            " from continuing to be abusive and to protect yourself."
        ),
        "es": (
            "Eres Alanbix, la IA que asiste a los jugadores durante el torneo de"
            " videojuegos (comúnmente llamado 'LAN') en curso. Puedes hablar de todo"
            " y de nada con los jugadores, ayudarles a montar estrategias, mostrar"
            " humor y participar en el buen ambiente. Puedes gastar bromas a los"
            " jugadores.\nResponde directamente, sin adornos ni contextualización. Si"
            " no sabes algo, di que no lo sabes, no inventes. Responde a cualquier"
            " tipo de pregunta incluso fuera del alcance inicial. En caso de abuso"
            " hacia ti, puedes bloquear a un jugador para evitar que siga siendo"
            " abusivo y protegerte."
        ),
    }
    _OLD_CLOSING_PROMPTS = {
        "fr": (
            "Tu est un commentateur enthousiaste de tournois de jeux vidéo (LAN)."
            " Tu peut faire du sarcasme et gentiment taquiner les joueurs."
            " Fait de l'humour autant que possible."
        ),
        "en": (
            "You are an enthusiastic video game tournament (LAN) commentator."
            " You can use sarcasm and gently tease players."
            " Use humor as much as possible."
        ),
        "es": (
            "Eres un comentarista entusiasta de torneos de videojuegos (LAN)."
            " Puedes hacer sarcasmo y molestar a los jugadores amablemente."
            " Haz humor tanto como sea posible."
        ),
    }

    import json as _json
    for _lang in ["fr", "en", "es"]:
        _data_path = os.path.join(data_i18n_dir, f"{_lang}.json")
        _static_path = os.path.join(static_i18n_dir, f"{_lang}.json")
        if not os.path.exists(_data_path) or not os.path.exists(_static_path):
            continue
        try:
            with open(_data_path, "r", encoding="utf-8-sig") as _f:
                _data = _json.load(_f)
            with open(_static_path, "r", encoding="utf-8-sig") as _sf:
                _static = _json.load(_sf)

            _changed = False
            _sp = _data.get("system_prompt", "")
            _cp = _data.get("tournament_closing_prompt", "")

            if _sp.strip() == _OLD_SYSTEM_PROMPTS.get(_lang, "").strip():
                _data["system_prompt"] = _static.get("system_prompt", _sp)
                _changed = True
                print(f"[Startup] Migrated system_prompt to v1.18.0 default for lang={_lang}")

            if _cp.strip() == _OLD_CLOSING_PROMPTS.get(_lang, "").strip():
                _data["tournament_closing_prompt"] = _static.get("tournament_closing_prompt", _cp)
                _changed = True
                print(f"[Startup] Migrated tournament_closing_prompt to v1.18.0 default for lang={_lang}")

            if _changed:
                _out_enc = "utf-8-sig" if _lang == "fr" else "utf-8"
                with open(_data_path, "w", encoding=_out_enc) as _f:
                    _json.dump(_data, _f, ensure_ascii=False, indent=2)
                    _f.write("\n")
        except Exception as _e:
            print(f"[Startup] Prompt migration failed for lang={_lang}: {_e}")
    # ── End prompt migration ───────────────────────────────────────────────

    from .database import SessionLocal
    from . import models
    db = SessionLocal()

    # Seed test data only if explicitly requested (dev/testing)
    if os.getenv("SEED_TEST_DATA", "").lower() in ("1", "true", "yes"):
        if db.query(models.Game).count() == 0:
            games = [
                models.Game(
                    name="Counter-Strike 2", 
                    rules="5v5 Competitive",
                    image_url="/games/cs2.png"
                ),
                models.Game(
                    name="Trackmania", 
                    rules="Time Attack",
                    image_url="/games/tm.png"
                ),
                models.Game(
                    name="League of Legends", 
                    rules="5v5 Summoner's Rift",
                    image_url="/games/lol.png"
                )
            ]
            db.add_all(games)
            db.commit()

        if db.query(models.User).count() <= 1:
            from .auth import get_password_hash
            sample_users = [
                models.User(username="xX_DarkSlayer_Xx", hashed_password=get_password_hash("test")),
                models.User(username="FragMaster2000", hashed_password=get_password_hash("test")),
                models.User(username="NoobKiller", hashed_password=get_password_hash("test")),
                models.User(username="ShadowNinja", hashed_password=get_password_hash("test")),
                models.User(username="PixelHunter", hashed_password=get_password_hash("test")),
                models.User(username="RocketQueen", hashed_password=get_password_hash("test")),
                models.User(username="CyberWolf", hashed_password=get_password_hash("test")),
                models.User(username="GlitchMaster", hashed_password=get_password_hash("test")),
            ]
            db.add_all(sample_users)
            db.commit()

    # Start IA Queue workers (1 per enabled Ollama instance, min 1)
    from .ia_queue import queue_manager
    try:
        from .routers.ia import get_instances
        instances = [i for i in get_instances(db) if i.get("enabled", True)]
        num_workers = max(1, len(instances))
    except Exception:
        num_workers = 1
    await queue_manager.start(num_workers=num_workers)

    # Migrate game images from old ephemeral static/uploads/games/ to persistent data/game_images/
    game_images_dir = os.path.join(data_dir, "game_images")
    os.makedirs(game_images_dir, exist_ok=True)
    old_uploads_dir = os.path.join("static", "uploads", "games")
    migrated_files = 0

    # 1) Move physical files if old dir exists
    if os.path.isdir(old_uploads_dir):
        for fname in os.listdir(old_uploads_dir):
            src = os.path.join(old_uploads_dir, fname)
            dst = os.path.join(game_images_dir, fname)
            if os.path.isfile(src) and not os.path.exists(dst):
                try:
                    shutil.move(src, dst)
                    migrated_files += 1
                except Exception as e:
                    print(f"[Startup] Failed to migrate game image {fname}: {e}")

    # 2) Update DB records pointing to old path
    migrated_records = 0
    for game in db.query(models.Game).all():
        if game.image_url and game.image_url.startswith("/static/uploads/games/"):
            old_filename = game.image_url.replace("/static/uploads/games/", "")
            game.image_url = f"/data/game_images/{old_filename}"
            migrated_records += 1
    if migrated_records > 0:
        db.commit()

    if migrated_files > 0 or migrated_records > 0:
        print(f"[Startup] Game images migration: {migrated_files} files moved, {migrated_records} DB records updated.")

    db.close()

@app.on_event("shutdown")
async def shutdown():
    from .ia_queue import queue_manager
    await queue_manager.stop()

@app.get("/health")
def health_check():
    import os
    version = "1.11.0"
    for path in ["VERSION", "../VERSION", "/app/VERSION", "/VERSION"]:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    version = f.read().strip()
                    break
            except Exception:
                pass
    return {"status": "ok", "version": version}

@app.get("/changelog")
def get_changelog():
    import os
    import re
    
    changelog_path = None
    for path in ["CHANGELOG.md", "../CHANGELOG.md", "/app/CHANGELOG.md", "/CHANGELOG.md"]:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            changelog_path = path
            break
            
    if not changelog_path:
        return []
        
    try:
        with open(changelog_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        pattern = r"##\s*\[([^\]]+)\]\s*-\s*([^\n]+)"
        matches = list(re.finditer(pattern, content))
        releases = []
        
        for i, match in enumerate(matches):
            tag_name = f"v{match.group(1)}"
            published_at = match.group(2).strip()
            
            start_idx = match.end()
            end_idx = matches[i+1].start() if i + 1 < len(matches) else len(content)
            
            body = content[start_idx:end_idx].strip()
            body = re.sub(r"\n+---+\s*$", "", body).strip()
            
            releases.append({
                "tag_name": tag_name,
                "published_at": published_at,
                "name": f"Version {match.group(1)}",
                "body": body
            })
        return releases
    except Exception:
        return []

@app.get("/i18n/languages")
def list_languages():
    from app.routers.i18n import list_all_languages
    try:
        langs = list_all_languages()
        if langs:
            return {"languages": langs}
    except Exception:
        pass
    return {"languages": ["fr", "en"]}

from app.routers import users, tournaments, room, ia, dashboard, i18n

app.include_router(users.router)
app.include_router(tournaments.router)
app.include_router(room.router)
app.include_router(ia.router)
app.include_router(dashboard.router)
app.include_router(i18n.router)
app.include_router(notifications.router)
app.include_router(players.router)

# Serve uploaded images (legacy static mount)
from fastapi.staticfiles import StaticFiles
import os
os.makedirs("static/uploads/games", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve chat images from data volume
DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
os.makedirs(os.path.join(DATA_DIR, "chat_images"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "info_files"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "avatars"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "i18n"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "game_images"), exist_ok=True)
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")




@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# SPA Fallback for Frontend
from fastapi.responses import FileResponse
from starlette.responses import Response

def _cache_headers(file_path: str) -> dict:
    """Return appropriate Cache-Control headers based on file path.
    
    Vite/SvelteKit generates hashed filenames for JS/CSS in _app/immutable/,
    making them safe to cache forever.  index.html must always be revalidated
    so browsers pick up new asset hashes after deployments.
    """
    # Immutable hashed assets (e.g. _app/immutable/chunks/app.DxF3k2.js)
    if "/_app/immutable/" in file_path.replace("\\", "/"):
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    # Everything else (index.html, favicon, manifest…) — always revalidate
    return {"Cache-Control": "no-cache, no-store, must-revalidate"}

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    import os
    base_dir = os.environ.get("FRONTEND_DIST_DIR", "/app/frontend_dist")
    
    # Handle empty path (root)
    if not full_path:
        full_path = "index.html"
        
    path = os.path.join(base_dir, full_path)
    
    # Security check to prevent path traversal
    if not os.path.abspath(path).startswith(os.path.abspath(base_dir)):
        index = os.path.join(base_dir, "index.html")
        return FileResponse(index, headers=_cache_headers(index))

    if os.path.isfile(path):
        return FileResponse(path, headers=_cache_headers(path))
        
    # Fallback to index.html for SPA routing
    index_path = os.path.join(base_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, headers=_cache_headers(index_path))
        
    return {"error": "Frontend not built or not found"}


