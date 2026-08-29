"""
Asset storage on the Data Fabric S3 gateway.

Replaces the POSIX operations the demo used to do against a /mapr FUSE mount:
shutil.copy for the HQ→edge transfer, and absolute filesystem paths handed to
ui.image as though they were URLs. Everything here goes over S3 so the app needs no
mount and no native client.
"""

from __future__ import annotations

import logging
from io import BytesIO

import settings
from dfabric import Profile

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


def stage_for_download(profile: Profile, key: str) -> bool:
    """Confirm the asset is present in the HQ bucket, ready to be catalogued.

    The bundled imagery is uploaded once during configure, so this is a presence check
    rather than a fetch. It stays a distinct step because it is the point in the story
    where HQ takes custody of the bytes.
    """
    if exists(profile, settings.HQ_BUCKET, key):
        return True
    logger.error("Asset %s missing from %s — was configure run?", key, settings.HQ_BUCKET)
    return False


def transfer_to_edge(profile: Profile, key: str) -> bool:
    """Copy a requested asset from the HQ bucket to the edge bucket.

    This is the moment bandwidth is actually spent: descriptions travel to every edge
    site continuously over the replicated stream, but the image itself crosses only
    when a field team asks for it.

    Implemented as a server-side S3 copy. The alternative — mirroring the bucket's
    underlying volume — works but produces mirror volumes that cannot be removed over
    REST, which would leave residue behind on every Reset. If the cluster's S3 gateway
    is configured with a `filestore` bucket, this is the single function to swap.
    """
    s3 = profile.s3()
    if s3 is None:
        return False
    try:
        s3.copy_object(
            Bucket=settings.EDGE_BUCKET,
            Key=key,
            CopySource={"Bucket": settings.HQ_BUCKET, "Key": key},
        )
        logger.info("Transferred %s to %s", key, settings.EDGE_BUCKET)
        return True
    except Exception as error:
        logger.error("Transfer of %s failed: %s", key, error)
        return False


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
