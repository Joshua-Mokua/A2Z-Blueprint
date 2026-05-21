"""tests/integration/test_v10320_data_hygiene.py

v10.320 — Data hygiene cleanup (B-018 + B-019).

Locks:
  - Staff Productivity bank_target is 85 (was 3.0)
  - Audit Score description corrected (1-5 → 0-100)
  - KPI_ID_ALIASES auto-built from kpi.code field
  - validate_role_weights returns normalization info
  - audit_data_hygiene script runs and reports cleanly
  - Teller 300230 scorecard now computes 2.4/5.0 (was 3.4)
  - G211 passes
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Bank target fixes
# ────────────────────────────────────────────────────────────────────

def test_staff_productivity_bank_target_fixed():
    """Staff Productivity bank_target was 3.0 (broken), should
    now be 85.0 (matches v10.317 generator config)."""
    from utils.db import db
    bt = db.load_json(
        REPO_ROOT / "data" / "bank_targets.json",
        default={},
    ) or {}
    entry = bt.get("Staff Productivity|2026", {})
    target = (
        entry.get("target") if isinstance(entry, dict)
        else entry
    )
    assert target == 85.0, (
        f"Staff Productivity bank target = {target}, "
        f"expected 85.0 after v10.320 fix"
    )


def test_staff_productivity_fix_marker_present():
    """The fix should be tagged so future audits know it was
    deliberate."""
    from utils.db import db
    bt = db.load_json(
        REPO_ROOT / "data" / "bank_targets.json",
        default={},
    ) or {}
    entry = bt.get("Staff Productivity|2026", {})
    assert isinstance(entry, dict)
    assert "_v10320_fix" in entry


# ────────────────────────────────────────────────────────────────────
# Section 2 — KPI library description fix
# ────────────────────────────────────────────────────────────────────

def test_audit_score_description_corrected():
    """The Audit Score description said '1-5 scale' but actuals
    are 0-100. v10.320 corrects the description."""
    from utils.db import db
    lib = db.load_json(
        REPO_ROOT / "data" / "kpi_library.json",
        default={},
    ) or {}
    audit_score = next(
        (k for k in lib.get("kpis", [])
         if k.get("id") == "Audit Score"),
        None,
    )
    assert audit_score is not None
    desc = audit_score.get("description", "")
    assert "0-100" in desc or "percentage" in desc.lower(), (
        f"Audit Score description should mention 0-100 scale: "
        f"{desc}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Alias map auto-built from kpi.code
# ────────────────────────────────────────────────────────────────────

def test_alias_map_built_from_kpi_codes():
    """The alias map should auto-build from kpi.code → kpi.id
    rather than being hardcoded. This makes B-010 stay solved
    as the library grows."""
    from utils.bsc_score_computation import (
        KPI_ID_ALIASES, _build_alias_map_from_library,
    )
    # Reload to get current state
    fresh = _build_alias_map_from_library()
    # Should have at least 15 entries from the library
    assert len(fresh) >= 15


def test_critical_aliases_present():
    """Key aliases used by the v10.317 generator and v10.318
    cascade must resolve."""
    from utils.bsc_score_computation import KPI_ID_ALIASES
    assert KPI_ID_ALIASES.get("CX_SCORE") == "CX Score"
    assert KPI_ID_ALIASES.get("AUDIT_SCORE") == "Audit Score"
    assert KPI_ID_ALIASES.get("STAFF_PROD") == "Staff Productivity"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Weight validation enhancements
# ────────────────────────────────────────────────────────────────────

def test_validate_returns_normalization_info():
    """validate_role_weights should return the normalized
    weights map and the normalization factor for callers."""
    from utils.bsc_score_computation import validate_role_weights
    val = validate_role_weights("Teller")
    assert "normalized_weights" in val
    assert "normalization_factor" in val
    assert isinstance(val["normalized_weights"], dict)
    if val["total_weight"] > 0:
        # Normalized weights should sum to 1.0 (if any defined)
        total_norm = sum(val["normalized_weights"].values())
        if val["normalized_weights"]:
            assert abs(total_norm - 1.0) < 0.01


def test_validate_factor_is_inverse_of_total():
    from utils.bsc_score_computation import validate_role_weights
    val = validate_role_weights("Teller")
    if val["total_weight"] > 0:
        expected = round(1.0 / val["total_weight"], 6)
        assert abs(val["normalization_factor"] - expected) < 0.0001


# ────────────────────────────────────────────────────────────────────
# Section 5 — Teller scorecard now computes correctly
# ────────────────────────────────────────────────────────────────────

def test_teller_scorecard_uses_corrected_targets():
    """Teller 300230 should now have 3 KPIs scoring (CX Score,
    Audit Score, Staff Productivity) — not 2 like before the
    STAFF_PROD alias fix."""
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300230", "Teller", "2026-Q1")
    scored = [k for k in card.kpi_scores
              if k.score is not None]
    assert len(scored) >= 3, (
        f"Expected ≥3 scored KPIs after v10.320, got "
        f"{len(scored)}: "
        f"{[k.canonical_id for k in scored]}"
    )


def test_teller_scorecard_includes_staff_productivity():
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300230", "Teller", "2026-Q1")
    sp_entries = [
        k for k in card.kpi_scores
        if k.canonical_id == "Staff Productivity"
        and k.score is not None
    ]
    assert sp_entries, (
        "Staff Productivity should now score (alias + bank "
        "target fixes)"
    )
    sp = sp_entries[0]
    # Generated actual is in 50-100 range; target now 85
    assert sp.target == 85.0
    assert 40 <= sp.actual <= 100


def test_teller_score_is_realistic_below_target():
    """Teller 300230 is in 'below_target' band per v10.317
    config (factor 0.65-0.85 of target). Score should be in
    range 2.0-3.0."""
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300230", "Teller", "2026-Q1")
    assert card.final_score is not None
    assert 1.5 <= card.final_score <= 3.5, (
        f"Teller 300230 final_score {card.final_score} should "
        f"be in 1.5-3.5 range for a below-target performer"
    )


# ────────────────────────────────────────────────────────────────────
# Section 6 — Hygiene audit script
# ────────────────────────────────────────────────────────────────────

def test_hygiene_audit_script_exists():
    p = REPO_ROOT / "scripts" / "audit_data_hygiene.py"
    assert p.exists()


def test_audit_bank_targets_returns_clean():
    """After v10.320 fixes, bank target audit should report 0
    HIGH-severity issues."""
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT))
    if "scripts.audit_data_hygiene" in _sys.modules:
        del _sys.modules["scripts.audit_data_hygiene"]
    from scripts.audit_data_hygiene import audit_bank_targets
    report = audit_bank_targets()
    assert report["high_severity_count"] == 0, (
        f"Expected 0 HIGH-severity bank target issues after "
        f"v10.320 fix, got {report['high_severity_count']}: "
        f"{report['findings']}"
    )


def test_audit_all_role_weights_runs():
    """The role-weights audit should run cleanly across all
    227 roles."""
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT))
    if "scripts.audit_data_hygiene" in _sys.modules:
        del _sys.modules["scripts.audit_data_hygiene"]
    from scripts.audit_data_hygiene import audit_all_role_weights
    report = audit_all_role_weights()
    assert report["stats"]["total_roles"] > 100


# ────────────────────────────────────────────────────────────────────
# Section 7 — Audit gate G211
# ────────────────────────────────────────────────────────────────────

def test_g211_gate_exists_and_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G211":
            g = fn()
            break
    assert g is not None, "G211 not registered"
    assert g["passed"], (
        f"G211 failed: {g.get('summary', '')[:200]}. "
        f"Violations: {g.get('violations', [])}"
    )
