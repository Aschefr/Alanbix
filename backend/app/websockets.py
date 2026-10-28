from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict, Set, Optional, Iterable
import datetime

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_users: Dict[WebSocket, int] = {}       # websocket -> user_id
        self.connection_clients: Dict[WebSocket, str] = {}     # websocket -> client_type ("web" | "push")
        self.user_connections: Dict[int, Set[WebSocket]] = {}   # user_id -> set of active websockets

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_clients[websocket] = "web"

    async def register_user(self, websocket: WebSocket, user_id: int, client_type: str = "web"):
        """Associate an authenticated user with this WebSocket and broadcast presence if first active non-push tab."""
        from .database import ACTIVE_USERS

        old_user = self.connection_users.get(websocket)
        if old_user and old_user != user_id:
            await self._detach_user_socket(websocket, old_user)

        self.connection_users[websocket] = user_id
        self.connection_clients[websocket] = client_type

        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()

        is_first_active_tab = (
            client_type != "push" and
            not any(self.connection_clients.get(ws) != "push" for ws in self.user_connections[user_id])
        )

        self.user_connections[user_id].add(websocket)

        if client_type != "push":
            ACTIVE_USERS[user_id] = datetime.datetime.utcnow()

        if is_first_active_tab:
            await self.broadcast({
                "type": "user_presence",
                "user_id": user_id,
                "is_online": True
            })

    async def _detach_user_socket(self, websocket: WebSocket, user_id: int):
        """Detach a socket from a user and broadcast offline event if this was their last active non-push tab."""
        from .database import ACTIVE_USERS
        was_non_push = self.connection_clients.get(websocket) != "push"
        sockets = self.user_connections.get(user_id)
        if sockets and websocket in sockets:
            sockets.remove(websocket)
            if len(sockets) == 0:
                self.user_connections.pop(user_id, None)
                ACTIVE_USERS.pop(user_id, None)
                if was_non_push:
                    await self.broadcast({
                        "type": "user_presence",
                        "user_id": user_id,
                        "is_online": False
                    })
            else:
                has_active_non_push = any(self.connection_clients.get(ws) != "push" for ws in sockets)
                if was_non_push and not has_active_non_push:
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
        self.connection_clients.pop(websocket, None)

    def is_user_online(self, user_id: int) -> bool:
        """Check if user currently has at least one active non-push websocket connection."""
        sockets = self.user_connections.get(user_id, set())
        return any(self.connection_clients.get(ws) != "push" for ws in sockets)

    def is_user_connected(self, user_id: int) -> bool:
        """Check if user has any active websocket connection (including background push sockets)."""
        return len(self.user_connections.get(user_id, set())) > 0

    async def send_to_user(self, user_id: int, message: dict) -> int:
        """Send a JSON message to all active WebSocket connections for a given user.
        Returns the number of sockets successfully sent to."""
        sockets = list(self.user_connections.get(user_id, set()))
        if not sockets:
            return 0
        dead_connections = []
        sent_count = 0
        for ws in sockets:
            try:
                await ws.send_json(message)
                sent_count += 1
            except Exception:
                dead_connections.append(ws)

        for dead in dead_connections:
            try:
                await self.disconnect(dead)
            except Exception:
                pass
        return sent_count

    async def send_to_users(self, user_ids: Iterable[int], message: dict) -> int:
        """Send a JSON message to active sockets of multiple users."""
        total = 0
        seen_sockets = set()
        dead_connections = []
        for uid in set(user_ids):
            for ws in list(self.user_connections.get(uid, set())):
                if ws in seen_sockets:
                    continue
                seen_sockets.add(ws)
                try:
                    await ws.send_json(message)
                    total += 1
                except Exception:
                    dead_connections.append(ws)

        for dead in dead_connections:
            try:
                await self.disconnect(dead)
            except Exception:
                pass
        return total

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

