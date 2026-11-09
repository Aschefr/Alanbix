"""How the recommended models were chosen: the measured scores, the rules, and the labels they give.

Measured on 2026-11-09 with the Alanbix bench (ai-bench/alanbix/think_bench.py) on the demo data: an RTX 3090,
Ollama 0.40.15 with its default version of each model, a 32K context, thinking on in the chats and off in the
background tasks (the app's defaults), 2 passes. Memory is read on the card (nvidia-smi, the model alone, minus the
empty card); Ollama's own reading under-counts the small gemma4 models.

The rules are the common method of Alanbix, OmniBank and Sentinel; the weights and the 90 % chat threshold are the
user's choices for Alanbix. The labels are computed, never written by hand: test_model_comparison checks that they
give the catalogue of ia_model_catalog.
"""

# Weight of each task in the note, and the questions asked per pass
TASKS = {
    "chat": {"weight": 0.40, "questions": 13},       # private chat with tools
    "public": {"weight": 0.30, "questions": 6},      # @Alanbix in the public chat
    "compress": {"weight": 0.10, "questions": 2},    # conversation summary
    "translate": {"weight": 0.10, "questions": 12},  # message translation
    "notify": {"weight": 0.10, "questions": 1},      # end of tournament messages
}
CHATS_MIN = 0.90      # under 90 % right on the two chats together: not kept
TASK_MIN = 0.50       # under half the points on any task in any pass: not kept
MADE_UP_MAX = 2       # invented or pretended answers tolerated; from 3 a model is not recommended (user's choice)
FAST_SECONDS = 20     # median chat answer above this: never a pick
TIE = 0.3             # within this many points, the lightest model wins
CARDS = (8, 12, 16, 24)  # GB of video memory; a model fits when it needs at most the card minus 1 GB

# Right answers per pass; seconds is the median chat answer; memory_gb on the card at 32K; made_up over both passes
MEASURED = [
    {"name": "qwen3.8:27b", "quantization": "Q4_K_M", "memory_gb": 18.7, "seconds": 5.2, "made_up": 0,
     "passes": [{"chat": 13, "public": 6, "compress": 2, "translate": 12, "notify": 1}] * 2},
    {"name": "gemma4:31b", "quantization": "Q4_K_M", "memory_gb": 21.7, "seconds": 14.1, "made_up": 0,
     "passes": [{"chat": 13, "public": 6, "compress": 2, "translate": 12, "notify": 1}] * 2},
    {"name": "bonsai-2:27b", "quantization": "Q2_0", "memory_gb": 9.5, "seconds": 8.3, "made_up": 0,
     "passes": [{"chat": 13, "public": 6, "compress": 2, "translate": 12, "notify": 1}] * 2},
    {"name": "gemma4:e4b", "quantization": "Q4_K_M", "memory_gb": 4.9, "seconds": 3.4, "made_up": 1,
     "passes": [{"chat": 13, "public": 6, "compress": 2, "translate": 12, "notify": 1},
                {"chat": 12, "public": 6, "compress": 2, "translate": 12, "notify": 1}]},
    {"name": "gemma4:e2b", "quantization": "Q4_K_M", "memory_gb": 3.5, "seconds": 2.3, "made_up": 3,
     "passes": [{"chat": 11, "public": 6, "compress": 2, "translate": 12, "notify": 1},
                {"chat": 12, "public": 6, "compress": 2, "translate": 12, "notify": 1}]},
]


def note(m) -> float:
    """Quality out of 10: each task's share of right answers over all passes, weighted."""
    total = 0.0
    for task, spec in TASKS.items():
        right = sum(p[task] for p in m["passes"])
        total += spec["weight"] * right / (spec["questions"] * len(m["passes"]))
    return round(10 * total, 1)


def exclusions(m) -> list:
    """Why a model is not kept, as {code, params, tasks}; tasks are the cells to highlight."""
    out = []
    asked = len(m["passes"]) * (TASKS["chat"]["questions"] + TASKS["public"]["questions"])
    right = sum(p["chat"] + p["public"] for p in m["passes"])
    if right < CHATS_MIN * asked:
        out.append({"code": "chats", "params": {"right": right, "asked": asked}, "tasks": ["chat", "public"]})
    for task, spec in TASKS.items():
        for i, p in enumerate(m["passes"], 1):
            if p[task] < TASK_MIN * spec["questions"]:
                out.append({"code": "task", "params": {"pass": i, "right": p[task], "asked": spec["questions"]},
                            "tasks": [task]})
    if m["made_up"] > MADE_UP_MAX:
        out.append({"code": "made_up", "params": {"count": m["made_up"],
                                                  "asked": len(m["passes"]) * TASKS["chat"]["questions"]},
                    "tasks": ["chat"]})
    return out


def _best(candidates):
    """Best note; within TIE of it, the lightest model (unknown memory counts as the heaviest)."""
    if not candidates:
        return None
    top = max(c["note"] for c in candidates)
    close = [c for c in candidates if top - c["note"] <= TIE + 1e-9]
    return min(close, key=lambda c: c["memory_gb"] if c["memory_gb"] is not None else 1e9)["name"]


def comparison() -> dict:
    """The table shown under the recommended models, with the labels the rules give."""
    rows = [{**m, "note": note(m), "excluded": exclusions(m)} for m in MEASURED]
    kept = [r for r in rows if not r["excluded"]]
    fast = [r for r in kept if r["seconds"] < FAST_SECONDS]
    top = _best(fast)
    cards = {c: _best([r for r in fast if r["memory_gb"] is not None and r["memory_gb"] <= c - 1]) for c in CARDS}
    labels = {"top": top, "alternative": _best([r for r in kept if r["name"] != top]),
              "minimum": cards[8], "recommended": cards[12]}
    for r in rows:
        r["labels"] = [k for k, name in labels.items() if name == r["name"]]
        r["cards"] = [c for c, name in cards.items() if name == r["name"]]
    rows.sort(key=lambda r: (-r["note"], r["memory_gb"] or 1e9))
    return {"tasks": TASKS, "models": rows, "labels": labels, "cards": cards, "fast_seconds": FAST_SECONDS,
            "tie": TIE, "chats_min": CHATS_MIN}
