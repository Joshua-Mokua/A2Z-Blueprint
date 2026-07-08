"""utils/config.py — Centralised config loader.
All modules read thresholds, labels, and settings from org_config.json.
Never hard-code a threshold in a page — always use cfg("key", default).

v10.220: Tenant identity helpers added (bank_name, currency, country,
regulator, core_banking_system, tax_authority, currency_symbol).
Per master prompt addendum Rule N1, pages must NEVER hardcode tenant
identifiers — read from these helpers. Audit gate G162 ratchets the
current count of hardcoded tenant strings.

Helper return-value defaults are NEUTRAL placeholders (e.g.
"[Bank Name]") rather than the configured tenant — this keeps the
helper code itself tenant-agnostic, and missing-config situations
visibly show the placeholder so admins know to configure.
"""
import json
import streamlit as st
from pathlib import Path

_CFG_PATH = Path(__file__).parent.parent / "data" / "org_config.json"

@st.cache_data(ttl=30, show_spinner=False)
def load_org_config() -> dict:
    """Load the full org config. Cached 30s."""
    try:
        return json.loads(_CFG_PATH.read_text())
    except Exception:
        return {}

def cfg(key: str, default=None):
    """Get a threshold or setting by key. Falls back to default."""
    org = load_org_config()
    val = org.get("thresholds", {}).get(key)
    if val is None:
        val = org.get("module_config", {}).get(key)
    return val if val is not None else default

def get_departments(active_only=True) -> list:
    """Return departments list from org_config."""
    org  = load_org_config()
    deps = org.get("departments", [])
    return [d for d in deps if not active_only or d.get("active", True)]

def get_dept_by_name(name: str) -> dict:
    """Return a department record by name."""
    for d in get_departments(active_only=False):
        if d["name"] == name:
            return d
    return {}

def get_branches(active_only=True, region=None) -> list:
    """Return branches, optionally filtered by region."""
    org = load_org_config()
    brs = org.get("branches", [])
    if active_only:
        brs = [b for b in brs if b.get("active", True)]
    if region:
        brs = [b for b in brs if b.get("region") == region]
    return sorted(brs, key=lambda x: x["name"])

def get_modules(active_only=True) -> list:
    """Return all module definitions."""
    org = load_org_config()
    mods = org.get("modules", [])
    return [m for m in mods if not active_only or m.get("active", True)]

def get_dept_modules(dept_id: str) -> list:
    """Return module keys assigned to a department."""
    org = load_org_config()
    return org.get("dept_module_assignments", {}).get(dept_id, [])

def get_roles() -> list:
    """Return roles library."""
    return load_org_config().get("roles", [])

def get_clusters() -> list:
    """Return cluster definitions."""
    return load_org_config().get("clusters", [])

def save_org_config(updated: dict):
    """Persist updated org config back to disk."""
    import datetime
    updated["_last_modified"] = str(datetime.date.today())
    _CFG_PATH.write_text(json.dumps(updated, indent=2, ensure_ascii=False))
    load_org_config.clear()  # bust the cache

def update_threshold(key: str, value):
    """Update a single threshold and save."""
    org = load_org_config()
    org.setdefault("thresholds", {})[key] = value
    save_org_config(org)


# ──────────────────────────────────────────────────────────────────
# v10.220 — Tenant identity helpers
# ──────────────────────────────────────────────────────────────────
# These are the canonical readers for tenant-specific identity values.
# Pages must call these helpers instead of hardcoding strings like
# "Ecobank", "KES", "CBK", "FLEXCUBE", "KRA", "Kenya".
#
# Audit gate G162 (v10.219) ratchets the count of hardcoded tenant
# strings; the count may only DECREASE over time. Adding these helpers
# is the prerequisite for the v10.221+ tenant cleanup sub-campaign.
#
# Defaults reflect the current target client (Ecobank Kenya) as a
# documented fallback. Defaults take effect only when the
# corresponding key is missing from org_config.json — and the admin
# page (pages/7_admin.py "🏦 Bank identity" sub-section) already
# exposes editors for all of them.
#
# Per master prompt addendum Rule N1, this file is FOUNDATIONAL and
# G162-exempt — the default values here are the canonical fallbacks,
# not drift.
# ──────────────────────────────────────────────────────────────────

def bank_name() -> str:
    """Return the configured bank name. e.g. 'Ecobank Kenya'."""
    return load_org_config().get("bank_name") or "[Bank Name]"


def app_name() -> str:
    """Return the configured platform/app display name."""
    return load_org_config().get("app_name") or "EKE MIS 360"


def bank_code() -> str:
    """Return short bank code used for account number prefixes."""
    return load_org_config().get("bank_code") or ""


def currency() -> str:
    """Return ISO currency code. e.g. 'KES'."""
    return load_org_config().get("currency") or "USD"


def currency_symbol() -> str:
    """Return display currency symbol. e.g. 'KES' or 'KSh'."""
    org = load_org_config()
    # Prefer explicit symbol; fall back to ISO code if missing
    return org.get("currency_symbol") or org.get("currency") or "$"


def country() -> str:
    """Return country of operation. e.g. 'Kenya'."""
    return load_org_config().get("country") or ""


def regulator() -> str:
    """Return prudential regulator short code. e.g. 'CBK'.

    Added in v10.220 alongside the admin Tenant Identity card.
    Pages displaying compliance text should use regulator() instead
    of hardcoding 'CBK'.
    """
    return load_org_config().get("regulator") or "[Regulator]"


def regulator_full() -> str:
    """Return regulator long-form name. e.g. 'Central Bank of Kenya'."""
    return load_org_config().get("regulator_full") or regulator()


def core_banking_system() -> str:
    """Return core banking system name. e.g. 'Oracle FLEXCUBE v12'.

    Added in v10.220. Pages with CBS integration captions should
    use core_banking_system() instead of hardcoding 'FLEXCUBE'.
    """
    return load_org_config().get("cbs_name") or "[CBS]"


def tax_authority() -> str:
    """Return tax authority short code. e.g. 'KRA'.

    Added in v10.220. Tax compliance pages should use tax_authority()
    instead of hardcoding 'KRA'.
    """
    return load_org_config().get("tax_authority") or "[Tax Authority]"


def fmt_money(amount, *, with_currency: bool = True,
                scale: str = "M", decimals: int = 1) -> str:
    """Format a monetary amount with the configured currency symbol.

    Args:
      amount: numeric value (assumed in raw units, e.g. 1_500_000_000).
      with_currency: prefix with currency symbol if True.
      scale: 'raw' | 'K' | 'M' | 'B' — divisor 1, 1e3, 1e6, 1e9.
      decimals: decimal places for non-raw scales.

    Returns: formatted string. Examples:
      fmt_money(1_500_000_000)              → "KES 1500.0M"
      fmt_money(1_500_000_000, scale="B")    → "KES 1.5B"
      fmt_money(450, scale="raw", with_currency=False) → "450"
    """
    try:
        v = float(amount or 0)
    except (TypeError, ValueError):
        return str(amount)
    div = {"raw": 1, "K": 1e3, "M": 1e6, "B": 1e9}.get(scale, 1)
    scaled = v / div
    if scale == "raw":
        body = f"{int(scaled):,}"
    else:
        body = f"{scaled:.{decimals}f}{scale}"
    return f"{currency_symbol()} {body}" if with_currency else body

def update_dept_modules(dept_id: str, module_keys: list):
    """Update module assignments for a department."""
    org = load_org_config()
    org.setdefault("dept_module_assignments", {})[dept_id] = module_keys
    save_org_config(org)
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

    Default is the verbatim Ecobank deployment text. Admins can
    override per-tenant via 'ip_notice' key in org_config.json.
    """
    return load_org_config().get("ip_notice") or _DEFAULT_IP_NOTICE