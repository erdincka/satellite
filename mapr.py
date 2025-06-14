from datetime import datetime
import os
import httpx
import logging
import shutil
import settings


logger = logging.getLogger(__name__)


def connect_and_configure():
    """
    Try connection to Data Fabric and configure for required settings, i.e., streams and volumes, for the app
    """

    try:
        # Create stream
        s = httpx.post(f"{settings.REST_URL}/stream/create?path={settings.HQ_STREAM}&ttl=3600", auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)

        if s.status_code == 200:
            logger.info("Stream created: %s", s.json())
        else:
            logger.error("Failed to create stream: %s", s.text)

    except Exception as error:
        logger.error(error)


def save_from_url(url: str):
    filename = url.split("/")[-1]
    logger.debug("Copy %s", filename)
    try:
        shutil.copy(f"images/{filename}", f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{filename}")
        return filename
    except Exception as error:
        logger.error(error)
        return None


def stream_replication_status(stream: str):
    URL = f"{settings.REST_URL}/stream/replica/list?path={stream}"
    logger.debug("Checking replication for: %s",stream)
    try:
        r = httpx.get(URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
        if r.status_code == 200 and r.json().get("status") == "OK":
            uptodate = r.json()['data'][0]['isUptodate']
            logger.debug("Replicating: %s", uptodate)
            return bool(uptodate)
        else:
            logger.error("Failed to retrieve stream replication status. %s", r.text)
            return False
    except Exception as e:
        logger.error("Failed to retrieve stream replication status. %s", e)
        return False


def volume_mirror_status():
    URL = f"{settings.REST_URL}/volume/list?filter=%5Bvolumename%3D%3D{os.path.basename(settings.EDGE_MIRROR_NAME)}" #&columns=mirrorstatus"
    r = httpx.get(URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200 and r.json().get("status") == "OK":
        logger.debug(r.json())
        last_mirrored = r.json()["data"][0].get("lastSuccessfulMirrorTime") # percentage of last or current mirror operation
        mirror_status = r.json()["data"][0].get("mirrorstatus", "3") # mirrorstatus = 0 means success, 1 means failure
        logger.debug("Volume mirror status %s, %s", mirror_status, datetime.now().timestamp() - last_mirrored / 1000)
        settings.APP_STATUS["EDGE_MIRROR"] = datetime.now().timestamp() - last_mirrored / 1000
        return not mirror_status
    else:
        settings.APP_STATUS["EDGE_MIRROR"] = "FAILED!"
        logger.error("Failed to retrieve volume mirror status. %s", r.text)
        return False


def start_volume_mirror():
    REST_URL = f"{settings.REST_URL}/volume/mirror/start?name={settings.EDGE_MIRROR_NAME}"

    r = httpx.get(REST_URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200:
        logger.info("Volume mirror started successfully.")
    else:
        logger.error("Failed to start volume mirror. Status code: %s", r.status_code)


def toggle_volume_mirror():
    toggle_action = "start"

    logger.info("Setting volume mirror to: %s", toggle_action)

    REST_URL = f"{settings.REST_URL}/volume/mirror/{toggle_action}?name={settings.EDGE_REPLICATED_VOLUME}"

    r = httpx.get(REST_URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200:
        logger.info("Volume mirror %sed successfully.", toggle_action)
    else:
        logger.error("Failed to %s volume mirror. Status code: %s", toggle_action, r.status_code)


def toggle_stream_replication(upstream: bool):
    toggle_action = "resume"

    logger.debug("Setting stream replication to: %s", toggle_action)

    REST_URL = f"{settings.REST_URL}/stream/replica/{toggle_action}?path={settings.HQ_STREAM if upstream else settings.EDGE_STREAM}&replica={settings.EDGE_STREAM if upstream else settings.HQ_STREAM}"

    r = httpx.get(REST_URL, auth=(settings.MAPR_USER, settings.MAPR_PASSWORD), verify=False)
    if r.status_code == 200:
        logger.info("Stream replication %sd successfully.", toggle_action)
    else:
        logger.error("Failed to %s stream replication. Status code: %s", toggle_action, r.status_code)
