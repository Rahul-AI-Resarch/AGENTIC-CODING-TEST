"""Id and slug helpers.

Run ids are short, sortable and filesystem-safe so they can be used directly as
directory names under ``data/runs/<run_id>/``.
"""
from __future__ import annotations

import re
import secrets
import time

_ALLOWED = re.compile(r"[^a-z0-9]+")


def new_run_id() -> str:
    """Sortable, collision-resistant: ``<base36 millis>-<6 hex>``."""
    stamp = int(time.time() * 1000)
    base36 = _to_base36(stamp)
    suffix = secrets.token_hex(3)
    return f"{base36}-{suffix}"


def _to_base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out: list[str] = []
    while value:
        value, rem = divmod(value, 36)
        out.append(alphabet[rem])
    return "".join(reversed(out))


def slugify(text: str, max_len: int = 48) -> str:
    slug = _ALLOWED.sub("-", (text or "").lower()).strip("-")
    return (slug[:max_len].rstrip("-") or "site")


def unique_slug(text: str, taken: set[str]) -> str:
    base = slugify(text)
    if base not in taken:
        return base
    for n in range(2, 1000):
        candidate = f"{base}-{n}"
        if candidate not in taken:
            return candidate
    return f"{base}-{secrets.token_hex(2)}"
