"""
The Satellite server: one service, two site connections.

Serves the built frontend, a small REST API for actions, and a WebSocket that pushes
state. HQ and the edge are two connections rather than two processes, which is what
makes pointing both at the same cluster an ordinary configuration rather than a special
case.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import aiclient
import assets
import clientsetup
import dfabric
import iceberger
import jobs
import link as link_module
import filestore
import provision
import runner
import settings
import sites
import streams
import utils
from connections import CONNECTIONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Imagery is the local stand-in for a feed, so it must exist wherever the server
    # runs — not wherever Configure happened to be clicked.
    staged = provision.stage_images()
    logger.info("Sample imagery: %s", staged.detail)

    aiclient.configure(settings.AI_ENDPOINT, settings.AI_MODEL)

    for site_runner in runner.RUNNERS.values():
        site_runner.start()
    link_module.LINK.start()
    pusher = asyncio.create_task(runner.HUB.push_state_forever(), name="state-push")

    yield

    pusher.cancel()
    await link_module.LINK.stop()
    for site_runner in runner.RUNNERS.values():
        await site_runner.stop()
    await asyncio.to_thread(streams.close_all)


app = FastAPI(title="Satellite", lifespan=lifespan)


# ------------------------------------------------------------------- websocket


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await runner.HUB.add(websocket)
    try:
        # Send state immediately so a new tab is correct before the next push.
        await websocket.send_json({"type": "state", "payload": runner.full_state()})
        while True:
            await websocket.receive_text()  # keeps the socket open; input is unused
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket closed", exc_info=True)
    finally:
        await runner.HUB.remove(websocket)


# ---------------------------------------------------------------------- state


@app.get("/api/state")
async def get_state() -> dict:
    return runner.full_state()


# ----------------------------------------------------------------- connections


class ConnectionUpdate(BaseModel):
    host: str | None = None
    username: str | None = None
    password: str | None = None
    rest_port: int | None = None
    s3_port: int | None = None


@app.get("/api/connections")
async def get_connections() -> dict:
    return CONNECTIONS.snapshot()


@app.put("/api/connections/{side}")
async def update_connection(side: str, update: ConnectionUpdate) -> dict:
    """Point a site at a cluster and prepare the client for it.

    Preparing here is what lets the container be deployed with no cluster at all and
    configured afterwards: the ticket and NFS mount are established now rather than
    only at boot.
    """
    _check_side(side)
    settings_after = CONNECTIONS.update(side, **update.model_dump())

    if settings_after.host:
        profile = CONNECTIONS.profile(side)
        report = await asyncio.to_thread(
            clientsetup.prepare, settings_after.host, settings_after.username,
            settings_after.password, profile.cluster_name,
            "/mapr", settings_after.rest_port)
        clientsetup.remember(side, report)

    await runner.for_side(side).refresh_status()
    return CONNECTIONS.snapshot()


@app.post("/api/connections/{side}/prepare-client")
async def prepare_client(side: str) -> dict:
    """Re-run client setup — after a cluster comes back, or a truststore is supplied."""
    _check_side(side)
    settings_now = CONNECTIONS.settings(side)
    if not settings_now.host:
        raise HTTPException(400, "No cluster configured for this site")
    profile = CONNECTIONS.profile(side)
    report = await asyncio.to_thread(
        clientsetup.prepare, settings_now.host, settings_now.username,
        settings_now.password, profile.cluster_name, "/mapr", settings_now.rest_port)
    clientsetup.remember(side, report)
    await runner.for_side(side).refresh_status()
    return report


@app.post("/api/connections/{side}/test")
async def test_connection(side: str, update: ConnectionUpdate | None = None) -> dict:
    """Probe a candidate cluster without committing to it.

    Lets an operator confirm a host before switching the demo onto it, which matters
    when repointing at a customer's cluster mid-session.
    """
    _check_side(side)
    current = CONNECTIONS.settings(side)
    candidate = dfabric.Profile(
        side=side.upper(),
        host=(update.host if update and update.host else current.host),
        rest_port=(update.rest_port if update and update.rest_port else current.rest_port),
        s3_port=(update.s3_port if update and update.s3_port else current.s3_port),
        username=(update.username if update and update.username else current.username),
        password=(update.password if update and update.password
                  and update.password != "********" else current.password),
    )
    if not candidate.host:
        raise HTTPException(400, "No host given")

    checks = await asyncio.to_thread(candidate.check)
    return {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()}


# --------------------------------------------------------------------- control


@app.post("/api/sites/{side}/run")
async def set_running(side: str, value: bool = True) -> dict:
    _check_side(side)
    runner.for_side(side).set_running(value)
    return {"running": runner.for_side(side).running}


@app.post("/api/sites/{side}/step")
async def step_once(side: str) -> dict:
    """Advance one cycle without starting continuous mode, for a scripted walkthrough."""
    _check_side(side)
    await runner.for_side(side).cycle_once()
    return {"ok": True}


@app.post("/api/sites/{side}/configure")
async def configure_site(side: str) -> dict:
    """Provision this site, reporting progress as it goes.

    Returns as soon as the job starts; each step appears in pushed state, so the
    interface fills in a checklist rather than sitting on a static message.
    """
    _check_side(side)
    site_runner = runner.for_side(side)
    peer = sites.EDGE if side.upper() == "HQ" else None
    peer_profile = CONNECTIONS.profile("EDGE") if side.upper() == "HQ" else None

    if jobs.JOB.busy:
        raise HTTPException(409, "Another operation is already running")

    asyncio.create_task(jobs.JOB.run(
        "configure", side,
        lambda: provision.configure(site_runner.profile, site_runner.site,
                                    peer, peer_profile),
        after=site_runner.refresh_status,
    ))
    return {"started": True}


@app.post("/api/sites/{side}/reset")
async def reset_site(side: str) -> dict:
    _check_side(side)
    site_runner = runner.for_side(side)
    site_runner.set_running(False)

    if jobs.JOB.busy:
        raise HTTPException(409, "Another operation is already running")

    def after():
        assets.board_for(side).clear()
        return site_runner.refresh_status()

    asyncio.create_task(jobs.JOB.run(
        "reset", side,
        lambda: provision.reset(site_runner.profile, site_runner.site),
        after=after,
    ))
    return {"started": True}


@app.post("/api/sites/EDGE/request/{key}")
async def request_asset(key: str) -> dict:
    """The demo's human decision point: spend bandwidth on this one."""
    asset = assets.EDGE_BOARD.get(key)
    if asset is None:
        raise HTTPException(404, f"{key} is not available at the edge")
    ok = await asyncio.to_thread(services.request_asset, asset)
    return {"ok": ok}


# ------------------------------------------------------------------------ link


class LinkMode(BaseModel):
    mode: str
    interval: float | None = None
    window: float | None = None


@app.put("/api/link")
async def set_link(body: LinkMode) -> dict:
    """Cut, schedule or restore the link between the sites.

    This pauses and resumes Data Fabric stream replication for real — messages queue on
    the cluster while it is down and drain when it comes back.
    """
    if body.mode not in (link_module.CONNECTED, link_module.SCHEDULED,
                         link_module.DISCONNECTED):
        raise HTTPException(400, f"Unknown link mode {body.mode}")
    await link_module.LINK.set_mode(body.mode, body.interval, body.window)
    # Status is cached for STATUS_INTERVAL, so without this the detail line keeps
    # reporting the old state for up to fifteen seconds after the link changes — long
    # enough to look broken while demonstrating exactly this.
    await runner.for_side("HQ").refresh_status()
    return link_module.LINK.snapshot()


@app.post("/api/link/mirror")
async def mirror_now() -> dict:
    """Pull the edge's assets volume from HQ's outbound volume, now."""
    ok, detail = await asyncio.to_thread(link_module.LINK.mirror_now)
    return {"ok": ok, "detail": detail}


@app.post("/api/link/sync")
async def sync_link() -> dict:
    """Open the link now for one window — an operator spending the link deliberately."""
    await link_module.LINK.sync_now()
    await runner.for_side("HQ").refresh_status()
    return link_module.LINK.snapshot()


# ---------------------------------------------------------------------- assets


@app.get("/api/assets/{side}/{key}/image")
async def asset_image(side: str, key: str):
    _check_side(side)
    data = await asyncio.to_thread(filestore.read_asset, side, key)
    if data is None:
        return Response(status_code=404)
    media = "image/png" if key.lower().endswith(".png") else "image/jpeg"
    return Response(content=data, media_type=media,
                    headers={"Cache-Control": "public, max-age=3600"})


class Question(BaseModel):
    question: str


@app.post("/api/assets/{side}/{key}/ask")
async def ask_about_asset(side: str, key: str, question: Question) -> dict:
    _check_side(side)
    ok, answer = await asyncio.to_thread(
        utils.ask_about_asset, side, key, question.question)
    return {"ok": ok, "answer": answer}


@app.get("/api/catalogue/{side}")
async def catalogue(side: str, limit: int = 50) -> dict:
    _check_side(side)
    site = sites.for_side(side)
    frame = await asyncio.to_thread(iceberger.read_all, site)
    history = await asyncio.to_thread(iceberger.snapshots, site)
    if frame is None or frame.empty:
        return {"rows": [], "snapshots": history, "warehouse": site.warehouse_bucket}
    columns = [c for c in ("title", "status", "analysis", "key") if c in frame.columns]
    return {
        "rows": frame[columns].tail(limit).to_dict("records"),
        "snapshots": history[-20:],
        "warehouse": site.warehouse_bucket,
        "total": len(frame),
    }


# ------------------------------------------------------------------------- AI


class ModelSettings(BaseModel):
    endpoint: str
    model: str


@app.get("/api/model")
async def get_model() -> dict:
    endpoint, model = aiclient.current()
    return {"endpoint": endpoint, "model": model}


@app.put("/api/model")
async def set_model(body: ModelSettings) -> dict:
    aiclient.configure(body.endpoint.strip(), body.model.strip())
    ok, detail = await asyncio.to_thread(aiclient.check)
    return {"ok": ok, "detail": detail}


@app.post("/api/model/test")
async def test_model() -> dict:
    ok, detail = await asyncio.to_thread(aiclient.check)
    return {"ok": ok, "detail": detail}


# --------------------------------------------------------------------- pacing


class Pace(BaseModel):
    interval: float | None = None
    batch: int | None = None


@app.put("/api/pace")
async def set_pace(pace: Pace) -> dict:
    """Let a presenter slow the demo down mid-sentence, or speed it up for a booth."""
    if pace.interval is not None:
        settings.FEED_INTERVAL = max(1.0, float(pace.interval))
    if pace.batch is not None:
        settings.FEED_BATCH = max(1, int(pace.batch))
    return {"interval": settings.FEED_INTERVAL, "batch": settings.FEED_BATCH}


# --------------------------------------------------------------------- static


def _check_side(side: str) -> None:
    if side.upper() not in ("HQ", "EDGE"):
        raise HTTPException(404, f"Unknown site {side}")


import services  # noqa: E402  (imported late; it pulls in the streams client)

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        """Serve the single-page app, letting the client handle its own routing."""
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
