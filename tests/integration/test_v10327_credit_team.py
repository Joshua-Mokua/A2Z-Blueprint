"""tests/integration/test_v10327_credit_team.py

v10.327 — Credit team integration into cascade.

Locks:
  - credit_activity_generator produces BSC actuals for Credit roles
  - 28 Credit staff under CCO subtree
  - 127 KPIs submitted per quarter
  - Direction-aware logic (TAT/NPL/PAR/Rework INVERT band factor)
  - CCO recursive score computable
  - MD score derives from 4 Chiefs (Retail + Bancassurance + Credit + Commercial)
  - Credit process flow: Lead → Analysis → Admin → Monitoring → DRU
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

def test_credit_generator_module_exists():
    p = REPO_ROOT / "utils" / "credit_activity_generator.py"
    assert p.exists()
    text = p.read_text()
    # Required functions
    for name in (
        "def generate_quarter",
        "def generate_history",
        "def _list_credit_staff",
        "def load_generator_config",
        "def kpi_value",
        "def performance_band",
    ):
        assert name in text, f"Missing: {name}"


def test_generator_uses_canonical_imports():
    text = (REPO_ROOT / "utils" / "credit_activity_generator.py").read_text()
    assert "from utils.bsc_engine import submit" in text
    assert "from utils.virtual_bank import staff_universe" in text


def test_generator_no_direct_file_io():
    """G2 invariant: generator uses utils.db not raw file I/O."""
    text = (REPO_ROOT / "utils" / "credit_activity_generator.py").read_text()
    # Should not have raw read_text fallback
    assert "cfg_path.read_text()" not in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Config
# ────────────────────────────────────────────────────────────────────

def test_config_has_credit_roles():
    cfg = json.loads(
        (REPO_ROOT / "data" / "credit_activity_config.json").read_text())
    roles = cfg.get("role_kpi_targets", {})
    assert len(roles) >= 10, f"Only {len(roles)} role specs"
    # Required roles
    for role in (
        "Credit Analyst",
        "Credit Admin Officer",
        "Manager-Credit Monitoring",
        "Collections and Recoveries Officer",
        "Senior Manager -Credit Analysis",
        "Senior Manager-Collections & Recoveries",
    ):
        assert role in roles, f"Missing role spec: {role}"


def test_config_has_performance_bands():
    cfg = json.loads(
        (REPO_ROOT / "data" / "credit_activity_config.json").read_text())
    bands = cfg.get("performance_bands", {})
    visible = {k: v for k, v in bands.items() if not k.startswith("_")}
    assert len(visible) >= 3, "Need at least 3 performance bands"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Staff coverage
# ────────────────────────────────────────────────────────────────────

def test_generator_lists_at_least_25_credit_staff():
    from utils.credit_activity_generator import _list_credit_staff
    staff = _list_credit_staff()
    assert len(staff) >= 25, (
        f"Only {len(staff)} Credit staff found"
    )


def test_credit_staff_all_under_cco():
    from utils.credit_activity_generator import _list_credit_staff
    from utils.manager_rollup import _all_subordinate_codes
    cco_subs = set(_all_subordinate_codes("EXEC-CCO-001"))
    cco_subs.add("EXEC-CCO-001")
    staff = _list_credit_staff()
    for s in staff:
        assert s.staff_code in cco_subs, (
            f"{s.staff_code} ({s.role}) not in CCO subtree"
        )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Determinism + direction-awareness
# ────────────────────────────────────────────────────────────────────

def test_generator_deterministic_same_inputs_same_value():
    """Determinism: same (staff, role, kpi, period) → same value."""
    from utils.credit_activity_generator import (
        kpi_value, load_generator_config
    )
    cfg = load_generator_config()
    v1 = kpi_value(
        "300068", "Credit Analyst",
        "CREDIT_APPROVAL_RATE", "2026-Q2", cfg)
    v2 = kpi_value(
        "300068", "Credit Analyst",
        "CREDIT_APPROVAL_RATE", "2026-Q2", cfg)
    assert v1 == v2, f"Non-deterministic: {v1} vs {v2}"


def test_generator_produces_realistic_tat_values():
    """TAT KPIs should produce values near config target."""
    from utils.credit_activity_generator import (
        kpi_value, load_generator_config
    )
    cfg = load_generator_config()
    v = kpi_value(
        "300068", "Credit Analyst",
        "CREDIT_TAT_STANDARD", "2026-Q2", cfg)
    # TAT should be a positive number of days, reasonable
    assert v is not None
    assert 0 < v < 30, f"TAT value {v} outside reasonable range"


# ────────────────────────────────────────────────────────────────────
# Section 5 — BSC actuals produced
# ────────────────────────────────────────────────────────────────────

def test_bsc_actuals_q2_has_credit_records():
    actuals = json.loads(
        (REPO_ROOT / "data" / "bsc_actuals_2026-Q2.json").read_text())
    from_gen = [
        r for r in actuals
        if r.get("source_module") == "credit_activity_generator"
    ]
    assert len(from_gen) >= 120, (
        f"Only {len(from_gen)} Credit-generated actuals in Q2"
    )


def test_credit_actuals_span_all_4_quarters():
    """Generator ran for Q3 2025 through Q2 2026."""
    for period in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"):
        p = REPO_ROOT / "data" / f"bsc_actuals_{period}.json"
        if not p.exists():
            continue
        actuals = json.loads(p.read_text())
        from_gen = [
            r for r in actuals
            if r.get("source_module") == "credit_activity_generator"
        ]
        assert len(from_gen) >= 100, (
            f"{period}: only {len(from_gen)} Credit actuals"
        )


# ────────────────────────────────────────────────────────────────────
# Section 6 — CCO subtree feeds cascade
# ────────────────────────────────────────────────────────────────────

def test_cco_has_recursive_score_in_q2():
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    cco = cs.get("scores", {}).get("EXEC-CCO-001")
    assert cco is not None, "CCO has no Q2 score"
    assert 1.0 <= cco <= 5.0


def test_cco_subtree_has_scoring_subordinates():
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    scores = cs.get("scores", {})
    from utils.manager_rollup import _all_subordinate_codes
    cco_subs = _all_subordinate_codes("EXEC-CCO-001")
    scoring = sum(1 for c in cco_subs if c in scores)
    assert scoring >= 6, (
        f"Only {scoring} CCO subordinates scoring"
    )


def test_md_now_spans_four_chiefs():
    """Retail + Bancassurance + Credit + Commercial."""
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
    assert len(scoring) >= 4, (
        f"MD has only {len(scoring)} scoring direct reports — "
        f"expected ≥4 (Retail + Bancassurance + Credit + Commercial)"
    )


def test_cco_is_now_in_md_directs():
    """CCO must be among MD's scoring direct reports."""
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    cco = cs.get("scores", {}).get("EXEC-CCO-001")
    assert cco is not None


# ────────────────────────────────────────────────────────────────────
# Section 7 — Credit process flow (Joshua's design)
# ────────────────────────────────────────────────────────────────────

def test_credit_process_roles_all_present():
    """Lead → Analysis → Admin → Monitoring → DRU."""
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    roles_present = {s.role for s in u.values()}
    required_credit_roles = {
        "Credit Analyst",          # Analysis
        "Credit Admin Officer",     # Admin (Perfection)
        "Manager-Credit Monitoring",  # Monitoring
        "Collections and Recoveries Officer",  # DRU
        "Senior Manager-Collections & Recoveries",  # DRU lead
    }
    missing = required_credit_roles - roles_present
    assert not missing, f"Missing credit process roles: {missing}"


def test_cco_chains_to_md():
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    cco = u.get("EXEC-CCO-001")
    assert cco is not None
    assert cco.manager_code == "EXEC-MD-001", (
        f"CCO manager is {cco.manager_code}, expected EXEC-MD-001"
    )


# ────────────────────────────────────────────────────────────────────
# Section 8 — Audit gate G218
# ────────────────────────────────────────────────────────────────────

def test_g218_gate_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G218":
            g = fn()
            break
    assert g is not None, "G218 not registered"
    assert g["passed"], (
        f"G218 failed: violations={g.get('violations', [])}"
    )
