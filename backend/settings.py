"""
Names, layout and presentation constants for the demo.

Cluster connections live in connections.py and are configurable at runtime. Nothing
here reads the local filesystem for cluster details: the cluster name comes from the
cluster itself, not from a mapr-clusters.conf that only exists on a node.
"""

import logging
import os
from pathlib import Path

# Current botocore adds CRC32 checksums and aws-chunked encoding by default, which the
# Data Fabric S3 gateway rejects (XAmzContentSHA256Mismatch) on every upload. Set before
# any boto3 or s3fs client is constructed.
os.environ.setdefault("AWS_REQUEST_CHECKSUM_CALCULATION", "when_required")
os.environ.setdefault("AWS_RESPONSE_CHECKSUM_VALIDATION", "when_required")

TITLE = "Satellite"
HQ_TITLE = "HQ — Command & Control"
EDGE_TITLE = "Edge — Mission Control"

BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

# How often the server pushes a state snapshot to connected browsers, and how often it
# re-probes each cluster. Status is cached between probes so the interface never waits
# on the cluster to render.
PUSH_INTERVAL = float(os.environ.get("PUSH_INTERVAL", "1"))
STATUS_INTERVAL = int(os.environ.get("STATUS_INTERVAL", "15"))

# Vision model defaults; both are changeable at runtime from the interface.
AI_ENDPOINT = os.environ.get("AI_ENDPOINT", "")   # empty disables narration
AI_MODEL = os.environ.get("AI_MODEL", "llava-v1.5")

# --------------------------------------------------------------- what lives where
#
# Per-site names (volumes, streams, buckets) live in sites.py, because HQ and the edge
# own separate sets of them and each side provisions only its own.

# Bundled sample imagery. Extracted to a local staging directory and uploaded to the HQ
# bucket as each asset flows through the pipeline, so "Stored" is a real write rather
# than a lookup of something Configure pre-loaded.
# Resolved against the app root (the parent of backend/) so the server can be started
# from any working directory.
_ROOT = Path(__file__).resolve().parent.parent
IMAGE_ARCHIVE = str(_ROOT / "downloaded_images.tar")
IMAGE_STAGING = os.environ.get("IMAGE_STAGING", str(_ROOT / "images"))
FEED_FILE = str(_ROOT / "images.json")

# --------------------------------------------------------------------- the stages
#
# The demo's whole story is an asset moving left to right through these stages. The UI
# renders one column per stage in this order, and an asset occupies exactly one of them
# at a time, so the board shows a pipeline rather than a pile of duplicate cards.

HQ_STAGES = ["pipeline", "download", "record", "broadcast", "request", "response"]
EDGE_STAGES = ["receive", "request", "response"]

STAGE_LABELS = {
    "pipeline": "Ingested",
    "download": "Stored",
    "record": "Catalogued",
    "broadcast": "Broadcast",
    "request": "Requested",
    "response": "Delivered",
    "receive": "Available",
    "failed": "Failed",
}

STAGE_HELP = {
    "pipeline": "Feed item picked up and published to the pipeline stream",
    "download": "Image fetched and stored in the HQ bucket",
    "record": "Metadata and AI narration written to the Iceberg table",
    "broadcast": "Description published to every edge site",
    "request": "An edge site asked for the full asset",
    "response": "Asset copied across for the edge to collect",
    "receive": "Description received — click to request the image",
    "failed": "Something went wrong; open the tile for the reason",
}

STAGE_COLORS = {
    "pipeline": "bg-indigo-6",
    "download": "bg-cyan-7",
    "record": "bg-teal-7",
    "broadcast": "bg-green-7",
    "request": "bg-amber-8",
    "response": "bg-deep-orange-7",
    "receive": "bg-indigo-6",
    "failed": "bg-red-7",
}

ICONS = {
    "pipeline": "input",
    "download": "cloud_download",
    "record": "table_rows",
    "broadcast": "podcasts",
    "request": "front_hand",
    "response": "inventory",
    "receive": "inbox",
    "failed": "error_outline",
}

# How many tiles a stage column keeps. Older ones retire so a demo can run for an hour
# without the page growing without bound.
COLUMN_LIMIT = int(os.environ.get("COLUMN_LIMIT", "8"))
# Seconds between feed injections. Slow enough to narrate over.
FEED_INTERVAL = float(os.environ.get("FEED_INTERVAL", "12"))
# Assets injected per interval.
FEED_BATCH = int(os.environ.get("FEED_BATCH", "2"))

APP_STATUS: dict = {}

# --------------------------------------------------------------------- log levels

for noisy in ("urllib3", "httpcore", "httpx", "requests", "watchfiles", "botocore",
              "boto3", "s3transfer", "pyiceberg.io", "openai", "asyncio"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
