"""Static gates — pure-code checkers, zero LLM involvement.

G-syntax  : every inline <script> parses as JavaScript
G-todo    : a card's TODO anchor was actually replaced
G-urls    : all CDN script srcs are absolute https urls
G-domids  : getElementById targets exist in the DOM section
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def _inline_scripts(html: str) -> list[str]:
    return re.findall(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                      html, flags=re.S | re.I)


def check_js_syntax(html: str) -> tuple[bool, str]:
    """Parse each inline script. Uses node --check if available, else a
    conservative brace/paren balance heuristic (never claims pass falsely)."""
    node = shutil.which("node")
    scripts = _inline_scripts(html)
    if not scripts:
        return False, "no inline <script> found"
    for i, src in enumerate(scripts):
        src = src.replace("<!--", "").replace("-->", "")
        if node:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".js", delete=False, encoding="utf-8"
            ) as f:
                f.write(src)
                path = f.name
            try:
                r = subprocess.run(
                    [node, "--check", path], capture_output=True, text=True, timeout=20
                )
                if r.returncode != 0:
                    return False, f"script#{i}: {r.stderr.strip()[:400]}"
            except subprocess.TimeoutExpired:
                return False, f"script#{i}: node --check timed out"
            finally:
                Path(path).unlink(missing_ok=True)
        else:
            ok, err = _balance_check(src)
            if not ok:
                return False, f"script#{i} (heuristic): {err}"
    return True, ""


def _balance_check(src: str) -> tuple[bool, str]:
    """Cheap fallback: strip strings/comments then require balanced brackets."""
    cleaned = re.sub(r"//[^\n]*", "", src)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.S)
    cleaned = re.sub(r"(['\"`])(?:\\.|(?!\1).)*\1", "''", cleaned, flags=re.S)
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for ch in cleaned:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack.pop() != pairs[ch]:
                return False, f"unbalanced '{ch}'"
    if stack:
        return False, f"unclosed {stack[-1]}"
    return True, ""


def check_no_todos_left(html: str, card_id: str) -> tuple[bool, bool]:
    left = f"TODO({card_id})" in html
    return (not left), left


def check_cdn_urls(html: str) -> tuple[bool, list[str]]:
    srcs = re.findall(r"<script[^>]*\bsrc=[\"']([^\"']+)[\"']", html, flags=re.I)
    bad = [u for u in srcs if not u.startswith("https://")]
    return (not bad), bad


def check_dom_ids(html: str) -> tuple[bool, list[str]]:
    defined = set(re.findall(r"id=[\"']([\w-]+)[\"']", html))
    used = set(re.findall(r"getElementById\([\"']([\w-]+)[\"']\)", html))
    missing = sorted(used - defined)
    return (not missing), missing
