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
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    version = f.read().strip()
                    break
            except Exception:
                pass
    return {"status": "ok", "version": version}

app.include_router(users.router)
app.include_router(tournaments.router)
app.include_router(room.router)
app.include_router(ia.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(players.router)

# Serve uploaded images
from fastapi.staticfiles import StaticFiles
import os
os.makedirs("static/uploads/games", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve chat images from data volume
DATA_DIR = os.path.dirname(os.getenv("DATABASE_PATH", "/app/data/alanbix.db"))
os.makedirs(os.path.join(DATA_DIR, "chat_images"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "info_files"), exist_ok=True)
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


