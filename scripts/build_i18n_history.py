"""Build backend/static/i18n_history/<lang>.json from git history.

For every key, lists the values that backend/static/i18n/<lang>.json shipped
in past versions (excluding the current one). At startup the backend uses it
to drop stale copies of old defaults from data/i18n, so text updates reach
existing installs while real admin customisations are kept.

Run from the repo root after changing shipped translations:
    python scripts/build_i18n_history.py
"""
import json
import os
import subprocess

STATIC_DIR = "backend/static/i18n"
OUT_DIR = "backend/static/i18n_history"


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in sorted(os.listdir(STATIC_DIR)):
        if not name.endswith(".json"):
            continue
        path = f"{STATIC_DIR}/{name}"
        with open(path, encoding="utf-8-sig") as f:
            current = json.load(f)
        history = {}
        for rev in git("log", "--format=%H", "--", path).decode().split():
            try:
                old = json.loads(git("show", f"{rev}:{path}").decode("utf-8-sig"))
            except (subprocess.CalledProcessError, ValueError):
                continue
            for key, value in old.items():
                if isinstance(value, str) and value != current.get(key):
                    values = history.setdefault(key, [])
                    if value not in values:
                        values.append(value)
        with open(f"{OUT_DIR}/{name}", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"{name}: {len(history)} keys with past defaults")


if __name__ == "__main__":
    main()
