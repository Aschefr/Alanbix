"""How the AI queue shares a burst of players between a fast and a slow server (real HTTP).

Starts two fake Ollama servers on localhost (fast and slow answers), feeds the real queue manager
PLAYERS chat requests at once, all assigned to the slow server like the old round-robin could do,
and prints who answered how many and how long the burst took. No database, no real AI server.
    backend/venv/Scripts/python scripts/load_ai_queue.py [PLAYERS] [FAST_SECONDS] [SLOW_SECONDS]
"""
import asyncio
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.ia_queue import IAQueueManager, QueueEntry  # noqa: E402

MODEL = "gemma4:e4b"


def fake_ollama(port: int, delay: float, counter: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, ctype="application/json"):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send(json.dumps({"models": [{"name": MODEL}], "version": "0.0.0"}).encode())

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            counter[port] = counter.get(port, 0) + 1
            time.sleep(delay)
            lines = [{"message": {"content": "Bonjour !"}}, {"done": True}]
            self._send("\n".join(json.dumps(x) for x in lines).encode(), "application/x-ndjson")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


async def main(players: int, fast: float, slow: float):
    counter = {}
    servers = [fake_ollama(41901, fast, counter), fake_ollama(41902, slow, counter)]
    insts = [{"url": "http://127.0.0.1:41901", "model": MODEL, "label": "fast"},
             {"url": "http://127.0.0.1:41902", "model": MODEL, "label": "slow"}]
    q = IAQueueManager()
    with patch.object(IAQueueManager, "_enabled_instances", return_value=insts), \
         patch.object(IAQueueManager, "load_persisted_durations"), \
         patch.object(IAQueueManager, "persist_durations"), \
         patch.object(q, "_default_model", return_value=MODEL):
        await q.start()
        entries = []
        for i in range(players):
            e = QueueEntry(priority=10, created_at=time.time(), user_id=i + 1, task_type="chat", payload={
                "ollama_host": insts[1]["url"], "conversation_id": 0, "model_info": {},
                "req_data": {"model": MODEL, "stream": True, "options": {},
                             "messages": [{"role": "user", "content": "Salut"}]}})
            entries.append(e)
        t0 = time.monotonic()
        for e in entries:
            await q.enqueue(e)
        await asyncio.wait_for(asyncio.gather(*(e.done_event.wait() for e in entries)), timeout=600)
        took = time.monotonic() - t0
        first_wait = q._wait_for(players)
        await q.stop()
    for s in servers:
        s.shutdown()
    by = {"fast": counter.get(41901, 0), "slow": counter.get(41902, 0)}
    old = (players / 2) * slow  # round-robin: half the players behind the slow server, one at a time
    print(f"{players} players, fast {fast}s, slow {slow}s: answered fast={by['fast']} slow={by['slow']}, "
          f"burst took {took:.1f}s (old round-robin about {old:.1f}s, all on the slow one {players * slow:.1f}s); "
          f"estimate shown to the last one {first_wait}s")


if __name__ == "__main__":
    a = sys.argv[1:]
    asyncio.run(main(int(a[0]) if a else 40, float(a[1]) if len(a) > 1 else 0.2, float(a[2]) if len(a) > 2 else 1.0))
