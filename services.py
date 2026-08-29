"""
The demo's services.

Each site attaches only to its own stream. HQ publishes the catalogue to
`hq-stream:broadcasts` and consumes `hq-stream:requests`; the edge consumes
`edge-stream:broadcasts` and publishes `edge-stream:requests`. Neither ever addresses
the other's stream — Data Fabric stream replication is what carries messages across,
which is exactly the mechanism the demo exists to show.

Services are synchronous and short-lived: each drains what is waiting and returns, so
they can run on a timer in a worker thread without holding one open. Every outcome,
including failure, lands on the board so it is visible on screen rather than only in a
log.
"""

from __future__ import annotations

import logging
import random

import assets
import dfabric
import iceberger
import objectstore
import settings
import sites
import streams
import utils
from assets import Asset
from sites import EDGE as EDGE_SITE
from sites import HQ as HQ_SITE

logger = logging.getLogger(__name__)

# Distinct consumer groups so each service tracks its own offsets.
GROUP_PIPELINE = "hq-pipeline"
GROUP_REQUESTS = "hq-requests"
GROUP_BROADCASTS = "edge-broadcasts"
GROUP_RESPONSES = "edge-responses"


# ------------------------------------------------------------------ HQ services


def publish_to_pipeline(count: int = None) -> None:  # type: ignore[assignment]
    """Take items from the feed and announce them on HQ's internal pipeline stream."""
    count = settings.FEED_BATCH if count is None else count
    feed = utils.feed_items()
    if not feed:
        logger.warning("Feed is empty; nothing to publish")
        return

    for record in random.sample(feed, min(len(feed), count)):
        asset = Asset.from_record(record)
        if assets.HQ_BOARD.get(asset.key):
            continue  # already in flight; do not duplicate it on the board
        if streams.produce(dfabric.HQ, HQ_SITE.pipeline_stream, sites.TOPIC_PIPELINE,
                           [asset.to_record()]):
            assets.HQ_BOARD.place(asset, "pipeline")
        else:
            assets.HQ_BOARD.fail(asset, "Could not publish to the pipeline stream")


def pipeline_to_broadcast() -> None:
    """Store, catalogue and broadcast everything waiting on the pipeline."""
    for record in streams.drain(dfabric.HQ, HQ_SITE.pipeline_stream,
                                sites.TOPIC_PIPELINE, GROUP_PIPELINE):
        asset = assets.HQ_BOARD.get(record.get("key", "")) or Asset.from_record(record)

        ok, detail = objectstore.store_asset(dfabric.HQ, HQ_SITE, asset.key)
        if not ok:
            assets.HQ_BOARD.fail(asset, detail)
            continue
        assets.HQ_BOARD.place(asset, "download")

        # Narration is best-effort: a missing or slow vision model must not stop the
        # pipeline, because the demo still tells its story without it.
        asset.analysis = utils.describe_image(HQ_SITE, asset.key, asset.description)

        if not iceberger.write_asset(HQ_SITE, asset):
            assets.HQ_BOARD.fail(asset, "Could not write to the Iceberg table")
            continue
        assets.HQ_BOARD.place(asset, "record")

        if streams.produce(dfabric.HQ, HQ_SITE.stream, sites.TOPIC_BROADCASTS,
                           [asset.to_record()]):
            assets.HQ_BOARD.place(asset, "broadcast")
        else:
            assets.HQ_BOARD.fail(asset, "Could not broadcast to edge sites")


def request_listener() -> None:
    """Answer edge requests: deliver the asset, then confirm on the stream."""
    for record in streams.drain(dfabric.HQ, HQ_SITE.stream,
                                sites.TOPIC_REQUESTS, GROUP_REQUESTS):
        if record.get("status") != "requested":
            continue

        asset = assets.HQ_BOARD.get(record.get("key", "")) or Asset.from_record(record)
        asset.status = "requested"
        assets.HQ_BOARD.place(asset, "request")

        ok, detail = objectstore.deliver_to_edge(
            dfabric.HQ, HQ_SITE, dfabric.EDGE, EDGE_SITE, asset.key)
        if not ok:
            assets.HQ_BOARD.fail(asset, detail)
            continue

        asset.status = "delivered"
        if streams.produce(dfabric.HQ, HQ_SITE.stream, sites.TOPIC_RESPONSES,
                           [asset.to_record()]):
            assets.HQ_BOARD.place(asset, "response")
        else:
            assets.HQ_BOARD.fail(asset, "Delivered the asset but could not confirm to the edge")


def hq_cycle() -> None:
    """One turn of the HQ pipeline, safe to call on a timer."""
    publish_to_pipeline()
    pipeline_to_broadcast()
    request_listener()


# ---------------------------------------------------------------- EDGE services


def broadcast_listener() -> None:
    """Receive descriptions from HQ and record them in the edge's own catalogue."""
    for record in streams.drain(dfabric.EDGE, EDGE_SITE.stream,
                                sites.TOPIC_BROADCASTS, GROUP_BROADCASTS):
        asset = Asset.from_record(record, stage="receive")
        if assets.EDGE_BOARD.get(asset.key):
            continue  # a redelivery, not news

        if iceberger.write_asset(EDGE_SITE, asset):
            assets.EDGE_BOARD.place(asset, "receive")
        else:
            assets.EDGE_BOARD.fail(asset, "Could not write to the edge catalogue")


def request_asset(asset: Asset) -> bool:
    """Ask HQ for the full image. Called when a presenter clicks an available asset."""
    asset.status = "requested"
    if streams.produce(dfabric.EDGE, EDGE_SITE.stream, sites.TOPIC_REQUESTS,
                       [asset.to_record()]):
        assets.EDGE_BOARD.place(asset, "request")
        return True
    assets.EDGE_BOARD.fail(asset, "Could not send the request upstream")
    return False


def response_listener() -> None:
    """Notice HQ's confirmations that an asset has landed in the edge's bucket."""
    for record in streams.drain(dfabric.EDGE, EDGE_SITE.stream,
                                sites.TOPIC_RESPONSES, GROUP_RESPONSES):
        if record.get("status") != "delivered":
            continue
        asset = assets.EDGE_BOARD.get(record.get("key", "")) or Asset.from_record(record)
        asset.status = "delivered"
        assets.EDGE_BOARD.place(asset, "response")


def edge_cycle() -> None:
    """One turn of the edge services, safe to call on a timer."""
    broadcast_listener()
    response_listener()


# Source shown when a stage header is clicked, so the audience can see the code behind
# the step being narrated.
CODE = {
    "HQ": {
        "pipeline": [publish_to_pipeline, streams.produce],
        "download": [objectstore.store_asset],
        "record": [iceberger.write_asset],
        "broadcast": [pipeline_to_broadcast],
        "request": [request_listener],
        "response": [objectstore.deliver_to_edge],
    },
    "EDGE": {
        "receive": [broadcast_listener, streams.drain],
        "request": [request_asset],
        "response": [response_listener],
    },
}
