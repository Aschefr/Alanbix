"""Starts a throwaway Alanbix server with invented data, for the documentation screenshots.

    python scripts/docs_demo/run.py fr     # http://localhost:41590, volume alanbix_docs_fr
    python scripts/docs_demo/run.py en     # http://localhost:41591, volume alanbix_docs_en

It never touches the dev stack or ./data. Needs Docker and Pillow. Each run starts from an empty volume.
It runs the latest published image; to show an unpublished version, build one and pass its name after the language.
"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE = "aschefr/alanbix:latest"
PORTS = {"fr": 41590, "en": 41591}


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, **kwargs)


def main(lang, image=IMAGE):
    name, port = f"alanbix_docs_{lang}", PORTS[lang]
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(["docker", "volume", "rm", name], capture_output=True)
    docker("run", "-d", "--name", name, "-p", f"{port}:41481", "-v", f"{name}:/app/data",
           "--add-host", "ollama.lan:127.0.0.1", "-e", f"DEMO_LANG={lang}", image, capture_output=True)
    url = f"http://localhost:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/health", timeout=2)
            break
        except OSError:
            time.sleep(1)
    else:
        raise SystemExit("The server did not start")
    docker("cp", str(HERE / "mock_ollama.py"), f"{name}:/tmp/mock_ollama.py")
    docker("exec", "-d", name, "python", "/tmp/mock_ollama.py")
    subprocess.run([sys.executable, str(HERE / "seed.py"), url, lang], check=True)
    docker("exec", "-i", "-w", "/app", "-e", "PYTHONPATH=/app", name, "python", "-",
           input=(HERE / "seed_in_container.py").read_bytes())
    print(f"Ready: {url}")


if __name__ == "__main__":
    main(*sys.argv[1:])
