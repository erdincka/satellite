import textwrap
from nicegui import ui, app, run
import logging

import services
import settings
from utils import LogElementHandler
import utils

logger = logging.getLogger(__name__)

def toggle_debug():
    app.storage.user["debug"] = not app.storage.user["debug"]
    logger.root.setLevel(logging.DEBUG if app.storage.user["debug"] else logging.INFO)
    logger.info("Debug mode %s", app.storage.user["debug"])


def update_ai_endpoint():
    with ui.dialog() as dialog,  ui.card():
        ui.input("Endpoint", placeholder="Enter your AI endpoint...").bind_value(app.storage.general, "AI_ENDPOINT")
        ui.input("Model Name", placeholder="Enter your AI model name...").bind_value(app.storage.general, "AI_MODEL")
        ui.button("OK", on_click=dialog.close).props("primary")
    dialog.on("close", dialog.clear)
    dialog.open()


async def start_demo():
    app.storage.general["working"] = True
    await run.io_bound(services.pipeline_to_broadcast, isLive=False)
    logger.debug("After broadcast: %d", len(settings.HQ_TILES))
    app.storage.general["working"] = False


async def configure_app():
    app.storage.general["working"] = True
    async for out in utils.run_command("/bin/bash -c ./configure-app.sh"):
        logger.info(out.strip())
    app.storage.general["working"] = False


def logging_card():
    # Realtime logging
    with ui.card().props("flat") as logging_card:
        # ui.label("App log").classes("uppercase")
        log = ui.log().classes("h-24 text-primary")
        handler = LogElementHandler(log, logging.INFO)
        rootLogger = logging.getLogger()
        rootLogger.addHandler(handler)
        ui.context.client.on_disconnect(lambda: rootLogger.removeHandler(handler))
        # rootLogger.info("Logging started")

    return logging_card


# Image dialog
def show_asset(asset: dict):
    with ui.dialog().props("") as show, ui.card().classes("grow"):
        ui.label(f"Asset: {asset['title']}").classes("w-full text-wrap")
        ui.space()
        ui.label(f"Description: {asset['description']}").classes("w-full text-wrap")
        ui.label(f"Keywords: {asset['keywords']}").classes("w-full text-wrap")
        ui.space()
        if asset["service"] in ["response", "broadcast"]:
            ui.image(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{asset['preview'].split('/')[-1]}")
        if "analysis" in asset:
            ui.label(f"AI Summary: {asset['analysis']}")
        if "object" in asset:
            ui.label(f"Detected: {asset['object']}")
            ui.input("question", placeholder="Ask a question...",)
            # on_submit=questions_to_image, args=(asset["preview"].split('/')[-1], asset["description"]
            ui.chat_message(name="AI Assistant").bind_label_from(app.storage.user, "ai_response")

    show.on("close", show.clear)
    show.open()


# return image to display on UI
async def dashboard_tiles(messages: list):
    # Return an image card if available
    while len(messages) > 0:
        asset = messages.pop(0) # FIFO
        logger.debug("Process tile for asset: %s", asset)

        with ui.card().classes("h-80").props("animate fadeIn fadeOut bordered").tight() as tileCard:
            with ui.card_section().classes(f"w-full text-sm {settings.BGCOLORS[asset["service"]]}"):
                ui.label(asset['service']).classes("uppercase")
            if asset["service"] in ["broadcast"]:
                ui.image(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{asset['preview'].split('/')[-1]}")
            if asset['service'] in ["response"]:
                ui.image(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{asset['preview'].split('/')[-1]}")
            ui.space()
            with ui.card_section().classes("text-sm"):
                ui.label(textwrap.shorten(asset['description'], 32)).tooltip(asset['description']).classes("text-sm")
                ui.label(textwrap.shorten(asset['keywords'], 32)).tooltip(asset['keywords']).classes("text-italic")
            with ui.card_section():
                ui.label(textwrap.shorten(asset['title'], 32)).classes("text-sm").tooltip(asset['title']).classes("text-bold")

            tileCard.on("click", lambda a=asset: show_asset(a)) # pyright: ignore
            if asset['service'] not in ["response", "broadcast"]: # auto remove tiles if not broadcast (hq) or response (edge)
                ui.timer(app.storage.user.get("tile_remove", 20), tileCard.delete, once=True)

            app.storage.user[asset["service"]] = app.storage.user.get(asset["service"], 0) + 1

        return tileCard
