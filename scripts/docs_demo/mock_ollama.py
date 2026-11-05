"""Tiny stand-in for Ollama, used only to illustrate the docs: no model, canned answers.
It lets the demo server show an instance online and finish its background AI tasks.
Runs inside the demo container (see run.py)."""
import itertools
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = ["gemma4:e4b", "qwen3.8:27b"]
ANSWERS = {
    "fr": [
        "Belle perf ! Tu as tenu le choc jusqu'au bout, et ton dernier match a fait lever la moitié de la salle.",
        "Parcours solide : deux victoires nettes avant de tomber sur plus fort. La revanche t'attend au prochain tournoi.",
        "Tu n'as pas gagné, mais tu as rendu chaque manche pénible pour tes adversaires. On appelle ça du talent.",
    ],
    "en": [
        "Great run! You held on to the very end, and your last match got half the room on its feet.",
        "Solid showing: two clean wins before meeting someone stronger. Your rematch is waiting at the next tournament.",
        "You did not win, but you made every round painful for your opponents. That is called talent.",
    ],
}
answers = itertools.cycle(ANSWERS.get(os.environ.get("DEMO_LANG", "fr"), ANSWERS["fr"]))


PLAYERS = ["Admin", "PixelHunter", "BlazeRunner", "RocketQueen", "DragonByte", "Zephyr", "LaserCat", "NightHawk", "GlitchMaster", "VoltStrike",
           "Orbit", "ShadowNinja", "CyberWolf", "ArcticFox", "TurboGamer", "Sable", "CosmicDust", "IcePhoenix", "StormBringer", "QuantumLeap", "Basalt"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/version"):
            return self._json({"version": "0.12.0"})
        if self.path.startswith("/api/ps"):
            return self._json({"models": []})
        return self._json({"models": [{"name": m, "model": m, "size": 9_600_000_000} for m in MODELS]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            req = {}
        text = next(answers)
        if self.path.startswith("/api/show"):
            return self._json({"capabilities": ["completion", "tools"], "model_info": {"general.context_length": 32768}})
        if self.path.startswith("/api/embed"):
            return self._json({"embeddings": [[0.0] * 8], "embedding": [0.0] * 8})
        if req.get("format") == "json" or req.get("response_format"):  # Tournament summaries: one message per player
            text = json.dumps({"messages": [{"player": p, "message": next(answers)} for p in PLAYERS]}, ensure_ascii=False)
        msg = {"role": "assistant", "content": text}
        chunk = {"model": req.get("model", MODELS[0]), "message": msg, "response": text, "done": True}
        self._json(chunk)  # Non-streamed even when asked: one final NDJSON line is a valid stream


ThreadingHTTPServer(("0.0.0.0", 11434), Handler).serve_forever()
