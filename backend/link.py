"""
The link between the two sites.

A field deployment's link is not a wire that is either there or not — it is
intermittent, sometimes scheduled, and the interesting question is what happens to
queued work while it is down. This models that directly by pausing and resuming Data
Fabric stream replication:

    connected      replication runs continuously
    scheduled      the link opens for a window every interval, then closes again
    disconnected   replication is paused; both sides keep working and queue

Nothing is simulated. Pausing the replica is a real cluster operation, messages really
do accumulate, and resuming really does drain them — which is the point worth showing.

Replication is multi-master, so both directions are paused together: descriptions stop
reaching the edge and requests stop reaching HQ, exactly as a severed link would behave.

The link governs both mechanisms the demo uses. Streams carry descriptions and requests
continuously; the edge's assets volume is a mirror of HQ's outbound volume and is pulled
on demand. Cutting the link stops both, which is what a real outage does.
"""

from __future__ import annotations

import asyncio
import logging
import time

import sites
from connections import CONNECTIONS

logger = logging.getLogger(__name__)

CONNECTED = "connected"
SCHEDULED = "scheduled"
DISCONNECTED = "disconnected"


class Link:
    def __init__(self) -> None:
        self.mode = CONNECTED
        # A short window every couple of minutes reads well in a walkthrough: long
        # enough to watch a backlog drain, short enough that the queue rebuilds.
        self.interval = 120.0     # seconds between sync windows
        self.window = 20.0        # seconds each window stays open
        self.open = True          # whether replication is currently running
        self.last_change = time.time()
        self.next_change: float | None = None
        self.last_error: str | None = None
        self._mirror_cache: dict = {"known": False}
        self._mirror_checked = 0.0
        self._task: asyncio.Task | None = None

    async def refresh_mirror(self) -> None:
        """Refresh cached mirror state off the event loop.

        Deliberately not called from snapshot(): that runs on every state push, and a
        REST call there blocks the whole interface whenever the cluster is slow or
        unreachable — the interface stops responding rather than reporting the problem.
        """
        try:
            self._mirror_cache = await asyncio.to_thread(self.mirror_state)
        except Exception:
            self._mirror_cache = {"known": False}
        self._mirror_checked = time.time()

    # ------------------------------------------------------------------ cluster

    def _set_replication(self, running: bool) -> bool:
        """Pause or resume both directions of the multi-master pair."""
        profile = CONNECTIONS.profile("HQ")
        action = "resume" if running else "pause"
        pairs = (
            (sites.HQ.stream, sites.EDGE.stream),
            (sites.EDGE.stream, sites.HQ.stream),
        )
        failures = []
        for source, replica in pairs:
            response = profile.rest(f"stream/replica/{action}",
                                    {"path": source, "replica": replica},
                                    method="POST", timeout=30)
            reason = profile.failed(response)
            # A replica that is already in the requested state is not a failure.
            if reason and "not found" not in reason.lower():
                failures.append(f"{source}: {reason}")

        if failures:
            self.last_error = "; ".join(failures)
            logger.error("Could not %s replication: %s", action, self.last_error)
            return False

        self.last_error = None
        self.open = running
        self.last_change = time.time()
        logger.info("Link %s", "opened" if running else "closed")
        return True

    # -------------------------------------------------------------------- modes

    async def set_mode(self, mode: str, interval: float | None = None,
                       window: float | None = None) -> None:
        if interval is not None:
            self.interval = max(10.0, float(interval))
        if window is not None:
            self.window = max(5.0, float(window))

        self.mode = mode
        if mode == CONNECTED:
            self.next_change = None
            await asyncio.to_thread(self._set_replication, True)
        elif mode == DISCONNECTED:
            self.next_change = None
            await asyncio.to_thread(self._set_replication, False)
        else:  # scheduled — start closed so the first window is something to wait for
            await asyncio.to_thread(self._set_replication, False)
            self.next_change = time.time() + self.interval

    # ------------------------------------------------------------------- mirror

    def mirror_now(self) -> tuple[bool, str]:
        """Pull the edge's assets volume from HQ's outbound volume.

        This is the moment bandwidth is actually spent on imagery. Data Fabric moves the
        bytes; the application only asked for it.
        """
        profile = CONNECTIONS.profile("EDGE")
        volume = sites.EDGE.assets_volume
        response = profile.rest("volume/mirror/start", {"name": volume},
                                method="POST", timeout=60)
        reason = profile.failed(response)
        if reason:
            logger.error("Could not start mirror of %s: %s", volume, reason)
            return False, reason
        logger.info("Mirror started for %s", volume)
        return True, "mirror started"

    def mirror_state(self) -> dict:
        """Where the edge's mirror has got to, read from the cluster."""
        profile = CONNECTIONS.profile("EDGE")
        response = profile.rest("volume/info", {
            "name": sites.EDGE.assets_volume,
            "columns": "mirrorstatus,lastSuccessfulMirrorTime,mirrorpercentcomplete,"
                       "mirrorSrcVolume",
        }, timeout=15)
        if profile.failed(response):
            return {"known": False}
        record = (response.get("data") or [{}])[0]
        last = record.get("lastSuccessfulMirrorTime") or 0
        # mirrorstatus 0 means the last run succeeded.
        status = record.get("mirrorstatus")
        return {
            "known": True,
            "source": record.get("mirrorSrcVolume"),
            "percent": record.get("mirrorpercentcomplete"),
            "running": str(status) == "1",
            "ok": str(status) == "0",
            "secondsSinceSync": (round(time.time() - last / 1000) if last else None),
        }

    async def sync_now(self) -> None:
        """Open the link immediately for one window, whatever the mode.

        The manual equivalent of a scheduled sync: an operator deciding this is the
        moment to spend the link.
        """
        await asyncio.to_thread(self._set_replication, True)
        # Opening the link means both mechanisms flow, so pull the imagery too.
        await asyncio.to_thread(self.mirror_now)
        self.next_change = time.time() + self.window
        if self.mode == DISCONNECTED:
            self.mode = SCHEDULED

    # --------------------------------------------------------------------- loop

    async def loop(self) -> None:
        ticks = 0
        while True:
            try:
                ticks += 1
                if ticks % 5 == 0:
                    await self.refresh_mirror()
                if self.next_change and time.time() >= self.next_change:
                    if self.open:
                        await asyncio.to_thread(self._set_replication, False)
                        self.next_change = (time.time() + self.interval
                                            if self.mode == SCHEDULED else None)
                    else:
                        await asyncio.to_thread(self._set_replication, True)
                        await asyncio.to_thread(self.mirror_now)
                        self.next_change = time.time() + self.window
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Link loop error")
            await asyncio.sleep(1)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.loop(), name="link")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def snapshot(self) -> dict:
        return {
            "mode": self.mode,
            "open": self.open,
            "mirror": self._mirror_cache,
            "interval": self.interval,
            "window": self.window,
            "secondsToChange": (round(self.next_change - time.time(), 1)
                                if self.next_change else None),
            "lastError": self.last_error,
        }


LINK = Link()
