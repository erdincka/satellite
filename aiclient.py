"""
Vision language model client.

The previous version read the endpoint and model into module-level globals at import
time and built one OpenAI client from them. Because the settings dialog only wrote to
storage, changing the endpoint in the UI appeared to work but had no effect until the
process restarted. Here the client is rebuilt whenever the configuration changes, so
what the dialog says is what gets used.
"""

from __future__ import annotations

import logging
import threading

import openai
from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "http://host.docker.internal:8080/v1"
DEFAULT_MODEL = "llava-v1.5"

_lock = threading.Lock()
_client: OpenAI | None = None
_config: tuple[str, str] = ("", "")


def configure(endpoint: str, model: str) -> None:
    """Point the client at a different VLM. Takes effect on the next query."""
    global _client, _config
    with _lock:
        if (endpoint, model) != _config:
            _config = (endpoint, model)
            _client = None
            logger.info("VLM set to %s (%s)", endpoint, model)


def current() -> tuple[str, str]:
    endpoint, model = _config
    return endpoint or DEFAULT_ENDPOINT, model or DEFAULT_MODEL


def _get_client() -> tuple[OpenAI, str]:
    global _client
    endpoint, model = current()
    with _lock:
        if _client is None:
            _client = OpenAI(base_url=endpoint, api_key="not-used", timeout=60.0, max_retries=1)
        return _client, model


def image_query(image_bytes: bytes | None, prompt: str = "Describe the image") -> tuple[bool, str]:
    """Ask the VLM about an image.

    Returns (ok, text). Callers get the failure reason as text so it can be shown on
    the tile rather than silently pasted into an asset's description, which is what the
    old `f'Failed to get a response for {filename}'` return value ended up doing.

    This blocks, so call it from a worker thread — never from the event loop, or every
    connected browser stalls for the duration of inference.
    """
    if not image_bytes:
        return False, "No image data"

    import base64

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    try:
        client, model = _get_client()
        response = client.chat.completions.create(
            model=model,
            max_tokens=512,
            messages=[
                {"role": "system", "content": "You are a world class image analyst."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
                ]},
            ],
        )
        return True, (response.choices[0].message.content or "").strip()
    except openai.APIConnectionError:
        endpoint, _ = current()
        return False, f"No VLM reachable at {endpoint}"
    except openai.RateLimitError:
        return False, "VLM is rate limiting; try again shortly"
    except openai.APIStatusError as error:
        return False, f"VLM returned {error.status_code}"
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"


def check(timeout: float = 4.0) -> tuple[bool, str]:
    """Probe the configured endpoint so the UI can show whether AI is actually wired up.

    Uses its own short-lived client: the query client allows a minute for inference,
    and borrowing it here would let an unreachable endpoint stall the status refresh
    — and with it the cluster pills, which have nothing to do with the model.
    """
    endpoint, model = current()
    try:
        probe = OpenAI(base_url=endpoint, api_key="not-used", timeout=timeout, max_retries=0)
        names = [m.id for m in probe.models.list()]
        if model in names:
            return True, f"{model} at {endpoint}"
        if names:
            return False, f"{endpoint} is up, but '{model}' is not among {len(names)} model(s)"
        return False, f"{endpoint} returned no models"
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"
