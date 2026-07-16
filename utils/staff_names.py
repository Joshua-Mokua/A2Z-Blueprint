"""Derived staff display names — one place, so every surface agrees.

A person's legal ``full_name`` (e.g. "Rabecca Mueni Mbithi") is kept intact as the
record of truth, but is rarely what we show:

    display_name    first name only            "Rabecca"          -> UI everywhere
    analytics_name  first + last               "Rabecca Mbithi"   -> scorecards / analytics
    full_name       legal, unchanged           "Rabecca Mueni..." -> stored, rarely shown

Anyone can set a PREFERRED name via admin (the MD drops "Mueni", Joshua drops
"Onyancha", Christine drops "Anyango"). A preferred name, when present, WINS over the
derived analytics name, and its first token becomes the display name. Preferred names
live in the user's ``metadata`` JSONB under "preferred_name", so no schema change and
the staff projection carries them across.

When the AD/email extract lands, bulk-populate preferred_name from each person's
domain-chosen pair — same field, no rework.
"""
from __future__ import annotations


def _tokens(name: str) -> list:
    return [t for t in str(name or "").replace(",", " ").split() if t]


def display_name(full_name: str, preferred: str = "") -> str:
    """The single name shown in the UI. Preferred first token if set, else first name."""
    pref = _tokens(preferred)
    if pref:
        return pref[0]
    toks = _tokens(full_name)
    return toks[0] if toks else str(full_name or "").strip()


def analytics_name(full_name: str, preferred: str = "") -> str:
    """Two-name form for analytics. Preferred (verbatim) if set, else first + last."""
    if str(preferred or "").strip():
        return str(preferred).strip()
    toks = _tokens(full_name)
    if len(toks) >= 2:
        return f"{toks[0]} {toks[-1]}"
    return toks[0] if toks else str(full_name or "").strip()


def preferred_of(rec: dict) -> str:
    """Read preferred_name from a user record's metadata (dict or JSON string)."""
    if not isinstance(rec, dict):
        return ""
    md = rec.get("metadata")
    if isinstance(md, str):
        try:
            import json
            md = json.loads(md or "{}")
        except Exception:
            md = {}
    if isinstance(md, dict):
        p = md.get("preferred_name")
        if p:
            return str(p).strip()
    # also accept a top-level preferred_name (some call sites flatten it)
    return str(rec.get("preferred_name") or "").strip()


def names_for(rec: dict) -> dict:
    """Given a user/staff record, return {display_name, analytics_name, full_name}."""
    full = str(rec.get("full_name") or rec.get("Staff Name") or "")
    pref = preferred_of(rec)
    return {
        "full_name": full,
        "display_name": display_name(full, pref),
        "analytics_name": analytics_name(full, pref),
        "preferred_name": pref,
    }
