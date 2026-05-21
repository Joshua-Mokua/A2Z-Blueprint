"""utils/smart_alerts_i18n.py — i18n scaffold for customer alerts (v8.26).

Closes v8.6 retrospective ack #12 (multi-language alerts) STRUCTURALLY.
This module provides:
    - Translation-string registry: TRANSLATIONS dict mapping locale → key → string
    - Locale detection: get_locale_for_customer(customer_id) — placeholder
    - Translation lookup: t(key, locale, **format_args) — falls back to English
    - Public accessors: get_supported_locales(), get_translation_keys()

What this batch ships (the scaffold):
    - 3 locales scaffolded: en (complete), fr (placeholder), sw (placeholder)
    - 8 translation keys covering the headline + body templates used by
      smart_alerts.py
    - Fallback to English when a translation is missing
    - Format-string substitution support

What this batch does NOT ship (the operational work):
    - Native-speaker French and Swahili translations (requires translator review)
    - Per-customer locale detection from customer profile (requires schema link)
    - Locale-aware delivery channel selection (some channels may not support
      certain scripts)

This is the structural close — the translation system exists and is
testable. Filling in real translations is operational work that happens
outside the codebase (translator engagement → review → JSON update).
"""
from __future__ import annotations
from typing import Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# Translation registry
# ════════════════════════════════════════════════════════════════════

# Format placeholders in translation strings:
#   {channel} — channel type (ATM, USSD, MOBILE_APP, etc.)
#   {location} — affected location (branch / region / "system-wide")
#   {severity} — DEGRADED / OUTAGE / SLA_BREACH
#   {affected} — estimated affected customers (numeric, not formatted)

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "headline_outage":
            "{channel} outage detected at {location}",
        "headline_degraded":
            "{channel} performance degraded at {location}",
        "headline_sla_breach":
            "{channel} SLA breach at {location}",
        "headline_default":
            "{channel} alert at {location}",
        "body_default":
            "Severity: {severity}. Estimated affected customers: {affected}. "
            "Engineering team is investigating.",
        "ack_button_label":
            "Acknowledge",
        "tier_urgent_prefix":
            "[URGENT]",
        "tier_high_prefix":
            "[HIGH]",
    },
    "fr": {
        # Placeholder French — needs native-speaker review
        "headline_outage":
            "Panne {channel} détectée à {location}",
        "headline_degraded":
            "Performance {channel} dégradée à {location}",
        "headline_sla_breach":
            "Violation SLA {channel} à {location}",
        # The remaining keys fall back to English via t() — placeholder
        # marker keeping the dict structure consistent.
    },
    "sw": {
        # Placeholder Swahili — needs native-speaker review
        "headline_outage":
            "Hitilafu ya {channel} imegunduliwa katika {location}",
        "headline_degraded":
            "Utendaji wa {channel} umeshuka katika {location}",
        # Other keys: English fallback
    },
}


SUPPORTED_LOCALES = ["en", "fr", "sw"]
DEFAULT_LOCALE = "en"


def get_supported_locales() -> List[str]:
    """v8.26 — list locales with at least scaffolded translations."""
    return list(SUPPORTED_LOCALES)


def get_translation_keys() -> List[str]:
    """v8.26 — list all translation keys (sourced from English completeness)."""
    return list(TRANSLATIONS["en"].keys())


def t(key: str, locale: str = DEFAULT_LOCALE, **format_args: object) -> str:
    """Translate a key into the requested locale.

    Falls back through: requested locale → English → key itself (so
    missing keys are visible in output, not silently empty).

    Format args are substituted via str.format(); missing args remain
    as `{name}` placeholders rather than raising — defensive against
    incomplete caller data.
    """
    locale_dict = TRANSLATIONS.get(locale, {})
    template = locale_dict.get(key)
    if template is None:
        # Fall back to English
        template = TRANSLATIONS[DEFAULT_LOCALE].get(key)
    if template is None:
        # Final fallback: visible key
        return f"[{key}]"
    try:
        return template.format(**format_args)
    except (KeyError, IndexError):
        # Missing format arg — return template unsubstituted rather than crashing
        return template


def get_locale_for_customer(
    customer_id: Optional[str] = None,
    fallback: str = DEFAULT_LOCALE,
) -> str:
    """v8.26 — placeholder for per-customer locale detection.

    In production, this would look up the customer's preferred locale from
    their profile (FLEXCUBE customer record + override field). v8.26 ships
    the function signature + fallback behavior; the actual lookup is
    operational work tied to customer profile schema.

    Args:
        customer_id: customer identifier (CIF, account, etc.); not used
            in v8.26 — placeholder for future implementation
        fallback: locale to return when lookup fails or customer_id is None

    Returns: locale code (currently always returns fallback)
    """
    # v8.26: scaffold only — always return fallback.
    # Future v9.x: query customer profile, return preferred_locale.
    return fallback


def is_translation_complete(locale: str) -> bool:
    """v8.26 — return True if locale has translations for ALL keys.

    Useful for admin UIs that want to show "100% translated" badges or
    flag locales that need translator engagement.
    """
    if locale not in TRANSLATIONS:
        return False
    en_keys = set(TRANSLATIONS[DEFAULT_LOCALE].keys())
    locale_keys = set(TRANSLATIONS[locale].keys())
    return en_keys.issubset(locale_keys)


def get_translation_completeness() -> Dict[str, Dict[str, object]]:
    """v8.26 — diagnostic: return per-locale translation completeness.

    Returns dict mapping locale → {translated_keys, total_keys,
    completeness_pct, complete}. Used by admin UI to show which locales
    need translator work.
    """
    en_keys = set(TRANSLATIONS[DEFAULT_LOCALE].keys())
    total = len(en_keys)
    out: Dict[str, Dict[str, object]] = {}
    for locale, locale_dict in TRANSLATIONS.items():
        translated = len(set(locale_dict.keys()) & en_keys)
        pct = round(100.0 * translated / total, 1) if total > 0 else 0.0
        out[locale] = {
            "translated_keys": translated,
            "total_keys": total,
            "completeness_pct": pct,
            "complete": translated == total,
        }
    return out
