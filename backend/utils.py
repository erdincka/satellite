"""Feed loading, AI helpers and the log handler that feeds the in-app console."""

from __future__ import annotations

import functools
import json
import logging
from pathlib import Path

import aiclient
from connections import CONNECTIONS
import filestore
import settings
import sites

logger = logging.getLogger(__name__)


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
                "key": filestore.object_name(previews[0]),
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
    image = filestore.read_asset(site.side, key)
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
    image = filestore.read_asset(side, key)
    if image is None:
        return False, f"{key} has not reached {site.assets_volume} yet"
    return aiclient.image_query(image, question)
