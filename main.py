import os
from nicegui import ui, binding, app
import logging
from page import dashboard_tiles, logging_card, start_demo
import services
import settings
import utils

# Configure logging.
logging.basicConfig(level=logging.DEBUG, encoding="utf-8", format=f'%(asctime)s:%(levelname)s:%(filename)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)
# https://sam.hooke.me/note/2023/10/nicegui-binding-propagation-warning/
# binding.MAX_PROPAGATION_TIME = 0.05

# catch-all exceptions
app.on_exception(utils.gracefully_fail)


@ui.page('/')
def index():
    if "tile_remove" not in app.storage.general.keys(): app.storage.general["tile_remove"] = 20
    app.storage.user['stream_replication'] = utils.stream_replication_status(settings.HQ_STREAM)

    with ui.header(elevated=True).classes('items-center justify-between'):
        ui.label('Command & Control Center')
        # ui.button(on_click=lambda: right_drawer.toggle(), icon='menu').props('flat color=white')
    # with ui.left_drawer(top_corner=True, bottom_corner=True):
    #     ui.label('LEFT DRAWER')
    # with ui.right_drawer(fixed=False).props('bordered') as right_drawer:
    #     ui.label('RIGHT DRAWER')
    with ui.footer().style('background-color: #3f3f3f'):
        logging_card().classes(
            "flex-grow shrink absolute sticky bottom-0 left-0 w-full opacity-50 hover:opacity-100"
        )


    with ui.row().classes("w-full no-wrap"):
        ui.chip("Replicating", icon='check' if app.storage.user["stream_replication"] else 'error', color="positive" if app.storage.user["stream_replication"] else "negative")
        ui.chip("Mounted", icon='check' if os.path.exists(settings.MAPR_MOUNT) else 'error', color="positive" if app.storage.user["stream_replication"] else "negative")
        ui.space()
        ui.button("Demo", on_click=start_demo, icon='play_circle').props('outline')

    # with ui.column().classes("w-full"):
        # with ui.grid(columns=5).classes("w-full"):
    with ui.element('pre'):
        settings.HQ_TILES

            # The image display widget to show downloaded assets in real-time
            # ui.timer(0.2, lambda: dashboard_tiles(settings.HQ_TILES))


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
    title=settings.TITLE,
        dark=None,
        storage_secret=settings.STORAGE_SECRET,
        reload=True,
        port=8501,
        favicon="📡",
    )
