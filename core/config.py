"""Environment-driven settings.

Deliberately stdlib-only (no pydantic-settings) so the core stays importable
without installing anything. Values are read once at import time via
``settings``; use ``Settings.from_env()`` for an isolated instance in tests.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "BAA"
    version: str = "3.0.0"
    tagline: str = "Build Anything Agent — web retrieval + real-time playtest"

    host: str = "0.0.0.0"
    port: int = 8000

    root: Path = ROOT
    data_dir: Path = field(default_factory=lambda: ROOT / "data")
    runs_dir: Path = field(default_factory=lambda: ROOT / "data" / "runs")
    db_path: Path = field(default_factory=lambda: ROOT / "data" / "baa.db")
    html_dist: Path = field(default_factory=lambda: ROOT / "html" / "dist")

    # Origins allowed to call the API. The React console may be served from
    # GitHub Pages (cross-origin) or from this same server (same-origin).
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    serve_console: bool = True

    # Per-run orchestration budgets (surfaced in the UI, enforced by the Conductor).
    run_max_seconds: int = 3600
    run_max_llm_calls: int = 400
    run_max_tokens: int = 2_000_000

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(_env("BAA_ROOT", str(ROOT))).resolve()
        data_dir = Path(_env("BAA_DATA_DIR", str(root / "data"))).resolve()
        return cls(
            app_name=_env("BAA_APP_NAME", "BAA"),
            version=_env("BAA_VERSION", "3.0.0"),
            host=_env("BAA_HOST", "0.0.0.0"),
            port=_env_int("BAA_PORT", 8000),
            root=root,
            data_dir=data_dir,
            runs_dir=Path(_env("BAA_RUNS_DIR", str(data_dir / "runs"))).resolve(),
            db_path=Path(_env("BAA_DB_PATH", str(data_dir / "baa.db"))).resolve(),
            html_dist=Path(_env("BAA_HTML_DIST", str(root / "html" / "dist"))).resolve(),
            cors_origins=_env_list(
                "BAA_CORS_ORIGINS",
                ["http://localhost:5173", "http://127.0.0.1:5173"],
            ),
            serve_console=_env_bool("BAA_SERVE_CONSOLE", True),
            run_max_seconds=_env_int("BAA_RUN_MAX_SECONDS", 3600),
            run_max_llm_calls=_env_int("BAA_RUN_MAX_LLM_CALLS", 400),
            run_max_tokens=_env_int("BAA_RUN_MAX_TOKENS", 2_000_000),
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings.from_env()
