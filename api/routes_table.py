"""The API contract — single source of truth.

Both adapters (FastAPI in :mod:`api.router`, stdlib dev server in
:mod:`tools.devstub`) are generated from this table and dispatch to the same
framework-free handlers in :mod:`api.handlers`. There is exactly one place where
a route is declared, so the two servers cannot drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    handler: str
    summary: str


ROUTES: tuple[Route, ...] = (
    Route("GET", "/api/health", "health", "Liveness + build info"),
    Route("GET", "/api/meta", "meta", "Capabilities, limits, supported modes"),
    Route("POST", "/api/runs", "create_run", "Start a new build"),
    Route("GET", "/api/runs", "list_runs", "List recent builds"),
    Route("GET", "/api/runs/{run_id}", "get_run", "Fetch one build"),
    Route("DELETE", "/api/runs/{run_id}", "delete_run", "Delete a build"),
    Route("GET", "/api/runs/{run_id}/files", "list_files", "List generated files"),
    Route("GET", "/api/runs/{run_id}/files/{path:path}", "get_file", "Read one generated file"),
    Route("GET", "/api/runs/{run_id}/events", "run_events", "SSE live event stream"),
)

# Routes whose handler is a generator (SSE) rather than a request/response pair.
STREAMING_ROUTES = frozenset({"run_events"})


def paths() -> list[str]:
    return [f"{r.method} {r.path}" for r in ROUTES]
