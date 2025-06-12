import os
from nicegui import ui, app, background_tasks
import logging
import documentation
import pages
import services
import settings
import utils

# Configure logging.
logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s: %(pathname)s:%(lineno)d: %(message)s')
logger = logging.getLogger(__name__)

# catch-all exceptions
app.on_exception(utils.gracefully_fail)


@ui.page('/')
async def index():
    await ui.context.client.connected()
    if "tile_remove" not in app.storage.tab.keys(): app.storage.tab["tile_remove"] = 20
    # if "assets" not in app.storage.tab.keys(): app.storage.tab['assets'] = []
    if "debug" not in app.storage.tab.keys(): app.storage.tab["debug"] = False

    logger.debug("App configured: %s", app.storage.general.get('ready', False))

    with ui.header(elevated=True).classes('items-center justify-between w-full bg-indigo'):
        ui.label('Command & Control').classes('text-bold')

        ui.space()

        for svc in settings.HQ_SERVICES:
            ui.chip(on_click=lambda s=svc: pages.show_code("HQ", s)).props('floating').bind_text_from(settings.APP_STATUS, svc).bind_icon_from(settings.ICONS, svc).tooltip(svc.capitalize()).classes(settings.BGCOLORS[svc]) # pyright: ignore

        ui.space()

        ui.button(on_click=pages.configure_app, color='negative').props('unelevated round').bind_icon_from(app.storage.general, 'ready', backward=lambda x: 'link' if x else 'link_off').tooltip('App not configured, click to configure!').bind_visibility_from(app.storage.general, 'ready', backward=lambda x: not x)
        pages.app_status(target="hq")
        # ui.button(on_click=pages.hq_services, icon='rocket_launch').props("unelevated round").bind_visibility_from(app.storage.general, 'ready')
        timer = ui.timer(10, pages.hq_services)
        ui.switch().bind_value_to(timer, 'active').props("checked-icon=check unchecked-icon=pause").bind_visibility_from(app.storage.general, 'ready')

        # Monitor volume status
        # ui.timer(5, lambda: utils.volume_mirror_status('HQ'))

    # Dashboard
    log = ui.log().classes('w-full h-32 sticky top-0')
    ui.timer(1, lambda: pages.asset_list_items('HQ', log))

    with ui.grid(columns=5).classes('w-full overflow-auto'):
        ui.timer(2, lambda: pages.asset_cards('HQ'))

    # Notify to configure the app
    ui.label('App needs to be configured, use the red "disconnected" icon to set up volumes and streams required for the app to function!').bind_visibility_from(app.storage.general, 'ready', lambda x: not x).classes('text-lg')

    # Show demo info
    documentation.help_page().bind_visibility_from(app.storage.general, 'ready', lambda x: not x)

    with ui.footer():
        if os.path.exists(settings.MAPR_MOUNT):
            ui.button("EDF Root", on_click=lambda: utils.run_command_with_dialog(f"tree -L 2 {settings.MAPR_MOUNT}")).bind_enabled_from(settings.APP_STATUS, "busy", backward=lambda x: not x).props('unelevated')
        ui.button("App Volume", on_click=lambda: utils.run_command_with_dialog(f"tree {settings.MAPR_MOUNT}{settings.HQ_VOLUME}")).bind_enabled_from(settings.APP_STATUS, "busy", backward=lambda x: not x).bind_visibility_from(app.storage.general, 'ready').props('unelevated')

        ui.space()

        ui.button(on_click=pages.toggle_debug).props('unelevated round').bind_icon_from(app.storage.tab, 'debug', backward=lambda x: 'bug_report' if x else 'info').tooltip('Toggle debug mode')
        documentation.welcome().tooltip('Demo Instructions')
        ui.button("VLM", on_click=pages.change_vlm).bind_visibility_from(app.storage.general, 'ready').props('unelevated')
        ui.button("Reset", on_click=pages.reset_app, color='red').bind_visibility_from(app.storage.general, 'ready').props('unelevated')

        pages.logging_card().classes(
            "flex-grow shrink absolute sticky bottom-0 left-0 w-full opacity-50 hover:opacity-100"
        ).bind_visibility_from(app.storage.tab, "debug")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        uvicorn_reload_excludes='.venv/**/*.py',
        title=settings.TITLE,
        dark=None,
        storage_secret=settings.STORAGE_SECRET,
        reload=True,
        port=3000,
        favicon="🛰️",
    )
