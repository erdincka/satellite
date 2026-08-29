"""
Names, layout and presentation constants for the demo.

Connection details live in dfabric.py. Nothing here touches the local filesystem: the
cluster name is resolved from the cluster itself, not read from a mapr-clusters.conf
that only exists on a node with the native client installed.
"""

import logging
import os

TITLE = "Satellite"
HQ_TITLE = "HQ — Command & Control"
EDGE_TITLE = "Edge — Mission Control"

# NiceGUI signs its browser storage cookie with this. Override in any deployment that
# is reachable by someone you would not hand a shell to.
STORAGE_SECRET = os.environ.get("STORAGE_SECRET", "ezmer@1r0cks")

HQ_PORT = int(os.environ.get("HQ_PORT", "3000"))
EDGE_PORT = int(os.environ.get("EDGE_PORT", "3001"))
# Shown on each page so a presenter can jump to the other site.
HQ_URL = os.environ.get("HQ_URL", f"http://localhost:{HQ_PORT}")
EDGE_URL = os.environ.get("EDGE_URL", f"http://localhost:{EDGE_PORT}")

# --------------------------------------------------------------- what lives where
#
# Per-site names (volumes, streams, buckets) live in sites.py, because HQ and the edge
# own separate sets of them and each side provisions only its own.

# Bundled sample imagery. Extracted to a local staging directory and uploaded to the HQ
# bucket as each asset flows through the pipeline, so "Stored" is a real write rather
# than a lookup of something Configure pre-loaded.
IMAGE_ARCHIVE = "downloaded_images.tar"
IMAGE_STAGING = os.environ.get("IMAGE_STAGING", "images")
FEED_FILE = "images.json"

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
