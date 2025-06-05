import asyncio
import logging
import random
import json

from nicegui import app, background_tasks
import iceberger
import streams, settings
import mapr
import utils

logger = logging.getLogger(__name__)


# HQ Services
def publish_to_pipeline(assets: list[dict], count: int = 5):
    logger.debug("Picking random %d assets out of %d samples", count, len(assets))
    messages = random.sample(assets, min(len(assets), count))
    if streams.produce(stream=settings.HQ_STREAM, topic=settings.PIPELINE, messages=messages):
        # Tag asset with service name
        for message in messages:
            message["service"] = "pipeline"
        settings.HQ_TILES.extend(messages)
        logger.info("Event notifications sent for %d assets", len(messages))
    else:
        for message in messages:
            message["service"] = "failed"
        settings.HQ_TILES.extend(messages)
        logger.error("Failed to put into pipeline: %s", messages)


def pipeline_to_broadcast(isLive: bool = False):
    logger.debug("Starting pipeline to broadcast live: %s", isLive)
    for msg in streams.consume(stream=settings.HQ_STREAM, topic=settings.PIPELINE):
        item = json.loads(msg)
        logger.info("Asset notification: %s", item["title"])
        logger.debug("Downloading from: %s", item["preview"])
        filename = mapr.save_from_url(item["preview"], isLive)
        if filename:
            i = item.copy()
            i["service"] = "download"
            settings.HQ_TILES.append(i)
            # work on another copy
            i = item.copy()
            # Run AI narration on the image
            i["analysis"] = utils.ai_describe_image(filename, i['description'])
            # Update the table with the analysis
            logger.debug("Updating table with analysis: %s", i['analysis'])
            if iceberger.write(warehouse_path=f"{settings.MAPR_MOUNT}{settings.HQ_VOLUME}", namespace="hq", tablename="asset_table", records=[i]):
                logger.debug("Updated table with analysis: %s", i['analysis'])
                i = i.copy()
                i["service"] = "record"
                settings.HQ_TILES.append(i)
                logger.debug("Notifying broadcast: %s", i['title'])
                if streams.produce(stream=settings.HQ_STREAM, topic=settings.ASSET_TOPIC, messages=[i]):
                    i = i.copy()
                    i["service"] = "broadcast"
                    settings.HQ_TILES.append(i)
                    logger.debug("Broadcasted: %s", i['title'])
                else:
                    i = i.copy()
                    i["service"] = "failed"
                    settings.HQ_TILES.append(i)
                    logger.error("Failed to broadcast: %s", i['title'])
            else:
                i = i.copy()
                i["service"] = "failed"
                settings.HQ_TILES.append(i)
                logger.error("Failed to record: %s",i['title'])
        else:
            i = item.copy()
            i["service"] = "failed"
            settings.HQ_TILES.append(i)
            logger.error("Failed to save file: %s", i['title'])


async def request_listener():
    for msg in streams.consume(settings.HQ_STREAM, settings.REQUEST_TOPIC):
        request = json.loads(msg)
        # process only pending requests
        if "status" in request and request["status"] == "requested":
            i = request.copy()
            settings.HQ_TILES.append(i)
            logger.info("Received request: %s", i["title"])
            if utils.process_request(i, isLive=False):
                i["service"] = "response"
                settings.HQ_TILES.append(i)
            else:
                logger.error("Failed to process request for %s", i['title'])
                i['service'] = 'failed'
                settings.HQ_TILES.append(i)
        else:
            logger.info("Ignoring request: %s with status: %s", request["title"], request["status"])


# EDGE SERVICES
async def asset_listener():
    while app.storage.general.get('receive_service', False):
        for msg in streams.consume(settings.EDGE_STREAM, settings.ASSET_TOPIC):
            asset = json.loads(msg)
            logger.info("Received: %s", asset["title"])
            logger.debug(asset)
            del asset['service'] # drop column for iceberg table
            if iceberger.write(f"{settings.MAPR_MOUNT}{settings.EDGE_VOLUME}", "edge", "asset_table", [asset]): # type: ignore
                logger.debug(f"Asset notification saved: %s", asset['title'])
                i = asset.copy()
                i["service"] = "received"
                settings.EDGE_TILES.append(i)
            else:
                i = asset.copy()
                i["service"] = "failed"
                settings.EDGE_TILES.append(i)
                logger.error("Failed to save asset notification: %s", asset['title'])
        await asyncio.sleep(4)


def asset_request(asset: dict):
    # Skip assets that are already requested
    if "status" in asset and asset["status"] in ["fulfilled", "requested"]: return
    logger.debug("Found asset to request: %s", asset["title"])
    # Mark asset for retrieval
    asset["status"] = "requested"

    if streams.produce(settings.EDGE_STREAM, settings.REQUEST_TOPIC, [asset]):
        logger.debug("Requested: %s", asset)
        i = asset.copy()
        i["service"] = "request"
        settings.EDGE_TILES.append(i)
    else:
        i = asset.copy()
        i['service'] = 'failed'
        settings.EDGE_TILES.append(i)
        logger.error("Failed to request asset: %s", asset['title'])


async def response_listener():
    while app.storage.general.get('request_service', False):
        for message in streams.consume(settings.EDGE_STREAM, settings.REQUEST_TOPIC):
            asset = json.loads(message)
            if asset["status"] == "fulfilled":
                logger.debug("Fulfilled: %s", asset)
                # Mark complete
                asset["status"] = "completed"
                settings.EDGE_TILES.append(asset)
            else:
                logger.info("ignoring %s with status: %s", asset["title"], asset["status"])
        await asyncio.sleep(4)

