"""Offline unit tests for the deterministic parts: ledger, graph validation,
static gates, fidelity audit. No LLM, no browser."""
import sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from baa.core.card import FeatureCard, Ledger, CardStatus
from baa.stages.decompose import validate_graph, acyclic_check
from baa.gates.static import check_js_syntax, check_dom_ids, check_cdn_urls
from baa.gates.fidelity import audit_spec_numbers


def mk(cid, layer, deps=None):
    return FeatureCard(id=cid, title=cid, layer=layer,
                       depends_on=deps or [], acceptance=f"{cid} works")


def test_ledger_ordering():
    with tempfile.TemporaryDirectory() as d:
        led = Ledger(pathlib.Path(d))
        led.add(mk("engine", "L0-engine"))
        led.add(mk("physics", "L1-physics", ["engine"]))
        led.add(mk("ui", "L5-ui", ["physics"]))
        ready = [c.id for c in led.ready_cards()]
        assert ready == ["engine"], ready
        led.get("engine").status = CardStatus.PASS.value
        ready = [c.id for c in led.ready_cards()]
        assert ready == ["physics"], ready
        led.save(); led2 = Ledger(pathlib.Path(d))
        assert led2.get("engine").status == CardStatus.PASS.value  # resumable


def test_quarantine_blocks_dependents():
    with tempfile.TemporaryDirectory() as d:
        led = Ledger(pathlib.Path(d))
        led.add(mk("a", "L0-engine")); led.add(mk("b", "L1-physics", ["a"]))
        led.get("a").status = CardStatus.QUARANTINED.value
        assert led.ready_cards() == []


def test_graph_rejects_bad_deps():
    cards = [mk("x", "L4-mechanics"), mk("y", "L0-engine", ["x"])]
    try:
        validate_graph(cards, {"fidelity_checklist": ["x thing"]})
        assert False, "should have rejected upward dep"
    except ValueError: pass
    cyc = [mk("p", "L1-physics", ["q"]), mk("q", "L1-physics", ["p"])]
    try:
        acyclic_check({c.id: c for c in cyc}); assert False
    except ValueError: pass


def test_static_gates():
    bad = "<html><script>function f(){ const x = (1+2; }</script></html>"
    ok, err = check_js_syntax(bad)
    assert not ok, err
    good = "<html><body><div id='hud'></div><script>document.getElementById('hud'); function f(a){return a*2;}</script></body></html>"
    ok, err = check_js_syntax(good); assert ok, err
    ok, missing = check_dom_ids(good); assert ok and missing == []
    ok, bads = check_cdn_urls("<script src='http://evil/x.js'></script>")
    assert not ok and bads


def test_fidelity_audit():
    spec = {"systems": [{"name": "wind", "params": {"max_speed": 12.0}}],
            "mechanics": []}
    html = "<script>const GAME_DATA = { wind: { maxSpeed: 12.5, }, }; /*;</script>"
    r = audit_spec_numbers(spec, html)
    assert r["checked"] == 1 and r["pass"], r
    html2 = "<script>const GAME_DATA = { wind: { maxSpeed: 99 } };</script>"
    assert not audit_spec_numbers(spec, html2)["pass"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} unit tests passed")
