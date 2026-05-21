"""
v10.351 — Convert the 16 consolidated originals to thin redirects.

Each original page is currently a thin wrapper (~26 lines) that:
  1. Calls require_access(...)
  2. Imports a render_* function from a utils/*_hub_render module
  3. Calls render_*(actor)

After this script runs, each becomes a thin REDIRECT:
  1. Still calls require_access(...) — preserves access gating
  2. Shows a clear redirect banner pointing to the unified hub
  3. Provides st.page_link() to the hub (Streamlit native navigation)
  4. STILL calls the render function below — backward-compat for bookmarks

The redirect signal makes the unified hub discoverable; the render call
keeps existing bookmarks working. Users see a notice + button to the hub,
then the same content they'd see on the hub anyway.

Run from repo root:  python scripts/v10351_apply_redirects.py
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Map: original page name → (hub page, hub display name, area description)
REDIRECTS = {
    # Live Cockpits → 115
    "109_cims_live.py":              ("pages/115_live_cockpits.py", "Live Cockpits", "CIMS"),
    "110_treasury_live.py":          ("pages/115_live_cockpits.py", "Live Cockpits", "Treasury"),
    "111_credit_live.py":            ("pages/115_live_cockpits.py", "Live Cockpits", "Credit"),
    "112_compliance_live.py":        ("pages/115_live_cockpits.py", "Live Cockpits", "Compliance"),

    # Finance Hub → 116
    "9_sbu.py":                      ("pages/116_finance_hub.py",   "Finance Hub", "SBU Performance"),
    "10_opex.py":                    ("pages/116_finance_hub.py",   "Finance Hub", "OpEx & CIR"),
    "52_mgmt_accounts.py":           ("pages/116_finance_hub.py",   "Finance Hub", "Management Accounts"),
    "114_sbu_drilldown.py":          ("pages/116_finance_hub.py",   "Finance Hub", "SBU Drilldown"),

    # Propositions Hub → 117
    "27_propositions.py":            ("pages/117_propositions_hub.py", "Propositions Hub", "Performance"),
    "92_propositions_workbench.py":  ("pages/117_propositions_hub.py", "Propositions Hub", "Workbench"),

    # Competitor Hub → 118
    "11_competitor.py":              ("pages/118_competitor_hub.py", "Competitor Hub", "Market Overview"),
    "93_competitor_intelligence.py": ("pages/118_competitor_hub.py", "Competitor Hub", "Workbench"),

    # Platform Hub → 119
    "91_systems_view.py":            ("pages/119_platform_hub.py",  "Platform Hub", "Systems View"),
    "96_it_digital_pt1.py":          ("pages/119_platform_hub.py",  "Platform Hub", "IT Digital Pt 1"),
    "97_it_digital_pt2.py":          ("pages/119_platform_hub.py",  "Platform Hub", "IT Digital Pt 2"),
    "98_platform_health.py":         ("pages/119_platform_hub.py",  "Platform Hub", "Platform Health"),
}

# The redirect banner template. Inserted between require_access and the
# render function call.
BANNER_TEMPLATE = '''
# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of {hub_display}** — the unified entry point "
    "consolidates {area} alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("{hub_path}", label="Open {hub_display} →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open {hub_display} →]({hub_path})")
st.markdown("---")
'''


def apply_redirect(page_name: str, hub_path: str, hub_display: str, area: str) -> None:
    """Inject the redirect banner into one thin wrapper. Idempotent —
    if the banner is already present, do nothing."""
    path = REPO / "pages" / page_name
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}")
    text = path.read_text()

    # Idempotency check
    if "v10.351 — Thin redirect" in text:
        return  # already converted

    # The thin wrappers all have this shape:
    #   from pages._access import require_access
    #   require_access("...")           ← anchor
    #   from utils.<hub>_render import render_*
    #   ...
    #   actor = st.session_state.get(...).get(...)
    #   render_*(actor)
    #
    # Insert the banner AFTER the `from utils.<hub>_render import ...`
    # block but BEFORE the actor + render call.

    # Find the render import line
    import re
    render_import = re.search(
        r"(from utils\.[a-z_]+_render import [\w, ]+\n)",
        text,
    )
    if not render_import:
        raise RuntimeError(f"No render import found in {page_name}")

    insert_pos = render_import.end()

    banner = BANNER_TEMPLATE.format(
        hub_display=hub_display,
        area=area,
        hub_path=hub_path,
    )

    new_text = text[:insert_pos] + "\n" + banner + text[insert_pos:]
    path.write_text(new_text)


def main() -> None:
    print(f"Applying v10.351 redirects to {len(REDIRECTS)} pages...")
    for page_name, (hub_path, hub_display, area) in REDIRECTS.items():
        try:
            apply_redirect(page_name, hub_path, hub_display, area)
            new_lines = len((REPO / "pages" / page_name).read_text().splitlines())
            print(f"  ✓ {page_name:35s}  → {hub_display:20s}  ({new_lines} lines)")
        except Exception as exc:
            print(f"  ✗ {page_name}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
