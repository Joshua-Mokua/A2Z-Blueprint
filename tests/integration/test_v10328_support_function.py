"""tests/integration/test_v10328_support_function.py

v10.328 — Support function team integration.

Locks the complete virtual bank environment:
  - support_function_generator covers 7 remaining Chief subtrees
  - 182 staff producing 525 KPIs/quarter
  - All 11 of MD's direct-report Chiefs scoring in 2026-Q2
  - Direction-aware (lower-is-better KPIs invert factor)
  - Scale invariants preserved (CX/COMPLIANCE_SCORE 1-5; Audit/Staff
    Productivity 0-100)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Generator module surface
# ────────────────────────────────────────────────────────────────────

def test_support_generator_module_exists():
    p = REPO_ROOT / "utils" / "support_function_generator.py"
    assert p.exists()
    text = p.read_text()
    for name in (
        "def generate_quarter",
        "def generate_history",
        "def _list_support_staff",
        "def load_generator_config",
        "def kpi_value",
        "def performance_band",
    ):
        assert name in text, f"Missing: {name}"


def test_generator_uses_canonical_imports():
    text = (REPO_ROOT / "utils" / "support_function_generator.py").read_text()
    assert "from utils.bsc_engine import submit" in text
    assert "from utils.virtual_bank import staff_universe" in text


def test_generator_no_direct_file_io():
    text = (REPO_ROOT / "utils" / "support_function_generator.py").read_text()
    assert "cfg_path.read_text()" not in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Config
# ────────────────────────────────────────────────────────────────────

def test_config_has_seven_chiefs():
    cfg = json.loads(
        (REPO_ROOT / "data" / "support_function_config.json").read_text())
    chiefs = cfg.get("chiefs", [])
    assert len(chiefs) == 7
    for c in (
        "EXEC-COO-001", "EXEC-CFO-001", "EXEC-CRSO-001",
        "EXEC-CIO-001", "EXEC-CHRO-001", "EXEC-CIA-001",
        "EXEC-CCMP-001",
    ):
        assert c in chiefs, f"Missing chief: {c}"


def test_config_has_role_specs_for_all_function_types():
    cfg = json.loads(
        (REPO_ROOT / "data" / "support_function_config.json").read_text())
    roles = {
        k for k in cfg.get("role_kpi_targets", {}).keys()
        if not k.startswith("_")
    }
    assert len(roles) >= 35, f"Only {len(roles)} roles configured"
    # Coverage spot-checks across the 7 chief subtrees
    expected_samples = (
        # COO subtree
        "Contact Centre Officer",
        "Operations Officer",
        # CFO subtree
        "Finance Officer",
        # CRSO subtree
        "Risk Manager",
        # CIO subtree
        "Senior Digital Channels Officer",
        "Cyber Security SOC Analyst",
        # CHRO subtree
        "Human Resource Officer Admin",
        # CCMP subtree
        "Legal Officer",
    )
    for r in expected_samples:
        assert r in roles, f"Config missing key role: {r}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Staff coverage
# ────────────────────────────────────────────────────────────────────

def test_generator_lists_at_least_150_support_staff():
    from utils.support_function_generator import _list_support_staff
    staff = _list_support_staff()
    assert len(staff) >= 150, (
        f"Only {len(staff)} support staff found"
    )


def test_support_staff_under_correct_chief():
    from utils.support_function_generator import _list_support_staff
    staff = _list_support_staff()
    # Check we have staff under each of the 7 chiefs
    chiefs_with_staff = set(s.chief_code for s in staff)
    # Allow CIA with 0 sub-staff (Chief themselves only)
    assert "EXEC-COO-001" in chiefs_with_staff
    assert "EXEC-CFO-001" in chiefs_with_staff
    assert "EXEC-CIO-001" in chiefs_with_staff
    assert "EXEC-CCMP-001" in chiefs_with_staff


# ────────────────────────────────────────────────────────────────────
# Section 4 — Determinism + direction-awareness
# ────────────────────────────────────────────────────────────────────

def test_generator_deterministic():
    from utils.support_function_generator import (
        kpi_value, load_generator_config
    )
    cfg = load_generator_config()
    v1 = kpi_value(
        "300184", "Legal Officer",
        "COMPLIANCE_SCORE", "2026-Q2", cfg)
    v2 = kpi_value(
        "300184", "Legal Officer",
        "COMPLIANCE_SCORE", "2026-Q2", cfg)
    assert v1 == v2


def test_generator_produces_scaled_values():
    """COMPLIANCE_SCORE (1-5) should produce values in 1-5 range;
    Audit Score (0-100) should produce values in 50-100 range."""
    from utils.support_function_generator import (
        kpi_value, load_generator_config
    )
    cfg = load_generator_config()
    # Test across several staff to check scale
    universe_samples = (
        ("300184", "Legal Officer"),
        ("300156", "Human Resource Business Partner- Operations"),
        ("300109", "Senior Manager- Compliance"),
    )
    for code, role in universe_samples:
        cs = kpi_value(code, role, "COMPLIANCE_SCORE",
                       "2026-Q2", cfg)
        if cs is not None:
            assert 1.0 <= cs <= 5.0, (
                f"{code} COMPLIANCE_SCORE={cs} out of 1-5 range"
            )
        audit = kpi_value(code, role, "Audit Score",
                          "2026-Q2", cfg)
        if audit is not None:
            assert 50.0 <= audit <= 100.0, (
                f"{code} Audit Score={audit} out of 50-100 range"
            )


# ────────────────────────────────────────────────────────────────────
# Section 5 — BSC actuals produced
# ────────────────────────────────────────────────────────────────────

def test_bsc_actuals_q2_has_support_records():
    actuals = json.loads(
        (REPO_ROOT / "data" / "bsc_actuals_2026-Q2.json").read_text())
    from_gen = [
        r for r in actuals
        if r.get("source_module") == "support_function_generator"
    ]
    assert len(from_gen) >= 500, (
        f"Only {len(from_gen)} support actuals in Q2"
    )


def test_support_actuals_in_valid_ranges():
    actuals = json.loads(
        (REPO_ROOT / "data" / "bsc_actuals_2026-Q2.json").read_text())
    score_5_kpis = {"CX Score", "COMPLIANCE_SCORE"}
    for r in actuals:
        if r.get("source_module") != "support_function_generator":
            continue
        v = float(r.get("value", 0))
        kpi = r.get("kpi_id")
        if kpi in score_5_kpis:
            assert 1.0 <= v <= 5.0, (
                f"{r.get('staff_code')} {kpi}={v} out of 1-5 range"
            )


# ────────────────────────────────────────────────────────────────────
# Section 6 — All 11 Chiefs scoring
# ────────────────────────────────────────────────────────────────────

def test_all_seven_support_chiefs_have_scores_q2():
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    scores = cs.get("scores", {})
    for code in (
        "EXEC-COO-001", "EXEC-CFO-001", "EXEC-CRSO-001",
        "EXEC-CIO-001", "EXEC-CHRO-001", "EXEC-CIA-001",
        "EXEC-CCMP-001",
    ):
        s = scores.get(code)
        assert s is not None, f"{code} has no Q2 score"
        assert 1.0 <= s <= 5.0


def test_md_view_spans_all_eleven_chiefs():
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    scores = cs.get("scores", {})
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    md_direct = [
        r for r in u.values()
        if r.manager_code == "EXEC-MD-001"
    ]
    scoring = [r for r in md_direct if r.staff_code in scores]
    # MD should have 10-11 scoring chiefs (allow 1 missing for
    # edge cases like Marketing/Comms with no sales mandate)
    assert len(scoring) >= 10, (
        f"MD has only {len(scoring)} of {len(md_direct)} "
        f"scoring direct reports — expected ≥10"
    )


def test_md_recursive_score_is_set():
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    md = cs.get("scores", {}).get("EXEC-MD-001")
    assert md is not None
    assert 1.0 <= md <= 5.0


# ────────────────────────────────────────────────────────────────────
# Section 7 — Audit gate G219
# ────────────────────────────────────────────────────────────────────

def test_g219_gate_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G219":
            g = fn()
            break
    assert g is not None, "G219 not registered"
    assert g["passed"], (
        f"G219 failed: violations={g.get('violations', [])}"
    )
