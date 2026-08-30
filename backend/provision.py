"""
Create and tear down each site's objects, over REST and S3.

Replaces configure-app.sh and reset-app.sh. Doing it over REST rather than shelling out
to `maprcli` means the app can prepare any reachable cluster, and it lets the UI report
progress per step instead of dumping command output at the presenter.

Each site provisions only what it owns. HQ additionally sets up the replication that
carries data between the two streams, because HQ is the source of the catalogue — and
replication is the one thing that inherently spans both sides.

Every step is idempotent. Configure is safe to re-run, which matters when one step
fails and the presenter simply clicks it again.
"""

from __future__ import annotations

import logging
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import settings
import sites
from dfabric import Profile
from sites import Site

logger = logging.getLogger(__name__)


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


def _exists_already(reason: str) -> bool:
    """Data Fabric has no create-if-missing, so 'already exists' counts as success."""
    lowered = reason.lower()
    return "already exists" in lowered or "already in use" in lowered or "exists" in lowered


def _absent(reason: str) -> bool:
    lowered = reason.lower()
    return ("not found" in lowered or "no such" in lowered
            or "does not exist" in lowered or "no such file" in lowered)


# --------------------------------------------------------------------- create


def _volume(profile: Profile, name: str, path: str) -> Step:
    response = profile.rest("volume/create", {"path": path, "name": name}, method="POST")
    reason = profile.failed(response)
    if reason and not _exists_already(reason):
        return Step(f"Volume {name}", False, reason)
    return Step(f"Volume {name}", True, path + (" (existing)" if reason else ""))


def _stream(profile: Profile, path: str) -> Step:
    response = profile.rest("stream/create", {
        "path": path, "produceperm": "p", "consumeperm": "p", "topicperm": "p",
    }, method="POST")
    reason = profile.failed(response)
    label = f"Stream {path.rsplit('/', 1)[-1]}"
    if reason and not _exists_already(reason):
        return Step(label, False, reason)
    return Step(label, True, path + (" (existing)" if reason else ""))


def _topic(profile: Profile, stream: str, topic: str) -> Step:
    """Create a topic explicitly.

    The native client will create a topic on first produce, but creating them up front
    means the replica is set up already carrying them, and it makes the demo's objects
    inspectable on the cluster before any data flows.
    """
    response = profile.rest("stream/topic/create",
                            {"path": stream, "topic": topic}, method="POST")
    reason = profile.failed(response)
    if reason and not _exists_already(reason):
        return Step(f"Topic {topic}", False, reason)
    return Step(f"Topic {topic}", True, "existing" if reason else "created")


def _mirror_volume(profile: Profile, name: str, path: str, source: str,
                   source_cluster: str) -> Step:
    """Create the edge's assets volume as a mirror of HQ's outbound volume.

    This is what carries imagery between the sites. Plain volumes, deliberately: a
    mirror of a *bucket* volume cannot be removed over REST afterwards, which would
    leave residue behind on every Reset.
    """
    existing = profile.rest("volume/info", {"name": name, "columns": "volumename,volumetype"})
    if not profile.failed(existing):
        return Step(f"Mirror {name}", True, f"already mirrors {source}")

    # Data Fabric requires the source qualified as volume@cluster even when the mirror
    # lives on the same cluster.
    target = f"{source}@{source_cluster}"
    response = profile.rest("volume/create", {
        "path": path, "name": name, "type": "mirror", "source": target,
    }, method="POST")
    reason = profile.failed(response)
    if reason and not _exists_already(reason):
        return Step(f"Mirror {name}", False, reason)
    return Step(f"Mirror {name}", True, f"mirrors {target}")


def _bucket(profile: Profile, name: str) -> Step:
    """Create a bucket and let the object store decide where to put it.

    Deliberately no volume is named: buckets live wherever the Object Store places
    them, and binding one to a volume is what made an earlier mirroring experiment
    impossible to clean up.
    """
    s3 = profile.s3()
    if s3 is None:
        return Step(f"Bucket {name}", False, "no S3 credentials")
    try:
        if name in {b["Name"] for b in s3.list_buckets().get("Buckets", [])}:
            return Step(f"Bucket {name}", True, "existing")
        s3.create_bucket(Bucket=name)
        return Step(f"Bucket {name}", True, "created")
    except Exception as error:
        return Step(f"Bucket {name}", False, f"{type(error).__name__}: {error}")


def _replication(profile: Profile, source: str, replica: str,
                 replica_cluster: str | None) -> Step:
    """Pair HQ's stream with the edge's, multi-master.

    Multi-master is what lets one replicated pair carry the catalogue outward and
    requests back, so neither side ever attaches to the other's stream.

    autosetup cannot be re-run against a stream that already has the replica — it fails
    with DC_NOT_SUPPORTED rather than saying "already exists" — so check first.
    """
    target = f"{replica}@{replica_cluster}" if replica_cluster else replica

    # A replica record can outlive the stream it points at — resetting the edge deletes
    # the stream but leaves the pairing listed, and trusting that record alone meant the
    # edge's stream was never recreated and the site could not be prepared again. Check
    # the replica stream actually exists before believing the pairing.
    replica_exists = profile.failed(profile.rest("stream/info", {"path": replica},
                                                 timeout=15)) is None
    existing = profile.rest("stream/replica/list", {"path": source})
    if replica_exists and not profile.failed(existing):
        for record in existing.get("data") or []:
            if record.get("replicaPath") == replica:
                state = "up to date" if record.get("isUptodate") else record.get("replicaState", "")
                return Step("Stream replication", True, f"already paired, {state}")

    if not replica_exists:
        # Clear the stale pairing so autosetup can recreate it.
        profile.rest("stream/replica/remove", {"path": source, "replica": replica},
                     method="POST", timeout=60)

    response = profile.rest("stream/replica/autosetup", {
        "path": source, "replica": target, "multimaster": "true",
    }, method="POST", timeout=180)
    reason = profile.failed(response)
    if reason and not _exists_already(reason):
        return Step("Stream replication", False, reason)
    return Step("Stream replication", True, f"{source} ⇄ {replica}")


def stage_images() -> Step:
    """Unpack the bundled imagery to local disk.

    The images are the demo's stand-in for a live feed. They stay local and are
    uploaded to HQ's bucket as each asset flows through the pipeline, so the Stored
    stage is a genuine write rather than a lookup of something Configure pre-loaded.
    """
    staging = Path(settings.IMAGE_STAGING)
    archive = Path(settings.IMAGE_ARCHIVE)

    if staging.is_dir() and any(staging.iterdir()):
        return Step("Sample imagery", True, f"{len(list(staging.iterdir()))} files in {staging}/")
    if not archive.exists():
        return Step("Sample imagery", False, f"{archive} not found")

    try:
        staging.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                (staging / Path(member.name).name).write_bytes(handle.read())
        return Step("Sample imagery", True, f"{len(list(staging.iterdir()))} files in {staging}/")
    except Exception as error:
        return Step("Sample imagery", False, f"{type(error).__name__}: {error}")


def _peer_volume(profile: Profile, peer: Site, same_cluster: bool) -> Step:
    """Make sure the edge's volume exists before creating a replica stream inside it.

    On one cluster HQ can simply create it. Across two, it belongs to the edge's
    cluster and the edge must be configured first — so say that plainly rather than
    failing with a path error.
    """
    response = profile.rest("volume/info", {"name": peer.volume_name}, timeout=15)
    if not profile.failed(response):
        return Step(f"Volume {peer.volume_name}", True, "present", skipped=True)
    if not same_cluster:
        return Step(f"Volume {peer.volume_name}", False,
                    "not on this cluster — run Configure on the edge first")
    return _volume(profile, peer.volume_name, peer.volume_path)


def configure(profile: Profile, site: Site, peer: Site | None = None,
              peer_profile: Profile | None = None,
              report: Reporter | None = None) -> Iterator[Step]:
    """Prepare one site. HQ also creates the topics and the replication pair."""
    # The edge's assets volume is a mirror and must be created as one, so it is
    # excluded from the plain-volume list here.
    plain = [v for v in site.volumes
             if not (site.side == "EDGE" and v[0] == site.assets_volume)]

    steps: list[Callable[[], Step]] = [
        *[(lambda n=n, p=p: _volume(profile, n, p)) for n, p in plain],
        *[(lambda b=b: _bucket(profile, b)) for b in site.buckets],
    ]

    if site.side == "HQ":
        same_cluster = peer_profile is None or peer_profile.host == profile.host
        steps += [
            lambda: _stream(profile, site.pipeline_stream),          # type: ignore[arg-type]
            lambda: _topic(profile, site.pipeline_stream, sites.TOPIC_PIPELINE),  # type: ignore[arg-type]
            lambda: _stream(profile, site.stream),
            # Topics before replication, so the replica is created already carrying them.
            *[(lambda t=t: _topic(profile, site.stream, t)) for t in sites.REPLICATED_TOPICS],
        ]
        if peer is not None:
            steps += [
                lambda: _peer_volume(profile, peer, same_cluster),
                lambda: _replication(
                    profile, site.stream, peer.stream,
                    None if same_cluster else (peer_profile.cluster_name if peer_profile else None)),
                # Created last, once its source volume exists.
                lambda: _mirror_volume(
                    peer_profile or profile, peer.assets_volume, peer.assets_path,
                    site.outbound_volume or "", profile.cluster_name),
            ]
        steps.append(stage_images)

    for make_step in steps:
        try:
            step = make_step()
        except Exception as error:  # one bad step must not abort the run
            logger.exception("Provisioning step failed")
            step = Step("Unexpected error", False, f"{type(error).__name__}: {error}")
        logger.info("configure %s: %s %s — %s", site.side, step.symbol, step.name, step.detail)
        if report:
            report(step)
        yield step


# ---------------------------------------------------------------------- remove


def _empty_bucket(profile: Profile, name: str) -> Step:
    """Remove every object *and version*, then the bucket.

    Buckets are versioned by default, so deleting objects leaves delete markers and a
    later DeleteBucket fails with BucketNotEmpty. Purge versions explicitly.
    """
    s3 = profile.s3()
    if s3 is None:
        return Step(f"Bucket {name}", False, "no S3 credentials")
    try:
        if name not in {b["Name"] for b in s3.list_buckets().get("Buckets", [])}:
            return Step(f"Bucket {name}", True, "absent", skipped=True)
        removed = 0
        for page in s3.get_paginator("list_object_versions").paginate(Bucket=name):
            for collection in ("Versions", "DeleteMarkers"):
                for obj in page.get(collection, []):
                    s3.delete_object(Bucket=name, Key=obj["Key"], VersionId=obj["VersionId"])
                    removed += 1
        s3.delete_bucket(Bucket=name)
        return Step(f"Bucket {name}", True, f"{removed} version(s) purged, deleted")
    except Exception as error:
        return Step(f"Bucket {name}", False, f"{type(error).__name__}: {error}")


def _delete_stream(profile: Profile, path: str) -> Step:
    response = profile.rest("stream/delete", {"path": path}, method="POST")
    reason = profile.failed(response)
    label = f"Stream {path.rsplit('/', 1)[-1]}"
    if reason:
        return Step(label, True, "absent", skipped=True) if _absent(reason) \
            else Step(label, False, reason)
    return Step(label, True, "deleted")


def _remove_volume(profile: Profile, name: str) -> Step:
    response = profile.rest("volume/remove", {"name": name, "force": "true"}, method="POST")
    reason = profile.failed(response)
    if reason:
        return Step(f"Volume {name}", True, "absent", skipped=True) if _absent(reason) \
            else Step(f"Volume {name}", False, reason)
    return Step(f"Volume {name}", True, "removed")


def reset(profile: Profile, site: Site, report: Reporter | None = None) -> Iterator[Step]:
    """Remove everything this site owns, in dependency order."""
    # Children before parents: a volume mounted inside another must go first.
    volumes = [name for name, _ in reversed(site.volumes)]
    steps: list[Callable[[], Step]] = [
        *[(lambda s=s: _delete_stream(profile, s)) for s in site.streams],
        *[(lambda b=b: _empty_bucket(profile, b)) for b in site.buckets],
        *[(lambda v=v: _remove_volume(profile, v)) for v in volumes],
    ]

    for make_step in steps:
        try:
            step = make_step()
        except Exception as error:
            logger.exception("Reset step failed")
            step = Step("Unexpected error", False, f"{type(error).__name__}: {error}")
        logger.info("reset %s: %s %s — %s", site.side, step.symbol, step.name, step.detail)
        if report:
            report(step)
        yield step

    # The Iceberg catalog caches a handle to a warehouse that no longer exists; drop it
    # so the next write rebuilds against fresh storage rather than failing silently.
    import iceberger
    iceberger.forget_catalog()


def is_configured(profile: Profile, site: Site) -> bool:
    """True once this site's stream exists — the thing everything else depends on."""
    response = profile.rest("stream/info", {"path": site.stream}, timeout=10)
    return profile.failed(response) is None
