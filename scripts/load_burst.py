"""Reproduce the server freeze seen during a LAN (2026-11-11): a burst of authenticated requests.

After a score entry every open browser reloads ~8 endpoints at once. With more requests in flight
than the database pool holds, the server froze (QueuePool timeout, /health not answering).

Starts the backend on a throwaway database with invented players, sends BURST requests at once
while timing /health, and prints what happened. Run from the repository root:
    backend/venv/Scripts/python scripts/load_burst.py [BURST]
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PORT = 41799
BASE = f"http://127.0.0.1:{PORT}"
PATHS = ["/me", "/notifications/unread-count", "/tournaments", "/tournaments/games", "/room/users",
         "/room/layout", "/dashboard/stats", "/dashboard/team-leaderboard"]


def start_server(db_path: str) -> subprocess.Popen:
    env = {**os.environ, "DATABASE_PATH": db_path, "PYTHONUNBUFFERED": "1"}
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=ROOT / "backend", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def make_token(db_path: str) -> str:
    """An invented player in the throwaway database, and a token for them."""
    os.environ["DATABASE_PATH"] = db_path
    sys.path.insert(0, str(ROOT / "backend"))
    from datetime import timedelta
    from app import auth, models
    from app.database import SessionLocal
    with SessionLocal() as db:
        if not db.query(models.User).filter(models.User.username == "BurstTester").first():
            db.add(models.User(username="BurstTester", hashed_password="x"))
            db.commit()
    return auth.create_access_token({"sub": "BurstTester"}, timedelta(hours=1))


async def main(burst: int):
    tmp = tempfile.mkdtemp(prefix="alanbix_burst_")
    db_path = os.path.join(tmp, "alanbix.db")
    server = start_server(db_path)
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for _ in range(120):
                try:
                    if (await client.get(f"{BASE}/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
            token = make_token(db_path)
            headers = {"Authorization": f"Bearer {token}"}

            health = []
            stop = asyncio.Event()

            async def probe():
                while not stop.is_set():
                    t = time.monotonic()
                    try:
                        await client.get(f"{BASE}/health", timeout=60)
                    except httpx.HTTPError:
                        pass
                    health.append(time.monotonic() - t)
                    await asyncio.sleep(0.2)

            async def one(path):
                t = time.monotonic()
                try:
                    r = await client.get(f"{BASE}{path}", headers=headers)
                    return r.status_code, time.monotonic() - t
                except httpx.HTTPError as e:
                    return type(e).__name__, time.monotonic() - t

            prober = asyncio.create_task(probe())
            await asyncio.sleep(0.5)
            started = time.monotonic()
            results = await asyncio.gather(*(one(PATHS[i % len(PATHS)]) for i in range(burst)))
            took = time.monotonic() - started
            stop.set()
            await prober

        codes = {}
        for code, _ in results:
            codes[code] = codes.get(code, 0) + 1
        print(f"burst={burst} took {took:.1f}s  status={codes}  slowest request={max(t for _, t in results):.1f}s  "
              f"slowest /health={max(health):.1f}s")
    finally:
        server.terminate()
        try:
            out, _ = server.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            out, _ = server.communicate()
        if "QueuePool" in out:
            print("server log: QueuePool limit reached", out.count("QueuePool limit"), "time(s)")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 40))
