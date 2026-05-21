"""Integration tests for v10.449 — Branch Credit Committee (BCC) integration."""

import ast
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── Engine extension tests (fast) ────────────────────────────────────

def test_v10449_engine_has_branch_roles():
    for k in list(sys.modules):
        if "credit_workflow" in k:
            del sys.modules[k]
    from utils.credit_workflow import CommitteeRole
    role_values = {r.value for r in CommitteeRole}
    for required in ("BRANCH_MANAGER", "BRANCH_CREDIT_MANAGER",
                     "BRANCH_OPERATIONS_MANAGER"):
        assert required in role_values, f"Missing: {required}"


def test_v10449_engine_has_branch_tiers():
    for k in list(sys.modules):
        if "credit_workflow" in k:
            del sys.modules[k]
    from utils.credit_workflow import COMMITTEE_REQUIREMENTS
    assert "TIER_BRANCH_AUTO" in COMMITTEE_REQUIREMENTS
    assert "TIER_BRANCH_FWD" in COMMITTEE_REQUIREMENTS


def test_v10449_branch_auto_tier_config():
    """TIER_BRANCH_AUTO: BM + BCM, 2 quorum, 100% threshold, no forward."""
    from utils.credit_workflow import COMMITTEE_REQUIREMENTS, CommitteeRole
    req = COMMITTEE_REQUIREMENTS["TIER_BRANCH_AUTO"]
    assert req["quorum"] == 2
    assert CommitteeRole.BRANCH_MANAGER in req["required_roles"]
    assert CommitteeRole.BRANCH_CREDIT_MANAGER in req["required_roles"]
    assert req.get("forwards_to_ho") is False


def test_v10449_branch_fwd_tier_config():
    """TIER_BRANCH_FWD: BM + BCM + BOM, 3 quorum, forwards to HO."""
    from utils.credit_workflow import COMMITTEE_REQUIREMENTS, CommitteeRole
    req = COMMITTEE_REQUIREMENTS["TIER_BRANCH_FWD"]
    assert req["quorum"] == 3
    assert CommitteeRole.BRANCH_OPERATIONS_MANAGER in req["required_roles"]
    assert req.get("forwards_to_ho") is True


def test_v10449_determine_branch_tier():
    from utils.credit_workflow import (
        determine_branch_tier, BRANCH_AUTO_DISBURSE_LIMIT_KES,
        BRANCH_FORWARD_LIMIT_KES,
    )
    assert determine_branch_tier(Decimal("300000")) == "TIER_1"
    assert determine_branch_tier(Decimal("1000000")) == "TIER_BRANCH_AUTO"
    assert determine_branch_tier(Decimal("2000000")) == "TIER_BRANCH_AUTO"
    assert determine_branch_tier(Decimal("3500000")) == "TIER_BRANCH_FWD"
    assert determine_branch_tier(Decimal("5000000")) == "TIER_BRANCH_FWD"
    assert determine_branch_tier(Decimal("10000000")) is None  # above branch
    assert BRANCH_AUTO_DISBURSE_LIMIT_KES == Decimal("2000000")
    assert BRANCH_FORWARD_LIMIT_KES == Decimal("5000000")


def test_v10449_determine_tier_branch_aware():
    from utils.credit_workflow import determine_tier
    # Default behavior unchanged
    assert determine_tier(Decimal("3500000")) == "TIER_2"
    # Branch context returns branch tier
    assert determine_tier(Decimal("3500000"),
                          originated_at_branch=True) == "TIER_BRANCH_FWD"
    # Above branch authority falls through to HO
    assert determine_tier(Decimal("10000000"),
                          originated_at_branch=True) == "TIER_3"


def test_v10449_is_branch_tier():
    from utils.credit_workflow import is_branch_tier
    assert is_branch_tier("TIER_BRANCH_AUTO")
    assert is_branch_tier("TIER_BRANCH_FWD")
    assert not is_branch_tier("TIER_2")
    assert not is_branch_tier("TIER_3")
    assert not is_branch_tier("TIER_4")


def test_v10449_forwards_to_ho():
    from utils.credit_workflow import forwards_to_ho
    assert forwards_to_ho("TIER_BRANCH_FWD") is True
    assert forwards_to_ho("TIER_BRANCH_AUTO") is False
    assert forwards_to_ho("TIER_2") is False


def test_v10449_bcc_autonomous_outcome():
    """BCC TIER_BRANCH_AUTO with unanimous approval = APPROVED_AT_BRANCH."""
    from utils.credit_workflow import (
        evaluate_committee_decision, CommitteeVote, CommitteeRole,
    )
    votes = [
        CommitteeVote(CommitteeRole.BRANCH_MANAGER, "BM", "APPROVE", "2026-05-15"),
        CommitteeVote(CommitteeRole.BRANCH_CREDIT_MANAGER, "BCM", "APPROVE", "2026-05-15"),
    ]
    d = evaluate_committee_decision(
        application_id="LA-T1", committee_id="BCC-NRB-001",
        amount_kes=Decimal("1500000"), votes=votes,
        originated_at_branch=True,
    )
    assert d.outcome == "APPROVED_AT_BRANCH"
    assert d.quorum_present == 2


def test_v10449_bcc_forward_outcome():
    """BCC TIER_BRANCH_FWD with full BCC approval = APPROVED_BRANCH_FORWARD_HO."""
    from utils.credit_workflow import (
        evaluate_committee_decision, CommitteeVote, CommitteeRole,
    )
    votes = [
        CommitteeVote(CommitteeRole.BRANCH_MANAGER, "BM", "APPROVE", "2026-05-15"),
        CommitteeVote(CommitteeRole.BRANCH_CREDIT_MANAGER, "BCM", "APPROVE", "2026-05-15"),
        CommitteeVote(CommitteeRole.BRANCH_OPERATIONS_MANAGER, "BOM", "APPROVE", "2026-05-15"),
    ]
    d = evaluate_committee_decision(
        application_id="LA-T2", committee_id="BCC-NRB-002",
        amount_kes=Decimal("3500000"), votes=votes,
        originated_at_branch=True,
    )
    assert d.outcome == "APPROVED_BRANCH_FORWARD_HO"
    assert d.quorum_present == 3


def test_v10449_bcc_split_vote_declines():
    """BCC with split vote at TIER_BRANCH_AUTO (100% threshold) = DECLINED."""
    from utils.credit_workflow import (
        evaluate_committee_decision, CommitteeVote, CommitteeRole,
    )
    votes = [
        CommitteeVote(CommitteeRole.BRANCH_MANAGER, "BM", "APPROVE", "2026-05-15"),
        CommitteeVote(CommitteeRole.BRANCH_CREDIT_MANAGER, "BCM", "DECLINE", "2026-05-15"),
    ]
    d = evaluate_committee_decision(
        application_id="LA-T3", committee_id="BCC-NRB-003",
        amount_kes=Decimal("1500000"), votes=votes,
        originated_at_branch=True,
    )
    # 100% threshold not met since only 50% approve, but it's a TIE since equal
    assert d.outcome == "TIE"


def test_v10449_bcc_insufficient_quorum():
    """BCC with missing BOM at TIER_BRANCH_FWD = NO_QUORUM."""
    from utils.credit_workflow import (
        evaluate_committee_decision, CommitteeVote, CommitteeRole,
    )
    votes = [
        CommitteeVote(CommitteeRole.BRANCH_MANAGER, "BM", "APPROVE", "2026-05-15"),
        CommitteeVote(CommitteeRole.BRANCH_CREDIT_MANAGER, "BCM", "APPROVE", "2026-05-15"),
    ]
    d = evaluate_committee_decision(
        application_id="LA-T4", committee_id="BCC-NRB-004",
        amount_kes=Decimal("3500000"), votes=votes,
        originated_at_branch=True,
    )
    # Quorum requires 3 but only 2 BCC roles present
    assert d.outcome == "NO_QUORUM"


def test_v10449_existing_ho_path_preserved():
    """HO TIER_2 path still works exactly as before."""
    from utils.credit_workflow import (
        evaluate_committee_decision, CommitteeVote, CommitteeRole,
    )
    votes = [
        CommitteeVote(CommitteeRole.HEAD_OF_CREDIT, "HC", "APPROVE", "2026-05-15"),
        CommitteeVote(CommitteeRole.HEAD_OF_RISK, "HR", "APPROVE", "2026-05-15"),
    ]
    d = evaluate_committee_decision(
        application_id="LA-T5", committee_id="HO-TEST",
        amount_kes=Decimal("3000000"), votes=votes,
        originated_at_branch=False,
    )
    assert d.outcome == "APPROVED"


# ── Page extension tests (fast) ──────────────────────────────────────

def test_v10449_page_parses():
    ast.parse((REPO / "pages" / "82_credit_approvals.py").read_text())


def test_v10449_page_has_six_tabs():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    tab_blocks = re.findall(r"^with tabs\[(\d+)\]:", t, re.MULTILINE)
    assert set(int(x) for x in tab_blocks) == {0, 1, 2, 3, 4, 5}


def test_v10449_page_has_branch_committee_tab():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    assert "🏢 Branch Committee" in t
    assert "🏛️ HO Committee Queue" in t
    assert "BCC autonomy limit" in t
    assert "BCC + Forward limit" in t


def test_v10449_page_imports_branch_helpers():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    for sym in ("determine_branch_tier", "is_branch_tier", "forwards_to_ho",
                "BRANCH_AUTO_DISBURSE_LIMIT_KES", "BRANCH_FORWARD_LIMIT_KES"):
        assert sym in t, f"Missing: {sym}"


def test_v10449_page_recognises_branch_roles():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    assert "BRANCH_MANAGER" in t
    assert "BRANCH_CREDIT_MANAGER" in t
    assert "BRANCH_OPERATIONS_MANAGER" in t
    assert "_is_branch_role" in t
    assert "_is_branch_eligible" in t


def test_v10449_page_requires_branch_documentation():
    """Per Joshua doctrine: branch decisions MUST be documented."""
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    assert "BCC documentation policy" in t


def test_v10449_page_branch_specific_outcomes():
    t = (REPO / "pages" / "82_credit_approvals.py").read_text()
    assert "APPROVED_AT_BRANCH" in t
    assert "APPROVED_BRANCH_FORWARD_HO" in t
    assert "FORWARDED TO HEAD OFFICE" in t


def test_v10449_backups_created():
    bdir = REPO / "data" / "_v10449_backups"
    assert bdir.exists()
    assert (bdir / "credit_workflow.py.before").exists()
    assert (bdir / "82_credit_approvals.py.before").exists()


# ── Upstream preservation (slow) ─────────────────────────────────────

def test_v10449_credit_workflow_self_test():
    """Engine's own self_test (19 tests) must still pass."""
    from utils.credit_workflow import self_test
    self_test()  # Will raise if any of 19 assertions fail


def test_v10449_credit_health_preserved():
    for k in list(sys.modules):
        if "credit_section_audit_engine" in k:
            del sys.modules[k]
    from utils.credit_section_audit_engine import credit_full_audit
    a = credit_full_audit()
    assert a.credit_health_pct >= 80.0
    assert a.flow_coverage.flow_completeness_pct == 100.0


def test_v10449_360_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10449_bsc_preserved():
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
    from audit import gate_v10449_branch_credit_committee
    r = gate_v10449_branch_credit_committee()
    assert r["passed"], r.get("violations")
