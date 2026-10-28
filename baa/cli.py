"""Build Anything Agent (codename YOK) — CLI.

  baa build "<prompt>"        full orchestra: spec -> decompose -> scaffold
                              -> per-card micro-loop -> gates -> ship
  baa resume <run-id>         continue an interrupted run from ledger.json
  baa edit <run-id> "<fb>"    Phase G: surgical feature-card delta + re-loop
  baa preview <game-id>       serve dist/<game-id>/ at http://localhost:8000
  baa status <run-id>         print ledger stats
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="baa",
                                description="Build Anything Agent (YOK)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("prompt")
    b.add_argument("--run-id", default=None)

    r = sub.add_parser("resume")
    r.add_argument("run_id")

    e = sub.add_parser("edit")
    e.add_argument("run_id")
    e.add_argument("feedback")

    v = sub.add_parser("preview")
    v.add_argument("game_id")
    v.add_argument("--port", type=int, default=8000)

    s = sub.add_parser("status")
    s.add_argument("run_id")

    a = p.parse_args(argv)

    if a.cmd == "status":
        from baa.core.card import Ledger
        led = Ledger(Path("runs") / a.run_id)
        print(f"run {a.run_id}: phase={led.meta.get('phase')}")
        for k, n in sorted(led.stats().items()):
            print(f"  {k:>12}: {n}")
        return 0

    if a.cmd == "preview":
        from baa.ship.iterate import serve
        root = Path("dist") / a.game_id
        if not (root / "index.html").exists():
            print(f"nothing shipped at {root}", file=sys.stderr)
            return 1
        serve(root, a.port)
        print(f"serving {root} on http://localhost:{a.port}/index.html "
              f"(self-test: ?selftest=1)")
        try:
            input("Ctrl-C to stop\n")
        except KeyboardInterrupt:
            pass
        return 0

    from baa.byok.config import BYOKConfig
    from baa.core.conductor import Conductor
    cfg = BYOKConfig.from_env()
    con = Conductor(cfg)

    if a.cmd == "build":
        ctx = con.build(a.prompt, run_id=a.run_id)
    elif a.cmd == "resume":
        ctx = con.resume(a.run_id)
    elif a.cmd == "edit":
        ctx = con._open_run(a.run_id)
        from baa.ship.iterate import apply_edit
        apply_edit(ctx, a.feedback)
        con._phase_d_microloop(ctx)
        con._phase_e_integration(ctx)
        con._phase_f_ship(ctx)
    else:  # pragma: no cover
        return 2

    print(f"\n=== run {ctx.run_id} finished: phase={ctx.ledger.meta.get('phase')} ===")
    for k, n in sorted(ctx.ledger.stats().items()):
        print(f"  {k:>12}: {n}")
    if ctx.ledger.meta.get("final_html"):
        print(f"shipped -> {ctx.ledger.meta['final_html']}")
    halt = ctx.ledger.meta.get("halt_reason")
    if halt:
        print(f"HALTED: {halt}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
