import os
import sys
import re
from pathlib import Path

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "frontend" / "src" / "lib" / "config.ts"
BUILD_DIR = ROOT_DIR / "frontend" / "build"
DOCKERFILE_STANDALONE = ROOT_DIR / "Dockerfile.standalone"

def check_config_source() -> bool:
    print("--- 1. VÉRIFICATION DU CODE SOURCE (config.ts) ---")
    if not CONFIG_PATH.exists():
        print(f"[ERREUR] Le fichier {CONFIG_PATH} n'existe pas.")
        return False

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify that '8000' is not mentioned outside 'import.meta.env.DEV' blocks
    # Specifically, check that resolveApiUrl() and resolveWsUrl() only reference 8000 under DEV
    lines = content.splitlines()
    in_dev_block = False
    brace_depth = 0
    dev_brace_start = -1
    violations = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        
        # Track if we are inside if (import.meta.env.DEV) { ... }
        if "import.meta.env.DEV" in stripped and "if" in stripped:
            in_dev_block = True
            dev_brace_start = brace_depth

        if in_dev_block:
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= dev_brace_start:
                in_dev_block = False
        else:
            brace_depth += stripped.count("{") - stripped.count("}")

        # Check for :8000 or 8000 outside DEV block and outside comments
        if not in_dev_block and not stripped.startswith(("//", "/*", "*")):
            if ":8000" in stripped or ("8000" in stripped and not stripped.startswith("import")):
                violations.append((idx, line))

    if violations:
        print("[ERREUR] Référence au port 8000 trouvée hors d'un bloc 'import.meta.env.DEV' :")
        for line_no, text in violations:
            print(f"  Ligne {line_no}: {text}")
        return False

    # Check that production API default return is empty string ''
    prod_api_return = re.search(r"//\s*In production[^\n]*\n\s*return\s*['\"]['\"];", content)
    if not prod_api_return and "return '';" not in content and 'return "";' not in content:
        print("[ERREUR] config.ts ne retourne pas une chaîne vide '' par défaut pour l'API en production.")
        return False

    # Check that production WS uses window.location.host
    if "window.location.host" not in content:
        print("[ERREUR] config.ts n'utilise pas 'window.location.host' pour la connexion WebSocket de production.")
        return False

    print("✅ frontend/src/lib/config.ts : Strictement conforme (port 8000 isolé dans DEV).")
    return True


def check_production_bundle() -> bool:
    print("\n--- 2. VÉRIFICATION DU BUNDLE COMPILÉ (frontend/build) ---")
    if not BUILD_DIR.exists():
        print(f"[INFO] Le dossier de build {BUILD_DIR} n'existe pas encore. Lancez 'npm run build' pour le générer.")
        return True

    forbidden_patterns = [
        re.compile(r":8000\b"),
        re.compile(r"localhost:8000\b"),
        re.compile(r"http://[a-zA-Z0-9.-]+:8000\b"),
    ]

    violations = []
    scanned_count = 0

    for file_path in BUILD_DIR.rglob("*"):
        if file_path.is_file() and file_path.suffix in [".js", ".html", ".css", ".json"]:
            scanned_count += 1
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                for pat in forbidden_patterns:
                    match = pat.search(text)
                    if match:
                        snippet_start = max(0, match.start() - 30)
                        snippet_end = min(len(text), match.end() + 30)
                        violations.append((file_path.relative_to(ROOT_DIR), match.group(0), text[snippet_start:snippet_end].replace("\n", " ")))
            except Exception as e:
                print(f"[ATTENTION] Impossible de lire {file_path}: {e}")

    if violations:
        print(f"[ERREUR] Le bundle de production contient des références interdites à des ports de dev ({len(violations)} trouvées) :")
        for fpath, match_str, snippet in violations:
            print(f"  Fichier : {fpath}")
            print(f"  Trouvé  : {match_str}")
            print(f"  Contexte: ...{snippet}...\n")
        return False

    print(f"✅ {scanned_count} fichiers inspectés dans frontend/build : Aucune fuite de port (:8000) détectée.")
    return True


def check_dockerfile() -> bool:
    print("\n--- 3. VÉRIFICATION DE DOCKERFILE.STANDALONE ---")
    if not DOCKERFILE_STANDALONE.exists():
        print(f"[ERREUR] {DOCKERFILE_STANDALONE} introuvable.")
        return False

    with open(DOCKERFILE_STANDALONE, "r", encoding="utf-8") as f:
        content = f.read()

    if "EXPOSE 41481" not in content:
        print("[ERREUR] Dockerfile.standalone doit exposer le port unifié 41481 (EXPOSE 41481).")
        return False

    if "--port" not in content or "41481" not in content:
        print("[ERREUR] Dockerfile.standalone doit démarrer uvicorn sur le port 41481.")
        return False

    print("✅ Dockerfile.standalone : Port unifié 41481 correctement configuré.")
    return True


def main() -> int:
    success = True
    if not check_config_source():
        success = False
    if not check_production_bundle():
        success = False
    if not check_dockerfile():
        success = False

    print("\n-----------------------------------------------------------")
    if success:
        print("🎉 CONTRÔLE RÉUSSI : Aucun risque de blocage réseau en production/Unraid.")
        return 0
    else:
        print("❌ CONTRÔLE ÉCHOUÉ : Des anomalies de configuration ont été détectées.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
