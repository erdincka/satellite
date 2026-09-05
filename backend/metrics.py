"""
Rolling metrics for the charts and the replication link.

Everything here is bounded and in memory. A demo that runs for an hour must not grow a
metrics store for an hour, and none of this is worth persisting.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

# One sample per second, twelve minutes of history. Enough to show a trend during a
# walkthrough without holding anything meaningful in memory.
WINDOW_SECONDS = 720


@dataclass
class Series:
    """A bounded time series of (timestamp, value)."""

    points: deque = field(default_factory=lambda: deque(maxlen=WINDOW_SECONDS))

    def add(self, value: float, at: float | None = None) -> None:
        self.points.append((at or time.time(), value))

    def since(self, seconds: float) -> list[tuple[float, float]]:
        cutoff = time.time() - seconds
        return [(t, v) for t, v in self.points if t >= cutoff]


class Metrics:
    """Counters, rates and latencies for one site."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Monotonic counters, sampled once a second into rates.
        self.counters: dict[str, int] = {}
        self._last_sample: dict[str, int] = {}
        self.rates: dict[str, Series] = {}
        # End-to-end time from an asset entering the pipeline to being broadcast.
        self.latencies: deque = deque(maxlen=200)
        self.replication_lag = Series()
        self.bytes_moved = 0

    def count(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self.counters[name] = self.counters.get(name, 0) + amount

    def record_latency(self, seconds: float) -> None:
        with self._lock:
            self.latencies.append(seconds)

    def record_bytes(self, count: int) -> None:
        with self._lock:
            self.bytes_moved += count

    def sample(self) -> None:
        """Turn counters into per-second rates. Called once a second by the runner."""
        now = time.time()
        with self._lock:
            for name, total in self.counters.items():
                previous = self._last_sample.get(name, total)
                self.rates.setdefault(name, Series()).add(max(0, total - previous), now)
                self._last_sample[name] = total

    def snapshot(self, window: int = 180) -> dict:
        with self._lock:
            latencies = sorted(self.latencies)
            return {
                "counters": dict(self.counters),
                "bytesMoved": self.bytes_moved,
                "rates": {
                    name: [{"t": round(t, 1), "v": v} for t, v in series.since(window)]
                    for name, series in self.rates.items()
                },
                "replicationLag": [
                    {"t": round(t, 1), "v": v} for t, v in self.replication_lag.since(window)
                ],
                "latency": {
                    "count": len(latencies),
                    "p50": _percentile(latencies, 0.50),
                    "p95": _percentile(latencies, 0.95),
                    "last": latencies[-1] if latencies else None,
                },
            }


def _percentile(ordered: list[float], fraction: float) -> float | None:
    if not ordered:
        return None
    index = min(len(ordered) - 1, int(len(ordered) * fraction))
    return round(ordered[index], 2)


HQ = Metrics()
EDGE = Metrics()


def for_side(side: str) -> Metrics:
    return HQ if side.upper() == "HQ" else EDGE
