import json
import os
import shutil
import textwrap
import httpx
import pandas as pd
import logging
import settings
import streams
import aiclient
import base64
from nicegui import ui
import asyncio
from typing import Callable


logger = logging.getLogger(__name__)

# class AssetItem:
#     def __init__(self, title, description, keywords, preview, href:str="", status:str="", analysis:str="", object:str=""):
#         self.title = title
#         self.description = description
#         self.keywords = keywords
#         self.preview = preview
#         self.href = href
#         self.status = status
#         self.analysis = analysis
#         self.object = object

class LogElementHandler(logging.Handler):
    """A logging handler that emits messages to a log element."""

    def __init__(self, element: ui.log, level: int = logging.DEBUG) -> None:
        self.element = element
        super().__init__(level)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.element.push(msg)
        except Exception:
            self.handleError(record)


# Handle exceptions without UI failure
def gracefully_fail(exc: Exception):
    print("gracefully failing...")
    logger.exception(exc)


async def run_command_with_dialog(command: str, callback: Callable = lambda: None) -> None:
    """
    Run a command in the background and display the output in the pre-created dialog.
    """

    with ui.dialog().props("full-width") as dialog, ui.card().classes("grow relative"):
        ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes("absolute right-2 top-2")
        ui.label(f"Running: {textwrap.shorten(command, width=80)}").classes("text-bold")
        result = ui.log().classes("w-full mt-2").style("white-space: pre-wrap")

    dialog.on("close", lambda d=dialog: d.delete()) # pyright: ignore
    dialog.open()

    result.content = '' # pyright: ignore
    async for out in run_command(command): result.push(out)
    if callback:
        callback()


async def run_command(command: str):
    """
    Run a command in the background and return the output.
    """

    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

    # NOTE we need to read the output in chunks, otherwise the process will block
    while True:
        new = await process.stdout.read(4096) # pyright: ignore
        if not new:
            break
        yield new.decode()

    yield f"Finished cmd: {command}"
    logger.debug(f"Finished cmd: {command}")


def load_data(live: bool = True):
    if live:
        logger.debug("Getting data from API...")
        search_terms = ["missile", "earthquake", "tsunami", "oil", "flood", "iraq", "syria", "korea", "pacific"]
        query = ui.toggle(options=search_terms, clearable=False, value=search_terms[0])
        return nasa_feed(isLive=True, query=str(query) if query else "")
    else:
        logger.debug("Loading data from file...")
        return nasa_feed(isLive=False)


def nasa_feed(isLive: bool, query: str = ""):
    logger.debug("Loading data, Live: %s, Query: %s", isLive, query)
    data = None
    if isLive:
        params = { "media_type": "image", "q": query}
        r = httpx.get("https://images-api.nasa.gov/search", params=params)
        if r.status_code == 200:
            data = r.json()
    else:
        with open("images.json", "r") as f:
            data = json.loads(f.read())

    logger.info("Feed assets: %s", len(data['collection']['items']) if data else 0)

    if data:
        df = parse_data(data)
        return df
    else:
        logger.error("Failed to feed data.")
        return pd.DataFrame()


def parse_data(data):
    """Parse the NASA API response data into a DataFrame."""
    logger.debug(f"Parsing NASA API response with {len(data['collection']['items'])} items.")
    try:
        # logger.debug(data)
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
        return pd.DataFrame()


def image_to_base64(image_path: str):
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except FileNotFoundError:
        print(f"File not found: {image_path}")
        return


def ai_describe_image(filename: str, context: str = ""):
    image_b64 = image_to_base64(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{filename}")
    ai_response = aiclient.image_query(image_b64=image_b64,
        prompt=f"Analyze the scene in this image as an intelligence officer and describe the situation in 1 sentence, use this description about the image: '{context}'")
    logger.info("AI analysis for %s: %s", filename, ai_response)
    return ai_response if ai_response else f'Failed to get a response for {filename}'


def ai_detect_objects(filename: str):
    image_b64 = image_to_base64(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{filename}")
    ai_response = aiclient.image_query(image_b64=image_b64, prompt="list the objects in the image")
    logger.info("AI identification for %s: %s", filename, ai_response)
    return ai_response if ai_response else f'failed to get object detection for {filename}'


def ai_ask_question(filename: str, question: str):
    # TODO: questions should be checked for malicious content
    image_b64 = image_to_base64(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{filename}")
    ai_response = aiclient.image_query(image_b64=image_b64, prompt=question)
    logger.info("AI response for q: %s on image %s: %s", question, filename, ai_response)
    return ai_response if ai_response else "Your question remained unanswered!!!"


def process_request(request: dict, isLive: bool = False) -> bool:
    if isLive:
        logger.info("Capturing asset metadata: for %s", request['title'])
        # extract full filename from metadata
        baseUrl = "/".join(request["href"].split("/")[:-1])
        metaUrl = baseUrl + "/metadata.json"
        logger.debug("Base URL: %s \nMeta URL: %s", baseUrl, metaUrl)
        r = httpx.get(metaUrl, timeout=10)
        if r.status_code != 200:
            logger.error("Failed to get metadata: %s", request["href"])
            return False
        metadata = r.json()
        logger.debug("Metadata: %s", metadata)
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
    i = request.copy()
    i["status"] = "responded"
    if streams.produce(settings.EDGE_STREAM, settings.RESPONSE_TOPIC, [i]):
        logger.info("Response is sent for: %s", i['title'])
        return True
    else:
        logger.error("Failed to send response for: %s", i['title'])
        return False
