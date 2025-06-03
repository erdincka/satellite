import os
from nicegui import ui, app
import logging
import pages
import services
import settings
import utils

# Configure logging.
logging.basicConfig(level=logging.INFO, encoding="utf-8", format=f'%(asctime)s:%(levelname)s:%(pathname)s:%(lineno)d:%(message)s')
logger = logging.getLogger(__name__)

# catch-all exceptions
app.on_exception(utils.gracefully_fail)


@ui.page('/')
def index():
    if "tile_remove" not in app.storage.user.keys(): app.storage.user["tile_remove"] = 20
    if "debug" not in app.storage.user.keys(): app.storage.user["debug"] = False

    logger.debug("App configured: %s", app.storage.general['ready'])

    with ui.header(elevated=True).classes('items-center justify-between w-full bg-dark'):
        ui.label('Command & Control Center').classes('text-bold')

        ui.space()

        for svc in settings.HQ_SERVICES:
            ui.chip().props('floating').bind_text_from(app.storage.user, svc).bind_icon_from(settings.ICONS, svc).tooltip(svc).classes(settings.BGCOLORS[svc])
            # with ui.chip(svc.upper(), icon='').bind_visibility_from(app.storage.general, 'ready'):
            #     ui.badge("0", color='red').props('floating rounded').bind_text_from(app.storage.user, svc)

        ui.space()

        ui.button(on_click=pages.configure_app, color='negative').props('unelevated round').bind_icon_from(app.storage.general, 'ready', backward=lambda x: 'link' if x else 'link_off').tooltip('App not configured, click to configure!').bind_visibility_from(app.storage.general, 'ready', backward=lambda x: not x)
        pages.app_status()
        ui.separator().props('vertical').classes('mx-2')
        ui.button(on_click=pages.start_demo, icon='rocket_launch').props("unelevated round").bind_visibility_from(app.storage.general, 'ready')

    # Dashboard
    with ui.grid(columns=5).classes("w-full"):
        ui.timer(0.4, lambda: pages.dashboard_tiles(settings.HQ_TILES))

    with ui.grid(columns=5).classes("w-full").bind_visibility_from(settings, "HQ_TILES", backward=lambda x: len(x) == 0):
        # Placeholders
        for _ in range(3):
            with ui.card().tight().classes('w-full'):
                with ui.card_section().classes(f"w-full bg-dark"):
                    ui.skeleton('text').classes('text-subtitle1')
                ui.skeleton(square=True, animation='fade', height='150px', width='100%')
                with ui.card_section().classes('w-full'):
                    ui.skeleton('text').classes('text-subtitle2') # title
                    ui.skeleton('text').classes('text-caption') # description
                    ui.skeleton('text').classes('text-caption w-1/2') # keywords

    with ui.footer():
        ui.button("Mount point", on_click=lambda: utils.run_command_with_dialog(f"tree -L 2 {settings.MAPR_MOUNT}")).bind_enabled_from(app.storage.user, "busy", backward=lambda x: not x)
        ui.button("HQ Volume", on_click=lambda: utils.run_command_with_dialog(f"tree {settings.MAPR_MOUNT}{settings.HQ_VOLUME}")).bind_enabled_from(app.storage.user, "busy", backward=lambda x: not x)

        ui.space()

        ui.button(on_click=pages.toggle_debug).props('unelevated round').bind_icon_from(app.storage.user, 'debug', backward=lambda x: 'bug_report' if x else 'info').tooltip('Debug mode')
        ui.button("Reset", on_click=pages.reset_app, color='red').bind_visibility_from(app.storage.general, 'ready')

        pages.logging_card().classes(
            "flex-grow shrink absolute sticky bottom-0 left-0 w-full opacity-50 hover:opacity-100"
        ).bind_visibility_from(app.storage.user, "debug")


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
