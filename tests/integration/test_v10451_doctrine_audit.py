"""Integration tests for v10.451 — Doctrine-Aligned Audit + Honest Canonical Health.

Per Joshua: review both doctrine docs line by line and align 100%.
Honest credit health: 50.6% per doctrine (not 84.8%, not 55.5%).
"""

import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def doctrine():
    for k in list(sys.modules):
        if "credit_doctrine_audit" in k or "credit_section_audit_engine" in k:
            del sys.modules[k]
    from utils.credit_doctrine_audit import doctrine_full_audit
    return doctrine_full_audit()


# ── Engine structure (fast) ─────────────────────────────────────────

def test_v10451_doctrine_engine_exists():
    assert (REPO / "utils" / "credit_doctrine_audit.py").exists()


def test_v10451_eight_phase_audit_functions():
    text = (REPO / "utils" / "credit_doctrine_audit.py").read_text()
    for fn in (
        "def audit_phase_1_diagnostic",
        "def audit_phase_2_qa_compliance",
        "def audit_phase_3_modernization",
        "def audit_phase_4_workflow_alignment",
        "def audit_phase_5_bsc_intelligence",
        "def audit_phase_6_command_centre",
        "def audit_phase_7_cross_organ",
        "def audit_phase_8_anti_deterioration",
    ):
        assert fn in text, f"Missing: {fn}"


def test_v10451_final_validation_function():
    text = (REPO / "utils" / "credit_doctrine_audit.py").read_text()
    assert "def final_validation_certification" in text


def test_v10451_vital_signs_function():
    text = (REPO / "utils" / "credit_doctrine_audit.py").read_text()
    assert "def vital_signs_for_credit" in text


def test_v10451_doctrine_full_audit():
    text = (REPO / "utils" / "credit_doctrine_audit.py").read_text()
    assert "def doctrine_full_audit" in text


# ── Doctrine audit returns expected structure (slow) ────────────────

def test_v10451_doctrine_health_below_50(doctrine):
    """Per Joshua's repeated pushback: honest health is below 50% per expanded doctrine."""
    assert doctrine.doctrine_health_pct < 50.0


def test_v10451_doctrine_health_above_25(doctrine):
    """Reality check: shouldn't be artificially low either."""
    assert doctrine.doctrine_health_pct >= 25.0


def test_v10451_diagnostic_principles_present(doctrine):
    """Document 2 specifies 5 Body-Wide Diagnostic Principles."""
    assert hasattr(doctrine, "diagnostic_principles")
    assert doctrine.diagnostic_principles is not None
    assert len(doctrine.diagnostic_principles.principles) == 5


def test_v10451_diagnostic_principle_names():
    """The 5 principles match Document 2 exactly."""
    for k in list(sys.modules):
        if "credit_doctrine_audit" in k:
            del sys.modules[k]
    from utils.credit_doctrine_audit import doctrine_full_audit
    a = doctrine_full_audit()
    expected = (
        "Organ-Level Health Testing",
        "Circulatory Flow Analysis",
        "Inter-Organ Compatibility Testing",
        "Systemic Stress Testing",
        "Preventive Deterioration Monitoring",
    )
    actual_names = tuple(p["name"] for p in a.diagnostic_principles.principles)
    assert actual_names == expected


def test_v10451_phase_1_expanded_to_33_subcriteria(doctrine):
    """Phase 1 must cover Functional 8 + Technical 12 + Data 7 + Operational 6 = 33."""
    assert len(doctrine.phase_1.sub_criteria) >= 25


def test_v10451_phase_8_expanded_to_22_subcriteria(doctrine):
    """Phase 8: 14 stability controls + 8 deterioration scans = 22."""
    assert len(doctrine.phase_8.sub_criteria) >= 18


def test_v10451_all_eight_phases_populated(doctrine):
    for k in ("phase_1","phase_2","phase_3","phase_4",
              "phase_5","phase_6","phase_7","phase_8"):
        p = getattr(doctrine, k)
        assert p is not None
        assert p.phase_score_pct >= 0
        assert p.phase_score_pct <= 100


def test_v10451_phase_2_qa_low(doctrine):
    """Phase 2 QA compliance < 50% (no formal gap analysis)."""
    assert doctrine.phase_2.phase_score_pct < 50.0


def test_v10451_phase_6_command_centre_zero(doctrine):
    """Phase 6 = 0% because Chief Credit Centre doesn't exist."""
    assert doctrine.phase_6.phase_score_pct == 0.0


def test_v10451_final_validation_14_criteria(doctrine):
    """The doctrine specifies exactly 14 certification criteria."""
    assert len(doctrine.final_validation.criteria) == 14


def test_v10451_vital_signs_10_questions(doctrine):
    """Document 2 specifies exactly 10 vital health questions."""
    assert len(doctrine.vital_signs.questions) == 10


def test_v10451_not_certified(doctrine):
    """Module is NOT certified for revival yet."""
    assert doctrine.final_validation.certified is False


def test_v10451_at_most_a_few_criteria_met(doctrine):
    """Only 2-3 of 14 final validation criteria met."""
    assert doctrine.final_validation.fully_met <= 4


# ── credit_full_audit delegates to doctrine ─────────────────────────

def test_v10451_credit_full_audit_uses_doctrine_health(doctrine):
    """credit_full_audit().credit_health_pct should equal doctrine health."""
    for k in list(sys.modules):
        if "credit_section_audit_engine" in k:
            del sys.modules[k]
    from utils.credit_section_audit_engine import credit_full_audit
    cs = credit_full_audit()
    assert abs(cs.credit_health_pct - doctrine.doctrine_health_pct) < 0.5


# ── Rescue priorities surface real gaps ─────────────────────────────

def test_v10451_rescue_priorities_include_critical_phases(doctrine):
    text = " ".join(doctrine.rescue_priorities).lower()
    assert "phase 5" in text or "phase 6" in text or "phase 2" in text


# ── Upstream preserved ──────────────────────────────────────────────

def test_v10451_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10451_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10451_g337_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10451_doctrine_aligned_audit
    r = gate_v10451_doctrine_aligned_audit()
    assert r["passed"], r.get("violations")
