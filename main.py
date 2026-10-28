"""BAA — Build Anything Agent v3.

Single entry point. Builds the FastAPI application, wires the API contract from
:mod:`api.routes_table`, serves the React console from ``html/dist`` when it has
been built, and exposes the published-site proxy at ``/p/{slug}``.

Run locally::

    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

    # or, with no Python dependencies installed at all:
    python tools/devstub.py          # stdlib-only server, same API contract
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.handlers import AppContext
from api.router import build_router
from core.config import settings
from core.events import bus
from storage.db import RunRepository
from storage.runs import RunStore


def build_context() -> AppContext:
    """Create the shared application context (storage + event bus)."""
    settings.ensure_dirs()
    repo = RunRepository(settings.db_path)
    repo.connect()
    return AppContext(
        settings=settings,
        repo=repo,
        runs=RunStore(settings.runs_dir),
        bus=bus,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ctx: AppContext = app.state.ctx
    settings.ensure_dirs()
    await bus.publish("server.start", {"version": settings.version}, None)
    try:
        yield
    finally:
        await bus.publish("server.stop", {}, None)
        ctx.repo.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.version,
        description="Build Anything Agent — orchestration API for the React console.",
        lifespan=lifespan,
    )
    app.state.ctx = build_context()

    # The console may be hosted on GitHub Pages (different origin) or served by
    # this process (same origin). Explicit origins, never "*" with credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_router(app.state.ctx), prefix="")

    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"ok": True, "app": settings.app_name, "version": settings.version}

    # Published sites live under /p/{slug}. Registered before the static mount
    # so the console's catch-all "/" can never shadow it.
    @app.get("/p/{slug}", include_in_schema=False)
    @app.get("/p/{slug}/{path:path}", include_in_schema=False)
    async def published(slug: str, path: str = "index.html") -> FileResponse:
        ctx: AppContext = app.state.ctx
        for run in ctx.repo.list(limit=200):
            if run.get("slug") != slug:
                continue
            content = ctx.runs.read_file(run["id"], path)
            if content is None:
                raise HTTPException(status_code=404, detail=f"not found: {path}")
            return FileResponse(
                content=content.encode("utf-8"),
                media_type=_guess_media_type(path),
            )
        raise HTTPException(status_code=404, detail=f"no published site: {slug}")

    # The React console owns every other path. This mount must come last so it
    # never shadows an API route.
    if settings.serve_console and settings.html_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(settings.html_dist), html=True),
            name="console",
        )
    else:
        @app.get("/", include_in_schema=False)
        async def no_console() -> RedirectResponse:
            return RedirectResponse(url="/api/health")

    return app


_MEDIA_TYPES = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".wasm": "application/wasm",
}


def _guess_media_type(path: str) -> str:
    suffix = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
    return _MEDIA_TYPES.get(suffix, "application/octet-stream")


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)
