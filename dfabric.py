"""
Connection layer for an external HPE Ezmeral Data Fabric cluster.

The demo used to run inside a single-node sandbox container and reach the cluster
through the native client: `maprcli` for provisioning, `mapr-streams-python` against
`/opt/mapr/lib`, and a POSIX `/mapr/<cluster>` FUSE mount for files.

None of that is required. Every access path this app needs is available over the
network, so the app can run on any machine against any reachable cluster:

    provisioning / status   REST apiserver      https://<host>:8443/rest
    streams                 Kafka Wire Protocol <host>:9092   (data-access-gateway)
    files + iceberg         S3 gateway          https://<host>:9000 (s3server)

HQ and EDGE each own a Profile. Today both point at the same cluster; pointing EDGE
at a second cluster with a trust relationship is a configuration change, not a
refactor.
"""

from __future__ import annotations

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


def _env(side: str, name: str, default: str) -> str:
    """Read SIDE_NAME, falling back to NAME, then to the default.

    Lets one variable configure both sides (`DF_HOST=...`) while still allowing a
    split deployment to override just one (`EDGE_DF_HOST=...`).
    """
    return os.environ.get(f"{side}_{name}") or os.environ.get(name) or default


@dataclass
class Profile:
    """Everything needed to reach one cluster, for one side of the demo."""

    side: str  # "HQ" or "EDGE"
    host: str
    rest_port: int = 8443
    kafka_port: int = 9092
    s3_port: int = 9000
    username: str = "mapr"
    password: str = "mapr"
    # The Kafka gateway on 9092 accepts SASL_PLAINTEXT only on a default install;
    # override when the gateway is configured for TLS.
    kafka_security_protocol: str = "SASL_PLAINTEXT"
    verify_tls: bool = False
    s3_domain: str = "primary"
    s3_account: str = "default"

    # Resolved from the cluster on first contact rather than read from a local
    # mapr-clusters.conf, which does not exist off-cluster.
    _cluster_name: str | None = field(default=None, repr=False)
    _s3_key: dict | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_env(cls, side: str) -> "Profile":
        return cls(
            side=side,
            host=_env(side, "DF_HOST", "df01.kayalab.uk"),
            rest_port=int(_env(side, "DF_REST_PORT", "8443")),
            kafka_port=int(_env(side, "DF_KAFKA_PORT", "9092")),
            s3_port=int(_env(side, "DF_S3_PORT", "9000")),
            username=_env(side, "DF_USER", "mapr"),
            password=_env(side, "DF_PASSWORD", "mapr"),
            kafka_security_protocol=_env(side, "DF_KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT"),
            verify_tls=_env(side, "DF_VERIFY_TLS", "false").lower() in ("1", "true", "yes"),
            s3_domain=_env(side, "DF_S3_DOMAIN", "primary"),
            s3_account=_env(side, "DF_S3_ACCOUNT", "default"),
        )

    # ------------------------------------------------------------------ endpoints

    @property
    def rest_url(self) -> str:
        return f"https://{self.host}:{self.rest_port}/rest"

    @property
    def kafka_bootstrap(self) -> str:
        return f"{self.host}:{self.kafka_port}"

    @property
    def s3_endpoint(self) -> str:
        return f"https://{self.host}:{self.s3_port}"

    @property
    def auth(self) -> tuple[str, str]:
        return (self.username, self.password)

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
            r = httpx.request(method, url, params=params or {}, auth=self.auth,
                              verify=self.verify_tls, timeout=timeout)
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
        """The cluster's own name, needed for mirror sources (`volume@cluster`)."""
        if self._cluster_name is None:
            info = self.rest("dashboard/info")
            if not self.failed(info):
                self._cluster_name = info["data"][0]["cluster"]["name"]
            else:
                logger.warning("Could not resolve cluster name for %s", self.host)
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

    # ------------------------------------------------------------ streams (Kafka)

    def kafka_config(self, overrides: dict | None = None) -> dict:
        config = {
            "bootstrap.servers": self.kafka_bootstrap,
            "security.protocol": self.kafka_security_protocol,
            "sasl.mechanism": "PLAIN",
            "sasl.username": self.username,
            "sasl.password": self.password,
        }
        if self.kafka_security_protocol.endswith("SSL"):
            config["enable.ssl.certificate.verification"] = str(self.verify_tls).lower()
        config.update(overrides or {})
        return config

    # ------------------------------------------------------------------- health

    def check(self) -> dict[str, tuple[bool, str]]:
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

        try:
            from confluent_kafka.admin import AdminClient

            AdminClient(self.kafka_config()).list_topics(timeout=10)
            results["streams"] = (True, f"{self.kafka_bootstrap} ({self.kafka_security_protocol})")
        except Exception as error:
            results["streams"] = (False, f"{type(error).__name__}: {error}")

        return results


# One profile per side. Both default to the same cluster; set EDGE_DF_HOST to split
# the demo across a second cluster.
HQ = Profile.from_env("HQ")
EDGE = Profile.from_env("EDGE")


def for_side(side: str) -> Profile:
    return HQ if side.upper() == "HQ" else EDGE
