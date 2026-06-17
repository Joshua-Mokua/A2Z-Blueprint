"""utils/api_branding.py — Branding API for React SPA.

v10.495 — Exposes tenant identity + brand colors + IP notice as a
single JSON endpoint for the React frontend.

The React SPA fetches GET /api/branding once on app mount, populates
a BrandingContext, and renders bank-correct identity throughout.
This enables multi-tenant deployment: change org_config.json,
restart, and the React UI reflects the new tenant without code change.

This endpoint is PUBLIC (no JWT required) because the login page
itself needs branding before authentication. It returns NO sensitive
data — only display values that would appear on the login screen
anyway (bank name, brand colors, regulator name, IP notice text).

PATTERN: Mirrors utils/api_cascade.py, utils/api_strategy.py etc.
Mounted in utils/api.py via app.include_router(branding_router).
"""

from fastapi import APIRouter

from utils.config import (
    bank_name, app_name, currency, currency_symbol, country,
    regulator, regulator_full, core_banking_system, tax_authority,
    brand_primary_hex, brand_secondary_hex, brand_accent_hex,
    ip_notice,
)


router = APIRouter(prefix="/api", tags=["branding"])


@router.get("/branding")
def get_branding() -> dict:
    """Return the current tenant's branding identity.

    Response shape (stable contract for React SPA):
      {
        "bank_name": str,            e.g. "Ecobank Kenya"
        "app_name": str,             e.g. "A2Z Blueprint"
        "currency": str,             e.g. "KES"
        "currency_symbol": str,      e.g. "KES" or "KSh"
        "country": str,              e.g. "Kenya"
        "regulator": str,            e.g. "CBK"
        "regulator_full": str,       e.g. "Central Bank of Kenya"
        "core_banking_system": str,  e.g. "Oracle FLEXCUBE v12"
        "tax_authority": str,        e.g. "KRA"
        "brand": {
          "primary": str (hex),      e.g. "#1797ce"
          "secondary": str (hex),    e.g. "#0e2440"
          "accent": str (hex)        e.g. "#ffd200"
        },
        "ip_notice": str             verbatim legal text
      }

    No auth required. Cacheable for 30 seconds (matches
    load_org_config()'s @st.cache_data ttl in utils/config.py).
    """
    return {
        "bank_name": bank_name(),
        "app_name": app_name(),
        "currency": currency(),
        "currency_symbol": currency_symbol(),
        "country": country(),
        "regulator": regulator(),
        "regulator_full": "",          # removed from UI/branding (per Josh)
        "core_banking_system": "",     # removed from UI/branding (per Josh)
        "tax_authority": tax_authority(),
        "brand": {
            "primary": brand_primary_hex(),
            "secondary": brand_secondary_hex(),
            "accent": brand_accent_hex(),
        },
        "ip_notice": ip_notice(),
    }
