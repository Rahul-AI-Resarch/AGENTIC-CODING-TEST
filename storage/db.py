"""SQLite-backed run metadata.

stdlib ``sqlite3`` only — no ORM, no async driver. The dataset is tiny (one row
per build) so a thread-safe synchronous repository behind the FastAPI threadpool
is more than enough, and it keeps the dependency list short.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    mode        TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    prompt      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'queued',
    phase       TEXT NOT NULL DEFAULT 'intake',
    slug        TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_slug ON runs(slug);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
"""

VALID_MODES = ("website", "game")
VALID_STATUSES = ("queued", "running", "paused", "failed", "done", "cancelled")


class RunRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    # -- writes ------------------------------------------------------------
    def create(self, run: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        record = {
            "id": run["id"],
            "mode": run.get("mode", "website"),
            "title": run.get("title", "") or "Untitled",
            "prompt": run.get("prompt", ""),
            "status": run.get("status", "queued"),
            "phase": run.get("phase", "intake"),
            "slug": run["slug"],
            "created_at": now,
            "updated_at": now,
            "metadata": json.dumps(run.get("metadata", {})),
        }
        conn = self._require()
        with self._lock:
            conn.execute(
                """INSERT INTO runs
                   (id, mode, title, prompt, status, phase, slug, created_at, updated_at, metadata)
                   VALUES (:id, :mode, :title, :prompt, :status, :phase, :slug, :created_at, :updated_at, :metadata)""",
                record,
            )
            conn.commit()
        return self.get(record["id"])  # type: ignore[return-value]

    def update(self, run_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get(run_id)
        allowed = {"mode", "title", "prompt", "status", "phase", "slug", "metadata"}
        data = {k: v for k, v in fields.items() if k in allowed}
        if "metadata" in data and not isinstance(data["metadata"], str):
            data["metadata"] = json.dumps(data["metadata"])
        data["updated_at"] = time.time()
        assignments = ", ".join(f"{k} = :{k}" for k in data)
        conn = self._require()
        with self._lock:
            conn.execute(
                f"UPDATE runs SET {assignments} WHERE id = :id",
                {**data, "id": run_id},
            )
            conn.commit()
        return self.get(run_id)

    def delete(self, run_id: str) -> bool:
        conn = self._require()
        with self._lock:
            cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.commit()
        return cur.rowcount > 0

    # -- reads -------------------------------------------------------------
    def get(self, run_id: str) -> dict[str, Any] | None:
        conn = self._require()
        with self._lock:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._require()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def taken_slugs(self) -> set[str]:
        conn = self._require()
        with self._lock:
            rows = conn.execute("SELECT slug FROM runs").fetchall()
        return {r["slug"] for r in rows}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        data["metadata"] = json.loads(data.get("metadata") or "{}")
    except json.JSONDecodeError:
        data["metadata"] = {}
    return data
