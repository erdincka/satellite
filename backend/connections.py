"""
Runtime cluster connections.

The two sites are two *connections*, not two processes. That is what makes "point both
at the same cluster" the ordinary case rather than a special one: HQ and the edge are
distinguished by the objects they own, never by which cluster they happen to live on.

Connections come from the environment as defaults and can be changed in the interface
while the app is running, so a demo can be repointed at a customer's cluster without
editing files or restarting anything. What the operator sets is persisted server-side.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import dfabric

logger = logging.getLogger(__name__)

STATE_FILE = Path(os.environ.get("CONNECTION_STATE", "/app/state/connections.json"))


@dataclass
class ConnectionSettings:
    host: str = ""
    username: str = "mapr"
    password: str = "mapr"
    rest_port: int = 8443
    s3_port: int = 9000
    # Used only to copy the truststore from /opt/mapr/conf, which is the documented way
    # a secure client obtains it. Defaults to the cluster credentials.
    ssh_user: str = ""
    ssh_password: str = ""
    ssh_port: int = 22

    def redacted(self) -> dict:
        """Never send the password to the browser; report only whether one is set."""
        data = asdict(self)
        data["password"] = "********" if self.password else ""
        data["ssh_password"] = "********" if self.ssh_password else ""
        return data


def _from_env(side: str) -> ConnectionSettings:
    """Read SIDE_HOST / SIDE_USER / SIDE_PASSWORD, e.g. HQ_HOST, EDGE_HOST."""
    return ConnectionSettings(
        host=os.environ.get(f"{side}_HOST", ""),
        username=os.environ.get(f"{side}_USER", "mapr"),
        password=os.environ.get(f"{side}_PASSWORD", "mapr"),
        rest_port=int(os.environ.get(f"{side}_REST_PORT", "8443")),
        s3_port=int(os.environ.get(f"{side}_S3_PORT", "9000")),
        ssh_user=os.environ.get(f"{side}_SSH_USER", ""),
        ssh_password=os.environ.get(f"{side}_SSH_PASSWORD", ""),
        ssh_port=int(os.environ.get(f"{side}_SSH_PORT", "22")),
    )


class Connections:
    """Holds both sides' settings and hands out configured Profiles."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings: dict[str, ConnectionSettings] = {
            "HQ": _from_env("HQ"),
            "EDGE": _from_env("EDGE"),
        }
        self._load()
        self._profiles: dict[str, dfabric.Profile] = {}
        self._rebuild()

    # ------------------------------------------------------------- persistence

    def _load(self) -> None:
        """Saved settings win over environment defaults; a missing file is normal."""
        if not STATE_FILE.exists():
            return
        try:
            saved = json.loads(STATE_FILE.read_text())
            for side in ("HQ", "EDGE"):
                if side in saved:
                    self._settings[side] = ConnectionSettings(**saved[side])
            logger.info("Loaded saved connections from %s", STATE_FILE)
        except Exception as error:
            logger.warning("Ignoring unreadable %s: %s", STATE_FILE, error)

    def _save(self) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(
                {side: asdict(s) for side, s in self._settings.items()}, indent=2))
            STATE_FILE.chmod(0o600)  # it holds cluster passwords
        except Exception as error:
            logger.warning("Could not save connections to %s: %s", STATE_FILE, error)

    # ---------------------------------------------------------------- profiles

    def _rebuild(self) -> None:
        for side, settings in self._settings.items():
            self._profiles[side] = dfabric.Profile(
                side=side,
                host=settings.host,
                rest_port=settings.rest_port,
                s3_port=settings.s3_port,
                username=settings.username,
                password=settings.password,
            )

    def profile(self, side: str) -> dfabric.Profile:
        with self._lock:
            return self._profiles[side.upper()]

    def settings(self, side: str) -> ConnectionSettings:
        with self._lock:
            return self._settings[side.upper()]

    def configured(self, side: str) -> bool:
        return bool(self.settings(side).host)

    def update(self, side: str, **changes) -> ConnectionSettings:
        """Apply changes and rebuild that side's profile.

        A blank or masked password means "keep the current one", so the operator can
        edit a host without the browser ever having to hold the real password.
        """
        side = side.upper()
        with self._lock:
            current = self._settings[side]
            for field in ("password", "ssh_password"):
                if changes.get(field) in (None, "", "********"):
                    changes[field] = getattr(current, field)
            merged = {**asdict(current), **{k: v for k, v in changes.items() if v is not None}}
            for field in ("rest_port", "s3_port", "ssh_port"):
                merged[field] = int(merged[field])
            self._settings[side] = ConnectionSettings(**merged)
            self._rebuild()
            self._save()
            logger.info("%s now points at %s as %s", side,
                        self._settings[side].host, self._settings[side].username)
            return self._settings[side]

    def same_cluster(self) -> bool:
        """True when both sites are on one cluster — a supported, ordinary setup."""
        hq, edge = self.settings("HQ"), self.settings("EDGE")
        return bool(hq.host) and hq.host == edge.host

    def snapshot(self) -> dict:
        return {
            "HQ": self.settings("HQ").redacted(),
            "EDGE": self.settings("EDGE").redacted(),
            "sameCluster": self.same_cluster(),
        }


CONNECTIONS = Connections()
