"""v10.495 — APPEND THIS BLOCK to the end of utils/config.py.

DO NOT replace utils/config.py. The existing file (~200 lines, 8KB)
must stay intact. The README in the zip explains exactly how to
append. Do not edit any existing function.

This block adds 4 helpers + 1 constant following the v10.220 tenant
helper pattern: read from load_org_config() with documented fallbacks.
"""


# ─────────────────────────────────────────────────────────────────
# v10.495 — Brand identity + IP notice helpers (React enablement)
# ─────────────────────────────────────────────────────────────────
# Added to enable the React SPA (frontend/web/) to render tenant-
# correct branding without hardcoding. Same pattern as v10.220
# tenant helpers (bank_name, currency, etc).
#
# Defaults are Ecobank corporate brand colors (cyan-blue #1797ce,
# deep navy #0e2440, accent yellow #ffd200). Admins can override
# per tenant via the existing org_config.json mechanism.
#
# The IP notice default is the exact verbatim text from
# pages/_login.py:318 (the deployed legal text approved for the
# Ecobank deployment). Admins can override for other tenants.

_DEFAULT_IP_NOTICE = (
    "Confidential · Authorised users only · "
    "All sessions are logged. "
    "This system is protected intellectual property. "
    "Unauthorised access or reproduction is strictly prohibited "
    "and may be subject to legal action."
)


def brand_primary_hex() -> str:
    """Return the primary brand color hex. e.g. '#1797ce' for Ecobank."""
    return load_org_config().get("brand_primary_hex") or "#1797ce"


def brand_secondary_hex() -> str:
    """Return the secondary brand color hex. e.g. '#0e2440' for Ecobank."""
    return load_org_config().get("brand_secondary_hex") or "#0e2440"


def brand_accent_hex() -> str:
    """Return the accent brand color hex. e.g. '#ffd200' for Ecobank."""
    return load_org_config().get("brand_accent_hex") or "#ffd200"


def ip_notice() -> str:
    """Return the intellectual-property notice text for login screens.

    Default is the verbatim Ecobank deployment text (per
    pages/_login.py:318). Admins can override per-tenant via
    'ip_notice' key in org_config.json.
    """
    return load_org_config().get("ip_notice") or _DEFAULT_IP_NOTICE
