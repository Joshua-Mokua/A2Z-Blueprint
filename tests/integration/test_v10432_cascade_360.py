"""Integration tests for v10.432 — cascade-BSC 360° audit."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10432_engine_exists():
    path = REPO / "utils" / "cascade_bsc_360_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_bank_to_md",
        "def audit_cascade_integrity",
        "def audit_cascade_to_bsc_targets",
        "def audit_bsc_actuals_coverage",
        "def audit_score_calculation",
        "def cascade_bsc_360_audit",
        "class BankToMDAudit",
        "class CascadeIntegrityAudit",
        "class CascadeBSCTargetAudit",
        "class BSCActualsAudit",
        "class ScoreCalculationAudit",
        "class Master360Audit",
        "_compute_kpi_achievement",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10432_zero_streamlit():
    text = (REPO / "utils" / "cascade_bsc_360_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10432_stage1_md_has_kpis():
    """MD must have BSC entries (Stage 1 prerequisite)."""
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import audit_bank_to_md
    s1 = audit_bank_to_md()
    assert s1.md_bsc_kpi_count > 0


def test_v10432_stage2_cascade_integrity_perfect():
    """Cascade integrity: all entries should have allocations summing to total_target."""
    from utils.cascade_bsc_360_engine import audit_cascade_integrity
    s2 = audit_cascade_integrity()
    # Expecting clean (per v10.397 regenerated cascade)
    assert s2.sum_mismatch_count == 0
    assert len(s2.orphan_allocations) == 0


def test_v10432_stage3_returns_audit():
    """Stage 3 runs and returns a proper structure (even if coverage low)."""
    from utils.cascade_bsc_360_engine import audit_cascade_to_bsc_targets
    s3 = audit_cascade_to_bsc_targets()
    assert s3.total_allocations > 0
    assert 0 <= s3.coverage_pct <= 100


def test_v10432_stage4_actuals_coverage_100():
    """Post-BSC-rescue: all rows should have actuals + targets."""
    from utils.cascade_bsc_360_engine import audit_bsc_actuals_coverage
    s4 = audit_bsc_actuals_coverage()
    assert s4.target_coverage_pct == 100.0
    assert s4.actuals_coverage_pct == 100.0


def test_v10432_stage5_all_staff_scoreable():
    """Every staff should be scoreable (no NaN scores)."""
    from utils.cascade_bsc_360_engine import audit_score_calculation
    s5 = audit_score_calculation()
    assert s5.total_staff > 0
    assert s5.staff_with_nan_score == 0
    # Scores should be in plausible range
    assert s5.score_range[0] >= 0
    assert s5.score_range[1] <= 250  # cap is 200 per KPI but pillar avg can be higher? No, weighted avg can't exceed max KPI score


def test_v10432_master_audit_runs():
    """Master audit returns a Master360Audit with 5 stages."""
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit, Master360Audit
    m = cascade_bsc_360_audit()
    assert isinstance(m, Master360Audit)
    assert m.total_stages == 5
    assert 0 <= m.stages_passing <= 5
    assert 0 <= m.overall_harmony_pct <= 100


def test_v10432_compute_achievement_higher_direction():
    from utils.cascade_bsc_360_engine import _compute_kpi_achievement
    # On-target = 100%
    assert _compute_kpi_achievement(100, 100) == 100.0
    # Half = 50%
    assert _compute_kpi_achievement(50, 100) == 50.0
    # Over = capped at 200
    assert _compute_kpi_achievement(500, 100) == 200.0
    # Zero target = 0 (avoid div-by-zero)
    assert _compute_kpi_achievement(50, 0) == 0.0


def test_v10432_compute_achievement_lower_direction():
    """Lower-is-better (e.g., NPL ratio): inverse calculation."""
    from utils.cascade_bsc_360_engine import _compute_kpi_achievement
    # On-target (actual=target=10): 100%
    assert _compute_kpi_achievement(10, 10, "lower") == 100.0
    # Better (actual=5, target=10): 200% capped
    assert _compute_kpi_achievement(5, 10, "lower") == 200.0
    # Worse (actual=20, target=10): 50%
    assert _compute_kpi_achievement(20, 10, "lower") == 50.0


def test_v10432_admin_panel_has_360_render():
    text = (REPO / "utils" / "bsc_admin_panel.py").read_text()
    assert "def render_cascade_360_panel" in text


def test_v10432_admin_page_wires_360_panel():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "render_cascade_360_panel" in text


def test_v10432_admin_page_syntax_valid():
    import ast
    text = (REPO / "pages" / "7_admin.py").read_text()
    ast.parse(text)


def test_v10432_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/cascade-360/audit" in text
    assert "/api/v1/cascade-360/stage" in text


def test_v10432_dataclasses_json_serializable():
    import json
    from utils.cascade_bsc_360_engine import (
        audit_bank_to_md, audit_cascade_integrity,
        audit_cascade_to_bsc_targets, audit_bsc_actuals_coverage,
        audit_score_calculation, cascade_bsc_360_audit,
    )
    for fn in (
        audit_bank_to_md, audit_cascade_integrity,
        audit_cascade_to_bsc_targets, audit_bsc_actuals_coverage,
        audit_score_calculation, cascade_bsc_360_audit,
    ):
        result = fn()
        json.dumps(result.to_dict())


def test_v10432_bsc_health_still_100():
    """v10.432 is audit-only — BSC rescue health unchanged."""
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    audit = bsc_full_audit()
    assert audit.overall_health_pct == 100.0


def test_v10432_g318_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10432_cascade_360
    r = gate_v10432_cascade_360()
    assert r["passed"], r.get("violations")
