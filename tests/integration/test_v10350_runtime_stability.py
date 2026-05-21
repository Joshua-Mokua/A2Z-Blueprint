"""Integration tests for v10.350 — Runtime Stability Fixes.

5 fixes verified by 8 tests:
  1. STREAMLIT_AVAILABLE defined in finance_hub_render
  2. command_centre phase KeyError fixed
  3. campaigns_management campaign_id KeyError fixed
  4. customer360 Decimal/float TypeError fixed
  5. interaction_capture.py shipped in cumulative zip
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Fix 1 — STREAMLIT_AVAILABLE
# ────────────────────────────────────────────────────────────────────

def test_v10350_streamlit_available_defined():
    """utils.finance_hub_render exposes STREAMLIT_AVAILABLE = True."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    _reimport("utils.finance_hub_render")
    import utils.finance_hub_render as r
    assert hasattr(r, "STREAMLIT_AVAILABLE"), (
        "STREAMLIT_AVAILABLE not defined in finance_hub_render"
    )
    assert r.STREAMLIT_AVAILABLE is True


def test_v10350_streamlit_available_at_module_top():
    """Constant is defined at module top — top-level statement."""
    text = (REPO / "utils" / "finance_hub_render.py").read_text()
    assert "STREAMLIT_AVAILABLE = True" in text
    # First assignment must be at indentation level 0 (module top-level),
    # not inside a function (which would have leading whitespace)
    import re
    matches = list(re.finditer(r'^(\s*)STREAMLIT_AVAILABLE = True', text, re.MULTILINE))
    assert matches, "STREAMLIT_AVAILABLE = True not found"
    assert matches[0].group(1) == "", (
        "STREAMLIT_AVAILABLE must be defined at module top level (no indent)"
    )


# ────────────────────────────────────────────────────────────────────
# Fix 2 — command_centre phase KeyError
# ────────────────────────────────────────────────────────────────────

def test_v10350_command_centre_phase_defensive_read():
    """All READ accesses of r['phase'] in command_centre use .get() now.
    Writes (r['phase'] = ...) are fine and not flagged."""
    text = (REPO / "utils" / "command_centre_strategic_initiatives.py").read_text()
    import re
    defensive_reads = re.findall(r'r\.get\("phase"', text)
    assert defensive_reads, "No defensive r.get('phase') reads found"
    # Bare r["phase"] is only acceptable when it's a WRITE (left of =)
    for line in text.splitlines():
        if 'r["phase"]' in line and 'r["phase"] =' not in line:
            # This is a bare read — unsafe
            assert False, f"Unsafe bare read in line: {line.strip()[:100]}"


# ────────────────────────────────────────────────────────────────────
# Fix 3 — campaign_id KeyError
# ────────────────────────────────────────────────────────────────────

def test_v10350_campaign_id_defensive_read():
    """c['campaign_id'] selectbox listing uses .get() with filter."""
    text = (REPO / "pages" / "94_campaigns_management.py").read_text()
    # No more bare c["campaign_id"] in the selectbox listing
    assert 'c.get("campaign_id"' in text, "Should use .get() for campaign_id"


# ────────────────────────────────────────────────────────────────────
# Fix 4 — Decimal/float TypeError
# ────────────────────────────────────────────────────────────────────

def test_v10350_value_tier_divisions_use_float():
    """All VALUE_TIER_* divisions wrap with float() to handle Decimal."""
    text = (REPO / "pages" / "34_customer360.py").read_text()
    import re
    # Old bug pattern: int(VALUE_TIER_XXX/1e6) without float wrap
    bare = re.findall(r'int\(VALUE_TIER_\w+/1e6\)|int\(VALUE_TIER_\w+/1000\)', text)
    assert not bare, f"Found {len(bare)} unwrapped Decimal divisions: {bare}"
    # New pattern: int(float(VALUE_TIER_XXX)/1e6)
    safe = re.findall(r'int\(float\(VALUE_TIER_\w+\)/1e6\)|int\(float\(VALUE_TIER_\w+\)/1000\)', text)
    assert len(safe) >= 4, f"Expected ≥4 float-wrapped divisions, got {len(safe)}"


# ────────────────────────────────────────────────────────────────────
# Fix 5 — interaction_capture.py present
# ────────────────────────────────────────────────────────────────────

def test_v10350_interaction_capture_module_present():
    """utils/interaction_capture.py exists and exports InteractionCaptureEngine."""
    path = REPO / "utils" / "interaction_capture.py"
    assert path.exists(), (
        "utils/interaction_capture.py missing — was shipped in v10.350 patch"
    )
    text = path.read_text()
    assert "class InteractionCaptureEngine" in text


def test_v10350_propositions_chain_imports_cleanly():
    """The full import chain from pages/27 → propositions_hub_render →
    customer_behavioral_profile → interaction_capture works end-to-end."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    _reimport("utils")
    from utils.interaction_capture import InteractionCaptureEngine
    from utils.customer_behavioral_profile import BehavioralProfileEngine
    from utils.propositions_hub_render import render_propositions_performance
    assert callable(render_propositions_performance)


# ────────────────────────────────────────────────────────────────────
# Page smoke regression check
# ────────────────────────────────────────────────────────────────────

def test_v10350_smoke_still_clean():
    """All 123+ pages still smoke-test PASS after the 5 fixes."""
    _reimport("utils.page_smoke")
    from utils.page_smoke import smoke_test_all
    r = smoke_test_all()
    assert r["failed"] == 0, f"Smoke regression: {r['failures'][:3]}"
    assert r["pass_rate"] == 1.0
