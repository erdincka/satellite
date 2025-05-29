import textwrap
from nicegui import ui, app, run
import logging

import services
import settings
from utils import LogElementHandler
import utils

logger = logging.getLogger(__name__)


async def start_demo():
    feed_data = utils.load_data(live=False)
    logger.debug("Loaded %d assets", len(feed_data))
    services.publish_to_pipeline(feed_data.to_dict(orient='records'))
    logger.debug("Published assets: %d", len(settings.HQ_TILES))
    res = await run.io_bound(services.pipeline_to_broadcast, isLive=False)
    logger.debug("After broadcast: %d", len(settings.HQ_TILES))

def logging_card():
    # Realtime logging
    with ui.card().bind_visibility_from(app.storage.user, 'demo_mode').props("flat") as logging_card:
        # ui.label("App log").classes("uppercase")
        log = ui.log().classes("h-24")
        handler = LogElementHandler(log, logging.INFO)
        rootLogger = logging.getLogger()
        rootLogger.addHandler(handler)
        ui.context.client.on_disconnect(lambda: rootLogger.removeHandler(handler))
        # rootLogger.info("Logging started")

    return logging_card

# Image dialog
def show_image(title: str, description: str, imageUrl: str):
    with ui.dialog().props("full-width") as show, ui.card().classes("grow"):
        ui.label(title).classes("w-full")
        ui.space()
        ui.label(description).classes("w-full text-wrap")
        ui.space()
        ui.image()

    show.on("close", show.clear)
    show.open()


# return image to display on UI
async def dashboard_tiles(messages: list):
    # Return an image card if available
    while len(messages) > 0:
        asset = messages.pop()
        logger.debug("Process tile for asset: %s", asset)

        # if service == "Asset Viewer Service" or service == "Image Download Service":
        #     with ui.card().classes("h-80 animate-fadeIn").props("bordered").tight() as img:
        #         with ui.card_section().classes(f"w-full text-sm {BGCOLORS[service]}"):
        #             ui.label(service)
        #         # TODO: use /mapr mount
        #         ui.image()
        #         ui.space()
        #         with ui.card_section():
        #             ui.label(textwrap.shorten(title, 32)).classes("text-sm")

        #     img.on("click", lambda t=title,d=description,u=imageUrl: show_image(t,d,u))
        #     if service == "Image Download Service": # auto remove tiles if not asset viewer
        #         ui.timer(app.storage.general.get("tile_remove", 20), img.delete, once=True)

        # else:
        #     with ui.card().classes("h-80 animate-fadeIn").props("bordered") as img:
        #         with ui.card_section().classes(f"w-full text-sm {BGCOLORS[service]}"):
        #             ui.label(service)
        #         with ui.card_section().classes("text-sm"):
        #             ui.label(textwrap.shorten(description, 64))
        #         ui.space()
        #         with ui.card_section().classes("text-sm"):
        #             ui.label(textwrap.shorten(title, 32))

        #     ui.timer(app.storage.general.get("tile_remove", 20), img.delete, once=True)

        # return img
