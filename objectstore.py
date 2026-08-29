"""
Asset storage on the Data Fabric S3 gateway.

Replaces the POSIX operations the demo used to do against a /mapr FUSE mount, so the
app needs no mount and no native client for storage. Each site reads and writes its own
bucket; nothing here reaches into the other side's storage except the one deliberate
hand-off in `deliver_to_edge`.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import settings
from dfabric import Profile
from sites import Site

logger = logging.getLogger(__name__)


def object_name(preview_url: str) -> str:
    """The storage key for a feed item, taken from the tail of its preview URL."""
    return preview_url.rstrip("/").split("/")[-1]


def exists(profile: Profile, bucket: str, key: str) -> bool:
    s3 = profile.s3()
    if s3 is None:
        return False
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def get_bytes(profile: Profile, bucket: str, key: str) -> bytes | None:
    s3 = profile.s3()
    if s3 is None:
        return None
    try:
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except Exception as error:
        logger.debug("Could not read %s/%s: %s", bucket, key, error)
        return None


def put_bytes(profile: Profile, bucket: str, key: str, body: bytes) -> bool:
    s3 = profile.s3()
    if s3 is None:
        return False
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=BytesIO(body))
        return True
    except Exception as error:
        logger.error("Could not write %s/%s: %s", bucket, key, error)
        return False


def store_asset(profile: Profile, site: Site, key: str) -> tuple[bool, str]:
    """Take custody of an asset: read it from the local feed and write it to HQ's bucket.

    This is a real upload, not a lookup. The bytes live on local disk as the demo's
    stand-in for an external source, and the write to object storage is the moment HQ
    actually owns the asset — which is what the Stored stage claims on screen.

    Returns (ok, detail) so a failure can name itself on the tile.
    """
    source = Path(settings.IMAGE_STAGING) / key
    if not source.exists():
        return False, f"{key} is not in {settings.IMAGE_STAGING}/ — run Configure"

    if exists(profile, site.assets_bucket, key):
        return True, "already stored"

    try:
        data = source.read_bytes()
    except Exception as error:
        return False, f"Could not read {source}: {error}"

    if not put_bytes(profile, site.assets_bucket, key, data):
        return False, f"Could not write to {site.assets_bucket}"
    return True, f"{len(data) / 1024:.0f} KB to {site.assets_bucket}"


def deliver_to_edge(hq_profile: Profile, hq_site: Site,
                    edge_profile: Profile, edge_site: Site, key: str) -> tuple[bool, str]:
    """Copy a requested asset from HQ's bucket into the edge's bucket.

    This is the moment bandwidth is actually spent. Descriptions travel to every edge
    site continuously over the replicated stream; the image itself crosses only when a
    field team asks for it.

    Reads the bytes and writes them through the edge's own profile rather than using a
    server-side copy, because the two sites may be on different clusters — a
    CopyObject cannot span them, but a read-then-write can.
    """
    data = get_bytes(hq_profile, hq_site.assets_bucket, key)
    if data is None:
        return False, f"{key} not readable from {hq_site.assets_bucket}"
    if not put_bytes(edge_profile, edge_site.assets_bucket, key, data):
        return False, f"Could not write to {edge_site.assets_bucket}"
    logger.info("Delivered %s to %s (%d bytes)", key, edge_site.assets_bucket, len(data))
    return True, f"{len(data) / 1024:.0f} KB delivered"


def bucket_count(profile: Profile, bucket: str) -> int | None:
    s3 = profile.s3()
    if s3 is None:
        return None
    try:
        total = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            total += len(page.get("Contents", []))
        return total
    except Exception:
        return None
