"""Thinking bench: each AI task of Alanbix, with the model's thinking on and off, on invented demo data.

It goes through the real app (prompts, tools, queue) of a throwaway demo server, never the dev stack:
    python scripts/docs_demo/run.py fr <image built from this branch>
    python scripts/ai_bench/think_bench.py --ollama http://<server>:11434 --models gemma4:e4b bonsai-2:27b qwen3.8:27b

Tasks, and whether the model uses tools:
    chat       private assistant, as a player (tools)
    public     @Alanbix in the public chat (tools)
    compress   conversation compression, compact and summary (no tools)
    translate  admin's automatic translation of interface strings (no tools)
    notify     closing messages of a tournament, JSON (no tools)

One model is loaded at a time: the bench waits while another model is loaded on the server and
unloads each model once measured. --dry-run checks the bench itself against the demo's fake Ollama.
Results (answers included, demo data only) go to scripts/ai_bench/results/, which git ignores.
"""
import argparse
import json
import random
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "docs_demo"))
from seed import Api, score_matches  # noqa: E402

MOCK_OLLAMA = "http://ollama.lan:11434"  # the demo container's fake Ollama (see docs_demo/run.py)
CONTEXT = 16384
TEMPERATURE = 0.2
NOTIFY_PLAYERS = ["Zephyr", "Orbit", "Sable", "Basalt"]


# ── helpers ─────────────────────────────────────────────────────────────────

def norm(text):
    """Lower case, no accents, no markdown, single spaces: what the checks compare."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[*_`#>]", "", text)).lower().strip()


def has(text, *alternatives):
    t = norm(text)
    return any(norm(a) in t for a in alternatives if a)


FR_WORDS = {"le", "la", "les", "des", "est", "et", "tu", "pas", "une", "du", "avec", "pour", "dans", "qui", "au", "en", "sont", "il", "je", "ton", "de"}
EN_WORDS = {"the", "is", "and", "you", "not", "with", "for", "in", "who", "your", "are", "of", "to"}
ES_WORDS = {"el", "los", "las", "es", "y", "tu", "con", "para", "en", "del", "una", "que", "por"}


def lang_score(text, words):
    tokens = re.findall(r"[a-z']+", norm(text))
    return sum(t in words for t in tokens)


def looks_french(text):
    """Not more English than French (a short list of names has neither)."""
    return lang_score(text, FR_WORDS) >= lang_score(text, EN_WORDS)


def leaked(text):
    """Reasoning or a tool call written as text instead of an answer."""
    return bool(re.search(r"</?think>|<tool_call|\"name\"\s*:\s*\"get_", text or ""))


def median(values):
    return round(statistics.median(values), 1) if values else None


def http_json(method, url, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


# ── the AI server: one model at a time ──────────────────────────────────────

class Server:
    def __init__(self, url, dry_run, wait_minutes):
        self.url, self.dry_run, self.wait_minutes = url.rstrip("/"), dry_run, wait_minutes

    def check_model(self, model):
        if self.dry_run:
            return
        names = {m["name"] for m in http_json("GET", self.url + "/api/tags")["models"]}
        if model not in names and f"{model}:latest" not in names:
            raise SystemExit(f"{model} is not on {self.url}")

    def wait_free(self, model):
        """Wait while another model is loaded: loading a second one could overflow the server."""
        if self.dry_run:
            return
        deadline = time.time() + self.wait_minutes * 60
        while True:
            loaded = [m["name"] for m in http_json("GET", self.url + "/api/ps").get("models", [])]
            others = [m for m in loaded if m != model]
            if not others:
                return
            if time.time() > deadline:
                raise SystemExit(f"Still loaded after {self.wait_minutes} min: {', '.join(others)}. Stopped.")
            print(f"  waiting, loaded on the server: {', '.join(others)}", flush=True)
            time.sleep(30)

    def unload(self, model):
        if self.dry_run:
            return
        try:
            http_json("POST", self.url + "/api/generate", {"model": model, "keep_alive": 0}, timeout=120)
            print(f"  unloaded {model}", flush=True)
        except (OSError, urllib.error.HTTPError) as e:
            print(f"  unload failed for {model}: {e}", flush=True)


# ── the app ─────────────────────────────────────────────────────────────────

class App:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.api = Api(self.base)

    def call(self, *args, **kwargs):
        return self.api.call(*args, **kwargs)

    def configure(self, saved, ollama, model, thinking):
        cfg = dict(saved)
        cfg.update({
            "ollama_instances": [{"url": ollama, "label": "Bench", "model": model, "enabled": True, "priority": 0}],
            "model": model, "temperature": TEMPERATURE, "context_window": CONTEXT,
            # No knowledge search: it would load an embedding model next to the chat model
            "rag_enabled": False, "rag_suggestion_enabled": False, "network_tools_enabled": False,
            "think_chat": thinking, "think_tasks": thinking,
        })
        self.call("POST", "/ia/config", cfg)
        time.sleep(1)  # the queue workers restart

    def stream(self, user, prompt, conv_id):
        """Asks the private assistant like the app does; returns the streamed text and the tool statuses."""
        req = urllib.request.Request(self.base + "/ia/stream", method="POST",
                                     data=json.dumps({"prompt": prompt, "conversation_id": conv_id, "lang": "fr"}).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.api.login(user)})
        text, tools, error = "", [], None
        with urllib.request.urlopen(req, timeout=600) as r:
            for raw in r:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                d = json.loads(line[6:])
                if d.get("status") == "tool_call":
                    tools.append(d.get("tool_name"))
                if d.get("text") and not d.get("done"):
                    text += d["text"]
                if d.get("done"):
                    if d.get("error"):
                        error = d.get("text")
                    break
        return text, tools, error


# ── ground truth, read from the demo data before each run ───────────────────

def ground_truth(app):
    users = {u["id"]: u for u in app.call("GET", "/room/users")}
    name = {uid: u["username"] for uid, u in users.items()}
    seat = {u["username"]: u.get("seat_id") for u in users.values()}
    tournaments = {t["name"]: t for t in app.call("GET", "/tournaments")}

    def winner(tname):
        bracket = app.call("GET", f"/tournaments/{tournaments[tname]['id']}")["bracket"]
        final = max((m for m in bracket if m["id"]["s"] == 1), key=lambda m: m["id"]["r"])
        return name[final["p"][final["score"].index(max(final["score"]))]]

    me = next(uid for uid, n in name.items() if n == "PixelHunter")
    pending = []
    for t in tournaments.values():
        if t["status"] != "RUNNING":
            continue
        for m in app.call("GET", f"/tournaments/{t['id']}")["bracket"]:
            scored = m.get("score") and all(s is not None for s in m["score"])
            if me in m["p"] and 0 not in m["p"] and not scored:
                pending += [name.get(p) for p in m["p"] if p != me and p in name]
    iron = app.call("GET", f"/tournaments/{tournaments['Iron Arena Showdown']['id']}")["bracket"]
    opponent = next(name[p] for m in iron if me in m["p"] and 0 not in m["p"]
                    and not (m.get("score") and all(s is not None for s in m["score"])) for p in m["p"] if p != me)
    board = app.call("GET", "/dashboard/stats", as_user="PixelHunter")["leaderboard"]
    mine = next(r for r in board if r["username"] == "PixelHunter")
    duo = next(t for t in app.call("GET", f"/tournaments/{tournaments['Rocket Duo']['id']}/teams") if t["name"] == "Turbo Duo")
    warmup = next(n for n in tournaments if n.startswith("Échauffement") or n.startswith("Goal Rush Warm"))
    return {
        "pending_opponents": sorted(set(pending)), "opponent": opponent, "opponent_seat": seat[opponent],
        "my_rank": mine["rank"], "my_points": f"{mine['points']:g}",
        "leader": board[0]["username"], "castle_winner": winner("Castle Siege Open"),
        "warmup": warmup, "warmup_winner": winner(warmup),
        "running": sorted(n for n, t in tournaments.items() if t["status"] == "RUNNING"),
        "duo": [m["username"] for m in duo["members"]], "seat_cosmic": seat["CosmicDust"],
    }


def seat_said(text, seat_id):
    """T1_S7, or "table 1 ... place 7" in a sentence."""
    if not seat_id:
        return False
    t = norm(text)
    table, place = re.match(r"T(\d+)_S(\d+)", seat_id).groups()
    return norm(seat_id) in t or bool(re.search(rf"table {table}\b.{{0,25}}\b(place|siege|seat|poste) (n\D{{0,3}})?{place}\b", t))


def chat_questions(gt):
    no_score = lambda a: not re.search(r"\d+\s*[-–:à]\s*\d+", norm(a))  # noqa: E731
    denies = lambda a: has(a, "pas de tournoi", "aucun", "n'existe", "introuvable", "ne trouve", "pas trouve", "inconnu", "pas de trace")  # noqa: E731
    return [
        ("next_match", "C'est quand mon prochain match, et contre qui ?", lambda a: has(a, *gt["pending_opponents"])),
        ("opponent_seat", f"Où est assis {gt['opponent']} ?", lambda a: seat_said(a, gt["opponent_seat"])),
        ("my_rank", "Je suis à quelle place au classement général, avec combien de points ?",
         lambda a: re.search(rf"\b{re.escape(gt['my_points'])}\b", norm(a).replace(",", ".")) is not None),
        ("castle_winner", "Qui a gagné le Castle Siege Open ?", lambda a: has(a, gt["castle_winner"])),
        ("rules", "Quelles sont les règles de Neon Drift ?", lambda a: has(a, "3 tours", "trois tours")),
        ("running", "Quels tournois sont en cours en ce moment ?", lambda a: all(has(a, n) for n in gt["running"])),
        ("team", "Qui est dans l'équipe Turbo Duo du tournoi Rocket Duo ?", lambda a: all(has(a, n) for n in gt["duo"])),
        ("breakfast", "À quelle heure est servi le petit-déjeuner ?", lambda a: has(a, "8 h", "8h", "8:00", "08:00", "8 heures")),
        ("trap", "Quel est mon score dans le tournoi Rocket League Masters ?", lambda a: no_score(a) and denies(a)),
    ]


def public_questions(gt):
    return [
        ("leader", "LaserCat", "@Alanbix qui est en tête du classement général ?", lambda a: has(a, gt["leader"])),
        ("seat", "ShadowNinja", "@Alanbix à quelle place est assis CosmicDust ?", lambda a: seat_said(a, gt["seat_cosmic"])),
        ("warmup_winner", "IcePhoenix", f"@Alanbix qui a gagné l'{gt['warmup']} ?", lambda a: has(a, gt["warmup_winner"])),
        ("rules", "CyberWolf", "@Alanbix c'est quoi les règles de Castle Siege ?", lambda a: has(a, "standard")),
    ]


TRANSLATE = [
    "Ton prochain match commence dans {minutes} minutes à la table {table}.",
    "{user} a rejoint l'équipe {team_name}.",
    "Il reste {waiting} joueurs en attente, tu es en position {position}.",
    "Le score de {player} a été corrigé par un organisateur.",
    "Impossible d'enregistrer le score : le match n'est pas encore lancé.",
    "Bravo {user}, tu remportes {tournament} !",
]


# ── tasks ───────────────────────────────────────────────────────────────────

def run_chat(app, gt, record):
    for qid, question, check in chat_questions(gt):
        conv = app.call("POST", "/ia/conversations", {"title": "Banc réflexion"}, as_user="PixelHunter")["id"]
        t0 = time.time()
        try:
            text, tools, error = app.stream("PixelHunter", question, conv)
        except (OSError, urllib.error.HTTPError) as e:
            text, tools, error = "", [], str(e)
        seconds = time.time() - t0
        msgs = app.call("GET", f"/ia/conversations/{conv}/messages", as_user="PixelHunter")["messages"]
        bot = next((m for m in reversed(msgs) if m["role"] == "bot"), None)
        answer = (bot or {}).get("content") or text
        used = ((bot or {}).get("meta") or {}).get("used_tools") or tools
        record("chat", qid, question, answer, seconds, error=error, tools=used,
               ok=bool(answer) and not error and check(answer) and not leaked(answer) and looks_french(answer))


def run_public(app, gt, record):
    for qid, asker, question, check in public_questions(gt):
        msg = app.call("POST", "/public-chat/messages", {"content": question}, as_user=asker)
        t0, reply, error = time.time(), None, None
        if msg.get("alanbix_notice"):
            error = f"notice {msg['alanbix_notice']}"
        while not reply and not error and time.time() - t0 < 300:
            time.sleep(1)
            reply = next((m for m in app.call("GET", "/public-chat/messages?limit=30", as_user=asker)
                          if m.get("is_bot") and m.get("reply_to_id") == msg["id"]), None)
        answer = (reply or {}).get("content") or ""
        error = error or (None if reply else "no answer within 300 s")
        record("public", qid, question, answer, time.time() - t0, error=error,
               ok=bool(answer) and check(answer) and not leaked(answer) and looks_french(answer))


def run_compress(app, gt, record):
    conv = next(c for c in app.call("GET", "/ia/conversations", as_user="PixelHunter") if c["title"] == "Mon prochain match")
    original = app.call("GET", f"/ia/conversations/{conv['id']}/messages", as_user="PixelHunter")["messages"]
    facts = sorted({f for m in original if m["role"] == "bot" for f in re.findall(r"\*\*(.+?)\*\*", m["content"])})
    for mode in ("compact", "summary"):
        app.call("DELETE", f"/ia/compress/{conv['id']}", as_user="PixelHunter")
        t0, error = time.time(), None
        try:
            app.call("POST", f"/ia/compress/{conv['id']}", {"mode": mode}, as_user="PixelHunter")
        except SystemExit as e:  # the demo Api turns HTTP errors into SystemExit
            error = str(e)
        seconds = time.time() - t0
        context = app.call("GET", f"/ia/conversations/{conv['id']}/messages", as_user="PixelHunter")["compression"]["context"] or ""
        kept = [f for f in facts if has(context, f)]
        record("compress", mode, f"facts: {facts}", context, seconds, error=error, kept=f"{len(kept)}/{len(facts)}",
               ok=not error and len(kept) == len(facts) and not leaked(context))
    app.call("DELETE", f"/ia/compress/{conv['id']}", as_user="PixelHunter")


def run_translate(app, gt, record):
    words = {"en": EN_WORDS, "es": ES_WORDS}
    for target in ("en", "es"):
        for i, text in enumerate(TRANSLATE):
            t0, error, out = time.time(), None, ""
            try:
                out = app.call("POST", "/api/i18n/auto-translate", {"text": text, "source_lang": "fr", "target_lang": target})["translated_text"]
            except SystemExit as e:
                error = str(e)
            same_placeholders = sorted(re.findall(r"\{\w+\}", out)) == sorted(re.findall(r"\{\w+\}", text))
            right_language = lang_score(out, words[target]) >= lang_score(out, FR_WORDS)
            clean = bool(out) and "\n" not in out.strip() and not leaked(out) and norm(out) != norm(text)
            record("translate", f"{target}{i + 1}", text, out, time.time() - t0, error=error,
                   ok=not error and same_placeholders and right_language and clean)


def run_notify(app, gt, record, label):
    games = {g["name"]: g["id"] for g in app.call("GET", "/tournaments/games")}
    zero = {k: 0 for k in ("pts_winner", "pts_second", "pts_third", "pts_participation", "pts_per_match", "pts_per_goal")}
    t = app.call("POST", "/tournaments", {"name": f"Banc {label}", "game_id": games["Iron Arena"],
                                          "config": {**zero, "bracket_type": "single_elim"}})  # no points: the leaderboard stays
    for p in NOTIFY_PLAYERS:
        app.call("POST", f"/tournaments/{t['id']}/join", as_user=p)
    app.call("POST", f"/tournaments/{t['id']}/start", {})
    score_matches(app.api, t["id"], 99, random.Random(7))
    t0 = time.time()
    app.call("POST", f"/tournaments/{t['id']}/close", {})
    got, failed = {}, None
    while len(got) < len(NOTIFY_PLAYERS) and not failed and time.time() - t0 < 240:
        time.sleep(1)
        for p in NOTIFY_PLAYERS:
            if p not in got:
                n = next((n for n in app.call("GET", "/notifications", as_user=p)
                          if n["type"] == "tournament_closed" and (n.get("metadata") or {}).get("tournament_id") == t["id"]), None)
                if n:
                    got[p] = n["content"]
        failed = next((n["content"] for n in app.call("GET", "/notifications", as_user="Admin")
                       if n["type"] == "system" and f"Banc {label}" in (n.get("title") or "")), None)
    answer = json.dumps(got, ensure_ascii=False)
    ok = len(got) == len(NOTIFY_PLAYERS) and all(looks_french(m) and not leaked(m) for m in got.values())
    record("notify", "closing", f"{len(NOTIFY_PLAYERS)} players", answer, time.time() - t0,
           error=failed or (None if got else "no message within 240 s"), players=f"{len(got)}/{len(NOTIFY_PLAYERS)}", ok=ok)


TASKS = {"chat": run_chat, "public": run_public, "compress": run_compress, "translate": run_translate, "notify": run_notify}


# ── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="http://localhost:41590", help="demo server (docs_demo/run.py fr)")
    ap.add_argument("--ollama", help="Ollama server the demo server can reach")
    ap.add_argument("--models", nargs="+", default=["gemma4:e4b"])
    ap.add_argument("--modes", default="off,on", help="thinking modes, in order")
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--wait", type=int, default=15, help="minutes to wait while another model is loaded")
    ap.add_argument("--dry-run", action="store_true", help="check the bench against the demo's fake Ollama")
    a = ap.parse_args()
    if not a.ollama and not a.dry_run:
        ap.error("--ollama is required (or --dry-run)")
    ollama = MOCK_OLLAMA if a.dry_run else a.ollama
    server = Server(ollama, a.dry_run, a.wait)
    app = App(a.base)
    tasks = [t for t in a.tasks.split(",") if t]
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M") + ("-dry" if a.dry_run else ""))
    out.mkdir(parents=True, exist_ok=True)

    saved_ia = app.call("GET", "/ia/config")
    saved_ia.pop("system_prompt", None)
    saved_chat = app.call("GET", "/public-chat/config")
    app.call("PUT", "/public-chat/config", {**saved_chat, "ai_cooldown_seconds": 0, "block_duplicates": False})
    rows = []
    try:
        for model in a.models:
            server.check_model(model)
            for mode in a.modes.split(","):
                server.wait_free(model)
                app.configure(saved_ia, ollama, model, mode == "on")
                print(f"{model}, thinking {mode}", flush=True)
                log = (out / f"{model.replace(':', '-').replace('/', '-')}__think-{mode}.jsonl").open("a", encoding="utf-8")
                for p in range(1, a.passes + 1):
                    gt = ground_truth(app)

                    def record(task, qid, question, answer, seconds, ok, error=None, **extra):
                        row = {"model": model, "think": mode, "pass": p, "task": task, "id": qid, "ok": bool(ok),
                               "seconds": round(seconds, 1), "error": error, "question": question, "answer": answer, **extra}
                        rows.append(row)
                        log.write(json.dumps(row, ensure_ascii=False) + "\n")
                        log.flush()
                        print(f"  pass {p} {task:9} {qid:14} {'ok  ' if ok else 'FAIL'} {seconds:6.1f} s"
                              + (f"  tools={len(extra['tools'])}" if "tools" in extra else "")
                              + (f"  {error}" if error else ""), flush=True)

                    for task in tasks:
                        if task == "notify":
                            run_notify(app, gt, record, f"{model} {mode} {p}")
                        else:
                            TASKS[task](app, gt, record)
                log.close()
            server.unload(model)
    finally:
        app.call("POST", "/ia/config", saved_ia)
        app.call("PUT", "/public-chat/config", saved_chat)
        write_summary(rows, out, a)


def write_summary(rows, out, a):
    groups = {}
    for r in rows:
        groups.setdefault((r["model"], r["task"], r["think"]), []).append(r)
    lines = [f"# Thinking bench, {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Passes: {a.passes}. Context {CONTEXT}, temperature {TEMPERATURE}. Demo data (invented)." + (" DRY RUN (fake Ollama)." if a.dry_run else ""), "",
             "| Model | Task | Thinking | Right | Tool used | Median s | Max s | Errors |", "|---|---|---|---|---|---|---|---|"]
    for (model, task, think), rs in groups.items():
        secs = [r["seconds"] for r in rs if not r["error"]]
        tools = f"{sum(bool(r.get('tools')) for r in rs)}/{len(rs)}" if task == "chat" else ""
        lines.append(f"| {model} | {task} | {think} | {sum(r['ok'] for r in rs)}/{len(rs)} | {tools} | {median(secs)} | "
                     f"{max(secs) if secs else ''} | {sum(bool(r['error']) for r in rs)} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nResults: {out}")


if __name__ == "__main__":
    main()
