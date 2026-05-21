"""scripts/docgen/_honest_section.py — Honest Scope generation (v8.13).

Per docs/A2Z_LIVING_DOCS_PLAN.md Part 3 Rule 3 + Part 9 statement #3,
every rendered artifact ends with a section titled "What this document
does not claim." This module produces that content from the registry
dict + sales-content JSONs.

This is mandatory. Never edited out. Never minimised.
"""
from __future__ import annotations

from typing import Dict, List, Any


def collect_honest_scope_lines(registry: Dict[str, Any]) -> List[str]:
    """Aggregate honest-scope statements across the 6 sales-content JSONs.

    Returns a flat list of bullet-point text suitable for any rendered
    artifact's mandatory "What this document does not claim" section.
    """
    lines: List[str] = []
    sales_content = registry.get("sales_content", {})

    # Top-level honest_scope blocks
    for content_key, content in sales_content.items():
        if isinstance(content, dict) and "honest_scope" in content:
            scope = content["honest_scope"]
            if isinstance(scope, list):
                for item in scope:
                    if isinstance(item, str):
                        lines.append(item)

    # Per-entry honest_scope blocks (gap_analysis, security_architecture,
    # competitive_positioning use these inline)
    for content_key, content in sales_content.items():
        if not isinstance(content, dict):
            continue
        # Walk known nested structures
        for nested_key in ("gaps", "what_a2z_is_genuinely_distinctive_about",
                            "alternatives_a2z_does_not_attempt_to_replace"):
            if nested_key in content and isinstance(content[nested_key], list):
                for entry in content[nested_key]:
                    if isinstance(entry, dict) and "honest_scope" in entry:
                        scope = entry["honest_scope"]
                        if isinstance(scope, str):
                            lines.append(scope)

    # De-duplicate while preserving order
    seen = set()
    unique = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return unique


def collect_roadmap_callouts(registry: Dict[str, Any]) -> List[str]:
    """Pull explicit roadmap items from sales content (status='roadmap')."""
    callouts: List[str] = []
    sales_content = registry.get("sales_content", {})

    # gap_analysis
    gaps = sales_content.get("gap_analysis", {}).get("gaps", [])
    for g in gaps:
        if isinstance(g, dict):
            status = g.get("solution_status", "")
            if status == "roadmap":
                callouts.append(
                    f"{g.get('category', 'feature').upper()}: "
                    f"{g.get('a2z_solution', 'unknown')} — roadmap")

    # integrations_roadmap (specifically lists status: roadmap items)
    integ = sales_content.get("integrations_roadmap", {})
    for category in ("core_banking", "credit_bureaus", "mobile_money",
                      "payment_networks", "hris", "crm", "gl_erp"):
        cat_data = integ.get(category, {})
        if isinstance(cat_data, dict):
            for item_name, item_data in cat_data.items():
                if isinstance(item_data, dict) and item_data.get("status") == "roadmap":
                    callouts.append(
                        f"{category}/{item_name}: roadmap")

    return callouts


def standard_disclaimer_paragraph() -> str:
    """The mandatory disclaimer paragraph at the head of every Honest Scope section."""
    return (
        "This artifact is rendered from registries that the codebase audits on "
        "every build. Numbers that appear here trace to a registry path; if a "
        "future build changes the registry, the next regeneration of this "
        "artifact will reflect the change. To verify the platform's current "
        "state, run python scripts/audit.py. The list below enumerates what "
        "this artifact deliberately does NOT claim — features that are roadmap "
        "rather than shipped, integrations that are designed but not deployed, "
        "outcomes that are projections rather than measurements."
    )


def section_title() -> str:
    """The mandatory section title."""
    return "What this document does not claim"
