"""FastAPI adapter.

Thin by design: it walks :data:`api.routes_table.ROUTES`, extracts path params
and the body, calls the matching framework-free handler, and serialises the
result. All behaviour lives in :mod:`api.handlers` so the dev stub can share it.
"""
from __future__ import annotations

import inspect
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.handlers import HANDLERS, AppContext, HttpError
from api.routes_table import ROUTES, STREAMING_ROUTES


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _run_events(ctx: AppContext, request: Request) -> StreamingResponse:
    run_id = request.path_params.get("run_id", "")

    async def stream():
        yield _sse({"kind": "hello", "run_id": run_id, "data": {"ok": True}})
        async for event in ctx.bus.subscribe():
            if event.get("run_id") in (None, run_id):
                yield _sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _make_endpoint(route, ctx: AppContext):
    handler = HANDLERS[route.handler]
    # Only pass the arguments this handler actually declares, so a handler that
    # takes just `ctx` is not handed a stray `body=` / `query=` kwarg.
    accepted = set(inspect.signature(handler).parameters) - {"ctx"}

    async def endpoint(request: Request) -> JSONResponse:
        try:
            if route.method in ("POST", "PUT", "PATCH"):
                raw = await request.body()
                body: dict[str, Any] = json.loads(raw) if raw else {}
            else:
                body = {}
            candidates = {
                **request.path_params,
                "body": body,
                "query": dict(request.query_params),
            }
            kwargs = {k: v for k, v in candidates.items() if k in accepted}
            status, payload = handler(ctx, **kwargs)
            return JSONResponse(status_code=status, content=payload)
        except HttpError as exc:
            return JSONResponse(status_code=exc.status, content={"error": exc.message})
        except json.JSONDecodeError:
            return JSONResponse(status_code=400, content={"error": "invalid JSON body"})
        except TypeError as exc:
            return JSONResponse(status_code=500, content={"error": f"handler signature mismatch: {exc}"})

    return endpoint


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    for route in ROUTES:
        if route.handler in STREAMING_ROUTES:
            router.add_api_route(
                route.path,
                lambda request, _r=route: _run_events(ctx, request),
                methods=[route.method],
                name=route.handler,
                summary=route.summary,
            )
            continue
        router.add_api_route(
            route.path,
            _make_endpoint(route, ctx),
            methods=[route.method],
            name=route.handler,
            summary=route.summary,
        )
    return router
