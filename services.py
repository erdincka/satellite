from datetime import datetime
import logging
import random
import streamlit as st
import pandas as pd
import json
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
            # Run AI narration on the image
            item["analysis"] = utils.ai_describe_image(filename, item['description'])
            # Update the table with the analysis
            if iceberger.write(warehouse_path=f"{settings.MAPR_MOUNT}{settings.HQ_VOLUME}", namespace="hq", tablename="asset_table", records=[item]):
                i = item.copy()
                i["service"] = "record"
                settings.HQ_TILES.append(i)
                if streams.produce(stream=settings.HQ_STREAM, topic=settings.ASSET_TOPIC, messages=[item]):
                    i = item.copy()
                    i["service"] = "broadcast"
                    settings.HQ_TILES.append(i)
                else:
                    logger.error("Failed to broadcast: %s", item['title'])
            else:
                logger.error("Failed to record: %s",item['title'])
        else:
            logger.error("Failed to save file: %s", item['title'])


def request_listener():
    for msg in streams.consume(settings.HQ_STREAM, settings.REQUEST_TOPIC):
        request = json.loads(msg)
        # process only pending requests
        if "status" in request and request["status"] == "requested":
            i = request.copy()
            logger.info("Received request: %s", i["title"])
            if utils.process_request(i, isLive=False):
                i["service"] = "response"
                settings.HQ_TILES.append(i)
                yield i
            else:
                logger.error("Failed to process request for %s", i['title'])
                settings.HQ_TILES.append(i)
        else:
            logger.info("Ignoring request: %s with status: %s", request["title"], request["status"])


# EDGE SERVICES
def asset_listener():
    for msg in streams.consume(settings.EDGE_STREAM, settings.ASSET_TOPIC):
        asset = json.loads(msg)
        logger.info("Received: %s", asset["title"])
        logger.debug(asset)
        if iceberger.write(f"{settings.MAPR_MOUNT}{settings.EDGE_VOLUME}", "edge", "asset_table", [asset]): # type: ignore
            logger.debug(f"Asset notification saved: %s", asset['title'])
            i = asset.copy()
            i["service"] = "receive"
            settings.EDGE_TILES.append(i)
            yield asset
        else:
            logger.error("Failed to save asset notification: %s", asset['title'])


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
        return True
    else:
        logger.error("Failed to request asset: %s", asset['title'])


def response_listener():
    for message in streams.consume(settings.EDGE_STREAM, settings.REQUEST_TOPIC):
        asset = json.loads(message)
        if asset["status"] == "fulfilled":
            logger.debug("Fulfilled: %s", asset)
            # Mark complete
            asset["status"] = "completed"
            settings.EDGE_TILES.append(asset)
            yield asset
        else:
            logger.info("ignoring %s with status: %s", asset["title"], asset["status"])
