"""Integration tests for v10.448 — NEW Credit Approvals/Swim Lane page."""

import ast
import json
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def credit_audit_post_v448():
    for k in list(sys.modules):
        if "credit_section_audit_engine" in k:
            del sys.modules[k]
    from utils.credit_section_audit_engine import credit_full_audit
    return credit_full_audit()


# ── Page existence + structure (fast) ────────────────────────────────

def test_v10448_page_exists():
    p = REPO / "pages" / "82_credit_approvals.py"
    assert p.exists()


def test_v10448_page_substantial():
    p = REPO / "pages" / "82_credit_approvals.py"
    loc = len(p.read_text().splitlines())
    assert loc >= 400, f"Only {loc} LOC, expected >= 400 substantial"


def test_v10448_page_parses():
    ast.parse((REPO / "pages" / "82_credit_approvals.py").read_text())


def test_v10448_page_imports_credit_workflow():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    assert "from utils.credit_workflow import" in t
    for sym in (
        "CommitteeRole", "CommitteeVote", "evaluate_committee_decision",
        "determine_tier", "ALLOWED_TRANSITIONS", "ApplicationState",
        "COMMITTEE_REQUIREMENTS",
    ):
        assert sym in t, f"Missing import: {sym}"


def test_v10448_page_has_five_tabs():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    for tab in ("🏊 Swim Lane", "🏛️ Committee Queue", "🗳️ Cast Vote",
                "📜 Decision History", "⚙️ Committee Configuration"):
        assert tab in t, f"Missing tab: {tab}"


def test_v10448_page_has_access_gate():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    assert 'require_access("credit.approvals")' in t


def test_v10448_page_persists_decisions():
    """Vote tab persists to data/committee_decisions.json."""
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    assert "committee_decisions.json" in t
    assert "_save_decisions" in t


def test_v10448_page_has_bsc_trigger():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    assert "_bsc_trigger" in t
    assert "K022" in t  # Credit decision KPI


def test_v10448_manifest_registered():
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "82_credit_approvals.py" in m.get("pages", {})
    entry = m["pages"]["82_credit_approvals.py"]
    assert entry["department_primary"] == "credit"
    assert entry["module_path"] == "credit.approvals"


def test_v10448_credit_pages_now_fourteen():
    for k in list(sys.modules):
        if "credit_section_audit_engine" in k:
            del sys.modules[k]
    from utils.credit_section_audit_engine import CREDIT_PAGES, FLOW_STAGES
    assert len(CREDIT_PAGES) == 14
    assert "82_credit_approvals.py" in CREDIT_PAGES
    # FLOW_STAGES approvals now points at the page
    approvals = next(s for s in FLOW_STAGES if s["id"] == "approvals")
    assert "82_credit_approvals.py" in approvals["expected_pages"]


# ── Audit-level outcome (slow — fixture) ────────────────────────────

def test_v10448_credit_health_above_80(credit_audit_post_v448):
    assert credit_audit_post_v448.credit_health_pct >= 80.0


def test_v10448_flow_coverage_100_pct(credit_audit_post_v448):
    """All 9 flow stages now covered."""
    assert credit_audit_post_v448.flow_coverage.flow_completeness_pct == 100.0


def test_v10448_approvals_stage_not_in_gaps(credit_audit_post_v448):
    gap_ids = [g["stage_id"] for g in credit_audit_post_v448.flow_coverage.stages_with_gaps]
    assert "approvals" not in gap_ids


def test_v10448_no_critical_findings(credit_audit_post_v448):
    assert credit_audit_post_v448.severity_counts.get("critical", 0) == 0


def test_v10448_approvals_page_substantial_in_audit(credit_audit_post_v448):
    """The new page should be classified as substantial."""
    p = next(
        (p for p in credit_audit_post_v448.page_completeness.pages
         if p["page"] == "82_credit_approvals.py"),
        None,
    )
    assert p is not None
    assert p["status"] == "substantial"


# ── Upstream preservation ────────────────────────────────────────────

def test_v10448_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10448_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10448_g334_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10448_credit_approvals_page
    r = gate_v10448_credit_approvals_page()
    assert r["passed"], r.get("violations")
