"""
Create and tear down everything the demo needs, over REST and S3.

This replaces configure-app.sh and reset-app.sh. Those shelled out to `maprcli`,
which meant the app could only provision the cluster it was running inside. Doing it
over REST means the demo can target any reachable cluster, and it lets the UI report
progress per step instead of dumping raw command output at the presenter.

Every step is idempotent: running configure twice is harmless, which matters when a
step fails halfway and the presenter just clicks it again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterator

import settings
from dfabric import Profile

logger = logging.getLogger(__name__)

# Reported back to the UI for each step so it can render a running checklist.
@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False

    @property
    def symbol(self) -> str:
        return "—" if self.skipped else ("✓" if self.ok else "✗")


Reporter = Callable[[Step], None]


def _already_exists(reason: str) -> bool:
    """Data Fabric has no create-if-missing, so treat 'exists' as success."""
    lowered = reason.lower()
    return "already exists" in lowered or "already in use" in lowered or "exists" in lowered


# --------------------------------------------------------------------- volumes


def _volume(profile: Profile, name: str, path: str) -> Step:
    response = profile.rest("volume/create", {"path": path, "name": name}, method="POST")
    reason = profile.failed(response)
    if reason and not _already_exists(reason):
        return Step(f"Volume {name}", False, reason)
    return Step(f"Volume {name}", True, path + (" (existing)" if reason else ""))


def _stream(profile: Profile, path: str) -> Step:
    response = profile.rest("stream/create", {
        "path": path, "produceperm": "p", "consumeperm": "p", "topicperm": "p",
    }, method="POST")
    reason = profile.failed(response)
    if reason and not _already_exists(reason):
        return Step(f"Stream {path.rsplit('/', 1)[-1]}", False, reason)
    return Step(f"Stream {path.rsplit('/', 1)[-1]}", True, path + (" (existing)" if reason else ""))


def _topic(profile: Profile, stream: str, topic: str) -> Step:
    """Create a topic explicitly.

    The native client auto-creates topics on first produce, but the Kafka Wire Protocol
    gateway does not — a produce to a missing topic simply fails with
    UNKNOWN_TOPIC_OR_PART. Creating them up front is the difference between the demo
    working and silently dropping every message.
    """
    response = profile.rest("stream/topic/create",
                            {"path": stream, "topic": topic}, method="POST")
    reason = profile.failed(response)
    if reason and not _already_exists(reason):
        return Step(f"Topic {topic}", False, reason)
    return Step(f"Topic {topic}", True, "existing" if reason else "created")


def _replication(profile: Profile) -> Step:
    """Wire HQ's stream to the edge's as a multi-master pair.

    Multi-master is what lets one replicated stream carry the catalogue outbound and
    requests back, so neither side needs a route to the other's storage.

    autosetup cannot be re-run against a stream that already has the replica — it fails
    with DC_NOT_SUPPORTED rather than reporting "already exists" — so check first.
    """
    existing = profile.rest("stream/replica/list", {"path": settings.HQ_STREAM})
    if not profile.failed(existing):
        for replica in existing.get("data") or []:
            if replica.get("replicaPath") == settings.EDGE_STREAM:
                state = "up to date" if replica.get("isUptodate") else replica.get("replicaState", "")
                return Step("Stream replication", True, f"already configured, {state}")

    response = profile.rest("stream/replica/autosetup", {
        "path": settings.HQ_STREAM,
        "replica": settings.EDGE_STREAM,
        "multimaster": "true",
    }, method="POST", timeout=120)
    reason = profile.failed(response)
    if reason and not _already_exists(reason):
        return Step("Stream replication", False, reason)
    return Step("Stream replication", True,
                f"{settings.HQ_STREAM} ⇄ {settings.EDGE_STREAM}" + (" (existing)" if reason else ""))


# --------------------------------------------------------------------- buckets


def _bucket(profile: Profile, name: str) -> Step:
    s3 = profile.s3()
    if s3 is None:
        return Step(f"Bucket {name}", False, "no S3 credentials")
    try:
        existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
        if name in existing:
            return Step(f"Bucket {name}", True, "existing")
        s3.create_bucket(Bucket=name)
        return Step(f"Bucket {name}", True, "created")
    except Exception as error:
        return Step(f"Bucket {name}", False, f"{type(error).__name__}: {error}")


def _seed_images(profile: Profile) -> Step:
    """Upload the bundled sample imagery so the pipeline has something to serve.

    The demo ships pre-recorded NASA imagery rather than calling the live API, so it
    works without internet and always shows the same assets.
    """
    import tarfile
    from pathlib import Path

    archive = Path(settings.IMAGE_ARCHIVE)
    if not archive.exists():
        return Step("Sample imagery", False, f"{archive} not found")

    s3 = profile.s3()
    if s3 is None:
        return Step("Sample imagery", False, "no S3 credentials")

    try:
        existing = set()
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.HQ_BUCKET):
            existing.update(o["Key"] for o in page.get("Contents", []))

        uploaded = 0
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                key = Path(member.name).name
                if key in existing:
                    continue
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                s3.put_object(Bucket=settings.HQ_BUCKET, Key=key, Body=handle.read())
                uploaded += 1

        total = len(existing) + uploaded
        return Step("Sample imagery", True,
                    f"{uploaded} uploaded, {total} available in {settings.HQ_BUCKET}")
    except Exception as error:
        return Step("Sample imagery", False, f"{type(error).__name__}: {error}")


# ------------------------------------------------------------------- configure


def configure(profile: Profile, report: Reporter | None = None) -> Iterator[Step]:
    """Create every volume, stream and bucket the demo needs.

    Yields each step as it completes so the UI can show progress live rather than
    freezing until the whole thing finishes.
    """
    steps = [
        lambda: _volume(profile, settings.HQ_VOLUME_NAME, settings.HQ_VOLUME),
        lambda: _volume(profile, settings.EDGE_VOLUME_NAME, settings.EDGE_VOLUME),
        lambda: _stream(profile, settings.HQ_STREAM),
        # Topics before replication, so the replica is set up with them already present.
        *[(lambda t=t: _topic(profile, settings.HQ_STREAM, t)) for t in (
            settings.PIPELINE, settings.ASSET_TOPIC,
            settings.REQUEST_TOPIC, settings.RESPONSE_TOPIC)],
        lambda: _replication(profile),
        lambda: _bucket(profile, settings.HQ_BUCKET),
        lambda: _bucket(profile, settings.EDGE_BUCKET),
        lambda: _bucket(profile, settings.WAREHOUSE_BUCKET),
        lambda: _seed_images(profile),
    ]

    for make_step in steps:
        try:
            step = make_step()
        except Exception as error:  # a step must never abort the whole run
            logger.exception("Provisioning step failed")
            step = Step("Unexpected error", False, f"{type(error).__name__}: {error}")
        logger.info("configure: %s %s — %s", step.symbol, step.name, step.detail)
        if report:
            report(step)
        yield step


# ----------------------------------------------------------------------- reset


def _empty_bucket(profile: Profile, name: str) -> Step:
    """Remove every object *and version* from a bucket.

    Buckets are versioned by default, so deleting objects leaves delete markers behind
    and a subsequent DeleteBucket fails with BucketNotEmpty. Purge versions explicitly.
    """
    s3 = profile.s3()
    if s3 is None:
        return Step(f"Empty {name}", False, "no S3 credentials")
    try:
        if name not in {b["Name"] for b in s3.list_buckets().get("Buckets", [])}:
            return Step(f"Empty {name}", True, "absent", skipped=True)

        removed = 0
        paginator = s3.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=name):
            for collection in ("Versions", "DeleteMarkers"):
                for obj in page.get(collection, []):
                    s3.delete_object(Bucket=name, Key=obj["Key"], VersionId=obj["VersionId"])
                    removed += 1
        s3.delete_bucket(Bucket=name)
        return Step(f"Bucket {name}", True, f"{removed} objects removed, bucket deleted")
    except Exception as error:
        return Step(f"Bucket {name}", False, f"{type(error).__name__}: {error}")


def _delete_stream(profile: Profile, path: str) -> Step:
    response = profile.rest("stream/delete", {"path": path}, method="POST")
    reason = profile.failed(response)
    label = f"Stream {path.rsplit('/', 1)[-1]}"
    if reason:
        if "not found" in reason.lower() or "no such" in reason.lower():
            return Step(label, True, "absent", skipped=True)
        return Step(label, False, reason)
    return Step(label, True, "deleted")


def _remove_volume(profile: Profile, name: str) -> Step:
    response = profile.rest("volume/remove", {"name": name, "force": "true"}, method="POST")
    reason = profile.failed(response)
    if reason:
        if "not found" in reason.lower() or "no such" in reason.lower():
            return Step(f"Volume {name}", True, "absent", skipped=True)
        return Step(f"Volume {name}", False, reason)
    return Step(f"Volume {name}", True, "removed")


def reset(profile: Profile, report: Reporter | None = None) -> Iterator[Step]:
    """Remove everything configure() created, in dependency order.

    Streams go before their volumes, and buckets are emptied before deletion.
    """
    steps = [
        lambda: _delete_stream(profile, settings.EDGE_STREAM),
        lambda: _delete_stream(profile, settings.HQ_STREAM),
        lambda: _empty_bucket(profile, settings.HQ_BUCKET),
        lambda: _empty_bucket(profile, settings.EDGE_BUCKET),
        lambda: _empty_bucket(profile, settings.WAREHOUSE_BUCKET),
        lambda: _remove_volume(profile, settings.EDGE_VOLUME_NAME),
        lambda: _remove_volume(profile, settings.HQ_VOLUME_NAME),
    ]

    for make_step in steps:
        try:
            step = make_step()
        except Exception as error:
            logger.exception("Reset step failed")
            step = Step("Unexpected error", False, f"{type(error).__name__}: {error}")
        logger.info("reset: %s %s — %s", step.symbol, step.name, step.detail)
        if report:
            report(step)
        yield step

    # The Iceberg catalog caches a handle to a warehouse that no longer exists; drop it
    # so the next write rebuilds against fresh storage instead of failing silently.
    import iceberger
    iceberger.forget_catalog()


def is_configured(profile: Profile) -> bool:
    """True when the demo's streams exist, which is the last thing configure creates."""
    response = profile.rest("stream/info", {"path": settings.HQ_STREAM}, timeout=10)
    return profile.failed(response) is None
