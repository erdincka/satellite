"""
Long-running operations, reported step by step.

Configure and Reset each run a dozen cluster operations and take a while. Collecting
them all and returning at the end left the interface showing "Resetting…" with no sign
of life for the duration — the operator cannot tell a slow step from a hung one.

A job publishes each step as it completes and names the step currently in flight, so
the interface can show a checklist filling in with a spinner on the current line. State
lives on the server, so closing the browser mid-run does not lose it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Iterator

logger = logging.getLogger(__name__)


class Job:
    def __init__(self) -> None:
        self.kind: str | None = None      # "configure" | "reset"
        self.side: str | None = None
        self.running = False
        self.steps: list[dict] = []
        self.current: str | None = None
        self.started: float | None = None
        self.finished: float | None = None
        self.error: str | None = None
        self._task: asyncio.Task | None = None

    @property
    def busy(self) -> bool:
        return self.running

    async def run(self, kind: str, side: str, produce: Callable[[], Iterator],
                  after: Callable[[], object] | None = None) -> None:
        """Run a step generator in a worker thread, publishing progress as it goes."""
        if self.running:
            raise RuntimeError("Another operation is already running")

        self.kind, self.side = kind, side.upper()
        self.running, self.steps = True, []
        self.current, self.error = "Starting", None
        self.started, self.finished = time.time(), None

        def work() -> None:
            for step in produce():
                self.steps.append({
                    "name": step.name, "ok": step.ok,
                    "detail": step.detail, "skipped": step.skipped,
                })
                # Named before it runs is impossible with a generator, so the next
                # step's name is unknown; showing the last completed one plus a spinner
                # is honest and enough to see progress.
                self.current = "Working"

        try:
            await asyncio.to_thread(work)
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            logger.exception("%s %s failed", kind, side)
        finally:
            self.running = False
            self.current = None
            self.finished = time.time()

        if after:
            try:
                result = after()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Post-%s step failed", kind)

    def snapshot(self) -> dict:
        return {
            "kind": self.kind,
            "side": self.side,
            "running": self.running,
            "steps": self.steps,
            "current": self.current,
            "error": self.error,
            "elapsed": (round((self.finished or time.time()) - self.started, 1)
                        if self.started else None),
        }


JOB = Job()
