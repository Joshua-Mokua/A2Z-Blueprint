"""External / AD authentication service.

Mirrors the Ecobank Laravel AuthenticationService pattern:
  - Tries a configurable primary URL, then an optional fallback
  - GET request with email + password query params
  - Expects JSON response: {success: true, data: {fullname, email, department, title}}
  - Returns a normalised user dict on success, None on failure

Settings are read from data/auth_settings.json and are writable via
POST /api/admin/auth-config (require_config_admin gate).
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
_SETTINGS_FILE = DATA_DIR / "auth_settings.json"

# Canonical keys + defaults — only these are persisted.
_DEFAULTS: dict = {
    "ad_enabled": False,
    "ad_primary_url": "",
    "ad_fallback_url": "",
    "ad_timeout_seconds": 60,
    "ad_verify_ssl": False,
    "ad_fallback_to_local": True,   # always fall back to bcrypt on AD failure
}


# ── Settings I/O ──────────────────────────────────────────────────────────────

def get_auth_settings() -> dict:
    """Read auth_settings.json; return defaults if missing or unreadable."""
    if not _SETTINGS_FILE.exists():
        return dict(_DEFAULTS)
    try:
        txt = _SETTINGS_FILE.read_text(encoding="utf-8").strip()
        if txt:
            stored = json.loads(txt)
            return {**_DEFAULTS, **stored}
    except Exception as exc:
        logger.warning("auth_settings.json read error: %s", exc)
    return dict(_DEFAULTS)


def save_auth_settings(settings: dict) -> dict:
    """Persist only whitelisted keys to auth_settings.json (atomic write)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe = {k: settings[k] for k in _DEFAULTS if k in settings}
    merged = {**_DEFAULTS, **safe}

    fd, tmp = tempfile.mkstemp(dir=str(DATA_DIR), prefix=".authset_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, str(_SETTINGS_FILE))
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise
    return merged


# ── Auth service ──────────────────────────────────────────────────────────────

class ExternalAuthService:
    """Try primary AD URL, fall back to secondary if configured.

    On success returns a normalised user dict:
        {name, email, department, title}

    The caller (login endpoint) is responsible for upserting this into
    UserManager and issuing the JWT.
    """

    def __init__(self, settings: dict):
        self.primary_url  = (settings.get("ad_primary_url")  or "").strip()
        self.fallback_url = (settings.get("ad_fallback_url") or "").strip()
        self.timeout      = int(settings.get("ad_timeout_seconds") or 60)
        self.verify_ssl   = bool(settings.get("ad_verify_ssl", False))
        # Set when the most recent authenticate() call never got a response
        # from any configured URL within `timeout` — distinct from "AD
        # responded and said no". The login endpoint uses this to avoid
        # reporting a slow/unreachable AD server as "invalid credentials":
        # those are different problems with different fixes.
        self.timed_out = False

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Return normalised user dict on success, None on failure."""
        import requests  # lazy — not installed in all envs; fail fast here

        self.timed_out = False
        urls = [u for u in [self.primary_url, self.fallback_url] if u]
        if not urls:
            logger.warning("ExternalAuthService: ad_enabled=true but no URLs configured")
            return None

        any_timeout = False
        for idx, url in enumerate(urls):
            label = "primary" if idx == 0 else "fallback"
            try:
                resp = requests.get(
                    url,
                    params={"email": username, "password": password},
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                if resp.ok:
                    body = resp.json()
                    if body.get("success") and body.get("data"):
                        d = body["data"]
                        logger.info(
                            "ExternalAuth success for '%s' via %s URL", username, label
                        )
                        return {
                            "name":       d.get("fullname") or d.get("name") or username,
                            "email":      d.get("email", username),
                            "department": d.get("department") or "",
                            "title":      d.get("title") or "",
                        }
                logger.warning(
                    "ExternalAuth %s URL returned non-success for '%s': HTTP %d",
                    label, username, resp.status_code,
                )
            except requests.exceptions.Timeout:
                any_timeout = True
                logger.warning(
                    "ExternalAuth %s URL TIMED OUT after %ds for '%s'",
                    label, self.timeout, username,
                )
                # continue to next URL
            except Exception as exc:
                logger.warning(
                    "ExternalAuth %s URL error for '%s': %s", label, username, exc
                )
                # continue to next URL

        self.timed_out = any_timeout
        logger.warning("ExternalAuth failed on all URLs for '%s' (timed_out=%s)",
                        username, any_timeout)
        return None
