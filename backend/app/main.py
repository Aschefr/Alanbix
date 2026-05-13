from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, init_db
from . import models
from .routers import users, tournaments, room, ia, dashboard

from .websockets import manager

app = FastAPI(title="Alanbix API")


# CORS & Redirects Fix
app.router.redirect_slashes = False
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)





@app.on_event("startup")
async def startup():
    init_db()
    
    # Seed default games
    from .database import SessionLocal
    from . import models
    db = SessionLocal()
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

    # Seed sample users for testing
    if db.query(models.User).count() == 0:
        from .auth import get_password_hash
        sample_users = [
            models.User(username="Admin", hashed_password=get_password_hash("admin"), is_admin=True),
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

    db.close()

@app.get("/health")

def health_check():
    return {"status": "ok", "version": "1.0.0"}

app.include_router(users.router)
app.include_router(tournaments.router)
app.include_router(room.router)
app.include_router(ia.router)
app.include_router(dashboard.router)

# Serve uploaded images
from fastapi.staticfiles import StaticFiles
import os
os.makedirs("static/uploads/games", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")




@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


