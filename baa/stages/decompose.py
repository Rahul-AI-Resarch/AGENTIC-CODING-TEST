"""Phase B — Feature decomposition: spec.json -> layered feature graph.

The single biggest lever for 'huge games in one shot': instead of generating
one giant file, explode the spec into 30-120 atomic FeatureCards across
layers L0..L7, each with explicit dependencies. Cards are then built and
tested bottom-up by the micro-loop.
"""
from __future__ import annotations

from baa.core.card import FeatureCard, LAYER_ORDER
from baa.llm.client import LLMClient

SYSTEM = f"""You are the DECOMPOSER of an autonomous game-building agent.
Input: a JSON build-spec. Output: a complete FEATURE GRAPH as JSON.

Rules:
- Every behavior in the spec becomes exactly ONE feature card.
  Nothing may be left uncovered; the fidelity_checklist items must each map
  to at least one card.
- Layers (bottom-up): {", ".join(LAYER_ORDER)}
  L0 engine/loop/camera/input, L1 physics core, L2 entities, L3 systems,
  L4 gameplay mechanics, L5 UI/HUD/screens, L6 content/levels, L7 feel/juice.
- depends_on may only reference cards in LOWER or SAME layer, never future ids.
- acceptance is one testable sentence ("when X then Y within Z").
- id is kebab-case ascii.

Return JSON:
{{"cards": [
  {{"id","title","layer","depends_on":[ids],"spec_fields":[paths],
    "acceptance":"..." }}, ...
]}}"""


def decompose(llm: LLMClient, spec: dict) -> list[FeatureCard]:
    user = (
        "Build spec:\n" + _dumps(spec) +
        "\n\nDecompose into the full feature graph now."
    )
    data = llm.complete_json(SYSTEM, user, tag="decompose")
    raw_cards = data.get("cards", [])
    if not isinstance(raw_cards, list) or len(raw_cards) < 8:
        raise ValueError(
            f"decomposition too shallow: expected >=8 cards, got {len(raw_cards)}"
        )
    cards = [FeatureCard.from_dict(rc) for rc in raw_cards]
    validate_graph(cards, spec)
    return cards


def validate_graph(cards: list[FeatureCard], spec: dict) -> None:
    ids = [c.id for c in cards]
    if len(ids) != len(set(ids)):
        dupes = {i for i in ids if ids.count(i) > 1}
        raise ValueError(f"duplicate card ids: {dupes}")

    id_set = set(ids)
    by_id = {c.id: c for c in cards}
    for c in cards:
        if c.layer not in LAYER_ORDER:
            raise ValueError(f"card {c.id}: unknown layer {c.layer!r}")
        if not c.acceptance.strip():
            raise ValueError(f"card {c.id}: empty acceptance contract")
        unknown = set(c.depends_on) - id_set
        if unknown:
            raise ValueError(f"card {c.id}: depends on unknown ids {unknown}")
        # dependency direction check: no upward deps
        li = LAYER_ORDER.index(c.layer)
        for d in c.depends_on:
            lj = LAYER_ORDER.index(by_id[d].layer)
            if lj > li:
                raise ValueError(
                    f"card {c.id}({c.layer}) depends on higher layer {d}"
                    f"({by_id[d].layer})"
                )
    acyclic_check(by_id)

    covered = coverage_ratio(by_id, spec)
    if covered < 0.9:
        raise ValueError(
            f"fidelity_checklist coverage {covered:.0%} < 90%; decomposition "
            "dropped behaviors"
        )


def acyclic_check(by_id: dict[str, FeatureCard]) -> None:
    """Kahn's algorithm — reject cyclic dependency graphs."""
    indeg = {cid: 0 for cid in by_id}
    children: dict[str, list[str]] = {cid: [] for cid in by_id}
    for cid, c in by_id.items():
        for d in c.depends_on:
            indeg[cid] += 1
            children[d].append(cid)
    queue = [cid for cid, n in indeg.items() if n == 0]
    seen = 0
    while queue:
        cid = queue.pop()
        seen += 1
        for ch in children[cid]:
            indeg[ch] -= 1
            if indeg[ch] == 0:
                queue.append(ch)
    if seen != len(by_id):
        raise ValueError("dependency graph has a cycle")


def coverage_ratio(by_id: dict[str, FeatureCard], spec: dict) -> float:
    """Fraction of fidelity_checklist items covered by some card.

    A checklist item counts as covered when a majority (>50%) of its
    significant words appear in some card's title+acceptance text.
    """
    checklist = spec.get("fidelity_checklist", [])
    if not checklist:
        return 0.0
    STOP = {"the", "and", "with", "when", "then", "that", "this", "from",
            "into", "should", "must", "within", "after", "before", "while",
            "each", "every", "behavior", "number", "works", "responds"}
    card_token_sets = []
    for c in by_id.values():
        toks = {w.strip(".,;:()") for w in
                (c.title + " " + c.acceptance).lower().split()} - {""}
        card_token_sets.append(toks)
    hits = 0
    for item in checklist:
        words = {w.strip(".,;:()") for w in str(item).lower().split()} - STOP
        words.discard("")
        if not words:
            hits += 1
            continue
        for ctoks in card_token_sets:
            overlap = len(words & ctoks) / len(words)
            if overlap > 0.5:
                hits += 1
                break
    return hits / len(checklist)


def _dumps(obj) -> str:
    import json

    return json.dumps(obj, indent=1)
