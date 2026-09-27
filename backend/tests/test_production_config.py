import re
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
CONFIG_PATH = ROOT_DIR / "frontend" / "src" / "lib" / "config.ts"
DOCKERFILE_STANDALONE = ROOT_DIR / "Dockerfile.standalone"
BUILD_DIR = ROOT_DIR / "frontend" / "build"


def test_config_ts_isolates_dev_port_8000():
    """
    Ensure frontend/src/lib/config.ts NEVER references port 8000
    outside of an explicit 'if (import.meta.env.DEV)' block.
    This prevents regression where standalone Docker/Unraid on port 41481
    gets redirected to dead port 8000.
    """
    assert CONFIG_PATH.exists(), f"Missing config file: {CONFIG_PATH}"
    content = CONFIG_PATH.read_text(encoding="utf-8")

    lines = content.splitlines()
    in_dev_block = False
    brace_depth = 0
    dev_brace_start = -1
    violations = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        if "import.meta.env.DEV" in stripped and "if" in stripped:
            in_dev_block = True
            dev_brace_start = brace_depth

        if in_dev_block:
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= dev_brace_start:
                in_dev_block = False
        else:
            brace_depth += stripped.count("{") - stripped.count("}")

        # Check for 8000 or :8000 outside DEV block and outside comments
        if not in_dev_block and not stripped.startswith(("//", "/*", "*")):
            if ":8000" in stripped or ("8000" in stripped and not stripped.startswith("import")):
                violations.append((idx, line))

    assert not violations, (
        f"Found port 8000 referenced outside import.meta.env.DEV: {violations}"
    )


def test_config_ts_production_defaults():
    """
    Ensure production fallbacks use relative URL ('') for REST API
    and window.location.host for WebSockets.
    """
    assert CONFIG_PATH.exists()
    content = CONFIG_PATH.read_text(encoding="utf-8")

    # REST API production default must be relative path ('')
    assert "return '';" in content or 'return "";' in content, (
        "Production API fallback in config.ts must return empty string '' for same-origin routing"
    )

    # WebSocket must use window.location.host
    assert "window.location.host" in content, (
        "WebSocket URL in config.ts must use window.location.host in production"
    )


def test_dockerfile_standalone_exposed_port():
    """
    Ensure Dockerfile.standalone consistently exposes and runs on port 41481.
    """
    assert DOCKERFILE_STANDALONE.exists()
    content = DOCKERFILE_STANDALONE.read_text(encoding="utf-8")

    assert "EXPOSE 41481" in content, "Dockerfile.standalone must EXPOSE 41481"
    assert "41481" in content and "--port" in content, (
        "Dockerfile.standalone CMD must run uvicorn on port 41481"
    )


def test_compiled_bundle_has_no_dev_port_leak():
    """
    If frontend/build exists, scan all compiled assets to verify that
    neither ':8000' nor 'localhost:8000' leaked into the client bundle.
    """
    if not BUILD_DIR.exists():
        pytest.skip("frontend/build directory does not exist yet (run npm run build first)")

    forbidden_patterns = [
        re.compile(r":8000\b"),
        re.compile(r"localhost:8000\b"),
    ]

    violations = []
    scanned_files = 0

    for file_path in BUILD_DIR.rglob("*"):
        if file_path.is_file() and file_path.suffix in [".js", ".html", ".css"]:
            scanned_files += 1
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for pat in forbidden_patterns:
                match = pat.search(text)
                if match:
                    violations.append((file_path.name, match.group(0)))

    assert scanned_files > 0, "No files found to inspect in frontend/build"
    assert not violations, (
        f"Production build bundle contains illegal dev port references: {violations}"
    )
