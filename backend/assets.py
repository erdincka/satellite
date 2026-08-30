"""
The asset model and the stage board.

The demo previously kept a list of dicts that the UI *consumed*: each render loop
popped items off and drew a card for each one. That had three consequences worth
naming, because avoiding them is the point of this module.

  - The same asset appeared as six unrelated cards, one per stage it passed through,
    so its journey was invisible.
  - Nothing ever removed a card, so the page grew without bound.
  - Because rendering removed items, a second browser tab stole assets from the first.

Here an Asset is a single object that *moves* between stages, the board keeps a bounded
history per stage, and rendering only reads. Any number of tabs can watch the same
board and all see the same thing.
"""

from __future__ import annotations

import itertools
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import settings

logger = logging.getLogger(__name__)

_counter = itertools.count(1)


@dataclass
class Asset:
    """One item of imagery as it travels through the demo."""

    key: str  # storage key, unique per asset
    title: str
    description: str
    keywords: str
    preview: str

    stage: str = "pipeline"
    status: str = ""
    analysis: str = ""       # AI narration produced at HQ
    error: str = ""          # why it failed, shown on the tile
    seq: int = field(default_factory=lambda: next(_counter))
    entered_stage: float = field(default_factory=time.time)
    history: list[tuple[str, float]] = field(default_factory=list)

    def advance(self, stage: str, error: str = "") -> "Asset":
        self.history.append((self.stage, self.entered_stage))
        self.stage = stage
        self.entered_stage = time.time()
        self.error = error
        return self

    @property
    def failed(self) -> bool:
        return self.stage == "failed"

    @property
    def age(self) -> float:
        return time.time() - self.entered_stage

    def to_record(self) -> dict:
        """Flat dict for the Iceberg table and for stream messages."""
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "keywords": self.keywords,
            "preview": self.preview,
            "status": self.status,
            "analysis": self.analysis,
        }

    @classmethod
    def from_record(cls, record: dict, stage: str = "pipeline") -> "Asset":
        from filestore import object_name

        preview = record.get("preview", "")
        return cls(
            key=record.get("key") or object_name(preview),
            title=record.get("title", "(untitled)"),
            description=record.get("description", ""),
            keywords=record.get("keywords", ""),
            preview=preview,
            stage=stage,
            status=record.get("status", ""),
            analysis=record.get("analysis", ""),
        )


class Board:
    """Bounded, thread-safe per-stage view of the assets in flight.

    Services mutate it from worker threads; the UI reads it from the event loop. The
    `version` counter lets the UI skip rebuilding when nothing has changed, which keeps
    a 1-second refresh from thrashing the DOM.
    """

    def __init__(self, side: str, stages: list[str]):
        self.side = side
        self.stages = stages
        self._columns: dict[str, deque[Asset]] = {
            stage: deque(maxlen=settings.COLUMN_LIMIT) for stage in stages + ["failed"]
        }
        self._by_key: dict[str, Asset] = {}
        self._lock = threading.RLock()
        self.version = 0
        # Cumulative counts, which is what a presenter actually wants to quote. The old
        # header numbers counted tiles drawn, so they reset whenever the view did.
        self.totals: dict[str, int] = {stage: 0 for stage in stages + ["failed"]}

    def place(self, asset: Asset, stage: str, error: str = "") -> Asset:
        """Move an asset into `stage`, removing it from whichever stage it was in."""
        with self._lock:
            for column in self._columns.values():
                if asset in column:
                    column.remove(asset)
            asset.advance(stage, error)
            self._columns.setdefault(stage, deque(maxlen=settings.COLUMN_LIMIT)).append(asset)
            self._by_key[asset.key] = asset
            self.totals[stage] = self.totals.get(stage, 0) + 1
            self.version += 1
            return asset

    def fail(self, asset: Asset, reason: str) -> Asset:
        logger.error("%s failed at %s: %s", asset.title, asset.stage, reason)
        return self.place(asset, "failed", reason)

    def column(self, stage: str) -> list[Asset]:
        with self._lock:
            return list(reversed(self._columns.get(stage, ())))  # newest first

    def get(self, key: str) -> Asset | None:
        with self._lock:
            return self._by_key.get(key)

    def snapshot(self) -> dict[str, list[Asset]]:
        with self._lock:
            return {stage: list(reversed(column)) for stage, column in self._columns.items()}

    def clear(self) -> None:
        with self._lock:
            for column in self._columns.values():
                column.clear()
            self._by_key.clear()
            self.totals = {stage: 0 for stage in self.totals}
            self.version += 1


HQ_BOARD = Board("HQ", settings.HQ_STAGES)
EDGE_BOARD = Board("EDGE", settings.EDGE_STAGES)


def board_for(side: str) -> Board:
    return HQ_BOARD if side.upper() == "HQ" else EDGE_BOARD
