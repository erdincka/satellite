"""
Connection layer for an external HPE Ezmeral Data Fabric cluster.

Provisioning and object access go over the network, so neither needs `maprcli` nor a
POSIX `/mapr` FUSE mount. Streams use the native client, which does need the MapR
client libraries — see streams.py for why the Kafka Wire Protocol is not usable here.

    provisioning / status   REST apiserver      https://<host>:8443/rest
    files + iceberg         S3 gateway          https://<host>:9000 (s3server)
    streams                 native client       CLDB <host>:7222 (see streams.py)

HQ and EDGE each own a Profile. Today both point at the same cluster; pointing EDGE
at a second cluster with a trust relationship is a configuration change, not a
refactor.
"""

from __future__ import annotations

import functools
import logging
import os
import threading
import time
from dataclasses import dataclass, field

import boto3
import httpx
import urllib3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)

# Lab clusters use self-signed certificates. We disable verification explicitly per
# client rather than globally, but the warning noise is not useful either way.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Temporary S3 keys default to a 15 minute lifetime. Renew early so a long-running
# upload never starts with a key that expires mid-flight.
S3_KEY_RENEW_MARGIN = 120  # seconds


@functools.lru_cache(maxsize=32)
def _resolve(host: str) -> str:
    """Resolve a hostname once and remember it.

    Not a micro-optimisation. In a container whose first nameserver is slow to answer,
    every lookup costs seconds before the resolver falls through — measured at 3.07s
    per call against a cluster that answers in 0.30s once connected. The apiserver
    sends no keep-alive either, so without this every REST call re-resolves and the
    interface feels broken. Falls back to the name if resolution fails, so a transient
    DNS problem degrades rather than breaks.
    """
    import socket

    try:
        address = socket.gethostbyname(host)
        if address != host:
            logger.info("Resolved %s to %s (pinned for this process)", host, address)
        return address
    except Exception as error:
        logger.warning("Could not resolve %s: %s", host, error)
        return host


@dataclass
class Profile:
    """Everything needed to reach one cluster, for one side of the demo."""

    side: str  # "HQ" or "EDGE"
    host: str
    rest_port: int = 8443
    s3_port: int = 9000
    username: str = "mapr"
    password: str = "mapr"
    verify_tls: bool = False
    s3_domain: str = "primary"
    s3_account: str = "default"

    # Resolved from the cluster on first contact rather than read from a local
    # mapr-clusters.conf, which does not exist off-cluster.
    _cluster_name: str | None = field(default=None, repr=False)
    _s3_key: dict | None = field(default=None, repr=False)
    _client: "httpx.Client | None" = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ------------------------------------------------------------------ endpoints

    @property
    def address(self) -> str:
        """The cluster's IP, resolved once. Diagnostic only — see _resolve."""
        return _resolve(self.host)

    @property
    def rest_url(self) -> str:
        # Deliberately the hostname, not the pinned address: the cluster's certificate
        # is issued for the name, and pyiceberg's S3 layer validates it even when the
        # rest of the app does not. The entrypoint pins the name in /etc/hosts instead,
        # which makes resolution instant without breaking certificate matching.
        return f"https://{self.host}:{self.rest_port}/rest"

    @property
    def s3_endpoint(self) -> str:
        return f"https://{self.host}:{self.s3_port}"

    @property
    def auth(self) -> tuple[str, str]:
        return (self.username, self.password)

    def _session(self) -> httpx.Client:
        """A reusable client that keeps the session cookie.

        Data Fabric issues a session cookie on first authentication and honours it for
        subsequent calls. Reusing one client keeps the connection pool warm and avoids
        re-authenticating on every request — the demo polls status every 15 seconds and
        mints S3 keys on a timer, so that overhead is not hypothetical.
        """
        if self._client is None:
            self._client = httpx.Client(
                auth=self.auth,
                verify=self.verify_tls,
                timeout=30.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
        return self._client

    # ------------------------------------------------------------------- REST API

    def rest(self, path: str, params: dict | None = None, timeout: float = 30.0,
             method: str = "GET") -> dict:
        """Call a REST endpoint and return the parsed body.

        Data Fabric reports application errors as HTTP 200 with status=ERROR, so
        callers must inspect `status` rather than trusting the HTTP code alone.
        Mutating endpoints (volume/stream create and remove) require POST and answer
        GET with a bare HTML 405.
        """
        url = f"{self.rest_url}/{path.lstrip('/')}"
        try:
            r = self._session().request(method, url, params=params or {}, timeout=timeout)
        except Exception as error:
            logger.debug("REST %s failed: %s", path, error)
            return {"status": "ERROR", "errors": [{"desc": str(error)}]}

        if r.status_code != 200:
            return {"status": "ERROR", "errors": [{"desc": f"HTTP {r.status_code}: {r.text[:200]}"}]}
        try:
            return r.json()
        except Exception as error:
            return {"status": "ERROR", "errors": [{"desc": f"Bad JSON: {error}"}]}

    @staticmethod
    def failed(response: dict) -> str | None:
        """Return a human-readable reason if the REST call failed, else None."""
        if response.get("status") == "OK":
            return None
        errors = response.get("errors") or [{"desc": "unknown error"}]
        return "; ".join(str(e.get("desc", e)) for e in errors)

    @property
    def cluster_name(self) -> str:
        """The cluster's own name, needed for mirror sources (`volume@cluster`).

        Never makes a network call. This is read while building the state pushed to
        browsers once a second, and a blocking REST call there freezes the whole
        interface whenever the cluster is slow or unreachable — every endpoint, not just
        cluster-dependent ones. `resolve_cluster_name` does the lookup, from a worker
        thread, on the background status probe.
        """
        return self._cluster_name or "unknown"

    @property
    def cluster_name_known(self) -> bool:
        return self._cluster_name is not None

    def resolve_cluster_name(self) -> str:
        """Look the name up and cache it. Blocking — call from a worker thread."""
        if self._cluster_name is None:
            info = self.rest("dashboard/info", timeout=15)
            if not self.failed(info):
                self._cluster_name = info["data"][0]["cluster"]["name"]
            else:
                logger.debug("Could not resolve cluster name for %s", self.host)
        return self._cluster_name or "unknown"

    # -------------------------------------------------------------- S3 credentials

    def s3_credentials(self) -> dict | None:
        """Return a currently-valid temporary S3 key pair, minting one if needed.

        Avoids storing long-lived S3 secrets anywhere: any user who can authenticate
        to REST can mint their own. Note the cluster returns the *existing* key if one
        is still valid and ignores a longer requested duration, so we renew on expiry
        rather than asking for a long-lived key up front.
        """
        with self._lock:
            now = time.time()
            key = self._s3_key
            if key and key["expires_at"] - S3_KEY_RENEW_MARGIN > now:
                return key

            response = self.rest("s3keys/gentempkey", {
                "domainname": self.s3_domain,
                "accountname": self.s3_account,
                "username": self.username,
            })
            reason = self.failed(response)
            if reason:
                logger.error("Could not obtain S3 credentials from %s: %s", self.host, reason)
                return None

            record = response["data"][0]
            self._s3_key = {
                "access_key": record["accesskey"],
                "secret_key": record["secretkey"],
                "expires_at": record["expiryTime"] / 1000,
            }
            logger.debug("Obtained temporary S3 key for %s, valid %ds",
                         self.username, self._s3_key["expires_at"] - now)
            return self._s3_key

    def s3(self):
        """Return a boto3 S3 client bound to a fresh temporary key, or None.

        Two non-obvious settings are required against the Data Fabric S3 gateway:

        - path addressing, because virtual-host buckets need per-bucket DNS
        - `when_required` checksums, because current botocore otherwise sends
          `aws-chunked` bodies with trailing checksums that the gateway rejects
          with XAmzContentSHA256Mismatch on every PutObject
        """
        credentials = self.s3_credentials()
        if not credentials:
            return None
        return boto3.client(
            "s3",
            endpoint_url=self.s3_endpoint,
            aws_access_key_id=credentials["access_key"],
            aws_secret_access_key=credentials["secret_key"],
            verify=self.verify_tls,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    # ------------------------------------------------------------------ streams
    #
    # Streams use the native client, which authenticates with a MapR ticket rather
    # than credentials passed per connection, so there is nothing to configure here.
    # Reachability is checked over REST instead.

    # ------------------------------------------------------------------- health

    def check(self, stream: str | None = None) -> dict[str, tuple[bool, str]]:
        """Probe each subsystem so setup problems are diagnosable at a glance.

        Returns {subsystem: (ok, detail)} — the UI renders this directly instead of
        making the presenter read a log to find out which piece is broken.
        """
        results: dict[str, tuple[bool, str]] = {}

        info = self.rest("dashboard/info", timeout=10)
        reason = self.failed(info)
        if reason:
            results["rest"] = (False, reason)
            # Everything else authenticates the same way; report once and stop.
            results["s3"] = (False, "skipped, REST unreachable")
            results["streams"] = (False, "skipped, REST unreachable")
            return results

        cluster = info["data"][0]["cluster"]
        results["rest"] = (True, f"{cluster['name']} ({info['data'][0].get('version', '?')})")

        credentials = self.s3_credentials()
        if not credentials:
            results["s3"] = (False, "could not mint a temporary S3 key")
        else:
            try:
                self.s3().list_buckets()  # type: ignore[union-attr]
                results["s3"] = (True, self.s3_endpoint)
            except Exception as error:
                results["s3"] = (False, f"{type(error).__name__}: {error}")

        import streams
        ok, detail = streams.native_client()
        results["client"] = (ok, detail)

        if stream:
            info = self.rest("stream/info", {"path": stream}, timeout=10)
            reason = self.failed(info)
            if reason:
                results["streams"] = (False, reason)
            else:
                topics = (info.get("data") or [{}])[0].get("numtopics", "?")
                results["streams"] = (True, f"{stream} ({topics} topics)")

        return results


# Profile instances are created and owned by connections.py, because the two sites are
# runtime-configurable connections rather than fixed environment settings.
