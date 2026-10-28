# ▣ BAA — Build Anything Agent (codename YOK · BYOK)

An autonomous agent that replicates **any game** — 2D arcade, big 3D worlds like
wind-and-sail traders — top-to-bottom, feature by feature, the way Kimi Build does:
decompose → scaffold → per-feature **test-first micro-loop** → gates → ship a single HTML file.

## Quick start (local — this is where your API key lives)
```bash
pip install -r requirements.txt
cp .env.example .env          # put YOUR key here (OpenAI / Gemini / Kimi / any OpenAI-compatible)
python -m baa.cli web         # open http://localhost:8788  ← the console UI
# or headless:
python -m baa.cli build "arcade maze chase clone, 2d-top"
python -m baa.cli status <run-id>
python -m baa.cli preview <game-id>
```

## The UI
- **GitHub Pages deploy** (`docs/`, auto-published by `.github/workflows/pages.yml`):
  read-only orchestra console — phase stepper, feature-card ledger with each card's
  acceptance test (click a row), demo run included. No keys, no backend.
- **Local console** (`python -m baa.web`, port 8788): same page + full control —
  start/resume builds, live ledger polling, activity log. Keys go only to your own
  localhost process and are never written to disk or artifacts.

## Pipeline (orchestra)
```
A spec → B decompose (L0-engine … L7-feel feature cards) → C scaffold (§0–§9 skeleton)
→ D per-card micro-loop: TEST-FIRST → IMPLEMENT → VERIFY (syntax/unit/perf/fidelity) → REGRESS
→ E integration gates (boot, scene, input, loop-walk, soak/FPS) → F ship single index.html
→ G iterate (surgical card deltas, never regenerate)
```

## Security notes for public repos
- BYOK: no keys in code; `.env` is gitignored.
- The Pages site is static — it cannot start builds and contains no secrets.
- Don't commit `runs/<id>/` intermediates if they embed private prompts; only
  `runs/ledger.sample.json` is tracked as a showcase.

## Tests
```bash
python tests/test_units.py        # offline unit suite (no LLM/browser)
python tests/test_e2e_mocked.py   # full mocked pipeline e2e
```
