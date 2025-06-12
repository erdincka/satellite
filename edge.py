from nicegui import ui, app
import logging
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
    if "debug" not in app.storage.tab.keys(): app.storage.tab["debug"] = False

    with ui.header(elevated=True).classes('items-center justify-between w-full bg-blue-grey'):
        ui.label('Mission Control').classes('text-bold')
        ui.space()

        for svc in settings.EDGE_SERVICES:
            ui.chip(on_click=lambda s=svc: pages.show_code("EDGE", s) if s in services.CODE['EDGE'] else None).props('floating').bind_text_from(settings.APP_STATUS, svc).bind_icon_from(settings.ICONS, svc).tooltip(svc.capitalize()).classes(settings.BGCOLORS[svc]) # pyright: ignore

        ui.space()
        pages.app_status(target="EDGE")
        ui.timer(5, lambda: pages.app_status.refresh(target="EDGE"))
        # Start the demo with services
        timer = ui.timer(15, pages.edge_services)
        # Monitor volume status
        # ui.timer(5, lambda: utils.volume_mirror_status('EDGE'))
        ui.switch().bind_value_to(timer, 'active').props("checked-icon=check unchecked-icon=pause").bind_visibility_from(app.storage.general, 'ready')
        # ui.button("Start", on_click=pages.edge_services)


    # Dashboard
    # with ui.grid(columns=5).classes("w-full"):
    #     ui.timer(0.2, pages.dashboard_tiles)
    lister = ui.list().props('bordered separator').classes('w-full h-32 overflow-auto sticky top-0')
    ui.timer(2, lambda: pages.asset_list_items('EDGE', lister))

    with ui.grid(columns=5).classes('w-full overflow-auto'):
        ui.timer(2, lambda: pages.asset_cards('EDGE'))

    ui.label('App not configured!').bind_visibility_from(app.storage.general, 'ready', lambda x: not x).classes('text-lg')

    with ui.footer():
        ui.button("EDF Root", on_click=lambda: utils.run_command_with_dialog(f"tree -L 2 {settings.MAPR_MOUNT}")).bind_enabled_from(settings.APP_STATUS, "busy", backward=lambda x: not x).props('unelevated')
        ui.button("App Volume", on_click=lambda: utils.run_command_with_dialog(f"tree -L 1 {settings.MAPR_MOUNT}{settings.EDGE_VOLUME}")).bind_enabled_from(settings.APP_STATUS, "busy", backward=lambda x: not x).props('unelevated')

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
