"""
Preparing the Data Fabric client at runtime.

The container must start and stay up with no cluster configured at all, so an operator
can deploy it first and point it at a cluster from the interface afterwards. That rules
out doing this work only in the entrypoint: a cluster entered later needs the same
setup, and a cluster that is unreachable at boot must not stop the demo from running.

Four things have to happen before a cluster is usable:

    truststore     fetched from /opt/mapr/conf on the cluster, which is where it lives
    configure.sh   writes this container's mapr-clusters.conf
    maprlogin      obtains the ticket the native streams client authenticates with
    mount          NFS-mounts the cluster so imagery can live on volumes

The truststore is fetched rather than supplied. HPE's guidance for a secure client is to
copy ssl_truststore and ssl-client.xml from /opt/mapr/conf on a cluster node, and there
is no API that serves them — so this does exactly that over SCP, once a cluster is known.
Asking an operator to stage the file before the container starts made deployment harder
than it needed to be, and it could not work at all for a cluster configured later in the
interface.

All four are re-runnable, and every failure is reported rather than raised, so the
interface can show what is wrong instead of the container disappearing.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

CONF = Path("/opt/mapr/conf")
TRUSTSTORE = CONF / "ssl_truststore"
SSL_CLIENT_XML = CONF / "ssl-client.xml"
TICKET = Path("/tmp/maprticket_0")

# Where the files live on every cluster node.
REMOTE_CONF = "/opt/mapr/conf"

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


def fetch_truststore(host: str, ssh_user: str, ssh_password: str,
                     ssh_port: int = 22) -> tuple[bool, str]:
    """Copy ssl_truststore and ssl-client.xml from the cluster over SCP.

    This is the documented way a secure client gets them; there is no endpoint that
    serves them, and they cannot be derived from the server certificate — a truststore
    built that way is rejected by the CLDB handshake.

    Uses password authentication because that is what a demo environment has. Where SSH
    is unavailable or locked down, bind-mount the file instead and this step is skipped.
    """
    scp_options = [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=15",
        "-P", str(ssh_port),
    ]
    sources = f"{ssh_user}@{host}:{REMOTE_CONF}/{{ssl_truststore,ssl-client.xml}}"
    ok, detail = _run(
        ["sshpass", "-p", ssh_password, "scp", *scp_options, sources, str(CONF) + "/"],
        timeout=90,
    )
    if not ok:
        # ssl-client.xml is not present on every cluster; retry with just the truststore
        # so its absence does not block an otherwise working setup.
        ok, detail = _run(
            ["sshpass", "-p", ssh_password, "scp", *scp_options,
             f"{ssh_user}@{host}:{REMOTE_CONF}/ssl_truststore", str(CONF) + "/"],
            timeout=90,
        )
    if not ok:
        return False, (f"could not copy {REMOTE_CONF}/ssl_truststore from {host}: "
                       f"{detail}. Check the SSH user and password, or bind-mount the "
                       f"file at {TRUSTSTORE}.")
    if not truststore_present():
        return False, f"copied from {host} but {TRUSTSTORE} is empty"
    return True, f"fetched from {host}:{REMOTE_CONF}"


def prepare(host: str, username: str, password: str, cluster_name: str,
            mount_point: str = "/mapr", rest_port: int = 8443,
            cldb_port: int = 7222, zk_port: int = 5181,
            ssh_user: str | None = None, ssh_password: str | None = None,
            ssh_port: int = 22) -> dict:
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

    if truststore_present():
        record("truststore", True, "already present")
    else:
        ok, detail = fetch_truststore(host, ssh_user or username,
                                      ssh_password or password, ssh_port)
        record("truststore", ok, detail)
        if not ok:
            return {"host": host, "steps": steps, "ready": False}

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
