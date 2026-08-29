"""Feed loading, AI helpers and the log handler that feeds the in-app console."""

from __future__ import annotations

import functools
import json
import logging
from pathlib import Path

from nicegui import ui

import aiclient
import dfabric
import objectstore
import settings
import sites

logger = logging.getLogger(__name__)


class LogElementHandler(logging.Handler):
    """Emit log records into a ui.log element."""

    def __init__(self, element: ui.log, level: int = logging.INFO) -> None:
        self.element = element
        super().__init__(level)
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.element.push(self.format(record))
        except Exception:
            # The element is gone (tab closed) — dropping the line is the right move.
            pass


def gracefully_fail(exception: Exception) -> None:
    logger.exception("Unhandled error: %s", exception)


# ---------------------------------------------------------------------- the feed


@functools.cache
def feed_items() -> list[dict]:
    """Load the bundled NASA imagery catalogue.

    Pre-recorded rather than live so the demo works without internet and shows the same
    assets every time — useful when the same walkthrough is given repeatedly.
    """
    path = Path(settings.FEED_FILE)
    if not path.exists():
        logger.error("Feed file %s not found", path)
        return []

    try:
        raw = json.loads(path.read_text())
        items = []
        for item in raw["collection"]["items"]:
            data = item["data"][0]
            previews = [link["href"] for link in item.get("links", []) if link.get("rel") == "preview"]
            if not previews:
                continue
            items.append({
                "key": objectstore.object_name(previews[0]),
                "title": data.get("title", "(untitled)"),
                "description": data.get("description", ""),
                "keywords": ", ".join(data.get("keywords", [])),
                "preview": previews[0],
            })
        logger.info("Loaded %d feed items", len(items))
        return items
    except Exception as error:
        logger.error("Could not parse %s: %s", path, error)
        return []


# ------------------------------------------------------------------ AI helpers
#
# All of these block on the model. Call them from a worker thread.


def describe_image(site, key: str, context: str = "") -> str:
    """One-sentence intelligence-officer style narration for an asset."""
    image = objectstore.get_bytes(dfabric.for_side(site.side), site.assets_bucket, key)
    ok, text = aiclient.image_query(
        image,
        "Analyse the scene in this image as an intelligence officer and describe the "
        f"situation in one sentence. Context: '{context}'",
    )
    if not ok:
        logger.warning("No narration for %s: %s", key, text)
        return ""
    return text


def ask_about_asset(side: str, key: str, question: str) -> tuple[bool, str]:
    """Answer a question about an asset the given site holds."""
    site = sites.for_side(side)
    image = objectstore.get_bytes(dfabric.for_side(side), site.assets_bucket, key)
    if image is None:
        return False, f"{key} is not in {site.assets_bucket} yet"
    return aiclient.image_query(image, question)
