"""
The demo's services.

HQ: feed → pipeline → download → catalogue → broadcast, plus a listener that answers
edge requests. Edge: receive descriptions, request an asset, collect it when it lands.

Each service is synchronous and short-lived by design — it drains whatever is waiting
and returns — so it can be run on a timer in a worker thread without holding one open.
Every outcome, including failure, is recorded on the board so it is visible on screen
instead of only in a log.
"""

from __future__ import annotations

import logging
import random

import assets
import dfabric
import iceberger
import objectstore
import settings
import streams
import utils
from assets import Asset

logger = logging.getLogger(__name__)

# Distinct groups so HQ and edge consumers track their own offsets independently.
GROUP_PIPELINE = "hq-pipeline"
GROUP_REQUESTS = "hq-requests"
GROUP_ASSETS = "edge-assets"
GROUP_RESPONSES = "edge-responses"


# ------------------------------------------------------------------ HQ services


def publish_to_pipeline(count: int = settings.FEED_BATCH) -> None:
    """Take items from the feed and announce them on the pipeline stream."""
    feed = utils.feed_items()
    if not feed:
        logger.warning("Feed is empty; nothing to publish")
        return

    for record in random.sample(feed, min(len(feed), count)):
        asset = Asset.from_record(record)
        if streams.produce(dfabric.HQ, settings.HQ_STREAM, settings.PIPELINE, [asset.to_record()]):
            assets.HQ_BOARD.place(asset, "pipeline")
        else:
            assets.HQ_BOARD.fail(asset, "Could not publish to the pipeline stream")


def pipeline_to_broadcast() -> None:
    """Download, catalogue and broadcast everything waiting on the pipeline."""
    for record in streams.drain(dfabric.HQ, settings.HQ_STREAM, settings.PIPELINE, GROUP_PIPELINE):
        asset = assets.HQ_BOARD.get(record.get("key", "")) or Asset.from_record(record)

        if not objectstore.stage_for_download(dfabric.HQ, asset.key):
            assets.HQ_BOARD.fail(asset, f"{asset.key} is not in {settings.HQ_BUCKET}")
            continue
        assets.HQ_BOARD.place(asset, "download")

        # Narration is best-effort: a missing or slow VLM must not stop the pipeline,
        # because the demo still tells its story without it.
        asset.analysis = utils.describe_image(asset.key, asset.description)

        if not iceberger.write_asset(asset):
            assets.HQ_BOARD.fail(asset, "Could not write to the Iceberg table")
            continue
        assets.HQ_BOARD.place(asset, "record")

        if streams.produce(dfabric.HQ, settings.HQ_STREAM, settings.ASSET_TOPIC,
                           [asset.to_record()]):
            assets.HQ_BOARD.place(asset, "broadcast")
        else:
            assets.HQ_BOARD.fail(asset, "Could not broadcast to edge sites")


def request_listener() -> None:
    """Answer edge requests by copying the asset across and confirming on the stream."""
    for record in streams.drain(dfabric.HQ, settings.HQ_STREAM, settings.REQUEST_TOPIC,
                                GROUP_REQUESTS):
        if record.get("status") != "requested":
            continue

        asset = assets.HQ_BOARD.get(record.get("key", "")) or Asset.from_record(record)
        asset.status = "requested"
        assets.HQ_BOARD.place(asset, "request")

        if not objectstore.transfer_to_edge(dfabric.HQ, asset.key):
            assets.HQ_BOARD.fail(asset, "Could not copy the asset to the edge bucket")
            continue

        asset.status = "responded"
        if streams.produce(dfabric.HQ, settings.HQ_STREAM, settings.RESPONSE_TOPIC,
                           [asset.to_record()]):
            assets.HQ_BOARD.place(asset, "response")
        else:
            assets.HQ_BOARD.fail(asset, "Copied the asset but could not confirm to the edge")


def hq_cycle() -> None:
    """One full turn of the HQ pipeline, safe to call on a timer."""
    publish_to_pipeline()
    pipeline_to_broadcast()
    request_listener()


# ---------------------------------------------------------------- EDGE services


def asset_listener() -> None:
    """Receive broadcast descriptions and record them in the edge catalogue."""
    for record in streams.drain(dfabric.EDGE, settings.EDGE_STREAM, settings.ASSET_TOPIC,
                                GROUP_ASSETS):
        asset = Asset.from_record(record, stage="receive")
        if assets.EDGE_BOARD.get(asset.key):
            continue  # already known; a redelivery, not news

        if iceberger.write_asset(asset, namespace="EDGE"):
            assets.EDGE_BOARD.place(asset, "receive")
        else:
            assets.EDGE_BOARD.fail(asset, "Could not write to the edge catalogue")


def request_asset(asset: Asset) -> bool:
    """Ask HQ for the full image. Called when a presenter clicks an available asset."""
    asset.status = "requested"
    if streams.produce(dfabric.EDGE, settings.EDGE_STREAM, settings.REQUEST_TOPIC,
                       [asset.to_record()]):
        assets.EDGE_BOARD.place(asset, "request")
        return True
    assets.EDGE_BOARD.fail(asset, "Could not send the request upstream")
    return False


def response_listener() -> None:
    """Notice HQ's confirmations. The image is collected separately, on demand."""
    for record in streams.drain(dfabric.EDGE, settings.EDGE_STREAM, settings.RESPONSE_TOPIC,
                                GROUP_RESPONSES):
        if record.get("status") != "responded":
            continue
        asset = assets.EDGE_BOARD.get(record.get("key", "")) or Asset.from_record(record)
        asset.status = "available"
        assets.EDGE_BOARD.place(asset, "response")


def edge_cycle() -> None:
    """One full turn of the edge services, safe to call on a timer."""
    asset_listener()
    response_listener()


# Source shown in the UI when a stage header is clicked, so the audience can see the
# code behind the step being narrated.
CODE = {
    "HQ": {
        "pipeline": [publish_to_pipeline, streams.produce],
        "download": [objectstore.stage_for_download],
        "record": [iceberger.write_asset],
        "broadcast": [pipeline_to_broadcast],
        "request": [request_listener],
        "response": [objectstore.transfer_to_edge],
    },
    "EDGE": {
        "receive": [asset_listener, streams.drain],
        "request": [request_asset],
        "response": [response_listener],
    },
}
