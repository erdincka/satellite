"""
Data Fabric Streams over the Kafka Wire Protocol.

Previously this used mapr-streams-python, which needs the native client under
/opt/mapr and therefore pinned the app to a cluster node. The data-access-gateway
speaks the Kafka protocol on 9092, so a stock confluent-kafka client works from
anywhere. Topics keep the Data Fabric addressing form `/stream/path:topic`.

Consumers are long-lived and owned by this module. The previous code built a fresh
Consumer on every timer tick and closed it at the end, which meant the group rebalanced
every few seconds and messages arrived in bursts. Here each (stream, topic, group) gets
one consumer that is reused for the life of the process.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Iterator

from confluent_kafka import Consumer, KafkaError, Producer

from dfabric import Profile

logger = logging.getLogger(__name__)

_producers: dict[str, Producer] = {}
_consumers: dict[tuple[str, str, str], Consumer] = {}
_lock = threading.Lock()


def _producer(profile: Profile) -> Producer:
    with _lock:
        producer = _producers.get(profile.side)
        if producer is None:
            producer = Producer(profile.kafka_config({
                "socket.keepalive.enable": True,
                # Small linger batches the handful of messages a tick produces.
                "linger.ms": 20,
            }))
            _producers[profile.side] = producer
        return producer


def produce(profile: Profile, stream: str, topic: str, messages: list[dict]) -> bool:
    """Publish messages to `stream:topic`. Returns False if any failed to flush."""
    if not messages:
        return True

    producer = _producer(profile)
    target = f"{stream}:{topic}"
    try:
        for message in messages:
            producer.produce(target, json.dumps(message, default=str).encode("utf-8"))
        remaining = producer.flush(timeout=15)
        if remaining:
            logger.error("%d message(s) not delivered to %s", remaining, target)
            return False
        logger.debug("Published %d message(s) to %s", len(messages), target)
        return True
    except Exception as error:
        logger.error("Failed publishing to %s: %s", target, error)
        return False


def _consumer(profile: Profile, stream: str, topic: str, group: str) -> Consumer:
    key = (profile.side, f"{stream}:{topic}", group)
    with _lock:
        consumer = _consumers.get(key)
        if consumer is None:
            consumer = Consumer(profile.kafka_config({
                "group.id": group,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
                "socket.keepalive.enable": True,
            }))
            consumer.subscribe([f"{stream}:{topic}"])
            _consumers[key] = consumer
            logger.debug("Subscribed %s to %s:%s", group, stream, topic)
        return consumer


def drain(profile: Profile, stream: str, topic: str, group: str,
          limit: int = 25, timeout: float = 1.0) -> Iterator[dict]:
    """Yield up to `limit` messages currently waiting on `stream:topic`.

    Returns as soon as the topic is empty rather than blocking, so callers can be run
    on a timer without occupying a thread indefinitely.
    """
    try:
        consumer = _consumer(profile, stream, topic, group)
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


def replication_status(profile: Profile, stream: str) -> bool | None:
    """True when the stream's replica is up to date, False when lagging, None if unknown."""
    response = profile.rest("stream/replica/list", {"path": stream}, timeout=10)
    if profile.failed(response):
        return None
    replicas = response.get("data") or []
    if not replicas:
        return None
    return bool(replicas[0].get("isUptodate"))
