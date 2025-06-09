import os
from random import randint
from nicegui import background_tasks, ui, app, run
import logging

import services
import settings
from utils import LogElementHandler
import utils

logger = logging.getLogger(__name__)

feed_data = utils.load_data(live=False)
logger.debug("Loaded %d assets", len(feed_data))


def toggle_debug():
    app.storage.tab["debug"] = not app.storage.tab["debug"]
    logger.root.setLevel(logging.DEBUG if app.storage.tab["debug"] else logging.INFO)
    logger.info("Debug mode %s", app.storage.tab["debug"])


async def hq_services():
    logger.debug("HQ services running...")
    background_tasks.create(run.io_bound(services.publish_to_pipeline, assets=feed_data.to_dict(orient='records'), count=randint(1, 10)))
    background_tasks.create(run.io_bound(services.pipeline_to_broadcast, isLive=False))
    background_tasks.create(run.io_bound(services.request_listener))


async def edge_services():
    logger.debug("Edge services running...")
    background_tasks.create(run.io_bound(services.asset_listener))
    background_tasks.create(run.io_bound(services.response_listener))


@ui.refreshable
def app_status(target: str, caller = None):
    """
        Refresh the app status
        caller: (optional) the caller dialog
    """
    settings.APP_STATUS['stream_replication'] = utils.stream_replication_status(settings.HQ_STREAM if target == "hq" else settings.EDGE_STREAM)
    # MapR streams are links to tables, so we can check if the link exists
    app.storage.general['ready'] = os.path.islink(settings.MAPR_MOUNT + (settings.HQ_STREAM if target == "hq" else settings.EDGE_STREAM))
    ui.icon("", color="positive" if settings.APP_STATUS["stream_replication"] else "negative").bind_name_from(settings.APP_STATUS, "stream_replication", backward=lambda x: 'check_circle' if x else 'priority_high').tooltip('Stream replication status')
    ui.icon('check_circle' if os.path.exists(settings.MAPR_MOUNT) else 'priority_high', color="positive" if os.path.exists(settings.MAPR_MOUNT) else "negative").tooltip('Mount status')

    if caller and isinstance(caller, ui.dialog):
        caller.close()


async def configure_app():
    with ui.dialog().props('full-width') as dialog, ui.card().classes("relative grow place-items-center"):
        ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes("absolute right-2 top-2")
        ui.label("Create volumes & streams...").classes("text-bold w-full")
        ui.input("Endpoint", placeholder="Enter your AI endpoint...").bind_value(app.storage.general, "AI_ENDPOINT").classes('w-full')
        ui.input("Model Name", placeholder="Enter your AI model name...").bind_value(app.storage.general, "AI_MODEL").classes('w-full')
        ui.button("OK", on_click=lambda: utils.run_command_with_dialog("./configure-app.sh", callback=lambda d=dialog: app_status.refresh(target='hq', caller=d))).props("primary")

    dialog.on("close", lambda d=dialog: d.delete()) # pyright: ignore
    dialog.open()


async def reset_app():
    with ui.dialog().props('full-width') as dialog, ui.card().classes("relative grow place-items-center"):
        ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes("absolute right-2 top-2")
        ui.label("This will delete all data and refresh the app...").classes("text-bold w-full")
        ui.button("OK", on_click=lambda: utils.run_command_with_dialog("./reset-app.sh", callback=lambda d=dialog: app_status.refresh(target='hq', caller=d)), color='red').props("unelevated").classes('w-full')

    dialog.on("close", lambda d=dialog: d.delete()) # pyright: ignore
    dialog.open()


async def change_vlm():
    with ui.dialog().props('full-width') as dialog, ui.card().classes("relative grow place-items-center"):
        ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes("absolute right-2 top-2")
        ui.label("Point to your VLM...").classes("text-bold w-full")
        ui.input("Endpoint", placeholder="Enter your AI endpoint...").bind_value(app.storage.general, "AI_ENDPOINT").classes('w-full')
        ui.input("Model Name", placeholder="Enter your AI model name...").bind_value(app.storage.general, "AI_MODEL").classes('w-full')
        ui.button("OK", on_click=lambda d=dialog: app_status.refresh(target='hq', caller=d)).props("unelevated").classes('w-full')

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
    with ui.dialog() as show, ui.card().classes("grow overflow-scroll"):
        ui.label("Service: " + asset['service']).classes(f"w-full {settings.BGCOLORS[asset['service']]}") # TODO: remove, this is for debugging
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
            ui.chat_message(name="AI Assistant").bind_label_from(settings.APP_STATUS, "ai_response")
        if asset['service'] == 'receive':
            ui.button('Request', on_click=lambda a=asset: services.asset_request(a)).props('unelevated').classes('w-full') # pyright: ignore
    show.on("close", show.clear)
    show.open()


# return image to display on UI
async def asset_cards(target: str):
    for asset in settings.PROCESSED_ASSETS[target]:
        if asset['service'] in ['pipeline', 'download', 'record', 'failed']:
            continue
        logger.debug("Building the tile for asset: %s", asset)
        with ui.card().tight().classes('w-full') as tileCard:
            with ui.card_section().classes(f"w-full m-0 py-0 {settings.BGCOLORS[asset['service']]}"):
                ui.label(asset['service']).classes(f"uppercase text-subtitle1")
            with ui.card_section().classes("w-full h-24"):
                if asset["service"] in ["broadcast"]:
                    ui.image(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{asset['preview'].split('/')[-1]}").classes("w-full h-full")
                if asset['service'] in ["response"]:
                    if asset['status'] == 'requested':
                        ui.image(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{asset['preview'].split('/')[-1]}").classes("w-full h-full")
                    else:
                        ui.image(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{asset['preview'].split('/')[-1]}").classes("w-full h-full")

            ui.label(asset['title']).tooltip(asset['title']).classes("text-subtitle2 px-1 line-clamp-1")
            ui.label(asset['description']).tooltip(asset['description']).classes("text-caption px-1 line-clamp-1")
            ui.label(asset['keywords']).tooltip(asset['keywords']).classes("text-caption px-1 line-clamp-1")

            settings.APP_STATUS[asset["service"]] = settings.APP_STATUS.get(asset["service"], 0) + 1

            tileCard.on("click", lambda a=asset: show_asset(a)) # pyright: ignore

        settings.PROCESSED_ASSETS[target].remove(asset)
        return tileCard


# @ui.refreshable
def asset_list_items(target: str, ui_log: ui.log):
    for asset in settings.PROCESSED_ASSETS[target]:
        if asset['service'] in ['receive', 'broadcast', 'response', 'request']:
            continue
        # with ui.item(on_click=lambda a=asset: show_asset(a)).classes(settings.BGCOLORS[asset['service']]) as asset_card: # pyright: ignore
        #     with ui.item_section().props('avatar').classes(f"w-12 place-items-center") :
        #         # ui.item_label(asset['service']).classes(f"uppercase text-medium")
        #         ui.icon(settings.ICONS[asset['service']], color=settings.BGCOLORS[asset['service']]).tooltip(asset['service'])
        #     with ui.item_section():
        #         ui.item_label(asset['title']).tooltip(asset['description']).classes("text-subtitle2 px-1 line-clamp-1")
        #         # ui.item_label(asset['description']).tooltip(asset['description']).classes("text-caption px-1 line-clamp-1").props('caption')
        #         # ui.item_label(asset['keywords']).tooltip(asset['keywords']).classes("text-caption px-1 line-clamp-1").props('caption')
        #     with ui.item_section().props('side'):
        #         if asset["service"] in ["broadcast"]:
        #             ui.image(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{asset['preview'].split('/')[-1]}").classes("w-full h-full")
        #         if asset['service'] in ["response"]:
        #             if asset['status'] == 'requested':
        #                 ui.image(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{asset['preview'].split('/')[-1]}").classes("w-full h-full")
        #             else:
        #                 ui.image(f"{settings.MAPR_MOUNT}{settings.EDGE_ASSETS}/{asset['preview'].split('/')[-1]}").classes("w-full h-full")

        # # if asset['service'] not in ["response", "broadcast", "receive", "request"]: # auto remove tiles if not broadcast (hq) or response/receive (edge)
        # #     ui.timer(app.storage.tab.get("tile_remove", 20), asset_card.delete, once=True)

        ui_log.push(f"{asset['service'].upper()}: {asset['title']} - {asset['description']}")
        settings.APP_STATUS[asset["service"]] = settings.APP_STATUS.get(asset["service"], 0) + 1

        settings.PROCESSED_ASSETS[target].remove(asset)
