from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict, Set, Optional
import datetime

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_users: Dict[WebSocket, int] = {}       # websocket -> user_id
        self.user_connections: Dict[int, Set[WebSocket]] = {}   # user_id -> set of active websockets

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    async def register_user(self, websocket: WebSocket, user_id: int):
        """Associate an authenticated user with this WebSocket and broadcast presence if first active tab."""
        from .database import ACTIVE_USERS

        old_user = self.connection_users.get(websocket)
        if old_user and old_user != user_id:
            await self._detach_user_socket(websocket, old_user)

        self.connection_users[websocket] = user_id
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()

        is_first_tab = len(self.user_connections[user_id]) == 0
        self.user_connections[user_id].add(websocket)
        ACTIVE_USERS[user_id] = datetime.datetime.utcnow()

        if is_first_tab:
            await self.broadcast({
                "type": "user_presence",
                "user_id": user_id,
                "is_online": True
            })

    async def _detach_user_socket(self, websocket: WebSocket, user_id: int):
        """Detach a socket from a user and broadcast offline event if this was their last tab."""
        from .database import ACTIVE_USERS
        sockets = self.user_connections.get(user_id)
        if sockets and websocket in sockets:
            sockets.remove(websocket)
            if len(sockets) == 0:
                self.user_connections.pop(user_id, None)
                ACTIVE_USERS.pop(user_id, None)
                await self.broadcast({
                    "type": "user_presence",
                    "user_id": user_id,
                    "is_online": False
                })

    async def disconnect(self, websocket: WebSocket):
        try:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        except (ValueError, Exception):
            pass

        user_id = self.connection_users.pop(websocket, None)
        if user_id:
            await self._detach_user_socket(websocket, user_id)

    def is_user_online(self, user_id: int) -> bool:
        """Check if user currently has at least one active websocket connection."""
        return len(self.user_connections.get(user_id, set())) > 0

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            try:
                await self.disconnect(dead)
            except Exception:
                pass

manager = ConnectionManager()

