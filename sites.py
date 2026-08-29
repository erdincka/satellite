"""
What each site owns on its cluster.

HQ and the edge are fully independent: separate volumes, separate streams, separate
buckets, distinguished by name rather than by which cluster they happen to live on.
Neither side reads or writes the other's stream — data crosses between them only via
Data Fabric stream replication. That means the demo behaves identically whether both
sites share one cluster or sit on two, and moving the edge to its own cluster is a
change to .env rather than to the design.

Every name is overridable, because `hq-volume` and `edge-volume` are generic enough to
collide on a shared lab cluster.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Topic names are the same on both sides. Replication preserves topic names, so a
# broadcast published to hq-stream:broadcasts arrives as edge-stream:broadcasts — the
# name is the contract, and the stream it lives on says whose copy it is.
TOPIC_BROADCASTS = "broadcasts"   # HQ → edge: the catalogue
TOPIC_REQUESTS = "requests"       # edge → HQ: "send me this one"
TOPIC_RESPONSES = "responses"     # HQ → edge: "it is in your bucket"

# HQ's internal hand-off between its own services. Deliberately on a separate,
# unreplicated stream: it is HQ's business, and replicating it would push HQ's internal
# chatter down a link the demo is meant to be frugal with.
TOPIC_PIPELINE = "pipeline"

# Topics carried by the replicated stream pair, created on the HQ side and mirrored.
REPLICATED_TOPICS = (TOPIC_BROADCASTS, TOPIC_REQUESTS, TOPIC_RESPONSES)


@dataclass(frozen=True)
class Site:
    """The objects one site owns."""

    side: str               # "HQ" or "EDGE"
    volume_name: str        # e.g. hq-volume
    volume_path: str        # e.g. /apps/hq-volume
    stream: str             # the replicated stream this side attaches to
    assets_bucket: str      # imagery this side holds
    warehouse_bucket: str   # this side's Iceberg warehouse
    pipeline_stream: str | None = None  # HQ only: internal, unreplicated

    @property
    def stream_name(self) -> str:
        return self.stream.rsplit("/", 1)[-1]

    @property
    def buckets(self) -> tuple[str, ...]:
        return (self.assets_bucket, self.warehouse_bucket)

    @property
    def streams(self) -> tuple[str, ...]:
        return tuple(s for s in (self.stream, self.pipeline_stream) if s)


APP = os.environ.get("APP_NAME", "satellite")


def _name(side: str, key: str, default: str) -> str:
    return os.environ.get(f"{side}_{key}", default)


def _build(side: str, prefix: str) -> Site:
    # Volumes carry the app name so they are identifiable on a shared cluster; streams
    # and buckets carry the side prefix so ownership is obvious at a glance.
    volume = _name(side, "VOLUME_NAME", f"{APP}-{prefix}")
    path = _name(side, "VOLUME_PATH", f"/apps/{volume}")
    return Site(
        side=side,
        volume_name=volume,
        volume_path=path,
        stream=_name(side, "STREAM", f"{path}/{prefix}-stream"),
        assets_bucket=_name(side, "ASSETS_BUCKET", f"{prefix}-assets"),
        warehouse_bucket=_name(side, "WAREHOUSE_BUCKET", f"{prefix}-warehouse"),
        pipeline_stream=(f"{path}/{prefix}-pipeline" if side == "HQ" else None),
    )


HQ = _build("HQ", os.environ.get("HQ_PREFIX", "hq"))
EDGE = _build("EDGE", os.environ.get("EDGE_PREFIX", "edge"))


def for_side(side: str) -> Site:
    return HQ if side.upper() == "HQ" else EDGE
