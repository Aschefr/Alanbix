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
from .ia_title_utils import _build_title_prompt, _clean_title, _is_default_title


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
        # Rolling average of request duration (last 10)
        self._durations: deque = deque(maxlen=10)
        self._avg_duration: float = 15.0  # initial guess: 15s
        # Per-instance rolling average of request duration (last 10)
        self._instance_durations: Dict[str, deque] = {}
        self._instance_avg_durations: Dict[str, float] = {}

    def load_persisted_durations(self):
        """Load average durations history from database."""
        try:
            from .database import SessionLocal
            from .models import SystemConfig
            with SessionLocal() as db:
                # 1. Global durations
                g_cfg = db.query(SystemConfig).filter(SystemConfig.key == "global_durations_history").first()
                if g_cfg and isinstance(g_cfg.value, list):
                    self._durations = deque(g_cfg.value, maxlen=10)
                    if self._durations:
                        self._avg_duration = sum(self._durations) / len(self._durations)
                
                # 2. Per-instance durations
                i_cfg = db.query(SystemConfig).filter(SystemConfig.key == "instance_durations_history").first()
                if i_cfg and isinstance(i_cfg.value, dict):
                    for host, durs in i_cfg.value.items():
                        if isinstance(durs, list):
                            self._instance_durations[host] = deque(durs, maxlen=10)
                            if durs:
                                self._instance_avg_durations[host] = sum(durs) / len(durs)
            print("[IA Queue] Loaded response durations from database")
        except Exception as e:
            print(f"[IA Queue] Failed to load persisted durations: {e}")

    def persist_durations(self):
        """Save average durations history to database."""
        try:
            from .database import SessionLocal
            from .models import SystemConfig
            with SessionLocal() as db:
                # 1. Global durations
                g_cfg = db.query(SystemConfig).filter(SystemConfig.key == "global_durations_history").first()
                if not g_cfg:
                    g_cfg = SystemConfig(key="global_durations_history", value=list(self._durations))
                    db.add(g_cfg)
                else:
                    g_cfg.value = list(self._durations)
                
                # 2. Per-instance durations
                i_cfg = db.query(SystemConfig).filter(SystemConfig.key == "instance_durations_history").first()
                inst_dict = {host: list(durs) for host, durs in self._instance_durations.items()}
                if not i_cfg:
                    i_cfg = SystemConfig(key="instance_durations_history", value=inst_dict)
                    db.add(i_cfg)
                else:
                    i_cfg.value = inst_dict
                
                db.commit()
        except Exception as e:
            print(f"[IA Queue] Failed to persist durations: {e}")

    # --- Lifecycle ---

    async def start(self, num_workers: int = 1):
        """Start N worker coroutines."""
        self.load_persisted_durations()
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
                    host = e.payload.get("ollama_host", "default")
                    avg_dur = self._instance_avg_durations.get(host, self._avg_duration)
                    return {"position": 0, "estimated_wait": 0, "entry_id": e.id, "status": "processing", "conversation_id": e.conversation_id, "avg_duration": round(avg_dur, 1)}
            return None
        pos = self._get_position(entry.id)
        host = entry.payload.get("ollama_host", "default")
        avg_dur = self._instance_avg_durations.get(host, self._avg_duration)
        # If position is 0 or entry is in _active, it's being processed
        if pos == 0 or entry.id in self._active:
            return {"position": 0, "estimated_wait": 0, "entry_id": entry.id, "status": "processing", "conversation_id": entry.conversation_id, "avg_duration": round(avg_dur, 1)}
        return {
            "position": pos,
            "estimated_wait": round(pos * avg_dur),
            "entry_id": entry.id,
            "status": "queued",
            "conversation_id": entry.conversation_id,
            "avg_duration": round(avg_dur, 1)
        }

    def get_full_status(self) -> dict:
        """Full queue status for admin view."""
        now = time.time()
        pending = []
        # Rebuild ordered list from internal tracking
        entries = sorted(self._pending.values(), key=lambda e: (e.priority, e.created_at))
        for i, entry in enumerate(entries):
            host = entry.payload.get("ollama_host", "default")
            avg_dur = self._instance_avg_durations.get(host, self._avg_duration)
            pending.append({
                "id": entry.id,
                "position": i + 1,
                "user_id": entry.user_id,
                "username": entry.username,
                "task_type": entry.task_type,
                "priority": entry.priority,
                "waiting_since": round(now - entry.created_at),
                "estimated_wait": round((i + 1) * avg_dur),
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
            "instance_avg_durations": {h: round(v, 1) for h, v in self._instance_avg_durations.items()}
        }

    async def register_active_external_task(self, entry_id: str, user_id: int, username: str, task_type: str) -> QueueEntry:
        entry = QueueEntry(
            priority=0,
            created_at=time.time(),
            id=entry_id,
            user_id=user_id,
            username=username,
            task_type=task_type,
        )
        self._active[entry_id] = entry
        await self._broadcast_queue_state()
        return entry

    async def unregister_active_external_task(self, entry_id: str):
        if entry_id in self._active:
            del self._active[entry_id]
            await self._broadcast_queue_state()

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

            # Limit: 1 concurrent request per Ollama instance to prevent GPU overload
            host = entry.payload.get("ollama_host")
            if host:
                active_on_host = sum(1 for e in self._active.values() if e.payload.get("ollama_host") == host)
                if active_on_host >= 1:
                    # Put it back in the queue and sleep briefly to prevent busy spinning
                    await asyncio.sleep(0.5)
                    await self._queue.put(entry)
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
            tool_time = 0.0
            response_time = 0.0
            try:
                res = await self._process_entry(entry, worker_id)
                if isinstance(res, tuple):
                    tool_time, response_time = res
                else:
                    tool_time = res or 0.0
            except Exception as e:
                error_msg = f"Erreur IA ({type(e).__name__}): {str(e)[:200]}"
                await entry.result_stream.put({"text": error_msg, "done": True, "error": True})
            finally:
                if response_time > 0.0:
                    duration = response_time
                else:
                    duration = max(0.1, (time.time() - t0) - tool_time)
                self._durations.append(duration)
                self._avg_duration = sum(self._durations) / len(self._durations)

                host = entry.payload.get("ollama_host", "default")
                if host not in self._instance_durations:
                    self._instance_durations[host] = deque(maxlen=10)
                self._instance_durations[host].append(duration)
                self._instance_avg_durations[host] = sum(self._instance_durations[host]) / len(self._instance_durations[host])

                self.persist_durations()

                self._cleanup_entry(entry)
                entry.done_event.set()
                self._queue.task_done()
                await self._broadcast_queue_state()

    async def _process_entry(self, entry: QueueEntry, worker_id: int) -> tuple[float, float]:
        """Execute the Ollama request and stream results. Returns (total tool execution time, response time)."""
        payload = entry.payload
        task_type = entry.task_type

        if task_type == "chat":
            return await self._process_chat(entry, payload)
        elif task_type == "compress":
            await self._process_compress(entry, payload)
        elif task_type == "notification":
            await self._process_notification(entry, payload)
        elif task_type == "translate":
            await self._process_translate(entry, payload)
        elif task_type == "title_suggestion":
            await self._process_title_suggestion(entry, payload)
        elif task_type == "auto_title":
            await self._process_auto_title(entry, payload)
        return 0.0, 0.0

    async def _process_chat(self, entry: QueueEntry, payload: dict) -> tuple[float, float]:
        """Process a chat streaming request, with tool-calling support. Returns (total tool execution time, response time)."""
        ollama_host = payload["ollama_host"]
        req_data = payload["req_data"]
        conversation_id = payload["conversation_id"]
        raw_request = payload.get("raw_request")
        tool_calling_mode = payload.get("tool_calling_mode", "stream_intercept")

        client = httpx.AsyncClient()
        used_tools = []
        tool_time = 0.0
        response_time = 0.0
        t_start = time.time()
        
        try:
            tool_messages = list(req_data.get("messages", []))
            tools = req_data.get("tools")
            max_tool_rounds = 3
            tool_round = 0
            
            # Phase 1: Legacy Double Call mode (if requested)
            if tools and tool_calling_mode == "legacy_double":
                from .ia_tools import execute_tool
                has_moderation = any(t.get("function", {}).get("name") == "block_user_from_ia" for t in tools)
                moderation_instruction = ""
                if has_moderation:
                    moderation_instruction = (
                        " Si l'utilisateur est grossier, vulgaire, insultant, agressif ou s'il fait des demandes inappropriées ou abusives répétées, "
                        "ou si l'utilisateur te demande explicitement de le bloquer ou de tester la fonction de blocage, "
                        "tu DOIS impérativement appeler l'outil 'block_user_from_ia' avec une raison explicite. "
                    )
                tool_instruction = {
                    "role": "system",
                    "content": (
                        "Tu as accès à des outils (tools/functions) pour répondre aux questions. "
                        "Tu DOIS utiliser les outils disponibles pour obtenir des données factuelles. "
                        "IMPORTANT: Si ton API ne supporte pas l'appel d'outil natif ou si tu décides d'appeler un outil, "
                        "tu DOIS impérativement l'écrire sous ce format XML exact dans ta réponse :\n"
                        "<tool_call name=\"nom_de_l_outil\">\n"
                        "{\n"
                        "  \"nom_parametre\": \"valeur\"\n"
                        "}\n"
                        "</tool_call>\n"
                        + moderation_instruction
                    )
                }
                system_msgs = [m for m in tool_messages if m.get("role") == "system"]
                non_system = [m for m in tool_messages if m.get("role") != "system"]
                tool_detect_msgs = system_msgs + [tool_instruction] + non_system

                while tool_round < max_tool_rounds:
                    tool_round += 1
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
                        break

                    msg = tool_data.get("message", {})
                    tool_calls = msg.get("tool_calls")
                    direct_content = msg.get("content", "")
                    thinking_content = msg.get("thinking", "")

                    is_xml_fallback = False
                    if not tool_calls:
                        text_to_search = direct_content + "\n" + (thinking_content or "")
                        found_calls = []
                        import re
                        for match in re.finditer(r'<tool_call name="([^"]+)">\s*(.*?)\s*</tool_call>', text_to_search, re.DOTALL):
                            name = match.group(1)
                            args_str = match.group(2)
                            try:
                                args = json.loads(args_str)
                            except Exception:
                                try:
                                    args = json.loads(args_str.replace("'", '"'))
                                except Exception:
                                    args = {}
                            found_calls.append({"function": {"name": name, "arguments": args}})
                        if found_calls:
                            tool_calls = found_calls
                            is_xml_fallback = True

                    if not tool_calls:
                        break

                    if is_xml_fallback:
                        tool_messages.append({"role": "assistant", "content": direct_content})
                        tool_detect_msgs.append({"role": "assistant", "content": direct_content})
                    else:
                        tool_messages.append({"role": "assistant", "tool_calls": tool_calls})
                        tool_detect_msgs.append({"role": "assistant", "tool_calls": tool_calls})

                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        fn_name = fn.get("name", "")
                        fn_args = fn.get("arguments", {})
                        await entry.result_stream.put({"status": "tool_call", "tool_name": fn_name})
                        await entry.result_stream.put({"text": f"🔍 *Consultation des données : {fn_name}...*\n\n"})
                        if fn_name not in used_tools:
                            used_tools.append(fn_name)
                        t_tool_start = time.time()
                        try:
                            result = await execute_tool(fn_name, fn_args, user_id=entry.user_id)
                        except Exception as e:
                            result = json.dumps({"error": str(e)})
                        tool_time += (time.time() - t_tool_start)

                        if is_xml_fallback:
                            tool_messages.append({"role": "user", "content": f"Résultat de l'outil {fn_name}: {result}"})
                            tool_detect_msgs.append({"role": "user", "content": f"Résultat de l'outil {fn_name}: {result}"})
                        else:
                            tool_messages.append({"role": "tool", "content": result})
                            tool_detect_msgs.append({"role": "tool", "content": result})

            # Send initial thinking status (waiting for first token / prompt processing)
            await entry.result_stream.put({"status": "thinking"})

            # Streaming loop (Option A and final leg of Option B/D)
            while tool_round < max_tool_rounds:
                tool_round += 1
                
                # If we're executing tools in stream_intercept mode, remove tools from later requests to avoid infinite loops
                stream_req = {**req_data, "messages": tool_messages, "stream": True}
                if tool_round > 1:
                    stream_req.pop("tools", None)

                # Variables to control streaming chunk buffer for XML detection
                is_buffering_xml = (tools and tool_calling_mode == "stream_intercept")
                xml_buffer = ""
                detected_xml_call = False
                native_tool_calls = []

                full_response = ""
                in_think_block = False
                first_token = True

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
                            
                            # Check native tool calls
                            tc_list = data.get("message", {}).get("tool_calls")
                            if tc_list and tool_calling_mode == "stream_intercept":
                                native_tool_calls.extend(tc_list)
                                continue

                            token = data.get("message", {}).get("content", "")
                            if token:
                                full_response += token
                                
                                # Check for XML tool call start and buffer it
                                if is_buffering_xml:
                                    xml_buffer += token
                                    # If it looks like XML tool call, keep buffering without yielding
                                    if xml_buffer.strip().startswith("<tool_call") or "<tool_call" in xml_buffer:
                                        if "</tool_call>" in xml_buffer:
                                            detected_xml_call = True
                                            is_buffering_xml = False
                                            break # Exit client.stream reading loop to execute tool
                                        else:
                                            continue
                                    elif not xml_buffer.strip().startswith("<") and len(xml_buffer.strip()) > 12:
                                        # Not an XML call, flush buffer
                                        is_buffering_xml = False
                                        if first_token:
                                            first_token = False
                                            await entry.result_stream.put({"status": "generating"})
                                        await entry.result_stream.put({"text": xml_buffer})
                                        # Continue streaming normally for next tokens
                                        continue
                                    else:
                                        continue

                                if token:
                                    if first_token and response_time == 0.0:
                                        response_time = max(0.1, (time.time() - t_start) - tool_time)
                                    
                                    # Check for start of think block
                                    if "<think>" in token:
                                        in_think_block = True
                                        await entry.result_stream.put({"status": "thinking", "think": True})
                                        parts = token.split("<think>", 1)
                                        if parts[0]:
                                            if first_token:
                                                first_token = False
                                                await entry.result_stream.put({"status": "generating"})
                                            await entry.result_stream.put({"text": parts[0]})
                                        token = parts[1]
                                        
                                    if in_think_block:
                                        # Check for end of think block
                                        if "</think>" in token:
                                            parts = token.split("</think>", 1)
                                            if parts[0]:
                                                await entry.result_stream.put({"status": "thinking", "think_chunk": parts[0]})
                                            in_think_block = False
                                            await entry.result_stream.put({"status": "generating"})
                                            if parts[1]:
                                                first_token = False
                                                await entry.result_stream.put({"text": parts[1]})
                                        else:
                                            await entry.result_stream.put({"status": "thinking", "think_chunk": token})
                                    else:
                                        if first_token:
                                            first_token = False
                                            await entry.result_stream.put({"status": "generating"})
                                        await entry.result_stream.put({"text": token})
                                        
                            if data.get("done") and not detected_xml_call and not native_tool_calls:
                                if response_time == 0.0:
                                    response_time = max(0.1, (time.time() - t_start) - tool_time)
                                break
                        except json.JSONDecodeError:
                            pass

                # If a tool call was detected, execute it and do another round
                has_tool_call = bool(native_tool_calls) or detected_xml_call
                if has_tool_call and tool_calling_mode == "stream_intercept":
                    # Parse tools
                    parsed_calls = []
                    if detected_xml_call:
                        import re
                        match = re.search(r'<tool_call name="([^"]+)">\s*(.*?)\s*</tool_call>', xml_buffer, re.DOTALL)
                        if match:
                            name = match.group(1)
                            args_str = match.group(2)
                            try:
                                args = json.loads(args_str)
                            except Exception:
                                try:
                                    args = json.loads(args_str.replace("'", '"'))
                                except Exception:
                                    args = {}
                            parsed_calls.append({"function": {"name": name, "arguments": args}})
                    
                    for tc in native_tool_calls:
                        parsed_calls.append(tc)

                    if not parsed_calls:
                        # Fallback: if parse failed, flush buffer to user and stop
                        if xml_buffer:
                            await entry.result_stream.put({"status": "generating"})
                            await entry.result_stream.put({"text": xml_buffer})
                        break

                    from .ia_tools import execute_tool
                    # Notify tool executing
                    t_names = ", ".join(c["function"]["name"] for c in parsed_calls)
                    await entry.result_stream.put({"status": "tool_call", "tool_name": t_names})
                    await entry.result_stream.put({"text": f"🔍 *Consultation des données : {t_names}...*\n\n"})
                    
                    # Add assistant message
                    tool_messages.append({
                        "role": "assistant",
                        "content": xml_buffer if detected_xml_call else "",
                        "tool_calls": native_tool_calls if native_tool_calls else None
                    })

                    for call in parsed_calls:
                        fn_name = call["function"]["name"]
                        fn_args = call["function"]["arguments"]
                        if fn_name not in used_tools:
                            used_tools.append(fn_name)
                        t_tool_start = time.time()
                        try:
                            result = await execute_tool(fn_name, fn_args, user_id=entry.user_id)
                        except Exception as e:
                            result = json.dumps({"error": str(e)})
                        tool_time += (time.time() - t_tool_start)

                        if detected_xml_call:
                            tool_messages.append({"role": "user", "content": f"Résultat de l'outil {fn_name}: {result}"})
                        else:
                            tool_messages.append({"role": "tool", "content": result})

                    # Loop back for the next round of stream
                    continue
                else:
                    # No tool calls detected, flush any buffered content and exit
                    if is_buffering_xml and xml_buffer:
                        if first_token:
                            first_token = False
                            await entry.result_stream.put({"status": "generating"})
                        await entry.result_stream.put({"text": xml_buffer})

                    import re
                    clean_response = re.sub(r'<think>.*?</think>', '', full_response, flags=re.DOTALL).strip()
                    self._execute_post_stream_tool_calls(clean_response, tools, entry.user_id, used_tools)
                    meta = {
                        "model_info": entry.payload.get("model_info"),
                        "used_tools": used_tools,
                        "duration": response_time
                    }
                    saved_msg_id = self._save_bot_message(conversation_id, clean_response, meta=meta)
                    await entry.result_stream.put({
                        "done": True,
                        "full_response": clean_response,
                        "saved_by_worker": saved_msg_id is not None,
                        "meta": meta,
                    })
                    break
        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = f"Erreur IA ({type(e).__name__}): {str(e)[:200]}"
            await entry.result_stream.put({"text": error_msg, "done": True, "error": True})
        finally:
            await client.aclose()
        return tool_time, response_time

    def _save_bot_message(self, conversation_id: int, content: str, meta: dict = None):
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
                    content=content,
                    meta=meta
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
        num_ctx = payload.get("num_ctx", 4096)

        from .ia_compression import run_compaction, run_summary

        try:
            if mode == "compact":
                result = await run_compaction(text, url, model, num_ctx=num_ctx)
            elif mode == "summary":
                result = await run_summary(text, url, model, num_ctx=num_ctx)
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
        context_window = payload.get("context_window", 4096)

        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f"{ollama_host}/api/chat", json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.8, "num_predict": context_window}
                }, timeout=120.0)

            if res.status_code != 200:
                raise Exception(f"Ollama returned HTTP {res.status_code}: {res.text[:200]}")

            raw = res.json().get("message", {}).get("content", "")
            await entry.result_stream.put({"done": True, "result": raw})
        except Exception as e:
            await entry.result_stream.put({"done": True, "error": True, "result": str(e)})

    async def _process_translate(self, entry: QueueEntry, payload: dict):
        """Process a translation request (non-streaming)."""
        ollama_host = payload["ollama_host"]
        model = payload["model"]
        prompt = payload["prompt"]
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(f"{ollama_host}/api/chat", json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.1}
                }, timeout=45.0)

            if res.status_code != 200:
                raise Exception(f"Ollama returned HTTP {res.status_code}: {res.text[:200]}")

            raw = res.json().get("message", {}).get("content", "")
            await entry.result_stream.put({"done": True, "result": raw})
        except Exception as e:
            await entry.result_stream.put({"done": True, "error": True, "result": str(e)})

    async def _process_title_suggestion(self, entry: QueueEntry, payload: dict):
        """Generate a conversation title suggestion (non-streaming, fire-and-forget result via WebSocket)."""
        ollama_host = payload["ollama_host"]
        model = payload["model"]
        excerpt = payload["excerpt"]
        conv_id = payload["conversation_id"]
        user_id = payload["user_id"]
        try:
            timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(f"{ollama_host}/api/generate", json={
                    "model": model,
                    "prompt": _build_title_prompt(excerpt),
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 30}
                })
            if res.status_code == 200:
                raw = res.json().get("response", "")
                suggestion = _clean_title(raw)
                if suggestion:
                    await ws_manager.broadcast({
                        "type": "title_suggestion_ready",
                        "conversation_id": conv_id,
                        "user_id": user_id,
                        "suggestion": suggestion
                    })
                    return
            await ws_manager.broadcast({
                "type": "title_suggestion_ready",
                "conversation_id": conv_id,
                "user_id": user_id,
                "error": f"Ollama HTTP {res.status_code}"
            })
        except Exception as e:
            await ws_manager.broadcast({
                "type": "title_suggestion_ready",
                "conversation_id": conv_id,
                "user_id": user_id,
                "error": str(e)[:100]
            })

    async def _process_auto_title(self, entry: QueueEntry, payload: dict):
        """Generate a conversation title automatically (non-streaming, updates DB and pushes WebSocket)."""
        ollama_host = payload["ollama_host"]
        model = payload["model"]
        excerpt = payload["excerpt"]
        conv_id = payload["conversation_id"]
        try:
            timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(f"{ollama_host}/api/generate", json={
                    "model": model,
                    "prompt": _build_title_prompt(excerpt),
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 30}
                })
            if res.status_code == 200:
                raw = res.json().get("response", "")
                title_text = _clean_title(raw)
                if title_text:
                    from .database import SessionLocal
                    from .models import Conversation
                    with SessionLocal() as db:
                        c = db.query(Conversation).filter(Conversation.id == conv_id).first()
                        # Crucial safety check to prevent overwriting manual renames
                        if c and _is_default_title(c.title):
                            c.title = title_text
                            db.commit()
                            await ws_manager.broadcast({
                                "type": "conv_title_updated",
                                "conversation_id": conv_id,
                                "title": title_text
                            })
        except Exception as e:
            print(f"[IA Queue] Auto-title generation error: {e}", flush=True)

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

    def _execute_post_stream_tool_calls(self, response_text: str, tools: list, user_id: int, used_tools: list):
        if not tools:
            return
        
        import re
        import json
        tools_map = {t["function"]["name"]: t["function"] for t in tools}
        found_calls = []
        
        # 1. XML format
        for match in re.finditer(r'<tool_call name="([^"]+)">\s*(.*?)\s*</tool_call>', response_text, re.DOTALL):
            name = match.group(1)
            args_str = match.group(2)
            try:
                args = json.loads(args_str)
            except Exception:
                try:
                    args = json.loads(args_str.replace("'", '"'))
                except Exception:
                    args = {}
            found_calls.append((name, args))
            
        # 2. Python function call syntax fallback (e.g. tool_name("arg1", "arg2"))
        if not found_calls:
            for match in re.finditer(r'([a-zA-Z0-9_]+)\((.*?)\)', response_text):
                name = match.group(1)
                if name in tools_map:
                    args_str = match.group(2).strip()
                    args = {}
                    
                    # Try keyword arguments: key="val"
                    kw_matches = re.findall(r'(\w+)\s*=\s*["\']([^"\']*)["\']', args_str)
                    if kw_matches:
                        for k, v in kw_matches:
                            args[k] = v
                    else:
                        # Positional arguments: extract quoted strings
                        pos_args = re.findall(r'["\']([^"\']*)["\']', args_str)
                        params = list(tools_map[name].get("parameters", {}).get("properties", {}).keys())
                        for idx, val in enumerate(pos_args):
                            if idx < len(params):
                                args[params[idx]] = val
                                
                    found_calls.append((name, args))
                    
        # Execute each found tool call if it hasn't been executed yet
        from .ia_tools import execute_tool
        for name, args in found_calls:
            if name in tools_map and name not in used_tools:
                try:
                    print(f"[IA Queue] Executing post-stream tool call: {name}({args})", flush=True)
                    execute_tool(name, args, user_id=user_id)
                    used_tools.append(name)
                except Exception as e:
                    print(f"[IA Queue] Post-stream tool call {name} failed: {e}", flush=True)

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
        entry = self._by_user.get(user_id)
        if entry:
            host = entry.payload.get("ollama_host", "default")
            avg_dur = self._instance_avg_durations.get(host, self._avg_duration)
        else:
            avg_dur = self._avg_duration

        try:
            await ws_manager.broadcast({
                "type": "ia_queue_position",
                "user_id": user_id,
                "position": position,
                "estimated_wait": round(position * avg_dur),
                "avg_duration": round(avg_dur, 1),
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
