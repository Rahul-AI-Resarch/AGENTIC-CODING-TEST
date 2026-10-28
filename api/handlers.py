"""Framework-free request handlers.

Each handler takes plain values and returns ``(status_code, payload_dict)``.
No FastAPI import, no Request/Response objects — which means the same code
serves the real API and the dev stub, and is unit-testable directly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from core.config import Settings
from core.events import EventBus
from core.ids import new_run_id, unique_slug
from storage.db import RunRepository
from storage.runs import RunStore

MAX_PROMPT_LEN = 8000


class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class AppContext:
    settings: Settings
    repo: RunRepository
    runs: RunStore
    bus: EventBus


# --------------------------------------------------------------------------
# health / meta
# --------------------------------------------------------------------------
def health(ctx: AppContext) -> tuple[int, dict[str, Any]]:
    return 200, {
        "ok": True,
        "app": ctx.settings.app_name,
        "version": ctx.settings.version,
        "tagline": ctx.settings.tagline,
        "time": time.time(),
        "subscribers": ctx.bus.subscriber_count,
    }


def meta(ctx: AppContext) -> tuple[int, dict[str, Any]]:
    return 200, {
        "app": ctx.settings.app_name,
        "version": ctx.settings.version,
        "tagline": ctx.settings.tagline,
        "modes": [
            {
                "id": "website",
                "label": "Website / Web app",
                "hint": "Prompt, image, video, template or repo import",
            },
            {
                "id": "game",
                "label": "Game",
                "hint": "Reference a famous game, then playtest it live",
            },
        ],
        "limits": {
            "run_max_seconds": ctx.settings.run_max_seconds,
            "run_max_llm_calls": ctx.settings.run_max_llm_calls,
            "run_max_tokens": ctx.settings.run_max_tokens,
        },
        "pipeline": [
            "intake", "spec", "plan", "scaffold", "microloop",
            "playtest", "gates", "ship", "refine",
        ],
        "orchestra": [
            "conductor", "scout", "producer", "architect",
            "performer", "critic", "stagehand", "archivist",
        ],
    }


# --------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------
def create_run(ctx: AppContext, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise HttpError(422, "prompt is required")
    if len(prompt) > MAX_PROMPT_LEN:
        raise HttpError(422, f"prompt exceeds {MAX_PROMPT_LEN} characters")

    mode = str(body.get("mode") or "website")
    if mode not in ("website", "game"):
        raise HttpError(422, f"unknown mode: {mode}")

    run_id = new_run_id()
    title = str(body.get("title") or prompt.splitlines()[0][:80]).strip() or "Untitled"
    slug = unique_slug(title, ctx.repo.taken_slugs())

    run = ctx.repo.create({
        "id": run_id,
        "mode": mode,
        "title": title,
        "prompt": prompt,
        "slug": slug,
        "status": "queued",
        "phase": "intake",
        "metadata": {
            "reference": body.get("reference"),
            "inputs": body.get("inputs") or [],
            "source": body.get("source") or "prompt",
        },
    })
    ctx.runs.create(run_id)
    ctx.runs.write_meta(run_id, run)
    return 201, run


def list_runs(ctx: AppContext, query: dict[str, list[str]] | None = None) -> tuple[int, dict[str, Any]]:
    query = query or {}
    raw_limit = (query.get("limit") or ["50"])[0]
    try:
        limit = max(1, min(200, int(raw_limit)))
    except (TypeError, ValueError):
        limit = 50
    runs = ctx.repo.list(limit=limit)
    return 200, {"runs": runs, "count": len(runs)}


def get_run(ctx: AppContext, run_id: str) -> tuple[int, dict[str, Any]]:
    run = ctx.repo.get(run_id)
    if run is None:
        raise HttpError(404, f"run not found: {run_id}")
    return 200, run


def delete_run(ctx: AppContext, run_id: str) -> tuple[int, dict[str, Any]]:
    if ctx.repo.get(run_id) is None:
        raise HttpError(404, f"run not found: {run_id}")
    ctx.repo.delete(run_id)
    ctx.runs.delete(run_id)
    return 200, {"deleted": run_id}


# --------------------------------------------------------------------------
# generated files
# --------------------------------------------------------------------------
def list_files(ctx: AppContext, run_id: str) -> tuple[int, dict[str, Any]]:
    if ctx.repo.get(run_id) is None:
        raise HttpError(404, f"run not found: {run_id}")
    files = ctx.runs.list_files(run_id)
    return 200, {"run_id": run_id, "files": files, "count": len(files)}


def get_file(ctx: AppContext, run_id: str, path: str) -> tuple[int, dict[str, Any]]:
    if ctx.repo.get(run_id) is None:
        raise HttpError(404, f"run not found: {run_id}")
    content = ctx.runs.read_file(run_id, path)
    if content is None:
        raise HttpError(404, f"file not found: {path}")
    return 200, {"run_id": run_id, "path": path, "content": content}


HANDLERS = {
    "health": health,
    "meta": meta,
    "create_run": create_run,
    "list_runs": list_runs,
    "get_run": get_run,
    "delete_run": delete_run,
    "list_files": list_files,
    "get_file": get_file,
}
