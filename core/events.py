"""In-process async event bus.

The orchestrator publishes phase transitions, tool calls, ledger updates and
playtest frames here; the SSE endpoint at ``/api/runs/{run_id}/events``
subscribes and streams them to the React console in real time.

Stdlib-only on purpose: no Redis, no broker, no dependency. Swapping in a real
broker later means replacing this one class.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator


class EventBus:
    """Fan-out pub/sub with per-subscriber bounded queues.

    A slow subscriber drops its oldest events rather than blocking the
    publisher — the console should never stall the orchestrator.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._maxsize = maxsize
        self._history: list[dict[str, Any]] = []
        self._history_limit = 200
        self._lock = asyncio.Lock()

    async def publish(self, kind: str, data: dict[str, Any] | None = None,
                      run_id: str | None = None) -> None:
        event = {
            "kind": kind,
            "run_id": run_id,
            "ts": time.time(),
            "data": data or {},
        }
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                del self._history[: len(self._history) - self._history_limit]
            targets = list(self._subscribers)
        for queue in targets:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()  # drop oldest
                    queue.put_nowait(event)
                except Exception:
                    pass

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def history(self, run_id: str | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            if run_id is None:
                return list(self._history)
            return [e for e in self._history if e.get("run_id") == run_id]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


bus = EventBus()
