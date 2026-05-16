"""
AI Queue Manager — asyncio.Queue-based request queuing for Ollama.
Provides fair scheduling, priority (admin > player > background),
real-time position feedback via WebSocket, and estimated wait times.
"""
import asyncio
import time
import uuid
import json
import httpx
import base64
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from collections import deque

from .websockets import manager as ws_manager


# ---------------------------------------------------------------------------
# Queue Entry
# ---------------------------------------------------------------------------
@dataclass(order=True)
class QueueEntry:
    """A single queued AI request. Ordered by (priority, created_at)."""
    priority: int = field(compare=True)            # 0=admin, 10=player, 20=background
    created_at: float = field(compare=True)         # time.time()
    # --- non-comparison fields ---
    id: str = field(default_factory=lambda: uuid.uuid4().hex, compare=False)
    user_id: int = field(default=0, compare=False)
    username: str = field(default="", compare=False)
    conversation_id: int = field(default=0, compare=False)
    task_type: str = field(default="chat", compare=False)  # chat | compress | notification
    # Payload for the worker
    payload: Dict = field(default_factory=dict, compare=False)
    # Result channel — worker pushes SSE chunks here
    result_stream: asyncio.Queue = field(default_factory=asyncio.Queue, compare=False)
    # Signaled when the worker starts processing (position -> 0)
    processing_event: asyncio.Event = field(default_factory=asyncio.Event, compare=False)
    # Signaled when fully done
    done_event: asyncio.Event = field(default_factory=asyncio.Event, compare=False)
    cancelled: bool = field(default=False, compare=False)


# ---------------------------------------------------------------------------
# Queue Manager (Singleton)
# ---------------------------------------------------------------------------
class IAQueueManager:
    """Central queue manager for all Ollama requests."""

    def __init__(self):
        self._queue: asyncio.PriorityQueue[QueueEntry] = asyncio.PriorityQueue()
        self._pending: Dict[str, QueueEntry] = {}       # entry_id -> entry
        self._by_user: Dict[int, QueueEntry] = {}        # user_id -> entry (1 max)
        self._active: Dict[str, QueueEntry] = {}         # entry_id -> entry being processed
        self._workers: List[asyncio.Task] = []
        self._running = False
        # Rolling average of request duration (last 20)
        self._durations: deque = deque(maxlen=20)
        self._avg_duration: float = 15.0  # initial guess: 15s

    # --- Lifecycle ---

    async def start(self, num_workers: int = 1):
        """Start N worker coroutines."""
        self._running = True
        for i in range(num_workers):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        print(f"[IA Queue] Started {num_workers} worker(s)")

    async def stop(self):
        """Graceful shutdown: cancel pending, wait for active."""
        self._running = False
        # Cancel all pending entries
        for entry in list(self._pending.values()):
            entry.cancelled = True
            entry.done_event.set()
        # Signal workers to stop
        for _ in self._workers:
            sentinel = QueueEntry(priority=-1, created_at=0)
            sentinel.cancelled = True
            await self._queue.put(sentinel)
        # Wait for workers to finish
        for w in self._workers:
            try:
                await asyncio.wait_for(w, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                w.cancel()
        self._workers.clear()
        print("[IA Queue] Stopped")

    async def restart_workers(self, num_workers: int):
        """Hot-restart workers to match new instance count (e.g. after config change).
        Active requests finish naturally; only idle workers are replaced."""
        old_count = len(self._workers)
        if num_workers == old_count and self._running:
            return  # No change needed

        # Stop old workers gracefully
        self._running = False
        for _ in self._workers:
            sentinel = QueueEntry(priority=-1, created_at=0)
            sentinel.cancelled = True
            await self._queue.put(sentinel)
        for w in self._workers:
            try:
                await asyncio.wait_for(w, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                w.cancel()
        self._workers.clear()

        # Start new workers
        self._running = True
        for i in range(num_workers):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        print(f"[IA Queue] Restarted: {old_count} -> {num_workers} worker(s)")

    # --- Public API ---

    async def enqueue(self, entry: QueueEntry) -> tuple:
        """Add a request to the queue. Returns (entry, position).
        If the user already has a pending request, returns the existing one."""
        # Limit: 1 per user (skip for system/notification tasks with user_id=0)
        if entry.user_id and entry.user_id in self._by_user:
            existing = self._by_user[entry.user_id]
            pos = self._get_position(existing.id)
            return existing, pos

        self._pending[entry.id] = entry
        if entry.user_id:
            self._by_user[entry.user_id] = entry
        await self._queue.put(entry)

        pos = self._get_position(entry.id)
        await self._broadcast_queue_state()
        # Notify the specific user of their position
        if entry.user_id:
            await self._broadcast_user_position(entry.user_id, pos)
        return entry, pos

    async def cancel(self, entry_id: str) -> bool:
        """Cancel a pending entry. Returns True if found and cancelled."""
        entry = self._pending.get(entry_id) or self._active.get(entry_id)
        if not entry:
            return False
        entry.cancelled = True
        entry.done_event.set()
        # Push a cancel signal through the result stream
        await entry.result_stream.put({"cancelled": True})
        self._cleanup_entry(entry)
        await self._broadcast_queue_state()
        return True

    async def cancel_by_user(self, user_id: int) -> bool:
        """Cancel the pending entry for a specific user."""
        entry = self._by_user.get(user_id)
        if entry:
            return await self.cancel(entry.id)
        return False

    def get_user_position(self, user_id: int) -> Optional[dict]:
        """Get queue info for a specific user. Returns None if not queued."""
        entry = self._by_user.get(user_id)
        if not entry:
            # Check if user is being actively processed
            for e in self._active.values():
                if e.user_id == user_id:
                    return {"position": 0, "estimated_wait": 0, "entry_id": e.id, "status": "processing", "conversation_id": e.conversation_id}
            return None
        pos = self._get_position(entry.id)
        # If position is 0 or entry is in _active, it's being processed
        if pos == 0 or entry.id in self._active:
            return {"position": 0, "estimated_wait": 0, "entry_id": entry.id, "status": "processing", "conversation_id": entry.conversation_id}
        return {
            "position": pos,
            "estimated_wait": round(pos * self._avg_duration),
            "entry_id": entry.id,
            "status": "queued",
            "conversation_id": entry.conversation_id
        }

    def get_full_status(self) -> dict:
        """Full queue status for admin view."""
        now = time.time()
        pending = []
        # Rebuild ordered list from internal tracking
        entries = sorted(self._pending.values(), key=lambda e: (e.priority, e.created_at))
        for i, entry in enumerate(entries):
            pending.append({
                "id": entry.id,
                "position": i + 1,
                "user_id": entry.user_id,
                "username": entry.username,
                "task_type": entry.task_type,
                "priority": entry.priority,
                "waiting_since": round(now - entry.created_at),
                "estimated_wait": round((i + 1) * self._avg_duration),
            })
        active = []
        for entry in self._active.values():
            active.append({
                "id": entry.id,
                "user_id": entry.user_id,
                "username": entry.username,
                "task_type": entry.task_type,
                "processing_since": round(now - entry.created_at),
            })
        return {
            "pending": pending,
            "active": active,
            "queue_size": len(self._pending),
            "active_count": len(self._active),
            "avg_duration": round(self._avg_duration, 1),
        }

    # --- Worker ---

    async def _worker(self, worker_id: int):
        """Worker loop: consume queue, call Ollama, push results."""
        while self._running:
            try:
                entry = await asyncio.wait_for(self._queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            # Sentinel check (shutdown signal)
            if entry.priority == -1:
                break

            # Skip cancelled entries
            if entry.cancelled or entry.id not in self._pending:
                self._queue.task_done()
                continue

            # Move from pending to active
            self._pending.pop(entry.id, None)
            self._active[entry.id] = entry
            entry.processing_event.set()

            # Broadcast updated positions to all waiting users
            await self._broadcast_queue_state()
            await self._broadcast_all_positions()

            t0 = time.time()
            try:
                await self._process_entry(entry, worker_id)
            except Exception as e:
                error_msg = f"Erreur IA ({type(e).__name__}): {str(e)[:200]}"
                await entry.result_stream.put({"text": error_msg, "done": True, "error": True})
            finally:
                duration = time.time() - t0
                self._durations.append(duration)
                self._avg_duration = sum(self._durations) / len(self._durations)

                self._cleanup_entry(entry)
                entry.done_event.set()
                self._queue.task_done()
                await self._broadcast_queue_state()

    async def _process_entry(self, entry: QueueEntry, worker_id: int):
        """Execute the Ollama request and stream results."""
        payload = entry.payload
        task_type = entry.task_type

        if task_type == "chat":
            await self._process_chat(entry, payload)
        elif task_type == "compress":
            await self._process_compress(entry, payload)
        elif task_type == "notification":
            await self._process_notification(entry, payload)

    async def _process_chat(self, entry: QueueEntry, payload: dict):
        """Process a chat streaming request, with tool-calling support."""
        ollama_host = payload["ollama_host"]
        req_data = payload["req_data"]
        conversation_id = payload["conversation_id"]
        raw_request = payload.get("raw_request")

        client = httpx.AsyncClient()
        try:
            # ── Phase 1: Check for tool calls (non-streaming first call) ──
            tool_messages = list(req_data.get("messages", []))
            tools = req_data.get("tools")
            max_tool_rounds = 3
            tool_round = 0

            if tools:
                from .ia_tools import execute_tool

                # Inject tool-use instruction for the model
                tool_instruction = {
                    "role": "system",
                    "content": (
                        "Tu as accès à des outils (tools/functions) pour répondre aux questions. "
                        "Tu DOIS utiliser les outils disponibles pour obtenir des données factuelles "
                        "(heure, date, tournois, scores, classement, joueurs, jeux, notifications, infos). "
                        "N'invente JAMAIS de données. Appelle toujours l'outil approprié."
                    )
                }

                # Use full conversation history for tool detection.
                # Insert tool instruction after system messages.
                system_msgs = [m for m in tool_messages if m.get("role") == "system"]
                non_system = [m for m in tool_messages if m.get("role") != "system"]
                tool_detect_msgs = system_msgs + [tool_instruction] + non_system

                while tool_round < max_tool_rounds:
                    tool_round += 1
                    # Non-streaming call to check for tool_calls
                    tool_req = {**req_data, "messages": tool_detect_msgs, "stream": False}
                    try:
                        tool_res = await client.post(
                            f"{ollama_host}/api/chat",
                            json=tool_req,
                            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
                        )
                        tool_data = tool_res.json()
                    except Exception as e:
                        print(f"[ToolCall] Non-streaming call failed: {e}", flush=True)
                        break  # Fall through to normal streaming

                    msg = tool_data.get("message", {})
                    tool_calls = msg.get("tool_calls")
                    direct_content = msg.get("content", "")

                    print(f"[ToolCall] Round {tool_round}: tool_calls={bool(tool_calls)}, content_len={len(direct_content)}, keys={list(msg.keys())}", flush=True)
                    print(f"[ToolCall] Content: {direct_content[:300]}", flush=True)
                    print(f"[ToolCall] Full msg keys/types: { {k: type(v).__name__ for k,v in msg.items()} }", flush=True)
                    if tool_calls:
                        print(f"[ToolCall] Calls: {json.dumps(tool_calls, default=str)[:500]}", flush=True)

                    if not tool_calls:
                        # No tool calls needed — fall through to Phase 2
                        # for real streaming (tool detection was non-streaming).
                        break

                    # Execute each tool call
                    # Add assistant message with tool_calls to BOTH lists
                    tool_messages.append({"role": "assistant", "tool_calls": tool_calls})
                    tool_detect_msgs.append({"role": "assistant", "tool_calls": tool_calls})

                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        fn_name = fn.get("name", "")
                        fn_args = fn.get("arguments", {})
                        # Notify user that a tool is being called
                        await entry.result_stream.put({"text": f"🔍 *Consultation des données : {fn_name}...*\n\n"})
                        try:
                            result = execute_tool(fn_name, fn_args, user_id=entry.user_id)
                        except Exception as e:
                            result = json.dumps({"error": str(e)})
                        tool_messages.append({"role": "tool", "content": result})
                        tool_detect_msgs.append({"role": "tool", "content": result})

                    # Continue loop to check if model wants more tool calls

            # ── Phase 2: Final streaming response ──
            # If tool calls happened, use the enriched message history
            if tool_round > 0 and tools:
                # Stream the final response with tool results in context
                stream_req = {**req_data, "messages": tool_messages, "stream": True}
                # Remove tools to prevent another round
                stream_req.pop("tools", None)
            else:
                stream_req = req_data

            full_response = ""
            in_think_block = False
            async with client.stream("POST", f"{ollama_host}/api/chat",
                                     json=stream_req,
                                     timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)) as response:
                async for chunk in response.aiter_lines():
                    if entry.cancelled:
                        break
                    if raw_request:
                        try:
                            if await raw_request.is_disconnected():
                                break
                        except Exception:
                            pass
                    if not chunk:
                        continue
                    try:
                        data = json.loads(chunk)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            full_response += token
                            # Filter <think>...</think> blocks (Qwen3 etc.)
                            if "<think>" in token:
                                in_think_block = True
                            if not in_think_block:
                                await entry.result_stream.put({"text": token})
                            if "</think>" in token:
                                in_think_block = False
                        if data.get("done"):
                            # Strip think blocks from saved response
                            import re
                            clean_response = re.sub(r'<think>.*?</think>', '', full_response, flags=re.DOTALL).strip()
                            saved_msg_id = self._save_bot_message(conversation_id, clean_response)
                            await entry.result_stream.put({
                                "done": True,
                                "full_response": clean_response,
                                "saved_by_worker": saved_msg_id is not None,
                            })
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            error_msg = f"Erreur IA ({type(e).__name__}): {str(e)[:200]}"
            await entry.result_stream.put({"text": error_msg, "done": True, "error": True})
        finally:
            await client.aclose()

    def _save_bot_message(self, conversation_id: int, content: str):
        """Save bot message to DB. Returns message ID or None."""
        if not content or not conversation_id:
            return None
        try:
            from .database import SessionLocal
            from . import models
            with SessionLocal() as s:
                ai_msg = models.ChatMessage(
                    conversation_id=conversation_id,
                    role="bot",
                    content=content
                )
                s.add(ai_msg)
                s.commit()
                return ai_msg.id
        except Exception:
            return None

    async def _process_compress(self, entry: QueueEntry, payload: dict):
        """Process a compression request (non-streaming)."""
        url = payload["ollama_host"]
        model = payload["model"]
        mode = payload["mode"]
        text = payload["text"]

        from .ia_compression import run_compaction, run_summary

        try:
            if mode == "compact":
                result = await run_compaction(text, url, model)
            elif mode == "summary":
                result = await run_summary(text, url, model)
            else:
                result = ""
            await entry.result_stream.put({"done": True, "result": result})
        except Exception as e:
            await entry.result_stream.put({"done": True, "error": True, "result": str(e)})

    async def _process_notification(self, entry: QueueEntry, payload: dict):
        """Process a tournament notification generation request (non-streaming)."""
        ollama_host = payload["ollama_host"]
        model = payload["model"]
        prompt = payload["prompt"]

        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f"{ollama_host}/api/chat", json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.8}
                }, timeout=120.0)

            if res.status_code != 200:
                raise Exception(f"Ollama returned HTTP {res.status_code}: {res.text[:200]}")

            raw = res.json().get("message", {}).get("content", "")
            await entry.result_stream.put({"done": True, "result": raw})
        except Exception as e:
            await entry.result_stream.put({"done": True, "error": True, "result": str(e)})

    # --- Internal helpers ---

    def _get_position(self, entry_id: str) -> int:
        """Get 1-based position of an entry in the queue. 0 = processing."""
        if entry_id in self._active:
            return 0
        # Sort pending by (priority, created_at) to match PriorityQueue order
        ordered = sorted(self._pending.values(), key=lambda e: (e.priority, e.created_at))
        for i, e in enumerate(ordered):
            if e.id == entry_id:
                return i + 1
        return -1  # Not found

    def _cleanup_entry(self, entry: QueueEntry):
        """Remove entry from all tracking dicts."""
        self._pending.pop(entry.id, None)
        self._active.pop(entry.id, None)
        if entry.user_id and self._by_user.get(entry.user_id) is entry:
            del self._by_user[entry.user_id]

    async def _broadcast_queue_state(self):
        """Broadcast global queue state via WebSocket (for admin widget)."""
        try:
            await ws_manager.broadcast({
                "type": "ia_queue_update",
                "queue_size": len(self._pending),
                "active_count": len(self._active),
                "avg_duration": round(self._avg_duration, 1),
            })
        except Exception:
            pass

    async def _broadcast_user_position(self, user_id: int, position: int):
        """Broadcast position update to a specific user."""
        try:
            await ws_manager.broadcast({
                "type": "ia_queue_position",
                "user_id": user_id,
                "position": position,
                "estimated_wait": round(position * self._avg_duration),
            })
        except Exception:
            pass

    async def _broadcast_all_positions(self):
        """Recalculate and broadcast positions for all pending users."""
        ordered = sorted(self._pending.values(), key=lambda e: (e.priority, e.created_at))
        for i, entry in enumerate(ordered):
            if entry.user_id:
                await self._broadcast_user_position(entry.user_id, i + 1)


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------
queue_manager = IAQueueManager()
