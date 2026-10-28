# BAA — Build Anything Agent

An orchestrated agent that builds **websites and games** from a prompt, grounded in live web
research and verified by **real sandbox playtesting**.

> **Status: Phase 0 (foundation).** The orchestration engine, web-retrieval booster and
> playtester are designed and scoped but **not yet implemented**. What exists today is the
> foundation they plug into: the API, the run model, the live event stream, and the React
> console. See [Roadmap](#roadmap).

---

## What's here

```
main.py                 FastAPI entry point — app factory, lifespan, routers, static mounts
api/                    The API contract (one table) + framework-free handlers
  routes_table.py         ← single source of truth for every route
  handlers.py             ← no FastAPI imports; unit-testable, shared with the dev stub
  router.py               ← thin FastAPI adapter
core/                   config · event bus (SSE) · id & slug helpers   [stdlib only]
storage/                SQLite run metadata + on-disk run folders       [stdlib only]
tools/devstub.py        Dependency-free dev server, same API contract
tools/install_workflows.sh   Copies deploy/*.yml into .github/workflows/
deploy/                 ci.yml + pages.yml (see tools/install_workflows.sh)
tests/                  stdlib unittest: core suite + frontend/backend contract test
html/                   React 18 + Vite + TypeScript + Tailwind console
data/                   Runtime data (gitignored): baa.db + runs/<id>/
```

## Quick start

### Just want to see the console?

No Python packages required — the dev stub implements the same API with the standard library.

```bash
cd html && npm install && npm run build && cd ..
python3 tools/devstub.py --port 8000
# → http://127.0.0.1:8000
```

### Full stack

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# → http://127.0.0.1:8000  (FastAPI serves html/dist)
```

### Frontend dev with hot reload

```bash
cd html && npm run dev      # → http://127.0.0.1:5173, proxies /api to :8000
```

## Tests

```bash
python3 tests/test_core.py       # 27 tests — config, ids, events, db, storage, handlers
python3 tests/test_contract.py   # 5 tests  — React paths vs backend routes
```

The contract test parses `html/src/api/paths.ts` and `api/routes_table.py` and asserts they
describe the same endpoints — so a route rename fails CI instead of 404ing in the browser.

## Configuration

Copy `.env.example` to `.env`. Keys are read from the environment or posted per-run and are
**never written to disk**.

| Variable | Default | Purpose |
|---|---|---|
| `BAA_PORT` | `8000` | API port |
| `BAA_DATA_DIR` | `./data` | SQLite db + run folders |
| `BAA_SERVE_CONSOLE` | `true` | Serve `html/dist` at `/` |
| `BAA_CORS_ORIGINS` | localhost:5173 | Exact origins allowed to call the API |
| `BAA_RUN_MAX_SECONDS` | `3600` | Per-run wall-clock budget |
| `BAA_RUN_MAX_LLM_CALLS` | `400` | Per-run LLM call budget |
| `BAA_RUN_MAX_TOKENS` | `2000000` | Per-run token budget |
| `OPENAI_API_KEY` | — | BYOK key (any OpenAI-compatible provider) |
| `YDC_API_KEY` | — | Optional; unlocks the keyed web-search tier |

## Deployment

### Make the app open at your repo URL

This is the step that was broken in v1: the app existed, but the repo's Pages
URL served a README instead of the app, because the app lived on an unmerged
branch and the deploy workflow was wired to a branch that had no code.

**The fastest route (no workflow files, one click):** deploy the API + console
to Render with the blueprint — FastAPI serves both at one origin, so the repo
URL isn't involved at all.

**The GitHub Pages route:**

```bash
bash tools/install_workflows.sh   # copies deploy/*.yml -> .github/workflows/
git add .github/workflows && git commit -m "ci: install workflows"
```

(The two workflow files live in `deploy/` because automated writes to
`.github/workflows/` are blocked by the GitHub App's security policy — workflow
files can read repository secrets. The install script is a one-liner.)

Then two settings:

1. **Pages source is "GitHub Actions".** Settings → Pages → Source → *GitHub
   Actions*. (If it points at a branch, the workflow is ignored and that
   branch's README is rendered instead — exactly the v1 failure.)
2. **`VITE_API_URL` points at the API.** Settings → Secrets and variables →
   Actions → Variables → `VITE_API_URL` = your Render URL, e.g.
   `https://baa.onrender.com`. The Pages-hosted console then calls the API
   cross-origin, so add the Pages origin to the API's `BAA_CORS_ORIGINS`.

`deploy/pages.yml` builds the console and publishes it on every push to `main`;
`deploy/ci.yml` runs the test suites and the console typecheck/build on every
push and PR.

### Render (recommended) — API + console on one origin

`render.yaml` is a Render blueprint: New → Blueprint → point at this repo.

```
Build command:  pip install -r requirements.txt && cd html && npm ci && npm run build
Start command:  uvicorn main:app --host 0.0.0.0 --port $PORT
```

FastAPI serves both the API and the built console at `/` — no CORS, one
service, one domain. Set `BAA_CORS_ORIGINS` to your Pages origin if you also
publish the console to GitHub Pages.

> Chromium (the Phase 3 sandbox) needs ~1 GB RAM — Render's free tier (512 MB)
> will OOM. Use the Starter tier, or keep the per-card checks in-browser and
> reserve Playwright for integration gates only.

## Roadmap

| Phase | What lands |
|---|---|
| ✅ **0 — Foundation** | API + run model + SSE event bus + React console + contract tests |
| 1 | Tool registry (~50 tools), ledger, storage backends |
| 2 | Core build loop: intake → spec → plan → scaffold → implement → preview (multi-file) |
| 3 | **Critic**: playtester driver, bug oracles, rubric judge, shared-memory refine loop |
| 4 | **Retrieval**: Scout · Grounder (real API docs) · Perf advisor · Debugger |
| 5 | Kimi-Build UX: visual editing, viewport switcher, conversational refine, templates |
| 6 | Publish: zip, single-file, static deploy, custom slug, published proxy |
| 7 | Game mode: reference intake (search → fetch → screenshot → vision), fidelity checklist |
| 8 | Full-stack: generated backend, per-run sandbox, database, auth |

## Design notes

- **One contract, two adapters.** `api/routes_table.py` declares every route. FastAPI and the
  stdlib dev stub are both generated from it and dispatch to the same handlers, so they cannot
  drift.
- **The core has no dependencies.** `core/` and `storage/` are stdlib-only, so the whole
  foundation is testable without installing anything — and swappable later (Redis for the event
  bus, Postgres for SQLite) by replacing one class.
- **Multi-file from the start.** Builds produce a file tree, not one HTML string. Cards own
  files, and the preview is served over HTTP so ES module imports resolve.

## License

MIT
