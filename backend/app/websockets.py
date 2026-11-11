import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict, Set, Optional, Iterable
import datetime
from .clock import utcnow

# A client that stops reading (phone asleep, wifi gone without a clean close) made send_json wait
# without end. Every request that broadcast then kept its database connection while waiting, the
# pool (15) ran out and the whole server froze (prod, 2026-11-11, friends test). A socket that
# does not take a message within this delay is dropped; the app reconnects on its own.
SEND_TIMEOUT = 2.0


async def _send(ws: WebSocket, message: dict) -> bool:
    """Send one message; False when the socket failed or is too slow to take it."""
    try:
        await asyncio.wait_for(ws.send_json(message), timeout=SEND_TIMEOUT)
        return True
    except Exception:
        return False


async def _close_quietly(ws: WebSocket):
    try:
        await asyncio.wait_for(ws.close(), timeout=SEND_TIMEOUT)
    except Exception:
        pass

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
            ACTIVE_USERS[user_id] = utcnow()

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
        return await self._send_all(sockets, message)

    async def send_to_users(self, user_ids: Iterable[int], message: dict) -> int:
        """Send a JSON message to active sockets of multiple users."""
        sockets = []
        for uid in set(user_ids):
            for ws in list(self.user_connections.get(uid, set())):
                if ws not in sockets:
                    sockets.append(ws)
        return await self._send_all(sockets, message)

    async def broadcast(self, message: dict):
        await self._send_all(list(self.active_connections), message)

    async def _send_all(self, sockets: List[WebSocket], message: dict) -> int:
        """Send to every socket at once, each within SEND_TIMEOUT: one stuck client neither delays
        the others nor holds the caller. Failed or slow sockets are dropped and closed."""
        if not sockets:
            return 0
        results = await asyncio.gather(*(_send(ws, message) for ws in sockets))
        for ws, ok in zip(sockets, results):
            if not ok:
                try:
                    await self.disconnect(ws)
                except Exception:
                    pass
                asyncio.create_task(_close_quietly(ws))
        return sum(results)

manager = ConnectionManager()

