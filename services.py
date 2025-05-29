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
            item["analysis"] = utils.ai_describe_image(filename)
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
            logger.info("Received request: %s", request["title"])
            request["created_at"] = datetime.now()
            st.session_state["request_success"].append(request)
            if utils.process_request(request):
                request["created_at"] = datetime.now()
                st.session_state["response_success"].append(request)
                yield request
            else:
                st.error(f"Failed to process request for {request['title']}")
                request["created_at"] = datetime.now()
                st.session_state["response_fail"].append(request)
        else:
            logger.info("Ignoring request: %s with status: %s", request["title"], request["status"])

# EDGE SERVICES

def asset_listener():
    for msg in streams.consume(settings.EDGE_STREAM, settings.ASSET_TOPIC):
        asset = json.loads(msg)
        logger.info("Received: %s", asset["title"])
        asset["created_at"] = datetime.now()
        st.session_state["asset_broadcast"].append(asset)
        logger.debug(asset)
        if iceberger.write(f"{settings.MAPR_MOUNT}{settings.EDGE_VOLUME}", "edge", "asset_table", [asset]): # type: ignore
            logger.debug(f"Asset notification saved: %s", asset['title'])
            asset["created_at"] = datetime.now()
            st.session_state["receive_success"].append(asset)
            yield asset
        else:
            st.error(f"Failed to save asset notification: {asset['title']}")
            asset["created_at"] = datetime.now()
            st.session_state["receive_fail"].append(asset)
            logger.debug(f"Failed to save asset notification: %s", asset['title'])


def asset_request():
    if not "selected_assets" in st.session_state: return
    logger.debug(f"Requesting assets: {st.session_state['selected_assets']['selection']['rows']}")
    for idx in st.session_state["selected_assets"]["selection"]["rows"]:
        asset = st.session_state["asset_broadcast"][idx]
        # Skip assets that are already requested
        if "status" in asset and asset["status"] in ["fulfilled", "requested"]: continue

        logger.debug("Found asset to request: %s", asset["title"])
        # Mark asset for retrieval
        asset["status"] = "requested"

        if streams.produce(settings.EDGE_STREAM, settings.REQUEST_TOPIC, [asset]):
            logger.debug("Requested: %s", asset)
            asset["created_at"] = datetime.now()
            st.session_state["request_success"].append(asset)
            yield asset
        else:
            logger.error("Failed to request asset: %s", asset['title'])
            st.error(f"Failed to request {asset['title']}")
            asset["created_at"] = datetime.now()
            st.session_state["request_fail"].append(asset)


def response_listener():
    for message in streams.consume(settings.EDGE_STREAM, settings.REQUEST_TOPIC):
        asset = json.loads(message)
        if asset["status"] == "fulfilled":
            logger.debug("Fulfilled: %s", asset)
            # Mark complete
            asset["status"] = "completed"
            asset["created_at"] = datetime.now()
            st.session_state["response_success"].append(asset)
            yield asset
        else:
            logger.info("ignoring %s with status: %s", asset["title"], asset["status"])
            logger.debug("Ignoring message: %s", asset)
