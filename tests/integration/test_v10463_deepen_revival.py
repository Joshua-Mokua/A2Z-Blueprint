"""Integration tests for v10.463 — Deepen Revival of 10 Organs.

Three work-streams:
  1. Role alignment with actual users.json titles
  2. Phase 2 doc closeout (3 new generators + 30 docs)
  3. 21 module-specific audit gates added

Avg health: 75.2% → 81.3% (+6.1pp). Phase 2 = 100% all 10 organs.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def all_modules():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k or "cascade_bsc_360" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    return all_modules_audit()


# ── 1. ACTUAL ROLE NAMES IN MODULE_REGISTRY ──────────────────────────

@pytest.mark.parametrize("role,organ", [
    ("Chief Financial Officer", "finance"),
    ("Senior Manager Treasury", "treasury"),
    ("Company Secretary and Chief Legal Officer", "legal"),
    ("Risk Manager", "risk"),
    ("Senior Manager- Compliance", "compliance"),
])
def test_v10463_actual_role_in_registry(role, organ):
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    assert role in text, f"MODULE_REGISTRY missing actual role: {role!r}"


@pytest.mark.parametrize("role", [
    "Chief Financial Officer",
    "Senior Manager Treasury",
    "Company Secretary and Chief Legal Officer",
    "Risk Manager",
    "Senior Manager- Compliance",
])
def test_v10463_actual_role_in_super_user_map(role):
    text = (REPO / "utils" / "super_user_registry.py").read_text()
    assert role in text


# ── 2. NEW PHASE 2 DOC GENERATORS ─────────────────────────────────────

def test_v10463_doc_generator_has_risk_assessment():
    text = (REPO / "utils" / "module_doc_generator.py").read_text()
    assert "def gen_risk_assessment" in text


def test_v10463_doc_generator_has_recovery_priority_matrix():
    text = (REPO / "utils" / "module_doc_generator.py").read_text()
    assert "def gen_recovery_priority_matrix" in text


def test_v10463_doc_generator_has_remediation_roadmap():
    text = (REPO / "utils" / "module_doc_generator.py").read_text()
    assert "def gen_remediation_roadmap" in text


@pytest.mark.parametrize("organ", [
    "admin", "hr", "bsc_cascade", "credit", "ict",
    "finance", "treasury", "legal", "risk", "compliance"
])
@pytest.mark.parametrize("doc_type", [
    "risk_assessment", "recovery_priority_matrix", "remediation_roadmap"
])
def test_v10463_doc_exists(organ, doc_type):
    path = REPO / "docs" / f"{organ}_{doc_type}.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    # Must be real content, not stub
    assert len(text) >= 300, f"{organ}_{doc_type}.md too short ({len(text)})"


# ── 3. MODULE-SPECIFIC AUDIT GATES (QA1 >=3) ──────────────────────────

@pytest.mark.parametrize("organ", [
    "admin", "hr", "credit", "ict",
    "finance", "treasury", "legal", "risk", "compliance"
])
def test_v10463_organ_has_3_plus_module_gates(organ):
    audit_text = (REPO / "scripts" / "audit.py").read_text()
    pattern = rf"def gate_v10[\d_]+_{organ}_\w+"
    matches = re.findall(pattern, audit_text)
    assert len(matches) >= 3, \
        f"{organ}: only {len(matches)} module-specific gates; need >=3"


def test_v10463_bsc_has_module_gates():
    """bsc_cascade has gates under both 'bsc' and 'cascade' patterns."""
    audit_text = (REPO / "scripts" / "audit.py").read_text()
    bsc = len(re.findall(r"def gate_v10[\d_]+_bsc_\w+", audit_text))
    cas = len(re.findall(r"def gate_v10[\d_]+_cascade_\w+", audit_text))
    assert (bsc + cas) >= 3


# ── 4. PHASE 2 SCORE = 100% FOR ALL 10 ORGANS ─────────────────────────

def test_v10463_phase_2_100_for_all_organs(all_modules):
    failures = []
    for key, m in all_modules.modules.items():
        if m.phase_2.score_pct < 100.0:
            failures.append(f"{key}: {m.phase_2.score_pct}%")
    assert not failures, f"Phase 2 < 100%: {failures}"


# ── 5. HEALTH UPLIFT ──────────────────────────────────────────────────

def test_v10463_avg_health_above_80(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 80.0


def test_v10463_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


def test_v10463_hr_at_12_cert(all_modules):
    """HR should now hit 12/14."""
    assert all_modules.modules["hr"].criteria_fully_met >= 12


def test_v10463_most_organs_at_10_plus_cert(all_modules):
    """Most organs should reach 10+ cert criteria."""
    high = sum(1 for m in all_modules.modules.values()
              if m.criteria_fully_met >= 10)
    assert high >= 8, f"Only {high}/10 organs at >=10 cert criteria"


# ── 6. NO REGRESSION ──────────────────────────────────────────────────

def test_v10463_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10463_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10463_manifest_invariant_holds():
    """G343 + v10.462 file-existence still holds."""
    for k in list(sys.modules):
        if "page_manifest_loader" in k:
            del sys.modules[k]
    from utils.page_manifest_loader import list_ghost_entries
    assert list_ghost_entries() == []


def test_v10463_10_organs_registered(all_modules):
    assert len(all_modules.modules) == 10


def test_v10463_g349_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10463_deepen_revival
    r = gate_v10463_deepen_revival()
    assert r["passed"], r.get("violations")
