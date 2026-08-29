"""Edge — Mission Control. Receives descriptions, requests the few assets worth the link."""

import logging

from nicegui import app, ui

import aiclient
import pages
import settings
import streams
import utils

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app.on_exception(utils.gracefully_fail)
app.on_shutdown(streams.close_all)

SIDE = "EDGE"


@ui.page("/")
async def index() -> None:
    await ui.context.client.connected()

    aiclient.configure(app.storage.general.get("AI_ENDPOINT", aiclient.DEFAULT_ENDPOINT),
                       app.storage.general.get("AI_MODEL", aiclient.DEFAULT_MODEL))

    pages.header(SIDE, settings.EDGE_TITLE, "bg-blue-grey-9", "HQ", settings.HQ_URL)
    pages.activity_log()

    with ui.column().classes("w-full p-4 gap-4"):
        # The edge cannot prepare the cluster itself in the two-cluster case, but it
        # must still say so rather than showing an empty page with no explanation.
        pages.setup_banner(SIDE)
        with ui.element("div").classes("w-full").bind_visibility_from(
                app.storage.general, f"{SIDE}_ready"):
            # Tinted panels must set their own text colour: the default inverts to
            # white in dark mode, which is invisible on a light tint.
            with ui.element("div").classes(
                    "w-full rounded bg-blue-50 border border-blue-200 px-3 py-2 "
                    "text-sm text-blue-900"):
                ui.label("Click any available asset to spend bandwidth on it. "
                         "HQ will copy it across, and it appears under Delivered.")
            pages.stage_board(SIDE)

    pages.footer(SIDE, show_admin=False)

    await pages.refresh_status(SIDE)

    ui.timer(settings.FEED_INTERVAL, lambda: pages.run_cycle(SIDE))
    ui.timer(1.0, lambda: pages.maybe_refresh_board(SIDE))
    ui.timer(15.0, lambda: pages.refresh_status(SIDE))


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title=settings.EDGE_TITLE,
        dark=None,
        storage_secret=settings.STORAGE_SECRET,
        port=settings.EDGE_PORT,
        favicon="📡",
        reload=False,
        show=False,
    )
