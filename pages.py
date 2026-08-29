"""
The user interface for both sites.

The organising idea is that the screen should read as a pipeline. Each stage is a
column, and an asset is one tile that moves from left to right. A presenter can point
at a tile and say "this one is being catalogued now", which was impossible with the
previous design, where every stage produced its own card and the interesting ones were
buried among hundreds of identical broadcasts.
"""

from __future__ import annotations

import inspect
import logging
from datetime import datetime

from fastapi import Response
from nicegui import app, run, ui

import aiclient
import assets
import dfabric
import iceberger
import objectstore
import provision
import services
import settings
from assets import Asset
from utils import LogElementHandler

logger = logging.getLogger(__name__)


# --------------------------------------------------------------- image serving
#
# ui.image used to be handed an absolute filesystem path, which only worked because a
# FUSE mount happened to exist at that path inside the container. Serving through a
# route means the browser gets a normal URL and the bytes come from S3.


@app.get("/asset/{side}/{key}")
def _serve_asset(side: str, key: str):
    bucket = settings.EDGE_BUCKET if side.upper() == "EDGE" else settings.HQ_BUCKET
    data = objectstore.get_bytes(dfabric.for_side(side), bucket, key)
    if data is None:
        return Response(status_code=404)
    suffix = key.rsplit(".", 1)[-1].lower()
    media = "image/png" if suffix == "png" else "image/jpeg"
    # Assets are immutable once written, so let the browser keep them.
    return Response(content=data, media_type=media,
                    headers={"Cache-Control": "public, max-age=3600"})


def asset_url(side: str, key: str) -> str:
    return f"/asset/{side}/{key}"


# -------------------------------------------------------------------- run state
#
# Kept per-process rather than per-tab: the services are a property of the site, not of
# whoever happens to be looking at it.

RUNNING = {"HQ": False, "EDGE": False}


def running(side: str) -> bool:
    return RUNNING.get(side.upper(), False)


def set_running(side: str, value: bool) -> None:
    RUNNING[side.upper()] = value
    logger.info("%s services %s", side, "started" if value else "paused")


async def run_cycle(side: str) -> None:
    """Run one turn of a site's services, off the event loop.

    The services block on network and on the VLM. Running them in a worker keeps the
    interface responsive — the old code awaited a synchronous OpenAI call directly in a
    handler, which froze every connected browser for the length of the inference.
    """
    if not running(side) or not app.storage.general.get(f"{side}_ready"):
        return
    try:
        await run.io_bound(services.hq_cycle if side.upper() == "HQ" else services.edge_cycle)
    except Exception as error:
        logger.exception("%s cycle failed", side)
        ui.notify(f"{side} services error: {error}", type="negative", position="top")


# ------------------------------------------------------------------ status pills


@ui.refreshable
def connection_status(side: str) -> None:
    """A pill per subsystem, so a failure names itself instead of hiding in a log."""
    checks = settings.APP_STATUS.get(f"{side}_checks", {})
    if not checks:
        ui.spinner(size="sm").tooltip("Checking connection…")
        return

    for name, (ok, detail) in checks.items():
        with ui.element("div").classes(
            "flex items-center gap-1 px-2 py-0.5 rounded-full text-xs "
            + ("bg-green-100 text-green-900" if ok else "bg-red-100 text-red-900")
        ).tooltip(f"{name}: {detail}"):
            ui.icon("check_circle" if ok else "error", size="14px")
            ui.label(name)


async def refresh_status(side: str) -> None:
    """Probe the cluster in the background and update the pills."""
    profile = dfabric.for_side(side)

    def probe_cluster() -> tuple[dict, bool]:
        results = profile.check()
        # Provisioned is a separate question from reachable: the cluster can be healthy
        # and simply not have the demo's objects yet.
        return results, provision.is_configured(profile)

    try:
        checks, ready = await run.io_bound(probe_cluster)
    except Exception as error:
        logger.exception("%s status probe failed", side)
        checks, ready = {"cluster": (False, f"{type(error).__name__}: {error}")}, False

    settings.APP_STATUS[f"{side}_checks"] = checks
    app.storage.general[f"{side}_ready"] = ready
    connection_status.refresh(side)

    # The vision model is optional and may be unreachable, so probe it separately and
    # let the cluster pills appear without waiting for it.
    try:
        checks["ai"] = await run.io_bound(aiclient.check)
    except Exception as error:
        checks["ai"] = (False, str(error))
    connection_status.refresh(side)


# --------------------------------------------------------------- the stage board


def _tile(side: str, asset: Asset) -> None:
    """One asset, as it appears in a stage column."""
    failed = asset.failed
    with ui.card().tight().classes(
        "w-full cursor-pointer transition hover:shadow-lg "
        + ("border border-red-400" if failed else "")
    ) as card:
        if not failed:
            ui.image(asset_url(side, asset.key)).classes("w-full h-20 object-cover")
        with ui.card_section().classes("p-2"):
            ui.label(asset.title).classes("text-xs font-medium line-clamp-2 leading-tight")
            if failed and asset.error:
                ui.label(asset.error).classes("text-xs text-red-700 line-clamp-2 mt-1")
            elif asset.analysis:
                ui.label(asset.analysis).classes("text-xs opacity-70 line-clamp-2 mt-1")
    card.on("click", lambda a=asset: show_asset(side, a))
    card.tooltip(asset.title)


@ui.refreshable
def stage_board(side: str) -> None:
    """The columns. This reads the board; it never consumes from it."""
    board = assets.board_for(side)
    stages = board.stages + (["failed"] if board.column("failed") else [])
    snapshot = board.snapshot()

    # flex-nowrap is load-bearing: presenters run the two sites side by side at roughly
    # half a screen each, and a wrapped board puts later stages on a second row, which
    # destroys the left-to-right reading that is the whole point of the layout. Columns
    # shrink instead, and scroll horizontally only when they genuinely cannot fit.
    with ui.element("div").classes(
            "flex flex-nowrap gap-1.5 w-full items-start overflow-x-auto pb-2"):
        for stage in stages:
            column = snapshot.get(stage, [])
            with ui.column().classes("gap-2 flex-1 min-w-[6.5rem]"):
                header = ui.element("div").classes(
                    f"w-full rounded px-1.5 py-1 text-white {settings.STAGE_COLORS[stage]} "
                    "flex flex-nowrap items-center justify-between gap-1 cursor-pointer"
                )
                with header:
                    with ui.element("div").classes("flex flex-nowrap items-center gap-1 min-w-0"):
                        ui.icon(settings.ICONS[stage], size="14px").classes("shrink-0")
                        ui.label(settings.STAGE_LABELS[stage]).classes(
                            "text-[11px] font-semibold uppercase truncate leading-tight")
                    # shrink-0 keeps the count visible when the label truncates: the
                    # number is what a presenter quotes, so it must never be the thing
                    # that gets cut off.
                    ui.label(str(board.totals.get(stage, 0))).classes(
                        "text-[11px] font-bold tabular-nums shrink-0")
                header.tooltip(settings.STAGE_HELP[stage]
                               + ("  ·  Click to see the code" if stage in services.CODE[side] else ""))
                if stage in services.CODE[side]:
                    header.on("click", lambda s=stage: show_code(side, s))

                if not column:
                    ui.label("—").classes("text-xs opacity-30 text-center w-full py-2")
                for asset in column:
                    _tile(side, asset)


def maybe_refresh_board(side: str) -> None:
    """Rebuild the board only when it has actually changed."""
    board = assets.board_for(side)
    marker = f"{side}_board_version"
    if settings.APP_STATUS.get(marker) != board.version:
        settings.APP_STATUS[marker] = board.version
        stage_board.refresh(side)


# ------------------------------------------------------------------- the dialogs


def show_asset(side: str, asset: Asset) -> None:
    """Detail view, including the AI conversation for assets the edge holds."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-3xl"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label(asset.title).classes("text-lg font-medium")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        with ui.row().classes("items-center gap-2"):
            ui.badge(settings.STAGE_LABELS[asset.stage]).classes(
                f"{settings.STAGE_COLORS[asset.stage]} text-white")
            ui.label(f"in this stage for {asset.age:.0f}s").classes("text-xs opacity-60")

        if asset.failed and asset.error:
            with ui.element("div").classes(
                    "w-full rounded bg-red-50 border border-red-300 p-3 text-sm text-red-900"):
                ui.label(asset.error)

        has_image = objectstore.exists(
            dfabric.for_side(side),
            settings.EDGE_BUCKET if side.upper() == "EDGE" else settings.HQ_BUCKET,
            asset.key)
        if has_image:
            ui.image(asset_url(side, asset.key)).classes("w-full rounded max-h-96 object-contain")

        if asset.description:
            ui.label(asset.description).classes("text-sm opacity-80")
        if asset.keywords:
            with ui.row().classes("gap-1 flex-wrap"):
                for keyword in asset.keywords.split(",")[:8]:
                    if keyword.strip():
                        ui.badge(keyword.strip()).props("outline")
        if asset.analysis:
            with ui.element("div").classes("w-full rounded bg-blue-50 text-blue-900 p-3"):
                ui.label("AI narration").classes("text-xs uppercase opacity-70")
                ui.label(asset.analysis).classes("text-sm")

        # The edge's request action, which is the demo's human decision point.
        if side.upper() == "EDGE" and asset.stage == "receive":
            ui.button("Request this image from HQ",
                      icon="download",
                      on_click=lambda: (_request(asset), dialog.close())
                      ).props("unelevated color=primary").classes("w-full")

        if has_image:
            _ask_panel(side, asset)

    dialog.on("hide", dialog.delete)
    dialog.open()


def _request(asset: Asset) -> None:
    if services.request_asset(asset):
        ui.notify(f"Requested “{asset.title}” from HQ", type="positive", position="top")
    else:
        ui.notify("Could not send the request upstream", type="negative", position="top")


def _ask_panel(side: str, asset: Asset) -> None:
    """Ask the VLM about this image."""
    ui.separator()
    ui.label("Ask about this image").classes("text-xs uppercase opacity-60")
    answers = ui.column().classes("w-full gap-2")

    async def ask() -> None:
        question = box.value.strip()
        if not question:
            return
        box.value = ""
        with answers:
            ui.chat_message(question, name="You", sent=True)
            placeholder = ui.chat_message(name="VLM", sent=False)
            with placeholder:
                spinner = ui.spinner(type="dots")
        box.disable()
        try:
            ok, answer = await run.io_bound(utils_ask, side, asset.key, question)
        finally:
            box.enable()
        spinner.delete()
        with placeholder:
            ui.markdown(answer if ok else f"*{answer}*")

    box = ui.input(placeholder="e.g. how many vehicles are visible?") \
        .props("outlined dense").classes("w-full").on("keydown.enter", ask)


def utils_ask(side: str, key: str, question: str) -> tuple[bool, str]:
    import utils
    return utils.ask_about_asset(side, key, question)


def show_code(side: str, stage: str) -> None:
    """Show the source behind a stage, for narrating the implementation."""
    with ui.dialog().props("full-width") as dialog, ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"{settings.STAGE_LABELS[stage]} — {settings.STAGE_HELP[stage]}") \
                .classes("text-base font-medium")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")
        for function in services.CODE[side].get(stage, []):
            try:
                ui.code(inspect.getsource(function)).classes("w-full text-xs")
            except OSError:
                ui.label(f"(source unavailable for {function.__name__})").classes("text-xs")
    dialog.on("hide", dialog.delete)
    dialog.open()


# ------------------------------------------------------------ setup and teardown


async def configure_dialog(side: str) -> None:
    """Run provisioning, showing a checklist as each step completes."""
    with ui.dialog().props("persistent") as dialog, ui.card().classes("w-full max-w-xl"):
        ui.label("Prepare the cluster").classes("text-lg font-medium")
        ui.label("Creates the volumes, streams and buckets this demo needs, and uploads "
                 "the sample imagery. Safe to run more than once.").classes("text-sm opacity-70")
        checklist = ui.column().classes("w-full gap-1 mt-2")
        with ui.row().classes("w-full justify-end gap-2") as buttons:
            close = ui.button("Close", on_click=dialog.close).props("flat")
            start = ui.button("Configure").props("unelevated color=primary")

    async def go() -> None:
        start.disable()
        close.disable()
        checklist.clear()
        profile = dfabric.for_side(side)

        def work() -> list[provision.Step]:
            return list(provision.configure(profile))

        steps = await run.io_bound(work)
        with checklist:
            for step in steps:
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.icon("check_circle" if step.ok else "cancel",
                            color="positive" if step.ok else "negative", size="18px")
                    ui.label(step.name).classes("text-sm font-medium")
                    ui.label(step.detail).classes("text-xs opacity-60 truncate")

        failures = [s for s in steps if not s.ok]
        if failures:
            ui.notify(f"{len(failures)} step(s) failed — see the list", type="negative",
                      position="top", timeout=8000)
        else:
            ui.notify("Cluster ready", type="positive", position="top")
        close.enable()
        start.set_text("Run again")
        start.enable()
        await refresh_status(side)

    start.on_click(go)
    dialog.on("hide", dialog.delete)
    dialog.open()


async def reset_dialog(side: str) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-xl"):
        ui.label("Reset the demo").classes("text-lg font-medium")
        ui.label("Deletes the streams, volumes and buckets this demo created, including "
                 "every asset and the catalogue. The cluster's other data is untouched.") \
            .classes("text-sm opacity-70")
        checklist = ui.column().classes("w-full gap-1 mt-2")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            confirm = ui.button("Delete everything").props("unelevated color=negative")

    async def go() -> None:
        confirm.disable()
        set_running(side, False)
        profile = dfabric.for_side(side)

        def work() -> list[provision.Step]:
            return list(provision.reset(profile))

        steps = await run.io_bound(work)
        assets.HQ_BOARD.clear()
        assets.EDGE_BOARD.clear()
        with checklist:
            for step in steps:
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.icon("check_circle" if step.ok else "cancel",
                            color="positive" if step.ok else "negative", size="18px")
                    ui.label(step.name).classes("text-sm")
                    ui.label(step.detail).classes("text-xs opacity-60 truncate")
        ui.notify("Reset complete", type="positive", position="top")
        await refresh_status(side)

    confirm.on_click(go)
    dialog.on("hide", dialog.delete)
    dialog.open()


async def vlm_dialog(side: str) -> None:
    """Point the demo at a vision model, and prove it is reachable before closing."""
    endpoint_value, model_value = aiclient.current()
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-xl"):
        ui.label("Vision model").classes("text-lg font-medium")
        ui.label("Any OpenAI-compatible endpoint. Narration is optional — the pipeline "
                 "runs without it.").classes("text-sm opacity-70")
        endpoint = ui.input("Endpoint", value=endpoint_value).props("outlined dense").classes("w-full")
        model = ui.input("Model", value=model_value).props("outlined dense").classes("w-full")
        result = ui.label().classes("text-sm")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Close", on_click=dialog.close).props("flat")
            test = ui.button("Test").props("outline")
            ui.button("Save", on_click=lambda: save()).props("unelevated color=primary")

    def apply() -> None:
        aiclient.configure(endpoint.value.strip(), model.value.strip())
        app.storage.general["AI_ENDPOINT"] = endpoint.value.strip()
        app.storage.general["AI_MODEL"] = model.value.strip()

    async def run_test() -> None:
        apply()
        result.set_text("Checking…")
        ok, detail = await run.io_bound(aiclient.check)
        result.set_text(("✓ " if ok else "✗ ") + detail)
        result.classes(replace="text-sm " + ("text-green-700" if ok else "text-red-700"))

    def save() -> None:
        apply()
        ui.notify("Vision model updated", type="positive", position="top")
        dialog.close()

    test.on_click(run_test)
    dialog.on("hide", dialog.delete)
    dialog.open()


async def catalogue_dialog(side: str) -> None:
    """Show the Iceberg table the pipeline has been writing all along."""
    namespace = "EDGE" if side.upper() == "EDGE" else "HQ"
    with ui.dialog().props("full-width") as dialog, ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"{namespace} catalogue — Iceberg table").classes("text-lg font-medium")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")
        body = ui.column().classes("w-full")
        with body:
            ui.spinner()

    frame = await run.io_bound(iceberger.read_all, namespace)
    history = await run.io_bound(iceberger.snapshots, namespace)
    body.clear()
    with body:
        if frame is None or frame.empty:
            ui.label("Nothing catalogued yet — start the services and let an asset through.") \
                .classes("text-sm opacity-70")
        else:
            ui.label(f"{len(frame)} row(s), {len(history)} snapshot(s). "
                     "Every asset appends a snapshot, so the history is the pipeline's cadence.") \
                .classes("text-sm opacity-70")
            columns = [{"name": c, "label": c, "field": c, "align": "left"}
                       for c in ["title", "status", "analysis", "key"] if c in frame.columns]
            ui.table(columns=columns,
                     rows=frame[[c["name"] for c in columns]].tail(50).to_dict("records"),
                     row_key="key").classes("w-full").props("dense flat")
    dialog.on("hide", dialog.delete)
    dialog.open()


# --------------------------------------------------------------------- chrome


def header(side: str, title: str, colour: str, other_name: str, other_url: str) -> None:
    """The top bar: what this site is, whether it is healthy, and the run control."""
    with ui.header(elevated=True).classes(f"{colour} items-center gap-3 px-4 py-2"):
        ui.icon("satellite_alt" if side == "HQ" else "settings_input_antenna", size="24px")
        ui.label(title).classes("text-base font-semibold")

        ui.space()
        connection_status(side)
        ui.space()

        switch = ui.switch("Run services", value=running(side),
                           on_change=lambda e: set_running(side, e.value)) \
            .props("color=white keep-color") \
            .tooltip("Start and pause this site's services")
        switch.bind_enabled_from(app.storage.general, f"{side}_ready")

        ui.button(icon="open_in_new", on_click=lambda: ui.navigate.to(other_url, new_tab=True)) \
            .props("flat round dense color=white").tooltip(f"Open {other_name}")


def setup_banner(side: str) -> None:
    """Shown until the cluster is prepared, with the action right there in it."""
    # The explicit text colour matters: a tinted panel that relies on the default gets
    # white text in dark mode and becomes unreadable.
    with ui.element("div").classes(
        "w-full rounded border border-amber-400 bg-amber-50 text-amber-900 "
        "p-4 flex items-center gap-4"
    ).bind_visibility_from(app.storage.general, f"{side}_ready", backward=lambda x: not x):
        ui.icon("info", color="warning", size="28px")
        with ui.column().classes("gap-0 flex-grow"):
            ui.label("This cluster is not prepared yet").classes("font-medium")
            ui.label(f"Connected to {dfabric.for_side(side).host}. Create the volumes, "
                     "streams and buckets the demo needs.").classes("text-sm opacity-80")
        ui.button("Configure", icon="build",
                  on_click=lambda: configure_dialog(side)).props("unelevated color=primary")


def footer(side: str, show_admin: bool) -> None:
    """Secondary actions.

    Kept on one line at half-screen width, which is how these sites are presented. The
    running hint is the first thing allowed to disappear when space is tight, since it
    is the only element here that is not a control.
    """
    with ui.footer().classes("bg-grey-9 items-center gap-1 px-3 py-1 flex-nowrap"):
        ui.button("Catalogue", icon="table_view",
                  on_click=lambda: catalogue_dialog(side)).props("flat dense color=white")
        ui.button("Help", icon="help_outline",
                  on_click=lambda: help_dialog(side)).props("flat dense color=white") \
            .tooltip("How this demo works")
        ui.space()
        ui.label().classes("text-xs opacity-60 text-white truncate hidden sm:block") \
            .bind_text_from(settings.APP_STATUS, f"{side}_hint")
        ui.space()
        ui.button("Model", icon="visibility",
                  on_click=lambda: vlm_dialog(side)).props("flat dense color=white") \
            .tooltip("Choose the vision model")
        if show_admin:
            ui.button(icon="delete_outline",
                      on_click=lambda: reset_dialog(side)).props("flat round dense color=red-4") \
                .tooltip("Reset — delete everything the demo created")
        ui.button(icon="terminal", on_click=lambda: log_drawer.toggle()) \
            .props("flat round dense color=white").tooltip("Activity log")


def help_dialog(side: str) -> None:
    import documentation
    documentation.show(side)


def activity_log() -> ui.element:
    """A log you can open, rather than a debug mode you have to know about."""
    global log_drawer
    log_drawer = ui.right_drawer(value=False).props("width=520 bordered").classes("bg-grey-10")
    with log_drawer:
        ui.label("Activity").classes("text-white text-sm uppercase opacity-60 px-2 pt-2")
        log = ui.log(max_lines=400).classes("w-full h-full text-xs text-green-3 bg-transparent")
        handler = LogElementHandler(log, logging.INFO)
        logging.getLogger().addHandler(handler)
        ui.context.client.on_disconnect(lambda: logging.getLogger().removeHandler(handler))
    return log_drawer


log_drawer: ui.element | None = None
