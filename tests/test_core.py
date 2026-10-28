"""Core unit tests — standard library only.

Run without installing anything::

    python tests/test_core.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.handlers import AppContext, HttpError, HANDLERS  # noqa: E402
from api.routes_table import ROUTES, STREAMING_ROUTES  # noqa: E402
from core.config import Settings  # noqa: E402
from core.events import EventBus  # noqa: E402
from core.ids import new_run_id, slugify, unique_slug  # noqa: E402
from storage.db import RunRepository  # noqa: E402
from storage.runs import RunStore  # noqa: E402


def make_ctx(tmp: Path) -> AppContext:
    settings = Settings(
        root=tmp,
        data_dir=tmp / "data",
        runs_dir=tmp / "data" / "runs",
        db_path=tmp / "data" / "baa.db",
        html_dist=tmp / "html" / "dist",
    )
    settings.ensure_dirs()
    repo = RunRepository(settings.db_path)
    repo.connect()
    return AppContext(settings=settings, repo=repo, runs=RunStore(settings.runs_dir), bus=EventBus())


class TestConfig(unittest.TestCase):
    def test_ensure_dirs_creates_layout(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            s = Settings(data_dir=tmp / "data", runs_dir=tmp / "data" / "runs",
                         db_path=tmp / "data" / "baa.db", html_dist=tmp / "html" / "dist")
            s.ensure_dirs()
            self.assertTrue(s.data_dir.is_dir())
            self.assertTrue(s.runs_dir.is_dir())
            self.assertTrue(s.db_path.parent.is_dir())

    def test_cors_origins_are_explicit(self):
        s = Settings()
        self.assertNotIn("*", s.cors_origins)
        self.assertTrue(all(o.startswith("http") for o in s.cors_origins))


class TestIds(unittest.TestCase):
    def test_run_id_is_filesystem_safe(self):
        rid = new_run_id()
        self.assertRegex(rid, r"^[a-z0-9-]+$")
        self.assertNotIn("/", rid)

    def test_run_ids_are_unique(self):
        ids = {new_run_id() for _ in range(500)}
        self.assertEqual(len(ids), 500)

    def test_slugify(self):
        self.assertEqual(slugify("My Cool Game!"), "my-cool-game")
        self.assertEqual(slugify("   "), "site")
        self.assertEqual(slugify("Ünïcödé Tïtlé"), "n-c-d-t-tl")

    def test_unique_slug_avoids_collisions(self):
        taken = {"my-game"}
        self.assertEqual(unique_slug("My Game", taken), "my-game-2")
        self.assertEqual(unique_slug("Other", taken), "other")


class TestEventBus(unittest.TestCase):
    def test_publish_reaches_subscriber(self):
        async def scenario():
            bus = EventBus()
            queue_holder = {}

            async def consume():
                queue_holder["q"] = bus
                async for event in bus.subscribe():
                    return event

            task = asyncio.create_task(consume())
            await asyncio.sleep(0.05)
            await bus.publish("phase", {"name": "intake"}, "run-1")
            event = await asyncio.wait_for(task, timeout=2)
            self.assertEqual(event["kind"], "phase")
            self.assertEqual(event["data"]["name"], "intake")
            self.assertEqual(event["run_id"], "run-1")

        asyncio.run(asyncio.wait_for(scenario(), timeout=10))

    def test_slow_subscriber_does_not_block_publisher(self):
        async def scenario():
            bus = EventBus(maxsize=2)
            got: list = []

            async def consume():
                async for event in bus.subscribe():
                    got.append(event)

            # The consumer runs concurrently — a consumer that blocks the
            # publisher in the same coroutine would deadlock the bus.
            task = asyncio.create_task(consume())
            await asyncio.sleep(0.05)
            for i in range(20):
                await asyncio.wait_for(bus.publish("noise", {"i": i}), timeout=1)
            await asyncio.sleep(0.05)
            task.cancel()
            self.assertGreater(len(got), 0)
            self.assertLessEqual(len(got), 20)

        asyncio.run(asyncio.wait_for(scenario(), timeout=10))


class TestRepository(unittest.TestCase):
    def test_create_and_fetch(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = make_ctx(Path(d))
            run = ctx.repo.create({
                "id": "r1", "mode": "game", "title": "Snake",
                "prompt": "make snake", "slug": "snake",
            })
            self.assertEqual(run["title"], "Snake")
            self.assertEqual(run["status"], "queued")
            self.assertEqual(run["metadata"], {})
            self.assertIsNotNone(ctx.repo.get("r1"))
            self.assertIsNone(ctx.repo.get("nope"))

    def test_update_and_delete(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = make_ctx(Path(d))
            ctx.repo.create({"id": "r1", "title": "T", "prompt": "p", "slug": "t"})
            updated = ctx.repo.update("r1", status="running", phase="spec")
            self.assertEqual(updated["status"], "running")
            self.assertEqual(updated["phase"], "spec")
            self.assertTrue(ctx.repo.delete("r1"))
            self.assertFalse(ctx.repo.delete("r1"))

    def test_metadata_roundtrips_as_dict(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = make_ctx(Path(d))
            ctx.repo.create({"id": "r1", "title": "T", "prompt": "p", "slug": "t",
                             "metadata": {"reference": "pac-man"}})
            self.assertEqual(ctx.repo.get("r1")["metadata"]["reference"], "pac-man")

    def test_data_survives_reconnect(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ctx = make_ctx(tmp)
            ctx.repo.create({"id": "r1", "title": "T", "prompt": "p", "slug": "t"})
            ctx.repo.close()
            repo2 = RunRepository(tmp / "data" / "baa.db")
            repo2.connect()
            self.assertIsNotNone(repo2.get("r1"))
            repo2.close()


class TestRunStore(unittest.TestCase):
    def test_create_makes_standard_subdirs(self):
        with tempfile.TemporaryDirectory() as d:
            store = RunStore(Path(d))
            base = store.create("r1")
            for name in ("files", "retrieval", "tests", "playtest", "logs"):
                self.assertTrue((base / name).is_dir(), name)

    def test_path_traversal_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            store = RunStore(Path(d))
            store.create("r1")
            (store.files_dir("r1") / "ok.txt").write_text("hello")
            self.assertEqual(store.read_file("r1", "ok.txt"), "hello")
            self.assertIsNone(store.read_file("r1", "../../../etc/passwd"))
            self.assertIsNone(store.read_file("r1", "missing.txt"))

    def test_list_files_is_relative(self):
        with tempfile.TemporaryDirectory() as d:
            store = RunStore(Path(d))
            store.create("r1")
            (store.files_dir("r1") / "src").mkdir(parents=True, exist_ok=True)
            (store.files_dir("r1") / "src" / "a.js").write_text("x")
            files = store.list_files("r1")
            self.assertEqual([f["path"] for f in files], ["src/a.js"])


class TestHandlers(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ctx = make_ctx(Path(self._tmp.name))

    def tearDown(self):
        self.ctx.repo.close()
        self._tmp.cleanup()

    def test_health(self):
        status, payload = HANDLERS["health"](self.ctx)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], "3.0.0")

    def test_meta_lists_modes_and_pipeline(self):
        status, payload = HANDLERS["meta"](self.ctx)
        self.assertEqual(status, 200)
        self.assertEqual({m["id"] for m in payload["modes"]}, {"website", "game"})
        self.assertIn("playtest", payload["pipeline"])
        self.assertIn("critic", payload["orchestra"])

    def test_create_run_requires_prompt(self):
        with self.assertRaises(HttpError) as ctx:
            HANDLERS["create_run"](self.ctx, {"prompt": "  "})
        self.assertEqual(ctx.exception.status, 422)

    def test_create_run_rejects_unknown_mode(self):
        with self.assertRaises(HttpError) as ctx:
            HANDLERS["create_run"](self.ctx, {"prompt": "hi", "mode": "nope"})
        self.assertEqual(ctx.exception.status, 422)

    def test_create_run_makes_unique_slug(self):
        _, first = HANDLERS["create_run"](self.ctx, {"prompt": "snake game", "title": "Snake"})
        _, second = HANDLERS["create_run"](self.ctx, {"prompt": "snake game", "title": "Snake"})
        self.assertNotEqual(first["slug"], second["slug"])
        self.assertTrue(self.ctx.runs.exists(first["id"]))

    def test_get_run_404(self):
        with self.assertRaises(HttpError) as ctx:
            HANDLERS["get_run"](self.ctx, "missing")
        self.assertEqual(ctx.exception.status, 404)

    def test_delete_run_removes_files_too(self):
        _, run = HANDLERS["create_run"](self.ctx, {"prompt": "x"})
        self.assertTrue(self.ctx.runs.exists(run["id"]))
        HANDLERS["delete_run"](self.ctx, run["id"])
        self.assertFalse(self.ctx.runs.exists(run["id"]))

    def test_file_listing_roundtrip(self):
        _, run = HANDLERS["create_run"](self.ctx, {"prompt": "x"})
        (self.ctx.runs.files_dir(run["id"]) / "index.html").write_text("<h1>hi</h1>")
        status, payload = HANDLERS["list_files"](self.ctx, run["id"])
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        status, payload = HANDLERS["get_file"](self.ctx, run["id"], "index.html")
        self.assertEqual(payload["content"], "<h1>hi</h1>")


class TestRouteTable(unittest.TestCase):
    def test_every_route_has_a_handler(self):
        for route in ROUTES:
            if route.handler in STREAMING_ROUTES:
                continue  # streaming routes are implemented by the adapters
            self.assertIn(route.handler, HANDLERS, route.handler)

    def test_every_handler_is_reachable(self):
        declared = {r.handler for r in ROUTES}
        for name in HANDLERS:
            self.assertIn(name, declared, name)

    def test_streaming_handlers_have_no_direct_entry(self):
        for route in ROUTES:
            if route.handler in STREAMING_ROUTES:
                self.assertNotIn(route.handler, HANDLERS)

    def test_paths_are_unique(self):
        seen = set()
        for route in ROUTES:
            key = (route.method, route.path)
            self.assertNotIn(key, seen)
            seen.add(key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
