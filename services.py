import logging
import random
import json

from nicegui import app

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
            settings.PROCESSED_ASSETS['HQ'].append(message)
            # yield message # generator function doesn't work with background tasks
        # app.storage.tab['assets'].extend(messages) # app.storage doesn't work with background tasks
        logger.info("Event notifications sent for %d assets", len(messages))
    else:
        for message in messages:
            message["service"] = "failed"
            settings.PROCESSED_ASSETS['HQ'].append(message)
            # yield message
        # app.storage.tab['assets'].extend(messages)
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
            # app.storage.tab['assets'].append(i)
            settings.PROCESSED_ASSETS['HQ'].append(i)
            # yield i
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
                # app.storage.tab['assets'].append(i)
                # yield i
                settings.PROCESSED_ASSETS['HQ'].append(i)
                logger.debug("Notifying broadcast: %s", i['title'])
                if streams.produce(stream=settings.HQ_STREAM, topic=settings.ASSET_TOPIC, messages=[i]):
                    i = i.copy()
                    i["service"] = "broadcast"
                    # app.storage.tab['assets'].append(i)
                    # yield i
                    settings.PROCESSED_ASSETS['HQ'].append(i)
                    logger.debug("Broadcasted: %s", i['title'])
                else:
                    i = i.copy()
                    i["service"] = "failed"
                    # app.storage.tab['assets'].append(i)
                    # yield i
                    settings.PROCESSED_ASSETS['HQ'].append(i)
                    logger.error("Failed to broadcast: %s", i['title'])
            else:
                i = i.copy()
                i["service"] = "failed"
                # app.storage.tab['assets'].append(i)
                # yield i
                settings.PROCESSED_ASSETS['HQ'].append(i)
                logger.error("Failed to record: %s",i['title'])
        else:
            i = item.copy()
            i["service"] = "failed"
            # app.storage.tab['assets'].append(i)
            # yield i
            settings.PROCESSED_ASSETS['HQ'].append(i)
            logger.error("Failed to save file: %s", i['title'])


def request_listener():
    for msg in streams.consume(settings.HQ_STREAM, settings.REQUEST_TOPIC):
        request = json.loads(msg)
        # process only pending requests
        if "status" in request and request["status"] == "requested":
            # app.storage.tab['assets'].append(request)
            # yield request
            settings.PROCESSED_ASSETS['HQ'].append(request)
            logger.info("Received request: %s", request["title"])
            if utils.process_request(request, isLive=False):
                i = request.copy()
                i["service"] = "response"
                # app.storage.tab['assets'].append(i)
                # yield i
                settings.PROCESSED_ASSETS['HQ'].append(i)
            else:
                logger.error("Failed to process request for %s", request['title'])
                request['service'] = 'failed'
                # app.storage.tab['assets'].append(request)
                # yield request
                settings.PROCESSED_ASSETS['HQ'].append(request)
        else:
            logger.info("Ignoring request: %s with status: %s", request["title"], request["status"])


# EDGE SERVICES
def asset_listener():
    for msg in streams.consume(settings.EDGE_STREAM, settings.ASSET_TOPIC):
        asset = json.loads(msg)
        logger.info("Received: %s", asset["title"])
        logger.debug(asset)
        del asset['service'] # drop column for iceberg table
        if iceberger.write(f"{settings.MAPR_MOUNT}{settings.EDGE_VOLUME}", "edge", "asset_table", [asset]): # type: ignore
            logger.debug(f"Asset notification saved: %s", asset['title'])
            i = asset.copy()
            i["service"] = "receive"
            # app.storage.tab['assets'].append(i)
            settings.PROCESSED_ASSETS['EDGE'].append(i)
        else:
            i = asset.copy()
            i["service"] = "failed"
            # app.storage.tab['assets'].append(i)
            settings.PROCESSED_ASSETS['EDGE'].append(i)
            logger.error("Failed to save asset notification: %s", asset['title'])


def asset_request(asset: dict):
    logger.debug("Sending request for: %s", asset["title"])
    # Mark asset for response
    asset["service"] = "request"
    asset["status"] = "requested"
    if streams.produce(settings.EDGE_STREAM, settings.REQUEST_TOPIC, [asset]):
        logger.debug("Requested: %s", asset)
        # app.storage.tab['assets'].append(asset)
        settings.PROCESSED_ASSETS['EDGE'].append(asset)
    else:
        asset['service'] = 'failed'
        # app.storage.tab['assets'].append(asset)
        settings.PROCESSED_ASSETS['EDGE'].append(asset)
        logger.error("Failed to request asset: %s", asset['title'])


def response_listener():
    for message in streams.consume(settings.EDGE_STREAM, settings.RESPONSE_TOPIC):
        asset = json.loads(message)
        if asset["status"] == "responded":
            logger.debug("Got response: %s", asset)
            # Mark complete
            asset['service'] = 'response'
            asset['status'] = 'completed'
            asset['object'] = utils.ai_describe_image(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{asset['preview'].split('/')[-1]}", asset['description'])
            # app.storage.tab['assets'].append(asset)
            settings.PROCESSED_ASSETS['EDGE'].append(asset)
        else:
            logger.info("ignoring %s with status: %s", asset["title"], asset["status"])
