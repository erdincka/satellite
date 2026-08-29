"""HQ — Command & Control. Ingests imagery, catalogues it, broadcasts descriptions."""

import logging

from nicegui import app, ui

import aiclient
import assets
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

SIDE = "HQ"


@ui.page("/")
async def index() -> None:
    await ui.context.client.connected()

    # Restore any vision model the operator configured earlier.
    aiclient.configure(app.storage.general.get("AI_ENDPOINT", aiclient.DEFAULT_ENDPOINT),
                       app.storage.general.get("AI_MODEL", aiclient.DEFAULT_MODEL))

    pages.header(SIDE, settings.HQ_TITLE, "bg-indigo-9", "the edge", settings.EDGE_URL)
    pages.activity_log()

    with ui.column().classes("w-full p-4 gap-4"):
        pages.setup_banner(SIDE)
        with ui.element("div").classes("w-full").bind_visibility_from(
                app.storage.general, f"{SIDE}_ready"):
            pages.stage_board(SIDE)

    pages.footer(SIDE, show_admin=True)

    settings.APP_STATUS[f"{SIDE}_hint"] = (
        f"{len(utils.feed_items())} sample assets · {settings.FEED_BATCH} "
        f"published every {settings.FEED_INTERVAL:.0f}s"
    )

    await pages.refresh_status(SIDE)

    ui.timer(settings.FEED_INTERVAL, lambda: pages.run_cycle(SIDE))
    ui.timer(1.0, lambda: pages.maybe_refresh_board(SIDE))
    ui.timer(15.0, lambda: pages.refresh_status(SIDE))


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title=settings.HQ_TITLE,
        dark=None,
        storage_secret=settings.STORAGE_SECRET,
        port=settings.HQ_PORT,
        favicon="🛰️",
        reload=False,
        show=False,
    )
