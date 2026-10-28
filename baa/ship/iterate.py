"""Phase G — preview server + iterative edits (surgical re-entry to D)."""
from __future__ import annotations

import http.server
import socketserver
import threading
from pathlib import Path


def serve(dist_dir: str | Path, port: int = 8000) -> socketserver.TCPServer:
    """Serve dist/<game>/ statically; returns the running server (daemon thread)."""
    root = str(Path(dist_dir))
    handler = type("H", (http.server.SimpleHTTPRequestHandler,),
                   {"__init__": lambda s, *a, **k: http.server
                    .SimpleHTTPRequestHandler.__init__(s, *a, directory=root, **k)})
    httpd = socketserver.TCPServer(("0.0.0.0", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def apply_edit(ctx, feedback: str) -> None:
    """Turn user feedback into new/edited cards, then re-run micro-loop for
    affected cards + dependents only. Never regenerate the whole file."""
    from baa.core.card import CardStatus, FeatureCard, LAYER_ORDER
    from baa.stages.decompose import validate_graph

    spec = __import__("json").loads(
        Path(ctx.ledger.meta["spec_path"]).read_text())
    sysmsg = (
        "You convert USER FEEDBACK about a built game into NEW or REVISED "
        "feature cards. Output JSON {\"cards\":[{id,title,layer,depends_on,"
        "spec_fields,acceptance}]} with ONLY the delta cards. Reuse an "
        "existing id to revise that card."
    )
    existing = "\n".join(
        f"- {c.id}: {c.title}" for c in ctx.ledger.cards.values())[:3000]
    data = ctx.llm.complete_json(
        sysmsg,
        f"FEEDBACK: {feedback}\nSPEC EXCERPT: {str(spec)[:4000]}\n"
        f"EXISTING CARDS:\n{existing}",
        tag="edit-cards",
    )
    delta = [FeatureCard.from_dict(d) for d in data.get("cards", [])]
    for c in delta:
        if c.id in ctx.ledger.cards:  # revise: reset status so loop re-runs it
            old = ctx.ledger.cards[c.id]
            old.acceptance, old.title, old.layer = c.acceptance, c.title, c.layer
            old.status = CardStatus.PENDING.value
            old.attempts = old.repairs = 0
            old.test_source = ""
            old.gate_log = []
        else:
            ctx.ledger.add(c)
    # dependents of revised cards must also be re-verified
    ids = {c.id for c in delta}
    changed = True
    while changed:
        changed = False
        for oc in ctx.ledger.cards.values():
            if oc.id not in ids and set(oc.depends_on) & ids:
                if oc.status in (CardStatus.PASS.value, CardStatus.PATCHED.value):
                    oc.status = CardStatus.PENDING.value
                    ids.add(oc.id)
                    changed = True
    ctx.ledger.meta["phase"] = "D"
    ctx.ledger.save()
