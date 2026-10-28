"""Phase D — the micro-loop: TEST-FIRST -> IMPLEMENT -> VERIFY -> REGRESS.

This is where 'Kimi tests each thing' happens. For one FeatureCard:
 1. an acceptance test is written BEFORE any implementation code exists
 2. the LLM fills ONLY this card's stub functions in the working HTML
 3. gates verify: syntax, the card's own test, perf, spec-fidelity numbers
 4. all previously passed cards' tests are re-run (regression)
Statuses: PASS / PATCHED / QUARANTINED drive the conductor's next move.
"""
from __future__ import annotations

import time
from pathlib import Path

from baa.core.card import CardStatus, FeatureCard
from baa.gates.static import check_js_syntax, check_no_todos_left
from baa.stages.scaffold import extract_section, replace_section

SECTION_BY_LAYER = {
    "L0-engine": ["core-engine"],
    "L1-physics": ["physics"],
    "L2-entities": ["entities"],
    "L3-systems": ["systems"],
    "L4-mechanics": ["mechanics"],
    "L5-ui": ["ui", "dom", "css"],
    "L6-content": ["content"],
    "L7-feel": ["feel"],
}

TESTER_SYSTEM = """You write HEADLESS ACCEPTANCE TESTS for one feature of a
browser game. The game lives in a single HTML file; you may assume a global
`window.__BAAMock` harness exists exposing:
  loadHTML(path), stepFrames(n), dispatchKey(key), getState(), pixelSample()
Emit a JSON object {"test_fn": "<async function body as string>",
"assertions": ["plain english list"]}.
The test must FAIL if the feature is unimplemented and PASS only when the
acceptance contract holds. No network, no external files."""

IMPL_SYSTEM = """You implement EXACTLY ONE feature card inside an existing
single-file game skeleton. Rules:
- Replace ONLY the stub bodies belonging to TODO(<card-id>) anchors.
- Keep every other line byte-identical. Do not rename functions.
- Use constants from GAME_DATA; never inline magic numbers.
- No copyrighted names/assets; procedural everything.
Output format: for each section you changed, emit
  /*==SECTION:<id>==*/ ...new full section body... /*==END:<id>*/
Nothing else outside those blocks."""


def run_card(ctx, card: FeatureCard, spec: dict, skeleton_path: Path) -> None:
    work_path = ctx.run_dir / "work.html"
    html = work_path.read_text() if work_path.exists() else skeleton_path.read_text()
    card.status = CardStatus.IN_PROGRESS.value
    sections = SECTION_BY_LAYER[card.layer]

    # ---- 1. TEST-FIRST ----------------------------------------------------
    if not card.test_source:
        card.test_source = _write_test(ctx, card, spec)
        _save_test(ctx, card)

    # ---- 2/3. IMPLEMENT + VERIFY (bounded attempts) ------------------------
    for attempt in range(1, ctx.cfg.attempts_per_card + 1):
        card.attempts = attempt
        new_html = _implement(ctx, card, spec, html, sections, feedback=None)
        verdict = _verify(ctx, card, new_html, spec)
        if verdict["pass"]:
            html = new_html
            break
        # retry with structured feedback
        new_html = _implement(ctx, card, spec, html, sections,
                              feedback=verdict["errors"])
        verdict = _verify(ctx, card, new_html, spec)
        if verdict["pass"]:
            html = new_html
            break
        card.gate_log.append({"attempt": attempt, **verdict})
    else:
        # surgical repair pass before quarantine
        for r in range(1, ctx.cfg.repairs_per_card + 1):
            card.repairs = r
            patch_html = _repair(ctx, card, html, spec, card.gate_log[-1]["errors"])
            verdict = _verify(ctx, card, patch_html, spec)
            if verdict["pass"]:
                html, card.status = patch_html, CardStatus.PATCHED.value
                break
        else:
            card.status = CardStatus.FAILED.value if ctx.budget_exhausted() \
                else CardStatus.QUARANTINED.value
            card.updated_at = time.time()
            return

    # ---- 4. REGRESS ---------------------------------------------------------
    regress = _regress(ctx, card, html)
    if not regress["pass"]:
        # regression broke an older card: try one surgical repair of THIS card
        patch_html = _repair(ctx, card, html, spec, regress["errors"])
        if _verify(ctx, card, patch_html, spec)["pass"] and \
           _regress(ctx, card, patch_html)["pass"]:
            html, card.status = patch_html, CardStatus.PATCHED.value
        else:
            card.status = CardStatus.QUARANTINED.value
            card.gate_log.append({"stage": "regress", **regress})
    elif card.status != CardStatus.PATCHED.value:
        card.status = CardStatus.PASS.value

    work_path.write_text(html)
    card.updated_at = time.time()


# ------------------------------------------------------------------ helpers
def _write_test(ctx, card: FeatureCard, spec: dict) -> str:
    user = (
        f"FEATURE: {card.title}\nACCEPTANCE CONTRACT: {card.acceptance}\n"
        f"RELEVANT SPEC: {_pick_spec(spec, card)}\nWrite the test now."
    )
    data = ctx.llm.complete_json(TESTER_SYSTEM, user, tag=f"test:{card.id}")
    return data.get("test_fn", "")


def _implement(ctx, card: FeatureCard, spec: dict, html: str,
               sections: list[str], feedback) -> str:
    current = "\n\n".join(
        f"--- SECTION {s} ---\n{extract_section(html, s) or ''}" for s in sections
    )
    fb = ""
    if feedback:
        fb = "\nPREVIOUS ATTEMPT FAILED GATES:\n" + "\n".join(feedback[:8])
    user = (
        f"CARD {card.id}: {card.title}\nCONTRACT: {card.acceptance}\n"
        f"SPEC EXCERPT: {_pick_spec(spec, card)}\n"
        f"YOUR TEST (must make it pass):\n{card.test_source}\n"
        f"CURRENT SECTIONS:\n{current}{fb}\n\nImplement now."
    )
    out = ctx.llm.complete(IMPL_SYSTEM, user, tag=f"impl:{card.id}:{len(card.gate_log)}")
    merged = html
    n = 0
    for s in sections:
        marker_open = f"/*==SECTION:{s}==*/"
        if marker_open in out:
            body_start = out.find(marker_open) + len(marker_open)
            body_end = out.find(f"/*==END:{s}==*/", body_start)
            if body_end > body_start:
                merged = replace_section(merged, s, out[body_start:body_end])
                n += 1
    if n == 0:  # model echoed nothing usable — keep original, gate will fail
        return html
    return merged


def _verify(ctx, card: FeatureCard, html: str, spec: dict) -> dict:
    errors: list[str] = []
    ok_syn, err_syn = check_js_syntax(html)
    if not ok_syn:
        errors.append(f"G-syntax: {err_syn}")
    ok_todo, left = check_no_todos_left(html, card.id)
    if not ok_todo:
        errors.append(f"G-completeness: TODO({card.id}) still present")
    test_ok, test_err = _run_card_test(ctx, card, html)
    if not test_ok:
        errors.append(f"G-unit: {test_err}")
    return {"pass": not errors, "errors": errors}


def _regress(ctx, card: FeatureCard, html: str) -> dict:
    """Re-run acceptance tests of all passed cards except boot-sensitive ones."""
    from baa.core.card import Ledger  # type: ignore

    errors = []
    for other in ctx.ledger.cards.values():
        if other.id == card.id:
            continue
        if other.status in (CardStatus.PASS.value, CardStatus.PATCHED.value):
            ok, err = _run_card_test(ctx, other, html)
            if not ok:
                errors.append(f"REGRESSION on {other.id}: {err}")
    return {"pass": not errors, "errors": errors}


def _repair(ctx, card: FeatureCard, html: str, spec: dict, errors) -> str:
    sysmsg = (
        "You perform SURGICAL PATCHES on a single-file game. Change the minimum "
        "lines needed to fix the listed gate failures. Output changed sections "
        "in the same /*==SECTION:id==*/ block format. Nothing else."
    )
    user = (
        f"CARD {card.id} CONTRACT {card.acceptance}\nGATE FAILURES:\n"
        + "\n".join(errors[:10])
        + f"\n\nFULL FILE:\n{html[:60000]}"
    )
    out = ctx.llm.complete(sysmsg, user, tag=f"repair:{card.id}")
    merged = html
    for s in SECTION_BY_LAYER[card.layer]:
        marker_open = f"/*==SECTION:{s}==*/"
        if marker_open in out:
            body_start = out.find(marker_open) + len(marker_open)
            body_end = out.find(f"/*==END:{s}==*/", body_start)
            if body_end > body_start:
                merged = replace_section(merged, s, out[body_start:body_end])
    return merged


def _run_card_test(ctx, card: FeatureCard, html: str) -> tuple[bool, str]:
    """Execute one acceptance test headlessly. Returns (passed, error_str)."""
    try:
        from baa.gates.runtime import run_acceptance_test

        tmp = ctx.run_dir / f"probe_{card.id}.html"
        tmp.write_text(html)
        return run_acceptance_test(tmp, card.test_source)
    except Exception as e:
        return False, f"harness unavailable: {e}"


def _save_test(ctx, card: FeatureCard) -> None:
    d = ctx.run_dir / "tests"
    d.mkdir(exist_ok=True)
    (d / f"{card.id}.js").write_text(card.test_source)


def _pick_spec(spec: dict, card: FeatureCard) -> str:
    import json

    keys = [p.split(".")[0] for p in card.spec_fields] or [
        "controls", "entities", "systems", "mechanics"
    ]
    excerpt = {k: spec.get(k) for k in set(keys) if k in spec}
    return json.dumps(excerpt, indent=1)[:4000]
