"""Fidelity gate — spec numbers vs. built GAME_DATA table (pure code).

Every numeric rule in the spec should appear as a constant in the final
GAME_DATA literal within tolerance. This is the anti-hallucination check:
the LLM can't claim 'ghosts move at 0.9x player speed' if the data table
says 1.5.
"""
from __future__ import annotations

import re


def extract_game_data(html: str) -> dict:
    """Pull the `const GAME_DATA = {...}` literal via brace matching."""
    m = re.search(r"const\s+GAME_DATA\s*=\s*", html)
    if not m:
        return {}
    i = m.end()
    if i >= len(html) or html[i] != "{":
        return {}
    depth, j = 0, i
    in_str: str | None = None
    while j < len(html):
        ch = html[j]
        if in_str:
            if ch == "\\":
                j += 2; continue
            if ch == in_str:
                in_str = None
        elif ch in "'\"`":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    blob = html[i : j + 1]
    # tolerate trailing commas / single quotes before json.loads
    cleaned = re.sub(r",\s*([}\]])", r"\1", blob)
    cleaned = cleaned.replace("'", '"')
    # strip JS expressions: keep only plain literals
    cleaned = re.sub(r":\s*[A-Za-z_$][\w$.]*\s*,", ": 0,", cleaned)
    cleaned = re.sub(r":\s*[A-Za-z_$][\w$.]*\s*\}", ": 0}", cleaned)
    # quote bare identifier keys:  { wind: ... } -> { "wind": ... }
    cleaned = re.sub(r'([{,]\s*)([A-Za-z_$][\w$]*)\s*:', r'\1"\2":', cleaned)
    import json

    try:
        return json.loads(cleaned)
    except Exception:
        return {}


def flatten(d, prefix="") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(flatten(v, f"{prefix}[{i}]"))
    elif isinstance(d, (int, float)) and not isinstance(d, bool):
        out[prefix] = float(d)
    return out


def audit_spec_numbers(spec: dict, html: str, tol: float = 0.25) -> dict:
    """Compare every numeric spec param against GAME_DATA constants by name."""
    data = flatten(extract_game_data(html))
    results = []
    for group_key in ("systems", "mechanics"):
        for item in spec.get(group_key, []) or []:
            if not isinstance(item, dict):
                continue
            params = item.get("params") or item.get("rules") or {}
            if isinstance(params, list):
                merged = {}
                for r in params:
                    if isinstance(r, dict):
                        merged.update(r)
                params = merged
            for pname, pval in (params or {}).items():
                num = _first_number(pval)
                if num is None:
                    continue
                match = _find_constant(data, str(pname))
                if match is None:
                    results.append({"param": pname, "expect": num,
                                    "found": None, "pass": False})
                else:
                    ok = abs(match - num) <= max(abs(num) * tol, 1e-6)
                    results.append({"param": pname, "expect": num,
                                    "found": match, "pass": ok})
    passed = sum(1 for r in results if r["pass"])
    return {
        "pass": len(results) == 0 or passed >= max(1, int(len(results) * 0.8)),
        "checked": len(results), "passed": passed, "details": results[:40],
    }


def _first_number(v) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        if m:
            return float(m.group())
    if isinstance(v, list) and v:
        return _first_number(v[0])
    return None


def _split_camel(s: str) -> list[str]:
    """camelCase/PascalCase -> words; snake/kebab/dots split too."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def _find_constant(flat: dict[str, float], name: str) -> float | None:
    tokens = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]
    best, best_score = None, 0.0
    for key, val in flat.items():
        ktoks = _split_camel(key)
        inter = len(set(tokens) & set(ktoks))
        score = inter / max(len(set(tokens)), 1)
        if score > best_score:
            best, best_score = val, score
    return best if best_score >= 0.5 else None
