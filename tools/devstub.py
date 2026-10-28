"""Dependency-free development server.

Implements the exact same API contract as the FastAPI app (both are generated
from :data:`api.routes_table.ROUTES` and dispatch to the same handlers), so you
can develop the React console with nothing installed but Python:

    python tools/devstub.py --port 8000

This is a development convenience, not a production server — no TLS, no
concurrency tuning, no hardening. Use uvicorn + main:app in production.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.handlers import HANDLERS, AppContext, HttpError  # noqa: E402
from api.routes_table import ROUTES, STREAMING_ROUTES  # noqa: E402
from core.config import settings  # noqa: E402
from core.events import bus  # noqa: E402
from storage.db import RunRepository  # noqa: E402
from storage.runs import RunStore  # noqa: E402

_PARAM = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::(path))?\}")


def compile_pattern(path: str) -> tuple[re.Pattern[str], list[str]]:
    """Turn ``/api/runs/{run_id}/files/{path:path}`` into a regex + param names."""
    params: list[str] = []
    pattern = ""
    index = 0
    for match in _PARAM.finditer(path):
        pattern += re.escape(path[index:match.start()])
        name, converter = match.group(1), match.group(2)
        params.append(name)
        pattern += r"(?P<%s>%s)" % (name, ".+" if converter == "path" else "[^/]+")
        index = match.end()
    pattern += re.escape(path[index:])
    return re.compile("^" + pattern + "$"), params


COMPILED = [(route, *compile_pattern(route.path)) for route in ROUTES]


def build_context() -> AppContext:
    settings.ensure_dirs()
    repo = RunRepository(settings.db_path)
    repo.connect()
    return AppContext(settings=settings, repo=repo, runs=RunStore(settings.runs_dir), bus=bus)


CTX = build_context()

_MEDIA_TYPES = {
    ".html": "text/html", ".js": "application/javascript", ".mjs": "application/javascript",
    ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".ico": "image/x-icon", ".woff2": "font/woff2", ".wasm": "application/wasm",
    ".txt": "text/plain", ".map": "application/json",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "BAA-devstub/3.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter output
        if "--verbose" in sys.argv:
            super().log_message(fmt, *args)

    # -- helpers -----------------------------------------------------------
    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _match(self, method: str, path: str):
        for route, regex, params in COMPILED:
            if route.method != method:
                continue
            m = regex.match(path)
            if m:
                return route, {k: unquote(v) for k, v in m.groupdict().items()}
        return None, None

    def _serve_static(self, path: str) -> bool:
        dist = settings.html_dist
        if not dist.is_dir():
            return False
        rel = path.lstrip("/") or "index.html"
        target = (dist / rel).resolve()
        if not str(target).startswith(str(dist.resolve()) + "/"):
            return False
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return False
        body = target.read_bytes()
        suffix = "." + target.suffix.lstrip(".").lower()
        self.send_response(200)
        self.send_header("Content-Type", _MEDIA_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _stream_events(self, run_id: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        async def pump() -> None:
            hello = {"kind": "hello", "run_id": run_id, "ts": 0, "data": {"ok": True}}
            self.wfile.write(f"data: {json.dumps(hello)}\n\n".encode())
            self.wfile.flush()
            async for event in CTX.bus.subscribe():
                if event.get("run_id") in (None, run_id):
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()

        try:
            asyncio.run(pump())
        except (BrokenPipeError, ConnectionResetError):
            pass

    # -- verbs -------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        route, params = self._match("GET", path)
        if route is None:
            if self._serve_static(path):
                return
            self._send_json(404, {"error": f"no route for GET {path}"})
            return
        if route.handler in STREAMING_ROUTES:
            self._stream_events(params.get("run_id", ""))
            return
        self._dispatch(route, params, {}, dict(parse_qs(parsed.query)))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route, params = self._match("POST", parsed.path)
        if route is None:
            self._send_json(404, {"error": f"no route for POST {parsed.path}"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return
        self._dispatch(route, params, body, {})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route, params = self._match("DELETE", parsed.path)
        if route is None:
            self._send_json(404, {"error": f"no route for DELETE {parsed.path}"})
            return
        self._dispatch(route, params, {}, {})

    def _dispatch(self, route, params, body, query) -> None:
        handler = HANDLERS[route.handler]
        accepted = set(inspect.signature(handler).parameters) - {"ctx"}
        candidates = {**params, "body": body, "query": query}
        kwargs = {k: v for k, v in candidates.items() if k in accepted}
        try:
            status, payload = handler(CTX, **kwargs)
        except HttpError as exc:
            self._send_json(exc.status, {"error": exc.message})
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._send_json(status, payload)


def main() -> int:
    parser = argparse.ArgumentParser(prog="devstub")
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    console = settings.html_dist
    print(f"BAA devstub  → http://{args.host}:{args.port}/")
    print(f"  API contract : {len(ROUTES)} routes")
    print(f"  console      : {console if console.is_dir() else 'not built (run: cd html && npm run build)'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        CTX.repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
