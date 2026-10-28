"""Phase C — Scaffold: skeleton-first generation.

Before any real code is written, produce a numbered-section skeleton of the
final index.html: every section has an id anchor, stub functions with exact
signatures, and DATA TABLES as literals (no magic numbers later). The
micro-loop fills sections one card at a time; gates diff against this file.
"""
from __future__ import annotations

from baa.core.card import FeatureCard, LAYER_ORDER
from baa.llm.client import LLMClient

SYSTEM = """You are the SCAFFOLDER of an autonomous game-building agent.
Produce the EMPTY SKELETON of a single-file browser game HTML. No logic yet.

Structure required (each section wrapped in a marker comment):
  /*==SECTION:<id>==*/  ...content...  /*==END:<id>==*/
Sections, in order:
  head        : meta, title, CDN <script src=...> tags from spec.libs
  css         : layout + hud styles (rules may be empty placeholders)
  dom         : canvas + HUD element ids referenced by ui cards
  data        : ALL tunable constants as a single `const GAME_DATA = {...}`
                literal derived from spec (speeds, sizes, counts, colors)
  core-engine : stub fns for loop/timestep/camera/input per L0 cards
  physics     : stub fns per L1 cards
  entities    : stub classes/fns per L2 cards
  systems     : stub fns per L3 cards
  mechanics   : stub fns per L4 cards
  ui          : stub fns per L5 cards
  content     : stub fns per L6 cards
  feel        : stub fns per L7 cards
  boot        : main() calling every init stub in dependency order
Rules:
- Every feature card listed below MUST own exactly the sections shown and
  every stub fn name must appear so later patches can target it.
- Stubs bodies: `/* TODO(card-id) */` only. NEVER implement behavior here.
- Output ONLY the html document text, nothing else."""


def build_scaffold(llm: LLMClient, spec: dict, cards: list[FeatureCard]) -> str:
    card_lines = "\n".join(
        f"- {c.id} [{c.layer}] owns-section-for: {c.title} :: {c.acceptance}"
        for c in sorted(cards, key=lambda c: LAYER_ORDER.index(c.layer))
    )
    user = (
        f"SPEC:\n{_json(spec)}\n\nFEATURE CARDS ({len(cards)}):\n{card_lines}\n\n"
        "Emit the full skeleton HTML now."
    )
    html = llm.complete(SYSTEM, user, tag="scaffold")
    validate_scaffold(html, cards)
    return html


def validate_scaffold(html: str, cards: list[FeatureCard]) -> None:
    if "<html" not in html.lower():
        raise ValueError("scaffold is not an HTML document")
    required_sections = [
        "head", "css", "dom", "data", "core-engine", "physics", "entities",
        "systems", "mechanics", "ui", "content", "feel", "boot",
    ]
    missing = [
        s for s in required_sections
        if f"/*==SECTION:{s}==*/" not in html
    ]
    if missing:
        raise ValueError(f"scaffold missing section markers: {missing}")
    # every card id must be mentioned (as a TODO anchor) so patches can find it
    unanchored = [c.id for c in cards if f"TODO({c.id})" not in html]
    if len(unanchored) > max(2, len(cards) // 10):
        raise ValueError(
            f"scaffold has no anchors for too many cards: {unanchored[:10]}"
        )


def extract_section(html: str, section_id: str) -> str | None:
    start = html.find(f"/*==SECTION:{section_id}==*/")
    if start == -1:
        return None
    end = html.find(f"/*==END:{section_id}==*/", start)
    if end == -1:
        return None
    return html[start + len(f"/*==SECTION:{section_id}==*/"):end]


def replace_section(html: str, section_id: str, new_body: str) -> str:
    marker_open = f"/*==SECTION:{section_id}==*/"
    marker_close = f"/*==END:{section_id}==*/"
    start = html.find(marker_open)
    end = html.find(marker_close, start)
    if start == -1 or end == -1:
        raise ValueError(f"cannot replace unknown section {section_id!r}")
    return html[: start + len(marker_open)] + new_body + html[end:]


def _json(obj) -> str:
    import json

    return json.dumps(obj, indent=1)
