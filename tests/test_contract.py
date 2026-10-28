"""Contract test: the React console and the Python API must agree.

The backend declares its routes in ``api/routes_table.py``. The frontend
declares the paths it calls in ``html/src/api/paths.ts``. This test parses both
and asserts they describe the same set of endpoints — so renaming a route on
one side fails CI instead of 404ing in the browser.

Run with:  python tests/test_contract.py
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.handlers import HANDLERS  # noqa: E402
from api.routes_table import ROUTES, STREAMING_ROUTES  # noqa: E402

PATHS_TS = ROOT / "html" / "src" / "api" / "paths.ts"

# Frontend template-literal placeholders -> backend path-parameter names.
PLACEHOLDER_ALIASES = {
    "id": "{run_id}",
    "runId": "{run_id}",
    "run_id": "{run_id}",
    "path": "{path:path}",
    "filePath": "{path:path}",
}


def canonical(path: str) -> str:
    """Collapse both sides to a comparable shape.

    ``/api/runs/{run_id}/files/{path:path}`` -> ``/api/runs/*/files/**``
    ``/api/runs/${id}/files/${path}``         -> ``/api/runs/*/files/**``
    """
    # Frontend template placeholders are resolved through the alias table first,
    # so ${path} becomes the backend's catch-all {path:path}.
    out = re.sub(
        r"\$\{([^}]+)\}",
        lambda m: PLACEHOLDER_ALIASES.get(m.group(1), "{" + m.group(1) + "}"),
        path,
    )
    out = re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*:path\}", "**", out)
    out = re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", "*", out)
    return out


def extract_frontend_paths(source: str) -> list[str]:
    """Pull every /api/... path literal out of the TypeScript source."""
    found: list[str] = []
    # Double-quoted literals
    for match in re.finditer(r'"(/api/[^"]*)"', source):
        found.append(match.group(1))
    # Template literals
    for match in re.finditer(r"`(/api/[^`]*)`", source):
        found.append(match.group(1))
    return found


class TestContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PATHS_TS.exists():
            raise unittest.SkipTest(f"frontend paths file missing: {PATHS_TS}")
        cls.source = PATHS_TS.read_text(encoding="utf-8")
        cls.frontend_paths = extract_frontend_paths(cls.source)
        cls.backend_paths = [r.path for r in ROUTES]

    def test_frontend_declares_paths(self):
        self.assertGreater(
            len(self.frontend_paths), 0, "no /api paths found in paths.ts"
        )

    def test_every_frontend_path_exists_on_the_backend(self):
        backend = {canonical(p) for p in self.backend_paths}
        for path in self.frontend_paths:
            with self.subTest(path=path):
                self.assertIn(
                    canonical(path),
                    backend,
                    f"frontend calls {path!r} but the API declares no matching route",
                )

    def test_every_backend_route_is_called_by_the_frontend(self):
        frontend = {canonical(p) for p in self.frontend_paths}
        for route in ROUTES:
            with self.subTest(route=f"{route.method} {route.path}"):
                self.assertIn(
                    canonical(route.path),
                    frontend,
                    f"backend exposes {route.path!r} but the frontend never calls it",
                )

    def test_handlers_back_every_non_streaming_route(self):
        for route in ROUTES:
            if route.handler in STREAMING_ROUTES:
                continue
            with self.subTest(route=route.path):
                self.assertIn(route.handler, HANDLERS)

    def test_no_absolute_hardcoded_backend_hosts(self):
        """The frontend must not pin a backend hostname; VITE_API_URL is the knob."""
        for match in re.finditer(r"https?://[a-zA-Z0-9.\-]+", self.source):
            url = match.group(0)
            with self.subTest(url=url):
                self.assertIn(
                    url,
                    ("https://localhost", "http://localhost"),
                    f"hardcoded backend host in paths.ts: {url}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
