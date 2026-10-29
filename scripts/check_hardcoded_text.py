"""Detect user-facing text written directly in Svelte files instead of i18n keys.

Flags, with file:line:
  - text between tags that is not inside {...}
  - title / placeholder / aria-label / alt attributes with literal text
  - toast('...') and `|| '...'` fallbacks containing words

Usage:  python scripts/check_hardcoded_text.py [--quiet]
Exit code 1 when something is found (used by verify_i18n.py).
Lines ending with  <!-- i18n-ignore -->  or  // i18n-ignore  are skipped.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

SRC = os.path.join("frontend", "src")
WORD = re.compile(r"[A-Za-zÀ-ÿ]{2,}")
# Technical tokens that are not translatable copy
ALLOW = {"VS", "vs", "GIF", "IA", "AI", "LAN", "OK", "SSID", "URL", "JSON", "Alanbix", "ALANBIX",
         "Ollama", "OpenAI", "SearXNG", "Wi-Fi", "Discord", "Steam", "SE", "DE", "RR", "FFA", "px", "ms"}


CSS_WORDS = re.compile(r"\b(?:linear|ease(?:-in|-out)?|translate[XYZ]?|rotate|scale|transform|solid|dashed|inherit|none)\b")


def is_copy(text):
    text = re.sub(r"\$\{[^}]*\}", " ", text).strip()  # template placeholders are not copy
    if CSS_WORDS.search(text) and not re.search(r"[A-Za-zÀ-ÿ]{3,}\s+[A-Za-zÀ-ÿ]{3,}\s+[A-Za-zÀ-ÿ]{3,}", text):
        return False
    if not text or text.startswith("//"):
        return False
    words = WORD.findall(text)
    if not words:
        return False
    return any(w not in ALLOW for w in words)


def scan_file(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    hits = []
    # blank out <style> and <script> bodies but keep line numbers
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    markup = re.sub(r"<style[\s\S]*?</style>", blank, src)
    script_spans = [m.span() for m in re.finditer(r"<script[^>]*>[\s\S]*?</script>", markup)]
    markup_only = re.sub(r"<script[^>]*>[\s\S]*?</script>", blank, markup)
    lines = src.split("\n")

    def line_of(pos):
        return src.count("\n", 0, pos) + 1

    def ignored(ln):
        return "i18n-ignore" in lines[ln - 1]

    # text nodes: strip {...} expressions first so only literal text remains
    no_expr = markup_only
    while True:  # blank nested {...} from the innermost out
        nxt = re.sub(r"\{[^{}]*\}", lambda m: " " * len(m.group(0)), no_expr)
        if nxt == no_expr:
            break
        no_expr = nxt
    for m in re.finditer(r">([^<>]+)<", no_expr):
        if is_copy(m.group(1)):
            ln = line_of(m.start(1))
            if not ignored(ln):
                hits.append((ln, m.group(1).strip()))
    # string literals inside markup expressions, e.g. {ok ? 'Texte' : 'Autre'}
    for m in re.finditer(r"\{[^{}]*\}", markup_only):
        for lit in re.finditer(r"(['`])((?:(?!\1)[^\\\n])*)\1", m.group(0)):
            text = lit.group(2)
            if " " in text.strip() and is_copy(text) and not re.search(r"\$\{|\b(?:var|rgba?|translate|scale)\(", text):
                ln = line_of(m.start() + lit.start(2))
                if not ignored(ln):
                    hits.append((ln, text.strip()))
    for m in re.finditer(r'\b(?:title|placeholder|aria-label|alt)="([^"]*)"', no_expr):
        if is_copy(m.group(1)):
            ln = line_of(m.start(1))
            if not ignored(ln):
                hits.append((ln, m.group(1).strip()))
    # French sentences in <script> (error messages, labels built in code), console.* excluded
    french = re.compile(r"[éèêàçùûôî]|\b(?:le|la|les|des|du|une|vous|votre|pour|avec|aucun|erreur|impossible|veuillez)\b", re.I)
    for start, end in script_spans:
        for lit in re.finditer(r"(['`\"])((?:(?!\1)[^\\\n])*)\1", src[start:end]):
            text = lit.group(2)
            pos = start + lit.start(2)
            line_text = lines[line_of(pos) - 1]
            if "console." in line_text or "$t(" in text or "t)(" in text:
                continue
            if " " in text.strip() and french.search(text) and is_copy(text):
                ln = line_of(pos)
                if not ignored(ln):
                    hits.append((ln, text.strip()))
    for m in re.finditer(r"(?:toast\(\s*|\|\|\s*)(['`])((?:(?!\1).)*)\1", src):
        if is_copy(m.group(2)) and " " in m.group(2).strip():
            ln = line_of(m.start(2))
            if not ignored(ln):
                hits.append((ln, m.group(2).strip()))
    return sorted(set(hits))


def main():
    quiet = "--quiet" in sys.argv
    total = 0
    for root, _, files in os.walk(SRC):
        for name in sorted(files):
            if not name.endswith(".svelte"):
                continue
            path = os.path.join(root, name)
            hits = scan_file(path)
            total += len(hits)
            if hits and not quiet:
                for ln, text in hits:
                    print(f"{path}:{ln}: {text[:90]}")
    print(f"{total} texte(s) en dur trouvé(s).")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
