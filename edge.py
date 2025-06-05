from nicegui import ui, app
import logging
import pages
import services
import settings
import utils

# Configure logging.
logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s: %(filename)s:%(lineno)d: %(message)s')
logger = logging.getLogger(__name__)

# catch-all exceptions
app.on_exception(utils.gracefully_fail)


@ui.page('/')
async def index():
    await ui.context.client.connected()
    if "tile_remove" not in app.storage.tab.keys(): app.storage.tab["tile_remove"] = 20
    if "debug" not in app.storage.tab.keys(): app.storage.tab["debug"] = False

    with ui.header(elevated=True).classes('items-center justify-between w-full bg-blue-grey'):
        ui.label('Mission Control').classes('text-bold')
        ui.space()

        for svc in settings.EDGE_SERVICES:
            ui.chip().props('floating').bind_text_from(app.storage.user, svc).bind_icon_from(settings.ICONS, svc).tooltip(svc.capitalize()).classes(settings.BGCOLORS[svc])

        ui.space()
        pages.app_status(target="edge")

        # ui.button(on_click=pages.edge_start_demo, icon='rocket_launch').props("unelevated round").bind_visibility_from(app.storage.general, 'ready')

    # Dashboard
    with ui.grid(columns=5).classes("w-full"):
        ui.timer(0.2, lambda: pages.dashboard_tiles(settings.EDGE_TILES))
    # ui.timer(3.0, services.asset_listener)
    # ui.timer(5.0, services.response_listener)

    # Placeholders
    # with ui.grid(columns=5).classes("w-full").bind_visibility_from(settings, "EDGE_TILES", backward=lambda x: len(x) == 0):
    ui.label('App needs to be configured, use the "link" button on Main page to set up volumes and streams required for the app to function!').bind_visibility_from(app.storage.general, 'ready', lambda x: not x).classes('text-lg')
    pages.placeholders()
    with ui.footer():
        ui.button("Mount point", on_click=lambda: utils.run_command_with_dialog(f"tree -L 2 {settings.MAPR_MOUNT}")).bind_enabled_from(app.storage.user, "busy", backward=lambda x: not x)
        ui.button("Edge Volume", on_click=lambda: utils.run_command_with_dialog(f"tree -L 1 {settings.MAPR_MOUNT}{settings.EDGE_VOLUME}")).bind_enabled_from(app.storage.user, "busy", backward=lambda x: not x)

        ui.space()

        ui.button(on_click=pages.toggle_debug).props('unelevated round').bind_icon_from(app.storage.tab, 'debug', backward=lambda x: 'bug_report' if x else 'info').tooltip('Debug mode')
        pages.logging_card().classes(
            "flex-grow shrink absolute sticky bottom-0 left-0 w-full opacity-50 hover:opacity-100"
        ).bind_visibility_from(app.storage.tab, "debug")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
    title=settings.TITLE,
        dark=None,
        storage_secret=settings.STORAGE_SECRET,
        reload=True,
        port=3001,
        favicon="📡", # 🪖
    )
