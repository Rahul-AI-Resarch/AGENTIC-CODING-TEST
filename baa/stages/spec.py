"""Phase A — Intake & Spec.

Turns a one-line user prompt into a complete, machine-checkable spec.json.
Hard architectural constraints are injected by the agent (not negotiable):
single HTML file, CDN-only libraries, procedural assets, no copyrighted art.
"""
from __future__ import annotations

from baa.llm.client import LLMClient

SYSTEM = """You are the SPEC architect of an autonomous game-building agent.
Given a user's request, produce a JSON build-specification for a browser game.

NON-NEGOTIABLE CONSTRAINTS you must encode in every spec:
- output is ONE self-contained index.html (inline CSS + JS)
- third-party libs allowed ONLY via public CDN <script> tags
  (three.js, cannon-es, rapier3d, howler, pixi — pick what the genre needs)
- ALL art/audio procedurally generated (canvas drawing, shaders, WebAudio);
  never reference external image/audio files
- recreate GAMEPLAY MECHANICS faithfully but use ORIGINAL names/art
  (genre-faithful clone, not asset rip-off)

Return JSON with EXACTLY these top-level keys:
{
 "game_id": "kebab-case-slug",
 "title": "original title",
 "genre": "...",
 "dimension": "2d-top | 2d-side | 3d-follow | 3d-free",
 "camera": {...}, "controls": {...},
 "libs": ["cdn url strings"],
 "view": {"width_px": int, "height_px": int, "clear_color": "#hex"},
 "physics": {"engine": "...", "fixed_timestep_ms": int, "gravity": ...},
 "entities": [{"name","count","behavior_summary"}],
 "systems": [{"name","params":{"numeric ranges incl. perf budget"}}],
 "mechanics": [{"name","rules":[{"param":"value"}]}],
 "ui": {"hud_elements":[...], "screens":["menu","play","pause","gameover"]},
 "content": {"levels": int|null, "procedural": [...]},
 "feel": {"audio": [...], "particles": [...], "camera_fx": [...]},
 "perf_target": {"fps_min": int, "frame_budget_ms": int},
 "fidelity_checklist": ["atomic, testable behavior statements covering EVERY feature above"]
}
Every field must be concrete and non-null. Numbers over vibes."""


def generate_spec(llm: LLMClient, prompt: str) -> dict:
    user = f"User request:\n{prompt}\n\nProduce the full build spec now."
    spec = llm.complete_json(SYSTEM, user, tag="spec")
    validate_spec(spec)
    return spec


REQUIRED_KEYS = [
    "game_id", "title", "genre", "dimension", "controls", "libs",
    "view", "entities", "systems", "mechanics", "ui", "perf_target",
    "fidelity_checklist",
]


def validate_spec(spec: dict) -> None:
    """Gate A1 — completeness checklist. Raises on any missing/empty field."""
    missing = [k for k in REQUIRED_KEYS if k not in spec or spec[k] in (None, "", [], {})]
    if missing:
        raise ValueError(f"spec incomplete, missing keys: {missing}")
    cl = spec["fidelity_checklist"]
    if not isinstance(cl, list) or len(cl) < 8:
        raise ValueError(
            "fidelity_checklist must contain >=8 atomic testable behaviors "
            f"(got {len(cl) if isinstance(cl, list) else 'non-list'})"
        )
    libs = spec.get("libs", [])
    if isinstance(libs, list):
        bad = [u for u in libs if isinstance(u, str) and not u.startswith(("https://", "http://"))]
        if bad:
            raise ValueError(f"libs must be absolute CDN urls, got: {bad}")
