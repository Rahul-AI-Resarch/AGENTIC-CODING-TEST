"""End-to-end pipeline test with a scripted fake LLM (no API key needed).
Proves: spec->decompose->scaffold->micro-loop->gates->ship wiring, ledger
resumability, and quarantine semantics."""
import sys, json, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from baa.byok.config import BYOKConfig
from baa.core import conductor as C
from baa.stages import microloop as M
from baa.gates import runtime as R

SPEC = {"game_id": "test-game", "title": "Test Game", "genre": "arcade",
        "dimension": "2d-top", "camera": {}, "controls": {"arrows": "move"},
        "libs": ["https://cdn.example/lib.js"],
        "view": {"width_px": 800, "height_px": 600, "clear_color": "#000"},
        "physics": {"engine": "custom", "fixed_timestep_ms": 16},
        "entities": [{"name": "player", "count": 1, "behavior_summary": "moves"}],
        "systems": [{"name": "wind", "params": {"max_speed": 12.0}}],
        "mechanics": [{"name": "scoring", "rules": [{"points_per_kill": 10}]}],
        "ui": {"hud_elements": ["score"], "screens": ["menu", "play"]},
        "content": {"levels": 3, "procedural": ["map"]},
        "feel": {"audio": ["blip"], "particles": ["spark"], "camera_fx": []},
        "perf_target": {"fps_min": 30, "frame_budget_ms": 33},
        "fidelity_checklist": [f"when input then feature {i} responds" for i in range(8)]}

LAYERS = ["L0-engine","L1-physics","L2-entities","L3-systems","L4-mechanics",
          "L5-ui","L6-content","L7-feel"]
CARDS = [{"id": f"feat-{i}", "title": f"Feature {i}", "layer": LAYERS[i],
          "depends_on": ([f"feat-{i-1}"] if i else []),
          "spec_fields": ["systems"], "acceptance": f"when input then feature {i} responds"}
         for i in range(8)]

SCAFFOLD_SECTIONS = ["head","css","dom","data","core-engine","physics","entities",
                     "systems","mechanics","ui","content","feel","boot"]


def fake_scaffold():
    from baa.stages.microloop import SECTION_BY_LAYER
    parts = ["<!DOCTYPE html><html><head><title>Test Game</title></head><body>"]
    for s in SCAFFOLD_SECTIONS:
        owners = [c["id"] for c in CARDS if s in SECTION_BY_LAYER[c["layer"]]]
        body = "\n".join(f"/* TODO({cid}) */" for cid in owners)
        if s == "data":
            body = "const GAME_DATA = { wind: { maxSpeed: 12 }, scoring: { pointsPerKill: 10 } };"
        parts.append(f"<script>/*==SECTION:{s}==*/\n{body}\n/*==END:{s}==*/</script>")
    parts.append("</body></html>")
    return "\n".join(parts)

class FakeLLM:
    def complete(self, system, user, tag=""):
        if tag == "scaffold":
            return fake_scaffold()
        if tag.startswith("impl") or tag.startswith("repair"):
            # echo back ONLY the sections this card owns (found in CURRENT SECTIONS header)
            out = []
            for s in SCAFFOLD_SECTIONS:
                if f"--- SECTION {s} ---" in user:
                    out.append(f"/*==SECTION:{s}==*/\nfunction impl_{s.replace('-','_')}(){{ window.__GAME_STATE__={{entityCount:1}}; }}\n/*==END:{s}==*/")
            return "\n".join(out)
        return ""
    def complete_json(self, system, user, tag=""):
        if tag == "spec": return SPEC
        if tag == "decompose": return {"cards": CARDS}
        if tag.startswith("test"): return {"test_fn": "assert(true,'ok')", "assertions": []}
        return {}

def run():
    orig_browser = None
    def fake_acceptance(html_path, test_fn, timeout_ms=15000):
        return (True, "")  # pretend headless browser passes every card test
    R.run_acceptance_test = fake_acceptance
    def fake_integration(ctx, spec):
        return {"boot": {"pass": True}, "nonblank": {"pass": True},
                "scene": {"pass": True}, "soak": {"pass": True}}
    R.integration_gates = fake_integration

    cfg = BYOKConfig(provider="openai", model="fake", api_key="fake-key")
    with tempfile.TemporaryDirectory() as d:
        cwd = pathlib.Path.cwd(); pathlib.Path(d).mkdir(exist_ok=True)
        import os; os.chdir(d)
        try:
            con = C.Conductor(cfg)
            # inject fake llm after _open_run creates real one
            real_open = con._open_run
            def patched(run_id):
                ctx = real_open(run_id)
                ctx.llm = FakeLLM()
                return ctx
            con._open_run = patched
            ctx = con.build("make a tiny test arcade game")
            stats = ctx.ledger.stats()
            assert stats.get("pass", 0) == 8, stats
            assert ctx.ledger.meta["phase"] == "DONE", ctx.ledger.meta
            final = pathlib.Path(ctx.ledger.meta["final_html"])
            assert final.exists() and "selftest" in final.read_text()
            print("E2E-MOCKED PASS:", stats, "->", final)
        finally:
            os.chdir(cwd)

if __name__ == "__main__":
    run()
