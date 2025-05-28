import json
import os
import shutil
import httpx
import pandas as pd
import logging
import streamlit as st
import settings
import streams
# import vlm
import aiclient
import base64

logger = logging.getLogger(__name__)

class AssetItem:
    def __init__(self, title, description, keywords, preview, href:str="", status:str="", analysis:str="", object:str=""):
        self.title = title
        self.description = description
        self.keywords = keywords
        self.preview = preview
        self.href = href
        self.status = status
        self.analysis = analysis
        self.object = object


def load_data(live: bool = True):
    if live:
        logger.debug("Getting data from API...")
        search_terms = ["missile", "earthquake", "tsunami", "oil", "flood", "iraq", "syria", "korea", "pacific"]
        query = st.segmented_control(label="Assets", options=search_terms)
        st.session_state["data"] = nasa_feed(isLive=True, query=query if query else "")
    else:
        logger.debug("Loading data from file...")
        st.session_state["data"] = nasa_feed(isLive=False)


def nasa_feed(isLive: bool, query: str = ""):
    logger.debug("Loading data, Live: %s, Query: %s", isLive, query)
    data = None
    if isLive:
        with st.spinner("Using offline feed", show_time=True):
            params = { "media_type": "image", "q": query}
            r = httpx.get("https://images-api.nasa.gov/search", params=params)
            if r.status_code == 200:
                data = r.json()
    else:
        with st.spinner("Calling NASA API", show_time=True):
            with open("images.json", "r") as f:
                data = json.loads(f.read())

    logger.info("Feed assets: %s", len(data['collection']['items']) if data else 0)

    if data:
        df = parse_data(data)
        return df
    else:
        st.error("Failed to feed data.")
        return pd.DataFrame()


def parse_data(data):
    """Parse the NASA API response data into a DataFrame."""
    logger.debug(f"Parsing NASA API response with {len(data['collection']['items'])} items.")
    try:
        logger.debug(data)
        df = pd.DataFrame(data["collection"]["items"])
        # df.set_index("href", inplace=True)
        df["title"] = df["data"].apply(lambda x: x[0]["title"])
        df["description"] = df["data"].apply(lambda x: x[0]["description"])
        df["keywords"] = df["data"].apply(lambda x: ', '.join((x[0]["keywords"] if "keywords" in x[0] else [])))
        df["preview"] = df["links"].apply(lambda x: [link["href"] for link in x if link["rel"] == "preview"][0])
        df.drop("data", axis=1, inplace=True)
        df.drop("links", axis=1, inplace=True)
        return df
    except Exception as error:
        logger.error(error)
        st.error(error)
        return None


def last_five(items: list):
    return items[::-1][-5:]


def image_to_base64(image_path: str):
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except FileNotFoundError:
        print(f"File not found: {image_path}")
        return


def ai_describe_image(filename: str):
    image_b64 = image_to_base64(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{filename}")
    ai_response = aiclient.image_query(image_b64=image_b64,
        prompt="analyze the scene in this image as an intelligence officer and describe the situation in 1 sentence")
    logger.info("AI category for %s: %s", filename, ai_response)
    return ai_response


def ai_detect_objects(filename: str):
    image_b64 = image_to_base64(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{filename}")
    ai_response = aiclient.image_query(image_b64=image_b64, prompt="list the objects in the image")
    logger.info("AI identification for %s: %s", filename, ai_response)
    return ai_response


def ai_ask_question(filename: str, question: str):
    # TODO: questions should be checked for malicious content
    image_b64 = image_to_base64(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{filename}")
    ai_response = aiclient.image_query(image_b64=image_b64, prompt=question)
    logger.info("AI identification for %s: %s", filename, ai_response)
    return ai_response


def process_request(request: dict) -> bool:
    if st.session_state['isLive']:
        logger.info("Getting asset: for %s", request['title'])
        # extract full filename from metadata
        baseUrl = "/".join(request["href"].split("/")[:-1])
        metaUrl = baseUrl + "/metadata.json"
        logger.info("Base URL: %s \nMeta URL: %s", baseUrl, metaUrl)
        r = httpx.get(metaUrl, timeout=10)
        if r.status_code != 200:
            logger.error("Failed to get metadata: %s", request["href"])
            return False
        metadata = r.json()
        logger.info("Metadata: %s", metadata)
        filename = metadata['File:FileName']
        r = httpx.get(baseUrl + f"/{filename}", timeout=10)
        if r.status_code != 200:
            logger.error("Failed to get image: %s", request["href"])
            return False
        with open(f"{settings.MAPR_MOUNT}{settings.EDGE_REPLICATED_VOLUME}/{filename}", "wb") as f:
            s = f.write(r.content)
            logger.debug("Saved %s: %d bytes", filename, s)
        logger.info("Image saved for deployed unit: : %s", filename)
    else:
        filename = request['preview'].split("/")[-1]
        logger.info("Copying asset %s to %s", filename, settings.EDGE_REPLICATED_VOLUME)
        shutil.copy(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{filename}", f"{settings.MAPR_MOUNT}{settings.EDGE_REPLICATED_VOLUME}/{filename}")

    # Send message for copied asset
    request["status"] = "fulfilled"
    if streams.produce(settings.EDGE_STREAM, settings.REQUEST_TOPIC, [request]):
        logger.info("Request processed: %s", request['title'])
        return True
    else:
        logger.error("Failed to send request completion: %s", request['title'])
        return False


def start_volume_mirror():
    REST_URL = f"{settings.REST_URL}/volume/mirror/start?name={settings.EDGE_MIRROR_NAME}"

    r = httpx.get(REST_URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200:
        st.session_state["volume_mirror"] = 1
        st.toast(f"Volume mirror started successfully.")
    else:
        st.error(f"Failed to start volume mirror. Status code: {r.status_code}")


def toggle_volume_mirror():
    toggle_action = "start" if st.session_state.get("volume_mirror", False) else "stop"

    logger.info("Setting volume mirror to: %s", toggle_action)

    REST_URL = f"{settings.REST_URL}/volume/mirror/{toggle_action}?name={settings.EDGE_REPLICATED_VOLUME}"

    r = httpx.get(REST_URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200:
        st.session_state["volume_mirror"] = 0 if toggle_action == "stop" else 1
        st.toast(f"Volume mirror {toggle_action}ed successfully.")
    else:
        st.error(f"Failed to {toggle_action} volume mirror. Status code: {r.status_code}")


def toggle_stream_replication(upstream: bool):
    toggle_action = "resume" if st.session_state.get("stream_replication", False) else "pause"

    logger.debug("Setting stream replication to: %s", toggle_action)

    REST_URL = f"{settings.REST_URL}/stream/replica/{toggle_action}?path={settings.HQ_STREAM if upstream else settings.EDGE_STREAM}&replica={settings.EDGE_STREAM if upstream else settings.HQ_STREAM}"

    r = httpx.get(REST_URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200:
        st.session_state["stream_replication"] = True if toggle_action == "resume" else False
        st.toast(f"Stream replication {toggle_action}d successfully.")
    else:
        st.error(f"Failed to {toggle_action} stream replication. Status code: {r.status_code}")

def stream_replication_status(stream: str):
    URL = f"{settings.REST_URL}/stream/replica/list?path={stream}"
    r = httpx.get(URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200 and r.json().get("status") == "OK":
        logger.debug("Replicating: %s",r.json()['data'][0]['isUptodate'])
        st.session_state["stream_replication"] = r.json()["data"][0].get("isUptodate", False)
    else:
        st.error(f"Failed to retrieve stream replication status. {r.text}")


def volume_mirror_status():
    URL = f"{settings.REST_URL}/volume/list?filter=%5Bvolumename%3D%3D{os.path.basename(settings.EDGE_REPLICATED_VOLUME)}" #&columns=mirrorstatus"
    r = httpx.get(URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200 and r.json().get("status") == "OK":
        logger.debug(r.json())
        st.session_state["volume_mirror"] = not r.json()["data"][0].get("mirrorstatus", "3") # mirrorstatus = 0 means success, 1 means failure
    else:
        st.error(f"Failed to retrieve volume mirror status. {r.text}")
