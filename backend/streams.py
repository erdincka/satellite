"""
Data Fabric Streams via the native client.

Topics are addressed by their full path — `/apps/satellite-hq/hq-stream:broadcasts` —
which is what lets each site attach to the stream it owns and nothing else. Data
crosses between the two sites only through the replication pair.

This deliberately does not use the Kafka Wire Protocol. On Data Access Gateway 6.0 and
later, topic mapping rules were removed in favour of a scheme that auto-creates a
stream per topic name, and those auto-created streams are internal to the gateway: a
client cannot address a stream you provisioned yourself. Verified on a 7.1 gateway,
producing to `apps.satellite-hq.hq-stream.broadcasts` succeeds, reads back, and never
reaches the replica — while the stream you created stays empty and the replication pair
still reports itself healthy. A demo built on that would appear to work while
demonstrating nothing, so the native client is the only correct choice here.

The trade-off is that the app needs the MapR client libraries present, which is why it
ships as a container image. Provisioning still goes over REST and assets over S3, so no
FUSE mount and no maprcli are required.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Iterator

# The MapR streams client is a fork of confluent-kafka and installs under the same
# `confluent_kafka` import name. That is a trap worth naming: with upstream
# confluent-kafka installed instead, these imports still succeed and the API is
# identical, but `/path/stream:topic` addressing silently stops working. `native_client()`
# below is how the app tells which build it actually got.
from confluent_kafka import Consumer, KafkaError, Producer

from dfabric import Profile

logger = logging.getLogger(__name__)

def native_client() -> tuple[bool, str]:
    """Whether the MapR streams client is installed, rather than upstream confluent-kafka.

    Checked at startup and surfaced in the UI, because the failure mode otherwise is
    invisible: everything imports, produces succeed, and nothing reaches the stream the
    demo provisioned.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return True, f"mapr-streams-python {version('mapr-streams-python')}"
    except PackageNotFoundError:
        pass
    try:
        return False, (f"upstream confluent-kafka {version('confluent-kafka')} — "
                       "stream paths will not resolve; install mapr-streams-python")
    except PackageNotFoundError:
        return False, "no streams client installed"


_producers: dict[str, Producer] = {}
_consumers: dict[tuple[str, str], Consumer] = {}
_lock = threading.Lock()


def _producer(stream: str) -> Producer:
    """One producer per stream, reused for the life of the process."""
    with _lock:
        producer = _producers.get(stream)
        if producer is None:
            producer = Producer({"streams.producer.default.stream": stream})
            _producers[stream] = producer
        return producer


def produce(profile: Profile, stream: str, topic: str, messages: list[dict]) -> bool:
    """Publish messages to `stream:topic`. False if anything failed to flush."""
    if not messages:
        return True

    target = f"{stream}:{topic}"
    try:
        producer = _producer(stream)
        for message in messages:
            producer.produce(topic, json.dumps(message, default=str).encode("utf-8"))
        remaining = producer.flush(timeout=15)
        if remaining:
            logger.error("%d message(s) not delivered to %s", remaining, target)
            return False
        logger.debug("Published %d message(s) to %s", len(messages), target)
        return True
    except Exception as error:
        logger.error("Failed publishing to %s: %s", target, error)
        return False


def _consumer(stream: str, topic: str, group: str) -> Consumer:
    """One long-lived consumer per (topic, group).

    The previous implementation built a fresh Consumer on every timer tick and closed
    it at the end, so the group rebalanced every few seconds and messages arrived in
    bursts. Reusing one keeps offsets and membership stable.
    """
    key = (f"{stream}:{topic}", group)
    with _lock:
        consumer = _consumers.get(key)
        if consumer is None:
            consumer = Consumer({
                "group.id": group,
                "default.topic.config": {"auto.offset.reset": "earliest"},
                "enable.auto.commit": True,
            })
            consumer.subscribe([f"{stream}:{topic}"])
            _consumers[key] = consumer
            logger.debug("Subscribed %s to %s:%s", group, stream, topic)
        return consumer


def drain(profile: Profile, stream: str, topic: str, group: str,
          limit: int = 25, timeout: float = 1.0) -> Iterator[dict]:
    """Yield up to `limit` messages currently waiting on `stream:topic`.

    Returns as soon as the topic is empty rather than blocking, so a caller can run it
    on a timer without occupying a worker thread indefinitely.
    """
    try:
        consumer = _consumer(stream, topic, group)
    except Exception as error:
        logger.error("Cannot consume %s:%s — %s", stream, topic, error)
        return

    for _ in range(limit):
        try:
            message = consumer.poll(timeout=timeout)
        except Exception as error:
            logger.error("Poll failed on %s:%s — %s", stream, topic, error)
            return

        if message is None:
            return
        if message.error():
            if message.error().code() != KafkaError._PARTITION_EOF:
                logger.warning("Stream error on %s:%s — %s", stream, topic, message.error())
            return
        try:
            yield json.loads(message.value().decode("utf-8"))
        except Exception as error:
            logger.warning("Skipping unreadable message on %s:%s — %s", stream, topic, error)


def close_all() -> None:
    """Release consumers on shutdown so the group rebalances promptly on restart."""
    with _lock:
        for consumer in _consumers.values():
            try:
                consumer.close()
            except Exception:
                pass
        _consumers.clear()
        _producers.clear()


def replication_status(profile: Profile, stream: str) -> tuple[bool | None, str, int]:
    """Whether this stream's replica is keeping up.

    Returns (ok, detail, bytes_pending). Health is the *link state*, not whether the
    byte counter happens to be zero: under continuous load there is almost always
    something in flight, and reporting that as a fault made the indicator permanently
    red during a demo where replication was working perfectly. Bytes in flight are
    reported as a figure instead, and the lag chart plots them.
    """
    response = profile.rest("stream/replica/list", {"path": stream}, timeout=10)
    if profile.failed(response):
        return None, "unknown", 0
    replicas = response.get("data") or []
    if not replicas:
        return None, "no replica configured", 0

    replica = replicas[0]
    state = replica.get("replicaState", "")
    pending = int(replica.get("bytesPending", 0) or 0)
    paused = bool(replica.get("paused"))
    target = replica.get("replicaPath", "?")

    if paused:
        return False, f"paused — {target}", pending
    if state != "REPLICA_STATE_REPLICATING":
        return False, f"{state or 'not replicating'} — {target}", pending
    if pending or not replica.get("isUptodate"):
        return True, f"{_bytes(pending)} in flight to {target}", pending
    return True, f"in sync with {target}", 0


def _bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 ** 2:.1f} MB"
