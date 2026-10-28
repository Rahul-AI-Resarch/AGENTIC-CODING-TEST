"""Conductor — the dumb state machine that runs the orchestra.

Phases:  A spec -> B decompose -> C scaffold -> D micro-loop (per card)
         -> E integration gates -> F ship -> G iterate (later re-entry to D)

The conductor owns ordering, budgets and retries ONLY. All game knowledge
lives in prompts inside stages/; all judgement lives in gates/.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from baa.byok.config import BYOKConfig
from baa.core.card import Ledger, CardStatus
from baa.llm.client import LLMClient


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    cfg: BYOKConfig
    llm: LLMClient
    ledger: Ledger
    started_at: float = time.time()
    tokens_spent: int = 0

    def budget_exhausted(self) -> bool:
        elapsed_min = (time.time() - self.started_at) / 60.0
        if self.tokens_spent > self.cfg.token_budget:
            return True
        if elapsed_min > self.cfg.wall_clock_minutes:
            return True
        return False


class Conductor:
    def __init__(self, cfg: BYOKConfig):
        self.cfg = cfg

    # ---------------------------------------------------------------- entry
    def build(self, prompt: str, run_id: str | None = None) -> RunContext:
        ctx = self._open_run(run_id or _slug(prompt))
        if ctx.ledger.meta.get("phase", "A") == "A" and not ctx.ledger.cards:
            self._phase_a_spec(ctx, prompt)
            self._phase_b_decompose(ctx)
            self._phase_c_scaffold(ctx)
        self._phase_d_microloop(ctx)
        self._phase_e_integration(ctx)
        self._phase_f_ship(ctx)
        return ctx

    def resume(self, run_id: str) -> RunContext:
        ctx = self._open_run(run_id)
        phase = ctx.ledger.meta.get("phase", "D")
        if phase in ("A", "B", "C"):
            raise RuntimeError(
                f"run {run_id} is mid-phase {phase}; re-run build with same prompt"
            )
        self._phase_d_microloop(ctx)
        self._phase_e_integration(ctx)
        self._phase_f_ship(ctx)
        return ctx

    # ---------------------------------------------------------------- phases
    def _open_run(self, run_id: str) -> RunContext:
        run_dir = Path("runs") / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        llm = LLMClient(self.cfg)
        ledger = Ledger(run_dir)
        return RunContext(run_id, run_dir, self.cfg, llm, ledger)

    def _phase_a_spec(self, ctx: RunContext, prompt: str) -> None:
        from baa.stages.spec import generate_spec

        spec = generate_spec(ctx.llm, prompt)
        (ctx.run_dir / "spec.json").write_text(_json_dumps(spec))
        ctx.ledger.meta["spec_path"] = str(ctx.run_dir / "spec.json")
        ctx.ledger.meta["prompt"] = prompt
        ctx.ledger.meta["phase"] = "B"
        ctx.ledger.save()

    def _phase_b_decompose(self, ctx: RunContext) -> None:
        from baa.stages.decompose import decompose

        spec = _load_json(Path(ctx.ledger.meta["spec_path"]))
        cards = decompose(ctx.llm, spec)
        for c in cards:
            ctx.ledger.add(c)
        ctx.ledger.meta["phase"] = "C"
        ctx.ledger.save()

    def _phase_c_scaffold(self, ctx: RunContext) -> None:
        from baa.stages.scaffold import build_scaffold

        spec = _load_json(Path(ctx.ledger.meta["spec_path"]))
        skeleton = build_scaffold(ctx.llm, spec, list(ctx.ledger.cards.values()))
        (ctx.run_dir / "skeleton.html").write_text(skeleton)
        ctx.ledger.meta["skeleton_path"] = str(ctx.run_dir / "skeleton.html")
        ctx.ledger.meta["phase"] = "D"
        ctx.ledger.save()

    def _phase_d_microloop(self, ctx: RunContext) -> None:
        from baa.stages.microloop import run_card

        spec = _load_json(Path(ctx.ledger.meta["spec_path"]))
        skeleton_path = Path(ctx.ledger.meta["skeleton_path"])
        guard = 0
        while True:
            ready = ctx.ledger.ready_cards()
            if not ready:
                break
            card = ready[0]
            if ctx.budget_exhausted():
                card.status = CardStatus.FAILED.value
                ctx.ledger.meta["halt_reason"] = "budget exhausted"
                ctx.ledger.save()
                return
            run_card(ctx, card, spec, skeleton_path)
            ctx.ledger.save()
            guard += 1
            if guard > 500:  # safety valve against pathological loops
                raise RuntimeError("micro-loop exceeded 500 iterations")
        ctx.ledger.meta["phase"] = "E"
        ctx.ledger.save()

    def _phase_e_integration(self, ctx: RunContext) -> None:
        from baa.gates.runtime import integration_gates

        spec = _load_json(Path(ctx.ledger.meta["spec_path"]))
        results = integration_gates(ctx, spec)
        ctx.ledger.meta["integration"] = results
        ctx.ledger.meta["phase"] = "F" if all_pass(results) else "E-fail"
        ctx.ledger.save()

    def _phase_f_ship(self, ctx: RunContext) -> None:
        from baa.ship.packager import assemble_final

        final = assemble_final(ctx)
        ctx.ledger.meta["final_html"] = str(final)
        ctx.ledger.meta["phase"] = "DONE"
        ctx.ledger.save()


# ------------------------------------------------------------------ helpers
def _slug(prompt: str) -> str:
    words = [w for w in prompt.lower().split() if w.isalnum()][:4]
    return "-".join(words) or f"run-{int(time.time())}"


def _json_dumps(obj) -> str:
    return __import__("json").dumps(obj, indent=2)


def _load_json(p: Path):
    return __import__("json").loads(p.read_text())


def all_pass(results: dict) -> bool:
    return all(v.get("pass", False) for v in results.values())
