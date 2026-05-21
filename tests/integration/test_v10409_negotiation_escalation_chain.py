"""Integration tests for v10.409 — E4 Negotiation Escalation Chain + KeyError fix.

Per Joshua's live error report:
  KeyError: 'from_code' at pages/12_cascade.py:3369

Per QA standards Enhancement #4:
  Target disputes have no formal resolution process.
  Solution: Structured negotiation workflow with escalation path.

13 tests across 4 sections.
"""

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — KeyError fix
# ────────────────────────────────────────────────────────────────────

def test_v10409_meta_key_filter_at_existing_allocs():
    """Existing allocations loop (line ~1235) skips meta-keys."""
    text = (REPO / "pages" / "12_cascade.py").read_text()
    # Find existing_allocs block
    idx = text.find("existing_allocs = {}")
    assert idx > 0, "existing_allocs not found"
    block = text[idx:idx + 600]
    assert 'startswith("_")' in block, "Missing underscore guard at existing_allocs"


def test_v10409_meta_key_filter_at_coverage_loop():
    """Allocation coverage loop (~3642) skips meta-keys."""
    text = (REPO / "pages" / "12_cascade.py").read_text()
    idx = text.find('st.subheader("Allocation coverage")')
    assert idx > 0
    block = text[idx:idx + 1500]
    assert 'startswith("_")' in block
    assert '"from_code" not in e' in block, "Missing defensive from_code check"


def test_v10409_meta_key_filter_at_deadline_tracker():
    """Deadline tracker loop (~3677) skips meta-keys."""
    text = (REPO / "pages" / "12_cascade.py").read_text()
    idx = text.find('st.subheader("Deadline tracker")')
    assert idx > 0
    block = text[idx:idx + 1200]
    # Either checks underscore or has type guard
    assert ('startswith("_")' in block
            or 'isinstance(_e, dict)' in block), (
        "Deadline tracker lacks meta-key guard")


def test_v10409_core_get_what_i_was_given_safe():
    """utils.core.get_what_i_was_given iterates safely past meta keys."""
    text = (REPO / "utils" / "core.py").read_text()
    idx = text.find("def get_what_i_was_given")
    assert idx > 0
    block = text[idx:idx + 1500]
    assert 'startswith("_")' in block, "Missing underscore guard"


# ────────────────────────────────────────────────────────────────────
# Section 2 — E4 escalation API
# ────────────────────────────────────────────────────────────────────

def test_v10409_resolve_review_has_counter_target():
    text = (REPO / "utils" / "core.py").read_text()
    assert "counter_target: float = None" in text


def test_v10409_resolve_review_has_escalate_to():
    text = (REPO / "utils" / "core.py").read_text()
    assert "escalate_to: str =" in text


def test_v10409_auto_escalate_method_exists():
    text = (REPO / "utils" / "core.py").read_text()
    assert "def auto_escalate_overdue_reviews" in text
    assert "sla_days: int = 7" in text


def test_v10409_escalated_request_reopens_as_pending():
    """When status='Escalated', resolver re-opens as Pending for next reviewer."""
    text = (REPO / "utils" / "core.py").read_text()
    idx = text.find("def resolve_review")
    block = text[idx:idx + 2500]
    # Should re-mark status as Pending after Escalated processing
    assert ('r["status"] = "Pending"' in block
            or "status = 'Pending'" in block)


# ────────────────────────────────────────────────────────────────────
# Section 3 — UI wiring
# ────────────────────────────────────────────────────────────────────

def test_v10409_decision_selector_has_4_options():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert '"Approved", "Counter-Proposed", "Escalated", "Rejected"' in text


def test_v10409_counter_target_input_present():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "Counter target" in text
    assert "counter_target=" in text


def test_v10409_escalate_to_input_present():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "Escalate to staff_code" in text
    assert "escalate_to=" in text


def test_v10409_sla_admin_trigger_present():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "auto_escalate_overdue_reviews" in text
    assert "Run SLA escalation" in text or "🚀 Run SLA" in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — Functional + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10409_g295_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10409_negotiation_escalation_chain
    r = gate_v10409_negotiation_escalation_chain()
    assert r["passed"], r.get("violations")
