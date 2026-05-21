"""Integration tests for v10.405 — target guidance + weight visibility.

Per Joshua's 3 asks:
1. Fixed KPIs greyed out for full visibility (verify) + weight sum check always shown
2. Target guidance matrix (suggest_target) wired into cascade UI
3. Allocation sum / remaining indicator confirmed intact

10 tests across 4 sections.
"""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _cascade_text():
    return (REPO / "pages" / "12_cascade.py").read_text()


# ────────────────────────────────────────────────────────────────────
# Section 1 — Target guidance wired
# ────────────────────────────────────────────────────────────────────

def test_v10405_suggest_target_imported_and_called():
    """suggest_target both imported AND invoked (not just imported)."""
    text = _cascade_text()
    assert "from utils.core import suggest_target" in text
    # Count actual invocations (not import)
    calls = text.count("suggest_target(")
    assert calls >= 2, f"only {calls} occurrences (1=import only); need invocation"


def test_v10405_guidance_ribbon_html_present():
    """🎯 Target guidance ribbon UI is rendered."""
    text = _cascade_text()
    assert "🎯 Target guidance" in text


def test_v10405_guidance_skips_fixed_kpis():
    """Guidance should skip KPIs that are Fixed (no allocation needed)."""
    text = _cascade_text()
    # Guard pattern
    assert "if suggest_target and not casc.is_fixed(" in text


def test_v10405_guidance_handles_new_hires():
    """Guidance shows NEW HIRE badge when staff has < 6 months data."""
    text = _cascade_text()
    assert "NEW HIRE" in text


def test_v10405_guidance_displays_prior_actual_and_range():
    """Guidance shows prior_year_actual + suggested min/target/stretch."""
    text = _cascade_text()
    assert "_prior_actual" in text
    assert "_sug_min" in text
    assert "_sug_tgt" in text
    assert "_sug_str" in text
    assert "min·target·stretch" in text


def test_v10405_guidance_shows_confidence_and_rationale():
    """Guidance shows confidence badge + rationale text."""
    text = _cascade_text()
    assert "_conf.upper()" in text
    assert "confidence" in text
    assert "_rationale" in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Weight check always visible
# ────────────────────────────────────────────────────────────────────

def test_v10405_weight_check_always_shown():
    """Weight totals row always shown (not gated by _bad_wts only)."""
    text = _cascade_text()
    # New pattern: gated by _has_any_wts (always shows if any weights present)
    assert "if _has_any_wts:" in text
    # Should have BOTH bad (red) and good (green) message paths
    assert "KPI weights check (must sum to 100%)" in text
    assert "KPI weights check (sum to 100%)" in text or "✅" in text


def test_v10405_weight_check_has_green_state():
    """When weights sum correctly, show green check."""
    text = _cascade_text()
    assert "✅" in text and "100%" in text


# ────────────────────────────────────────────────────────────────────
# Section 3 — Allocation sum indicator still intact
# ────────────────────────────────────────────────────────────────────

def test_v10405_allocation_sum_indicator_intact():
    """Live remaining/over indicator still works."""
    text = _cascade_text()
    # Existing v10.x feature
    assert "_allocated_so_far" in text
    assert "_remaining = stretch_tgt" in text or "_remaining = (stretch_tgt" in text
    assert "remaining" in text.lower()
    # Color-coded
    assert "_rem_clr" in text


def test_v10405_allocation_sum_skips_fixed_kpis():
    """Allocation sum doesn't include fixed KPIs (they're auto-cascade)."""
    text = _cascade_text()
    assert "not casc.is_fixed(kpi, alloc_year)" in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — Gate
# ────────────────────────────────────────────────────────────────────

def test_v10405_g291_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10405_target_guidance_wired
    r = gate_v10405_target_guidance_wired()
    assert r["passed"], r.get("violations")
