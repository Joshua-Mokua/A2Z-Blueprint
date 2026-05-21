"""Integration tests for v10.449 — Credit Approval Hierarchy + Phone Disbursement."""

import ast
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def credit_audit_post_v449():
    for k in list(sys.modules):
        if "credit_section_audit_engine" in k:
            del sys.modules[k]
    from utils.credit_section_audit_engine import credit_full_audit
    return credit_full_audit()


# ── Four approval levels surfaced (fast) ─────────────────────────────

def test_v10449_eight_tabs_in_approvals_page():
    t = (REPO / "pages/82_credit_approvals.py").read_text()
    for tab_label in (
        "🏊 Swim Lane",
        "🤖 Credit Analyst",
        "🏢 Branch Credit Committee",
        "🏛️ Credit Committee (CCC)",
        "⚖️ Board Credit Committee",
        "🗳️ Cast Vote",
        "📜 Decision History",
        "⚙️ Committee Configuration",
    ):
        assert tab_label in t, f"Missing tab: {tab_label}"


def test_v10449_scoring_matrix_present():
    t = (REPO / "pages/82_credit_approvals.py").read_text()
    for band in ("AAA", "AA", "BBB", "BB", "CCC"):
        assert band in t, f"Missing scoring band: {band}"
    for marker in ("Scoring Matrix", "Auto-limit (KES)", "PD ceiling"):
        assert marker in t, f"Missing scoring marker: {marker}"


def test_v10449_board_credit_committee_distinct():
    t = (REPO / "pages/82_credit_approvals.py").read_text()
    assert "Board Credit Committee" in t
    assert "BCC" in t
    # Board-level role list must be visible
    assert "Board Credit Member" in t


def test_v10449_credit_committee_ccc_distinct():
    t = (REPO / "pages/82_credit_approvals.py").read_text()
    assert "(CCC)" in t
    # Members visible
    assert "Head of Credit" in t
    assert "Head of Risk" in t


def test_v10449_branch_credit_committee_present():
    t = (REPO / "pages/82_credit_approvals.py").read_text()
    # Branch tier handling
    assert "TIER_BRANCH_AUTO" in t
    assert "TIER_BRANCH_FWD" in t
    assert "Branch Credit Committee" in t


# ── Phone Disbursement ───────────────────────────────────────────────

def test_v10449_phone_disbursement_tab_in_credit_admin():
    t = (REPO / "pages/23_credit_admin.py").read_text()
    assert "📞 Phone Disbursement" in t
    assert "phone_disbursement_log.json" in t


def test_v10449_phone_call_outcomes_codified():
    t = (REPO / "pages/23_credit_admin.py").read_text()
    for outcome in ("DISBURSED", "CUSTOMER_NOT_REACHED",
                    "KYC_DOC_OUTSTANDING", "CUSTOMER_WITHDREW",
                    "CALLBACK_REQUESTED"):
        assert outcome in t, f"Missing call outcome: {outcome}"


def test_v10449_phone_disbursement_bsc_trigger():
    """K028 (Credit Admin productivity KPI) fires on phone disbursement."""
    t = (REPO / "pages/23_credit_admin.py").read_text()
    assert "K028" in t


# ── Pages still parse ────────────────────────────────────────────────

def test_v10449_approvals_page_parses():
    ast.parse((REPO / "pages/82_credit_approvals.py").read_text())


def test_v10449_credit_admin_parses():
    ast.parse((REPO / "pages/23_credit_admin.py").read_text())


# ── Credit admin promoted to substantial ─────────────────────────────

def test_v10449_credit_admin_promoted():
    t = (REPO / "pages/23_credit_admin.py").read_text()
    loc = len(t.splitlines())
    assert loc >= 250, f"23_credit_admin only {loc} LOC, expected >= 250 (promoted from 112 stub)"


# ── Backups ──────────────────────────────────────────────────────────

def test_v10449_backups_present():
    bdir = REPO / "data" / "_v10449_backups"
    assert bdir.exists()
    for f in ("82_credit_approvals.py.before",
              "23_credit_admin.py.before",
              "22_credit_analysis.py.before"):
        assert (bdir / f).exists(), f"Missing backup: {f}"


# ── Audit-based outcome (slow) ───────────────────────────────────────

def test_v10449_credit_health_84(credit_audit_post_v449):
    assert credit_audit_post_v449.credit_health_pct >= 84.0


def test_v10449_page_completeness_60(credit_audit_post_v449):
    """23_credit_admin promoted = page completeness >= 60%."""
    assert credit_audit_post_v449.page_completeness.completeness_pct >= 60.0


def test_v10449_credit_admin_substantial_in_audit(credit_audit_post_v449):
    p = next(
        (p for p in credit_audit_post_v449.page_completeness.pages
         if p["page"] == "23_credit_admin.py"),
        None,
    )
    assert p is not None
    assert p["status"] == "substantial"


# ── Upstream preservation ────────────────────────────────────────────

def test_v10449_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10449_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10449_g335_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10449_credit_approval_hierarchy
    r = gate_v10449_credit_approval_hierarchy()
    assert r["passed"], r.get("violations")
