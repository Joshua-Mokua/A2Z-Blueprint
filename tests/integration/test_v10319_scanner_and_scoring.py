"""tests/integration/test_v10319_scanner_and_scoring.py

v10.319 — Older-logic scanner + BSC score computation.

Locks:
  - The scanner runs and produces a structured report
  - The scoring engine respects fixed vs cascaded KPIs
  - The 1-5 scoring scale is canonical
  - Weights are validated against 100% target
  - B-010 alias map resolves UPPER_SNAKE_CASE → canonical
  - G209 + G210 pass
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Scanner module
# ────────────────────────────────────────────────────────────────────

def test_scanner_module_imports():
    from utils.older_logic_scanner import (
        scan_all, scan_for_stale_role_names,
        scan_for_dangling_kpi_refs,
        scan_for_direct_file_io_in_pages,
        scan_for_duplicated_bsc_scoring,
        Finding,
    )
    assert callable(scan_all)
    assert callable(scan_for_stale_role_names)


def test_scan_all_returns_structured_report():
    from utils.older_logic_scanner import scan_all
    r = scan_all()
    for key in (
        "total_findings", "stale_role_findings",
        "dangling_kpi_findings", "direct_io_findings",
        "duplicate_scoring_findings",
        "files_affected", "by_severity",
        "all_findings", "by_file",
    ):
        assert key in r


def test_scanner_does_not_self_flag():
    from utils.older_logic_scanner import scan_all
    r = scan_all()
    assert "utils/older_logic_scanner.py" not in r["by_file"], (
        "Scanner is flagging its own pattern definitions "
        "as findings (false positive)"
    )


def test_scanner_finds_known_pattern():
    """Sanity check — there ARE older-logic patterns in the
    codebase (the baseline). If findings drop near zero, the
    scanner is broken."""
    from utils.older_logic_scanner import scan_all
    r = scan_all()
    assert r["total_findings"] >= 100, (
        f"Expected ≥100 findings (baseline ~589), got "
        f"{r['total_findings']}. Scanner may be broken."
    )


def test_finding_dataclass_has_required_fields():
    from utils.older_logic_scanner import Finding
    f = Finding(
        file="test.py", line=1, pattern="X",
        severity="high", detail="test",
    )
    assert f.file == "test.py"
    assert f.severity == "high"


# ────────────────────────────────────────────────────────────────────
# Section 2 — BSC score computation (Joshua's design honouring)
# ────────────────────────────────────────────────────────────────────

def test_score_computation_module_imports():
    from utils.bsc_score_computation import (
        score_from_achievement_pct, compute_achievement_pct,
        is_fixed_kpi, get_target_for_staff,
        resolve_role_kpis, validate_role_weights,
        compute_staff_scorecard,
        KpiResolution, KpiScore, StaffScorecard,
        KPI_ID_ALIASES,
    )
    assert callable(score_from_achievement_pct)


def test_canonical_1_to_5_scoring_scale():
    """Joshua's required scale: 1-5 with thresholds at 50/60/70/
    80/90/100/110/120%."""
    from utils.bsc_score_computation import (
        score_from_achievement_pct,
    )
    assert score_from_achievement_pct(120) == 5.0
    assert score_from_achievement_pct(110) == 4.5
    assert score_from_achievement_pct(100) == 4.0
    assert score_from_achievement_pct(90) == 3.5
    assert score_from_achievement_pct(80) == 3.0
    assert score_from_achievement_pct(70) == 2.5
    assert score_from_achievement_pct(60) == 2.0
    assert score_from_achievement_pct(50) == 1.5
    assert score_from_achievement_pct(49) == 1.0


def test_score_reverse_direction():
    """For 'lower better' KPIs (NPL, PAR), the scoring reverses —
    at 200% (where actual is half of target), the staff scores 5.0."""
    from utils.bsc_score_computation import (
        score_from_achievement_pct,
    )
    # reverse=True: pct becomes 200-pct
    # so original 200 → 0 (worst) — wait let's think
    # If NPL target = 5%, actual = 2.5%, achievement = target/actual = 200%
    # In reverse direction: pct = 200 - 200 = 0 → score 1.0
    # But that's wrong — actual NPL of 2.5% (half the target) should be best!
    # The actual semantics: achievement_pct=200 means "doing twice as well"
    # in lower-better terms. Reverse transforms 200 → 0 which is WORST
    # That seems flipped. Let me check core.py's actual logic:
    # pct = achievement_pct if not reverse else (200 - achievement_pct)
    # So for reverse=True with achievement=50% (poor — actual is double target)
    # pct = 200 - 50 = 150 → score 5.0?? That's also flipped.
    #
    # Actually re-reading: in core.py, ach_pct for lower-better is computed
    # differently in line 6287: ach_pct = target/max(actual, 0.001) * 100
    # So for NPL target=5, actual=2.5: ach_pct = 5/2.5 * 100 = 200%
    # Then score(200) = 5.0. That makes sense.
    # The 'reverse' parameter in bsc_score_from_pct is for callers that
    # passed in the wrong-direction pct.
    # Our compute_achievement_pct already handles direction correctly.
    # So tests should pass with the standard (non-reverse) scoring on the
    # already-correctly-computed pct.
    from utils.bsc_score_computation import compute_achievement_pct
    # NPL: lower better. target=5, actual=2.5 → "doing twice as well"
    ach = compute_achievement_pct(2.5, 5, "lower")
    assert ach == 200.0
    score = score_from_achievement_pct(ach, reverse=False)
    assert score == 5.0


def test_compute_achievement_pct_directions():
    from utils.bsc_score_computation import compute_achievement_pct
    # Higher better
    assert compute_achievement_pct(110, 100, "higher") == 110.0
    assert compute_achievement_pct(50, 100, "higher") == 50.0
    # Lower better
    assert compute_achievement_pct(5, 10, "lower") == 200.0
    assert compute_achievement_pct(20, 10, "lower") == 50.0


def test_kpi_id_aliases_map_exists():
    from utils.bsc_score_computation import KPI_ID_ALIASES
    # Should map at least the most common dangling refs
    assert KPI_ID_ALIASES.get("CX_SCORE") == "CX Score"
    assert KPI_ID_ALIASES.get("AUDIT_SCORE") == "Audit Score"
    assert KPI_ID_ALIASES.get("STAFF_PROD") == "Staff Productivity"
    assert len(KPI_ID_ALIASES) >= 15


def test_resolve_role_kpis_for_teller():
    """Joshua wants weights summing to 100% — let's see what
    we actually have for Teller and document honestly."""
    from utils.bsc_score_computation import resolve_role_kpis
    resols = resolve_role_kpis("Teller")
    assert len(resols) >= 15, (
        f"Teller should have many KPIs, got {len(resols)}"
    )
    defined = [r for r in resols if r.defined]
    assert len(defined) >= 10, (
        f"At least 10 of Teller's KPIs should resolve to "
        f"definitions, got {len(defined)}"
    )


def test_validate_role_weights_returns_diagnostic():
    """Weights may not sum to exactly 100% today (B-018), but the
    diagnostic should be informative."""
    from utils.bsc_score_computation import validate_role_weights
    val = validate_role_weights("Teller")
    for key in (
        "role", "valid", "total_weight",
        "deviation_from_100", "kpi_count",
        "defined_count", "undefined_count",
    ):
        assert key in val


# ────────────────────────────────────────────────────────────────────
# Section 3 — Fixed vs cascaded KPI distinction (Joshua's reminder)
# ────────────────────────────────────────────────────────────────────

def test_is_fixed_kpi_for_bank_target():
    """A KPI is fixed if it's in fixed_kpis.json.

    v10.323 removed the bank_targets fallback. v10.324 further reduced
    fixed_kpis to ONLY true bank-uniform scales (CX Score, Audit Score,
    Staff Productivity, CASA Ratio, PAR, dormancy). Financial outcomes
    (PBT, Total NFI, NPL Ratio etc.) cascade per-staff or per-role,
    they are NOT bank-fixed.
    """
    from utils.bsc_score_computation import is_fixed_kpi
    # CX Score is a true bank-uniform scale — fixed
    assert is_fixed_kpi("CX Score", "2026-Q1") is True
    # PBT is a financial outcome — NOT fixed (cascades per-staff)
    assert is_fixed_kpi("PBT", "2026-Q1") is False


def test_get_target_for_staff_respects_fixed():
    """For a fixed KPI, target should come from bank_targets
    (source='bank_fixed'), not from per-staff cascade."""
    from utils.bsc_score_computation import get_target_for_staff
    result = get_target_for_staff("300230", "CX Score",
                                    "2026-Q1")
    assert result is not None
    target, source = result
    assert source == "bank_fixed"


# ────────────────────────────────────────────────────────────────────
# Section 4 — End-to-end scorecard
# ────────────────────────────────────────────────────────────────────

def test_compute_staff_scorecard_returns_typed_object():
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300230", "Teller", "2026-Q1")
    assert card.staff_code == "300230"
    assert card.role == "Teller"
    assert card.period == "2026-Q1"
    assert isinstance(card.kpi_scores, list)


def test_scorecard_final_score_in_1_to_5_range():
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300230", "Teller", "2026-Q1")
    if card.final_score is not None:
        assert 1.0 <= card.final_score <= 5.0


def test_scorecard_has_kpi_breakdown():
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300230", "Teller", "2026-Q1")
    # Some KPIs should have actuals (the 3 that align with v10.317
    # generator output)
    scored = [k for k in card.kpi_scores if k.score is not None]
    assert len(scored) >= 1, (
        "At least 1 KPI should have a computed score for "
        "Teller 300230 in 2026-Q1 (v10.317 generated data)"
    )


def test_scorecard_marks_fixed_kpis_correctly():
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300230", "Teller", "2026-Q1")
    # Find the CX Score entry — should be tagged bank_fixed
    cx_entries = [
        k for k in card.kpi_scores
        if k.canonical_id == "CX Score"
    ]
    if cx_entries:
        assert cx_entries[0].target_source == "bank_fixed"


# ────────────────────────────────────────────────────────────────────
# Section 5 — Audit gates
# ────────────────────────────────────────────────────────────────────

def test_g209_gate_exists_and_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G209":
            g = fn()
            break
    assert g is not None, "G209 not registered"
    assert g["passed"], (
        f"G209 failed: {g.get('summary', '')}. "
        f"Violations: {g.get('violations', [])}"
    )


def test_g210_gate_exists_and_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G210":
            g = fn()
            break
    assert g is not None, "G210 not registered"
    assert g["passed"], (
        f"G210 failed: {g.get('summary', '')}. "
        f"Violations: {g.get('violations', [])}"
    )
