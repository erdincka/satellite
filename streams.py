import logging
import httpx
import settings

from confluent_kafka import Producer, Consumer, KafkaError

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

CONSUMER_GROUP= "demo-app"

def produce(stream: str, topic: str, message: str):

    logger.debug("Got message %s for Topic: %s:%s", message, stream, topic)

    p = Producer({"streams.producer.default.stream": stream})

    try:
        logger.debug("Sending: %s", message)
        p.produce(topic, message.encode("utf-8"))

    except Exception as error:
        logger.warning(error)
        return False

    finally:
        p.flush()

    return True


def consume(stream: str, topic: str):

    logger.debug("Consuming from stream: %:%s", stream, topic)
    MAX_POLL_TIME = 10

    consumer = Consumer(
        {"group.id": CONSUMER_GROUP, "default.topic.config": {"auto.offset.reset": "earliest"}}
    )

    try:

        consumer.subscribe([f"{stream}:{topic}"])

        while True:
            message = consumer.poll(timeout=MAX_POLL_TIME)

            if message is None: raise EOFError

            if not message.error(): yield message.value().decode("utf-8")

            elif message.error().code() == KafkaError._PARTITION_EOF:
                logger.info("No more messages in topic: %s", topic)
                # ui.notify(f"No more messages in {topic}")
                raise EOFError
            # silently ignore other errors
            else: logger.warning(message.error())

    except Exception as error:
        if not isinstance(error, EOFError): logger.error(error)

    finally:
        consumer.close()
        return None


def stream_metrics(stream: str, topic: str):
    URL = f"https://{settings.MY_HOSTNAME}:8443/api/v1/streams/{stream}/metricstream/topic/info?path={stream}&topic={topic}"
    AUTH = ("mapr", "mapr")

    with httpx.Client(verify=False) as client:
        response = client.get(URL, auth=AUTH, timeout=2.0)

        if response is None or response.status_code != 200:
            # possibly not connected or topic not populated yet, just ignore
            logger.info(response.text)
            logger.warning(f"Failed to get topic stats for {topic}")

        else:
            metrics = response.json()
            if not metrics["status"] == "ERROR":
                logging.debug(f"Found {metrics}")
                yield metrics
