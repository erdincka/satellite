import os
from nicegui import ui, binding, app
import logging
from pages import dashboard_tiles, logging_card, start_demo, toggle_debug
import services
import settings
import utils

# Configure logging.
logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)

# catch-all exceptions
app.on_exception(utils.gracefully_fail)

feed_data = utils.load_data(live=False)
logger.debug("Loaded %d assets", len(feed_data))


@ui.page('/')
def index():
    if "tile_remove" not in app.storage.user.keys(): app.storage.user["tile_remove"] = 10
    if "debug" not in app.storage.user.keys(): app.storage.user["debug"] = False
    app.storage.user['stream_replication'] = utils.stream_replication_status(settings.HQ_STREAM)

    with ui.header(elevated=True).classes('items-center justify-between w-full'):
        ui.label('Command & Control Center').classes('text-bold')
        for svc in settings.HQ_SERVICES:
            with ui.chip(svc.capitalize(), icon=''):
                ui.badge(0, color='red').props('floating').bind_text_from(app.storage.user, svc)
        ui.space()
        ui.button("Start", on_click=start_demo, icon='play_circle').props('')
        ui.icon('check_circle' if app.storage.user["stream_replication"] else 'priority_high', color="positive" if app.storage.user["stream_replication"] else "negative").tooltip('Stream replication status')
        ui.icon('check_circle' if os.path.exists(settings.MAPR_MOUNT) else 'priority_high', color="positive" if os.path.exists(settings.MAPR_MOUNT) else "negative").tooltip('Mount status')
        ui.button(on_click=toggle_debug).props('flat color=white').bind_icon_from(app.storage.user, 'debug', backward=lambda x: 'bug_report' if x else 'info').tooltip('Debug mode')

    with ui.footer():
        logging_card().classes(
            "flex-grow shrink absolute sticky bottom-0 left-0 w-full opacity-50 hover:opacity-100"
        )

    # Start the pipeline process
    services.publish_to_pipeline(feed_data.to_dict(orient='records'))
    logger.debug("Published assets: %d", len([ i for i in settings.HQ_TILES if i["service"] == "pipeline"]))

    # Dashboard
    with ui.grid(columns=5).classes("w-full"):
        ui.timer(0.2, lambda: dashboard_tiles(settings.HQ_TILES))

    for item in services.request_listener():
        logger.debug("Received %s", item)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
    title=settings.TITLE,
        dark=None,
        storage_secret=settings.STORAGE_SECRET,
        reload=True,
        port=8501,
        favicon="📡",
    )
