import os
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


async def start_demo():
    # Start the pipeline process
    feed_data = utils.load_data(live=False)
    logger.debug("Loaded %d assets", len(feed_data))
    services.publish_to_pipeline(feed_data.to_dict(orient='records'))
    logger.debug("Published assets: %d", len([ i for i in settings.HQ_TILES if i["service"] == "pipeline"]))
    await run.io_bound(services.pipeline_to_broadcast, isLive=False)
    logger.debug("After broadcast: %d", len(settings.HQ_TILES))
    for item in services.request_listener():
        logger.debug("Received %s", item)


@ui.refreshable
def app_status(caller = None):
    """
        Refresh the app status
        caller: (optional) the caller dialog
    """
    app.storage.user['stream_replication'] = utils.stream_replication_status(settings.HQ_STREAM)
    # MapR streams are links to tables, so we can check if the link exists
    app.storage.general['ready'] = os.path.islink(settings.MAPR_MOUNT + settings.HQ_STREAM)
    ui.icon("", color="positive" if app.storage.user["stream_replication"] else "negative").bind_name_from(app.storage.user, "stream_replication", backward=lambda x: 'check_circle' if x else 'priority_high').tooltip('Stream replication status')
    ui.icon('check_circle' if os.path.exists(settings.MAPR_MOUNT) else 'priority_high', color="positive" if os.path.exists(settings.MAPR_MOUNT) else "negative").tooltip('Mount status')

    if caller and isinstance(caller, ui.dialog):
        caller.close()


async def configure_app():
    with ui.dialog() as dialog, ui.card().classes("grow relative"):
        ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes("absolute right-2 top-2")
        ui.label("Create volumes & streams...").classes("text-bold")
        ui.input("Endpoint", placeholder="Enter your AI endpoint...").bind_value(app.storage.general, "AI_ENDPOINT")
        ui.input("Model Name", placeholder="Enter your AI model name...").bind_value(app.storage.general, "AI_MODEL")
        ui.button("OK", on_click=lambda: utils.run_command_with_dialog("./configure-app.sh", callback=lambda d=dialog: app_status.refresh(d))).props("primary")

    dialog.on("close", lambda d=dialog: d.delete()) # pyright: ignore
    dialog.open()


async def reset_app():
    with ui.dialog() as dialog, ui.card().classes("grow relative"):
        ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes("absolute right-2 top-2")
        ui.label("This will delete all data and refresh the app...").classes("text-bold")
        ui.button("OK", on_click=lambda: utils.run_command_with_dialog("./reset-app.sh", callback=lambda d=dialog: app_status.refresh(d)), color='red')

    dialog.on("close", lambda d=dialog: d.delete()) # pyright: ignore
    dialog.open()


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

        with ui.card().tight().classes('w-full') as tileCard:
        # with ui.card().classes("h-80").props("animate fadeIn fadeOut bordered").tight() as tileCard:
            with ui.card_section().classes(f"w-full {settings.BGCOLORS[asset['service']]}"):
                ui.label(asset['service']).classes(f"uppercase text-subtitle1")
            with ui.card_section().classes("w-full h-64"):
                logger.debug(asset['service'])
                if asset["service"] in ["broadcast"]:
                    ui.image(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{asset['preview'].split('/')[-1]}").classes("w-full h-full")
                if asset['service'] in ["response"]:
                    ui.image(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{asset['preview'].split('/')[-1]}").classes("w-full h-full")

            ui.label(asset['title'][:40]).tooltip(asset['title']).classes("text-subtitle2")
            ui.label(asset['description'][:40]).tooltip(asset['description']).classes("text-caption")
            ui.label(asset['keywords'][:40]).tooltip(asset['keywords']).classes("text-caption")

            tileCard.on("click", lambda a=asset: show_asset(a)) # pyright: ignore
            if asset['service'] not in ["response", "broadcast"]: # auto remove tiles if not broadcast (hq) or response (edge)
                ui.timer(app.storage.user.get("tile_remove", 20), tileCard.delete, once=True)

            app.storage.user[asset["service"]] = app.storage.user.get(asset["service"], 0) + 1

        return tileCard
