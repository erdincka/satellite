"""
Imagery on Data Fabric volumes, reached over an NFS mount.

Bulk data lives in volumes rather than buckets so it can cross between the sites by
**volume mirroring**, which is how Data Fabric actually moves it. An S3 copy performed
by the application would demonstrate that the app can use S3, not anything about the
platform.

POSIX access comes from mounting the cluster's NFS export. The MapR FUSE client would
be the tidier option and does not work in this container: it creates the mount, the
process exits immediately, and every access then fails with "Transport endpoint is not
connected" — including under --privileged, with an empty ffs.log. NFS mounts first try
and is what the original demo used.

Each side has its own mount root, so HQ and the edge can sit on different clusters.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import sites
from connections import CONNECTIONS

logger = logging.getLogger(__name__)


def object_name(preview_url: str) -> str:
    """The storage key for a feed item, taken from the tail of its preview URL."""
    return preview_url.rstrip("/").split("/")[-1]


def mount_root(side: str) -> Path:
    """Where this side's cluster is mounted. Set by the entrypoint when it mounts NFS."""
    default = "/mapr" if side.upper() == "HQ" else os.environ.get("MAPR_MOUNT_HQ", "/mapr")
    return Path(os.environ.get(f"MAPR_MOUNT_{side.upper()}", default))


def cluster_root(side: str) -> Path | None:
    """`<mount>/<cluster name>`, or None when the mount is not usable.

    Returns None rather than raising so a missing mount surfaces as a clear status
    message instead of an exception in the middle of the pipeline.
    """
    root = mount_root(side)
    if not root.is_dir():
        return None
    cluster = CONNECTIONS.profile(side).cluster_name
    candidate = root / cluster
    if candidate.is_dir():
        return candidate
    # A single-cluster mount sometimes exposes exactly one directory; use it rather
    # than failing on a cluster-name mismatch.
    try:
        entries = [p for p in root.iterdir() if p.is_dir()]
    except OSError as error:
        logger.warning("Cannot read mount %s: %s", root, error)
        return None
    return entries[0] if len(entries) == 1 else None


def mounted(side: str) -> tuple[bool, str]:
    root = cluster_root(side)
    if root is None:
        return False, f"{mount_root(side)} is not mounted"
    return True, str(root)


def _path(side: str, subpath: str) -> Path | None:
    root = cluster_root(side)
    return None if root is None else root / subpath.lstrip("/")


def assets_dir(side: str) -> Path | None:
    return _path(side, sites.for_side(side).assets_path)


def outbound_dir() -> Path | None:
    """HQ's staging volume — the one the edge mirrors."""
    return _path("HQ", sites.HQ.outbound_path or "")


def asset_file(side: str, key: str) -> Path | None:
    directory = assets_dir(side)
    return None if directory is None else directory / key


def has_asset(side: str, key: str) -> bool:
    path = asset_file(side, key)
    return bool(path and path.is_file())


def read_asset(side: str, key: str) -> bytes | None:
    path = asset_file(side, key)
    if not path or not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError as error:
        logger.debug("Could not read %s: %s", path, error)
        return None


def store_asset(side: str, key: str, source: Path) -> tuple[bool, str]:
    """Take custody of an asset: copy it from the local feed onto the cluster.

    A real write to a Data Fabric volume, which is what the Stored stage claims.
    """
    directory = assets_dir(side)
    if directory is None:
        return False, f"{mount_root(side)} is not mounted — cannot store imagery"
    if not source.is_file():
        return False, f"{source.name} is not in the local feed"

    target = directory / key
    if target.is_file():
        return True, "already stored"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return True, f"{target.stat().st_size / 1024:.0f} KB to {sites.for_side(side).assets_volume}"
    except OSError as error:
        return False, f"Could not write {target}: {error}"


def stage_for_mirror(key: str) -> tuple[bool, str]:
    """Place a requested asset in HQ's outbound volume.

    This is all HQ does. The bytes reach the edge when the edge mirrors that volume —
    the transfer is Data Fabric's, on the edge's schedule, which is the point.
    """
    source = asset_file("HQ", key)
    outbound = outbound_dir()
    if outbound is None:
        return False, f"{mount_root('HQ')} is not mounted — cannot stage imagery"
    if not source or not source.is_file():
        return False, f"{key} is not in {sites.HQ.assets_volume}"

    target = outbound / key
    try:
        outbound.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            shutil.copyfile(source, target)
        size = target.stat().st_size
        return True, f"{size / 1024:.0f} KB staged in {sites.HQ.outbound_volume}"
    except OSError as error:
        return False, f"Could not stage {target}: {error}"


def count(side: str) -> int | None:
    directory = assets_dir(side)
    if directory is None or not directory.is_dir():
        return None
    try:
        return sum(1 for p in directory.iterdir() if p.is_file())
    except OSError:
        return None
