"""Run storage helpers — on-disk layout for a single build."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

# Sub-directories created for every run. Kept explicit so the layout is stable
# and the UI can rely on the paths existing.
SUBDIRS = ("files", "retrieval", "tests", "playtest", "logs")


class RunStore:
    """Filesystem layout for ``data/runs/<run_id>/``."""

    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = Path(runs_dir)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def create(self, run_id: str) -> Path:
        base = self.run_dir(run_id)
        for name in SUBDIRS:
            (base / name).mkdir(parents=True, exist_ok=True)
        return base

    def exists(self, run_id: str) -> bool:
        return self.run_dir(run_id).is_dir()

    def files_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "files"

    def write_meta(self, run_id: str, meta: dict[str, Any]) -> None:
        base = self.run_dir(run_id)
        base.mkdir(parents=True, exist_ok=True)
        (base / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def read_meta(self, run_id: str) -> dict[str, Any] | None:
        path = self.run_dir(run_id) / "run.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def list_files(self, run_id: str) -> list[dict[str, Any]]:
        """Return the generated file tree as a flat list of {path, size}."""
        root = self.files_dir(run_id)
        if not root.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for p in sorted(root.rglob("*")):
            if p.is_file():
                out.append({
                    "path": str(p.relative_to(root)).replace("\\", "/"),
                    "size": p.stat().st_size,
                })
        return out

    def read_file(self, run_id: str, rel_path: str) -> str | None:
        root = self.files_dir(run_id).resolve()
        target = (root / rel_path).resolve()
        # Path traversal guard: the resolved target must stay under the run's
        # files directory.
        if not str(target).startswith(str(root) + "/") and target != root:
            return None
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8", errors="replace")

    def delete(self, run_id: str) -> bool:
        base = self.run_dir(run_id)
        if not base.is_dir():
            return False
        shutil.rmtree(base, ignore_errors=True)
        return True
