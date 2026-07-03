"""
utils.flexcube_script_client — thin wrapper around the FlexCube script
execution API.

All FlexCube calls go through execute_script() so retries, timeouts,
and error shapes are centralized. URL is read from FLEXCUBE_SCRIPTS_URL
env var — not hardcoded anywhere in source.

Required env var:
  FLEXCUBE_SCRIPTS_URL   — full URL of the script execution endpoint
                           e.g. http://host:port/api/scripts/execute

Optional env vars:
  FLEXCUBE_TIMEOUT_SECONDS — per-request timeout (default: 15)
  FLEXCUBE_MAX_RETRIES     — retry attempts on network error (default: 3)
"""

import logging
import os
import time

import requests

logger = logging.getLogger("a2z.flexcube_client")

_TIMEOUT  = int(os.getenv("FLEXCUBE_TIMEOUT_SECONDS", "15"))
_RETRIES  = int(os.getenv("FLEXCUBE_MAX_RETRIES", "3"))


def _get_url() -> str:
    url = os.getenv("FLEXCUBE_SCRIPTS_URL", "").strip()
    if not url:
        raise FlexcubeScriptError(
            "FLEXCUBE_SCRIPTS_URL is not set. "
            "Add it to your .env and restart the server."
        )
    return url


class FlexcubeScriptError(Exception):
    """Raised on transport failure, HTTP error, or missing configuration."""


def execute_script(script_name: str, parameters: dict) -> list[dict]:
    """
    POST to the FlexCube script execution endpoint.

    Returns the 'data' list from the response, or [] when the script
    returns successfully but with no rows.

    Raises:
        FlexcubeScriptError  — FLEXCUBE_SCRIPTS_URL not set, network
                               error, HTTP 4xx/5xx, or malformed JSON.
    """
    url = _get_url()
    payload = {"script_name": script_name, "parameters": parameters}
    last_exc: Exception | None = None

    for attempt in range(1, _RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not isinstance(data, list):
                raise FlexcubeScriptError(
                    f"{script_name}: response 'data' is not a list"
                )
            return data
        except requests.RequestException as exc:
            last_exc = exc
            wait = 2 ** (attempt - 1)
            logger.warning(
                "flexcube %s attempt %d/%d failed: %s — %s",
                script_name, attempt, _RETRIES, exc,
                f"retrying in {wait}s" if attempt < _RETRIES else "giving up",
            )
            if attempt < _RETRIES:
                time.sleep(wait)

    raise FlexcubeScriptError(
        f"{script_name} failed after {_RETRIES} attempts: {last_exc}"
    ) from last_exc


def is_configured() -> bool:
    """True when FLEXCUBE_SCRIPTS_URL is set in the environment."""
    return bool(os.getenv("FLEXCUBE_SCRIPTS_URL", "").strip())
