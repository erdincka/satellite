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

HQ_SERVICES = ["pipeline", "download", "broadcast", "request", "response"]
EDGE_SERVICES = ["receive", "request", "response"]

# HQ Services
def publish_to_pipeline(count: int = 5):
    with st.spinner("Broadcasting pipeline...", show_time=True):
        assets = st.session_state.get("data", pd.DataFrame()).to_json(orient='records', lines=True).splitlines() # pyright: ignore[reportOptionalMemberAccess]
        logger.debug(f"Assets: {assets}")
        for item in random.sample(assets, min(len(assets), count)):
            # FIX: this shouldn't happen
            if not item: return
            if streams.produce(stream=settings.HQ_STREAM, topic=settings.PIPELINE, message=item):
                i = json.loads(item)
                logger.debug("In pipeline: %s", i["title"])
                st.session_state["pipeline_success"].append(i)
            else:
                logger.error("Failed to put into pipeline: %s", item) # type: ignore
                st.session_state["pipeline_fail"].append(item)


def pipeline_to_broadcast():
    for msg in streams.consume(stream=settings.HQ_STREAM, topic=settings.PIPELINE):
        item = json.loads(msg)
        logger.info("Asset from pipeline: %s", item["title"])
        logger.debug(item)
        logger.debug("Downloading from: %s", item["preview"])
        filename = mapr.save_from_url(item["preview"], st.session_state["isLive"])
        if filename:
            st.session_state["download_success"].append(item)
            # Run AI narration on the image
            item["analysis"] = utils.describe_image(filename)
            # Update the table with the analysis
            if iceberger.write(warehouse_path=f"{settings.MAPR_MOUNT}{settings.HQ_VOLUME}", namespace="hq", tablename="asset_table", records=[item]):
                if streams.produce(stream=settings.HQ_STREAM, topic=settings.ASSET_TOPIC, message=json.dumps(item)):
                    st.session_state["broadcast_success"].append(item)
                    yield item
                else:
                    st.error(f"Failed to publish: {item['title']}")
                    st.session_state["broadcast_fail"].append(item)
            else:
                st.error(f"Failed to update on HQ asset table: {item['title']}")
                # st.session_state["download_fail"].append(item)
        else:
            st.error(f"Failed to extract filename: {item['title']}")
            # st.session_state["download_fail"].append(item)

    logger.info("HQ FEED: %d success, %d fail", len(st.session_state["broadcast_success"]), len(st.session_state["pipeline_fail"]) + len(st.session_state["broadcast_fail"]))


# @st.fragment(run_every=5)
def request_listener():
    for msg in streams.consume(settings.HQ_STREAM, settings.REQUEST_TOPIC):
        request = json.loads(msg)
        # process only pending requests
        if "status" in request and request["status"] == "requested":
            logger.info("Received request: %s", request["title"])
            st.session_state["request_success"].append(request)
            if utils.process_request(request):
                st.session_state["response_success"].append(request)
                yield request
            else:
                st.error(f"Failed to process request for {request['title']}")
                st.session_state["response_fail"].append(request)
        else:
            logger.info("Ignoring request: %s with status: %s", request["title"], request["status"])

# EDGE SERVICES

def asset_listener():
    for msg in streams.consume(settings.EDGE_STREAM, settings.ASSET_TOPIC):
        asset = json.loads(msg)
        logger.info("Received: %s", asset["title"])
        st.session_state["asset_broadcast"].append(asset)
        logger.debug(asset)
        if iceberger.write(f"{settings.MAPR_MOUNT}{settings.EDGE_VOLUME}", "edge", "asset_table", [asset]): # type: ignore
            logger.debug(f"Asset notification saved: %s", asset['title'])
            st.session_state["receive_success"].append(asset)
            yield asset
        else:
            st.error(f"Failed to save asset notification: {asset['title']}")
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

        if streams.produce(settings.EDGE_STREAM, settings.REQUEST_TOPIC, json.dumps(asset)):
            logger.debug("Requested: %s", asset)
            st.session_state["request_success"].append(asset)
            yield asset
        else:
            logger.error("Failed to request asset: %s", asset['title'])
            st.error(f"Failed to request {asset['title']}")
            st.session_state["request_fail"].append(asset)


def response_listener():
    for message in streams.consume(settings.EDGE_STREAM, settings.REQUEST_TOPIC):
        asset = json.loads(message)
        if asset["status"] == "fulfilled":
            logger.debug("Fulfilled: %s", asset)
            # Mark complete
            asset["status"] = "completed"
            st.session_state["response_success"].append(asset)
            yield asset
        else:
            logger.info("ignoring %s with status: %s", asset["title"], asset["status"])
            logger.debug("Ignoring message: %s", asset)
