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


def save_from_url(url: str, isLive: bool):
    filename = url.split("/")[-1]
    if isLive:
        logger.info("Downloading %s as %s", url, filename)
        try:
            r = httpx.get(url)
            if r.status_code == 200:
                # BytesIO(r.content)
                with open(f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{filename}", "wb") as f:
                    s = f.write(r.content)
                    logger.debug("Saved %s: %d bytes", filename, s)
                return filename
            else:
                logger.error("Failed to download %s", url)
                return None
        except Exception as error:
            logger.error(error)
            return None
    else:
        logger.info("Copy %s", filename)
        try:
            shutil.copy(f"images/{filename}", f"{settings.MAPR_MOUNT}{settings.HQ_ASSETS}/{filename}")
            return filename
        except Exception as error:
            logger.error(error)
            return None
