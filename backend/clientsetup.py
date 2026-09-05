"""
Preparing the Data Fabric client at runtime.

The container must start and stay up with no cluster configured at all, so an operator
can deploy it first and point it at a cluster from the interface afterwards. That rules
out doing this work only in the entrypoint: a cluster entered later needs the same
setup, and a cluster that is unreachable at boot must not stop the demo from running.

Three things have to happen before a cluster is usable:

    configure.sh   writes this container's mapr-clusters.conf
    maprlogin      obtains the ticket the native streams client authenticates with
    mount          NFS-mounts the cluster so imagery can live on volumes

All three are re-runnable, and every failure is reported rather than raised, so the
interface can show what is wrong instead of the container disappearing.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

TRUSTSTORE = Path("/opt/mapr/conf/ssl_truststore")
TICKET = Path("/tmp/maprticket_0")

_lock = threading.Lock()
_state: dict[str, dict] = {}


def _run(command: list[str], stdin: str | None = None, timeout: int = 180) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command, input=stdin, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return False, f"{command[0]} not found — not running in the demo container"
    except subprocess.TimeoutExpired:
        return False, f"{command[0]} timed out after {timeout}s"
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        return False, (tail[-1] if tail else f"exit {result.returncode}")
    return True, ""


def truststore_present() -> bool:
    return TRUSTSTORE.is_file() and TRUSTSTORE.stat().st_size > 0


def ticket_present() -> bool:
    return TICKET.is_file() and TICKET.stat().st_size > 0


def prepare(host: str, username: str, password: str, cluster_name: str,
            mount_point: str = "/mapr", rest_port: int = 8443,
            cldb_port: int = 7222, zk_port: int = 5181) -> dict:
    """Configure the client, get a ticket and mount the cluster. Never raises.

    Returns a per-step report the interface can render, so a half-working setup names
    the step that failed instead of surfacing as an unrelated error later.
    """
    steps: dict[str, dict] = {}

    def record(name: str, ok: bool, detail: str = "") -> None:
        steps[name] = {"ok": ok, "detail": detail}

    if not host:
        record("cluster", False, "no cluster configured")
        return {"host": host, "steps": steps, "ready": False}

    if not truststore_present():
        record("truststore", False,
               "missing — copy /opt/mapr/conf/ssl_truststore from a cluster node and "
               "pass it as MAPR_TRUSTSTORE_B64 or bind-mount it")
        return {"host": host, "steps": steps, "ready": False}
    record("truststore", True, str(TRUSTSTORE))

    with _lock:
        ok, detail = _run([
            "/opt/mapr/server/configure.sh", "-N", cluster_name, "-c",
            "-C", f"{host}:{cldb_port}", "-Z", f"{host}:{zk_port}", "-secure",
        ])
        record("client config", ok, detail or f"{host} as {cluster_name}")
        if not ok:
            return {"host": host, "steps": steps, "ready": False}

        ok, detail = _run(["/opt/mapr/bin/maprlogin", "password", "-user", username],
                          stdin=f"{password}\n", timeout=90)
        record("ticket", ok, detail or f"as {username}")
        if not ok:
            return {"host": host, "steps": steps, "ready": False}

        ok, detail = mount(host, mount_point)
        record("nfs mount", ok, detail)

    return {"host": host, "steps": steps, "ready": all(s["ok"] for s in steps.values())}


def mount(host: str, mount_point: str = "/mapr") -> tuple[bool, str]:
    """NFS-mount the cluster, which is how imagery reaches Data Fabric volumes."""
    target = Path(mount_point)
    target.mkdir(parents=True, exist_ok=True)

    if os.path.ismount(target):
        return True, f"{target} already mounted"

    ok, detail = _run([
        "mount", "-t", "nfs", "-o", "nolock,vers=3,soft,timeo=50,retrans=2",
        f"{host}:/mapr", str(target),
    ], timeout=60)
    if not ok:
        return False, (f"{detail} — needs --cap-add SYS_ADMIN and the cluster's NFS "
                       f"service reachable on 2049")
    return True, str(target)


def remember(side: str, report: dict) -> None:
    _state[side.upper()] = report


def state(side: str) -> dict:
    return _state.get(side.upper(), {"steps": {}, "ready": False})


def summary(side: str) -> tuple[bool, str]:
    """One line for the status pills."""
    report = state(side)
    if not report.get("steps"):
        return False, "not prepared"
    failed = [name for name, s in report["steps"].items() if not s["ok"]]
    if failed:
        first = report["steps"][failed[0]]
        return False, f"{failed[0]}: {first['detail']}"
    return True, f"ready on {report.get('host', '?')}"
