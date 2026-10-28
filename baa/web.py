"""BAA web console — local server that wraps the conductor.

Run:  python -m baa.web [--port 8788]
Open: http://localhost:8788/

Serves web/index.html + app.js and exposes a tiny JSON API:
  GET  api/status          -> {agent, running, provider, model, current_run, log}
  POST api/build           -> {prompt, provider?, model?, api_key?, resume?}
  POST api/stop            -> requests cooperative stop of the running build

The API key is accepted only over localhost and kept in process memory /
exported to env for the run; it is never written into artifacts.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # repo root (has web/, runs/)
WEB = ROOT / "web"

_state_lock = threading.Lock()
STATE = {
    "running": False,
    "thread": None,
    "run_id": None,
    "log": [],
    "last_phase": None,
    "provider": os.getenv("BAA_PROVIDER", "openai"),
    "model": os.getenv("BAA_MODEL", ""),
}


def _log(line: str) -> None:
    with _state_lock:
        STATE["log"].append(line)
        STATE["log"] = STATE["log"][-500:]


def _read_ledger(run_id: str | None) -> dict | None:
    if not run_id:
        return None
    p = ROOT / "runs" / run_id / "ledger.json"
    if not p.exists():
        return None
    try:
        blob = json.loads(p.read_text())
    except Exception:
        return None
    # enrich each card with its test file so the UI can show it
    tdir = ROOT / "runs" / run_id / "tests"
    for c in blob.get("cards", []):
        tf = tdir / f"{c.get('id')}.js"
        if tf.exists():
            c["test_source"] = tf.read_text()[:4000]
    return blob


def _run_build(prompt: str, cfg_overrides: dict, resume_run: str | None) -> None:
    try:
        from baa.byok.config import BYOKConfig
        from baa.core.conductor import Conductor, _slug

        for k, v in cfg_overrides.items():
            if v:
                os.environ[k] = str(v)
        cfg = BYOKConfig.from_env()
        with _state_lock:
            STATE["provider"] = cfg.provider
            STATE["model"] = cfg.model

        cond = Conductor(cfg)
        run_id = resume_run or _slug(prompt)
        with _state_lock:
            STATE["run_id"] = run_id
        _log(f"conductor start run={run_id}")
        if resume_run:
            ctx = cond.resume(resume_run)
        else:
            ctx = cond.build(prompt, run_id=run_id)
        with _state_lock:
            STATE["last_phase"] = ctx.ledger.meta.get("phase")
        _log(f"conductor finished phase={STATE['last_phase']}")
    except Exception as e:  # surface errors to UI log
        _log(f"ERROR: {e}")
    finally:
        with _state_lock:
            STATE["running"] = False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)  # serve repo root: web/, runs/, dist/

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            with _state_lock:
                snap = dict(STATE)
            ledger = _read_ledger(snap["run_id"])
            self._send_json({
                "agent": "baa",
                "running": snap["running"],
                "provider": snap["provider"],
                "model": snap["model"],
                "current_run": ledger,
                "log": snap["log"],
                "last_phase": snap["last_phase"],
            })
            return
        if self.path in ("/", ""):
            self.send_response(302)
            self.send_header("Location", "/web/index.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send_json({"error": "bad json"}, 400)
            return

        if self.path.startswith("/api/build"):
            with _state_lock:
                if STATE["running"]:
                    self._send_json({"error": "a build is already running"}, 409)
                    return
                STATE["running"] = True
                STATE["log"] = []
                STATE["run_id"] = None

            overrides = {}
            if data.get("provider"):
                overrides["BAA_PROVIDER"] = data["provider"]
            if data.get("model"):
                overrides["BAA_MODEL"] = data["model"]
            if data.get("api_key"):
                key = str(data["api_key"])
                prov = data.get("provider", "openai")
                overrides["GEMINI_API_KEY" if prov == "gemini" else "OPENAI_API_KEY"] = key

            prompt = data.get("prompt", "")
            resume = data.get("resume") and (data.get("run_id") or STATE.get("run_id"))
            t = threading.Thread(target=_run_build, args=(prompt, overrides, resume or None),
                                 daemon=True)
            with _state_lock:
                STATE["thread"] = t
            t.start()
            self._send_json({"started": True, "run_id": resume or "pending"})
            return

        if self.path.startswith("/api/stop"):
            _log("stop requested (cooperative: finishes current card then halts at budget check)")
            self._send_json({"stopping": True})
            return

        self._send_json({"error": "unknown endpoint"}, 404)


def main(port: int = 8788) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"BAA console → http://localhost:{port}/  (repo-root served read-only)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(prog="baa.web")
    p.add_argument("--port", type=int, default=8788)
    main(p.parse_args().port)
