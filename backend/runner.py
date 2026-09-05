"""
Background execution and state broadcasting.

The services belong to the server, not to a browser tab. Previously they were driven by
`ui.timer` inside a page, so the demo only ran while someone was looking at it, two tabs
fought over the same queue, and closing the tab silently stopped everything. Here a
SiteRunner owns its own loop: close the browser and the pipeline keeps running; reopen
and the interface resynchronises from server state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import assets
import metrics
import provision
import services
import settings
import sites
import streams
from connections import CONNECTIONS

logger = logging.getLogger(__name__)


class SiteRunner:
    """Runs one site's services and keeps its status fresh."""

    def __init__(self, side: str) -> None:
        self.side = side.upper()
        self.running = False
        self.status: dict[str, Any] = {}
        self.ready = False
        self.busy = False
        self.last_error: str | None = None
        self._pending_bytes = 0
        self._task: asyncio.Task | None = None

    @property
    def site(self):
        return sites.for_side(self.side)

    @property
    def profile(self):
        return CONNECTIONS.profile(self.side)

    # ------------------------------------------------------------------ control

    def set_running(self, value: bool) -> None:
        self.running = bool(value)
        logger.info("%s services %s", self.side, "started" if value else "paused")

    async def cycle_once(self) -> None:
        """Run one turn of this site's services off the event loop."""
        if self.busy:
            return  # a slow cycle must not stack up behind itself
        self.busy = True
        try:
            work = services.hq_cycle if self.side == "HQ" else services.edge_cycle
            await asyncio.to_thread(work)
            self.last_error = None
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {error}"
            logger.exception("%s cycle failed", self.side)
        finally:
            self.busy = False

    async def refresh_status(self) -> None:
        """Probe the cluster in a worker thread and cache the result.

        Cached deliberately: the interface reads this snapshot instantly instead of
        waiting on the cluster, which is what makes the UI feel immediate.
        """
        if not CONNECTIONS.configured(self.side):
            self.status = {"cluster": (False, "no cluster configured — set one below")}
            self.ready = False
            return

        def probe() -> tuple[dict, bool, tuple[bool | None, str]]:
            profile, site = self.profile, self.site
            checks = profile.check(stream=site.stream)
            configured = provision.is_configured(profile, site)
            replication = streams.replication_status(profile, site.stream)
            return checks, configured, replication

        try:
            checks, ready, replication = await asyncio.to_thread(probe)
        except Exception as error:
            self.status = {"connection": (False, f"{type(error).__name__}: {error}")}
            self.ready = False
            return

        ok, detail, pending = replication
        if ok is not None:
            checks["replication"] = (ok, detail)

        # Whether this container can actually talk to the cluster as a client: the
        # ticket and the NFS mount, without which streams and imagery cannot work.
        import clientsetup
        checks["client setup"] = clientsetup.summary(self.side)
        self._pending_bytes = pending
        self.status = checks
        self.ready = ready

    # -------------------------------------------------------------------- loop

    async def loop(self) -> None:
        """Drive services, sample metrics, and refresh status on their own cadences."""
        tick = 0
        while True:
            try:
                if self.running and self.ready:
                    await self.cycle_once()
                metrics.for_side(self.side).sample()
                if tick % settings.STATUS_INTERVAL == 0:
                    await self.refresh_status()
                    self._sample_replication_lag()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s runner loop error", self.side)
            tick += 1
            await asyncio.sleep(1)

    def _sample_replication_lag(self) -> None:
        """Plot bytes in flight to the replica."""
        metrics.for_side(self.side).replication_lag.add(float(self._pending_bytes))

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.loop(), name=f"runner-{self.side}")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # ------------------------------------------------------------------ state

    def snapshot(self) -> dict:
        board = assets.board_for(self.side)
        site = self.site
        return {
            "side": self.side,
            "running": self.running,
            "ready": self.ready,
            "busy": self.busy,
            "lastError": self.last_error,
            "connection": CONNECTIONS.settings(self.side).redacted(),
            "status": {name: {"ok": ok, "detail": detail}
                       for name, (ok, detail) in self.status.items()},
            "objects": {
                "volume": site.volume_name,
                "volumePath": site.volume_path,
                "stream": site.stream,
                "pipelineStream": site.pipeline_stream,
                "assetsVolume": site.assets_volume,
                "assetsPath": site.assets_path,
                "outboundVolume": site.outbound_volume,
                "mirrorSource": site.mirror_source,
                "warehouseBucket": site.warehouse_bucket,
            },
            "stages": [
                {
                    "id": stage,
                    "label": settings.STAGE_LABELS[stage],
                    "help": settings.STAGE_HELP[stage],
                    "total": board.totals.get(stage, 0),
                    "assets": [_asset_json(a) for a in board.column(stage)],
                }
                for stage in board.stages + (["failed"] if board.column("failed") else [])
            ],
            "metrics": metrics.for_side(self.side).snapshot(),
        }


def _asset_json(asset) -> dict:
    return {
        "key": asset.key,
        "title": asset.title,
        "description": asset.description,
        "keywords": asset.keywords,
        "stage": asset.stage,
        "status": asset.status,
        "analysis": asset.analysis,
        "error": asset.error,
        "age": round(asset.age, 1),
        "seq": asset.seq,
    }


HQ = SiteRunner("HQ")
EDGE = SiteRunner("EDGE")
RUNNERS = {"HQ": HQ, "EDGE": EDGE}


def for_side(side: str) -> SiteRunner:
    return RUNNERS[side.upper()]


# --------------------------------------------------------------- broadcasting


class Hub:
    """Fans state out to every connected browser."""

    def __init__(self) -> None:
        self._clients: set = set()
        self._lock = asyncio.Lock()

    async def add(self, websocket) -> None:
        async with self._lock:
            self._clients.add(websocket)

    async def remove(self, websocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                await client.send_json(message)
            except Exception:
                await self.remove(client)

    async def push_state_forever(self) -> None:
        """Push a full snapshot on a steady cadence.

        A snapshot rather than deltas: the state is small, and it means a browser that
        reconnects is immediately correct with no replay logic.
        """
        while True:
            try:
                await self.broadcast({"type": "state", "payload": full_state()})
            except Exception:
                logger.exception("State broadcast failed")
            await asyncio.sleep(settings.PUSH_INTERVAL)


HUB = Hub()


def full_state() -> dict:
    import aiclient
    from link import LINK

    import filestore
    import jobs

    endpoint, model = aiclient.current()
    return {
        "job": jobs.JOB.snapshot(),
        "mounts": {side: dict(zip(("ok", "detail"), filestore.mounted(side)))
                   for side in ("HQ", "EDGE")},
        "model": {"endpoint": endpoint, "model": model, "configured": bool(endpoint)},
        "link": LINK.snapshot(),
        "sites": {side: runner.snapshot() for side, runner in RUNNERS.items()},
        "sameCluster": CONNECTIONS.same_cluster(),
        "feedSize": len(_feed()),
        "pace": {"interval": settings.FEED_INTERVAL, "batch": settings.FEED_BATCH},
        "time": time.time(),
    }


def _feed() -> list:
    import utils
    return utils.feed_items()
