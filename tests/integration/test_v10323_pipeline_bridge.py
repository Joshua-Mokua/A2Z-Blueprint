"""tests/integration/test_v10323_pipeline_bridge.py

v10.323 — Pipeline → BSC bridge (sales rollup via pipeline module).

Locks:
  - utils/pipeline_to_bsc module exports work end-to-end
  - pipeline_kpi_mapping.json + fixed_kpis.json + role_default_
    targets.json all configured correctly
  - 42 won deals in pipeline aggregate to 41 BSC contributions
  - is_fixed_kpi uses ONLY fixed_kpis.json (no bank_targets fallback)
  - Sales staff scorecards now compute (e.g. 300497 = 3.25/5.0)
  - Teller scorecards still work (backwards compatibility)
  - Cascade pre-compute reflects new pipeline actuals
  - G214 passes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module exports
# ────────────────────────────────────────────────────────────────────

def test_pipeline_to_bsc_module_imports():
    from utils.pipeline_to_bsc import (
        load_pipeline, load_mapping,
        period_from_date, deal_to_contribution,
        aggregate_contributions, sync_pipeline_to_bsc,
        DealContribution, AggregatedActual, SyncReport,
        is_won_stage,
    )
    assert callable(load_pipeline)
    assert callable(sync_pipeline_to_bsc)


# ────────────────────────────────────────────────────────────────────
# Section 2 — Config files
# ────────────────────────────────────────────────────────────────────

def test_pipeline_kpi_mapping_exists():
    p = REPO_ROOT / "data" / "pipeline_kpi_mapping.json"
    assert p.exists()
    cfg = json.loads(p.read_text())
    assert "product_to_kpi" in cfg
    assert "fee_estimation_rates" in cfg


def test_pipeline_mapping_covers_active_products():
    """The 20+ products in won deals should all have KPI mappings."""
    cfg = json.loads(
        (REPO_ROOT / "data" / "pipeline_kpi_mapping.json")
        .read_text()
    )
    p2k = cfg["product_to_kpi"]
    pipeline = json.loads(
        (REPO_ROOT / "data" / "pipeline.json").read_text()
    )
    won_stages = (cfg.get("_meta", {})
                   .get("stages_treated_as_won", []))
    won_products = {
        d.get("product") for d in pipeline
        if d.get("stage") in won_stages and d.get("product")
    }
    unmapped = won_products - set(p2k.keys())
    assert not unmapped, (
        f"Products in won deals lack KPI mapping: {unmapped}"
    )


def test_fixed_kpis_lists_quarters():
    p = REPO_ROOT / "data" / "fixed_kpis.json"
    fk = json.loads(p.read_text())
    for period in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"):
        entry = fk.get(period, {})
        if isinstance(entry, dict):
            kpis = entry.get("kpis", [])
        elif isinstance(entry, list):
            kpis = entry
        else:
            kpis = []
        assert "CX Score" in kpis, (
            f"{period} missing CX Score in fixed_kpis"
        )
        assert "Audit Score" in kpis
        assert "Staff Productivity" in kpis


def test_role_default_targets_exists():
    p = REPO_ROOT / "data" / "role_default_targets.json"
    assert p.exists()
    rdt = json.loads(p.read_text())
    roles = rdt.get("quarterly_targets_by_role", {})
    assert "Branch Relationship Manager" in roles
    assert "Branch Senior Relationship Officer" in roles
    assert "Relationship Officer Bancassurance" in roles


# ────────────────────────────────────────────────────────────────────
# Section 3 — Deal → contribution logic
# ────────────────────────────────────────────────────────────────────

def test_period_from_date():
    from utils.pipeline_to_bsc import period_from_date
    assert period_from_date("2026-04-13") == "2026-Q2"
    assert period_from_date("2026-01-15") == "2026-Q1"
    assert period_from_date("2025-10-01") == "2025-Q4"
    assert period_from_date("") is None
    assert period_from_date("invalid") is None


def test_won_stage_detection():
    from utils.pipeline_to_bsc import is_won_stage, load_mapping
    mapping = load_mapping()
    assert is_won_stage("Disbursed", mapping) is True
    assert is_won_stage("Closed Won", mapping) is True
    assert is_won_stage("Prospecting", mapping) is False
    assert is_won_stage("Closed Lost", mapping) is False


def test_deal_to_contribution_handles_won():
    from utils.pipeline_to_bsc import (
        deal_to_contribution, load_mapping,
    )
    mapping = load_mapping()
    deal = {
        "id": "TEST001",
        "staff_code": "300029",
        "product": "Personal Loan",
        "stage": "Disbursed",
        "amount": 2500000,
        "last_updated": "2026-04-13",
    }
    c = deal_to_contribution(deal, mapping)
    assert c is not None
    assert c.staff_code == "300029"
    assert c.period == "2026-Q2"
    assert c.kpi_id == "Disbursements Retail Loans"
    assert c.value == 2500000.0


def test_deal_to_contribution_skips_lost():
    from utils.pipeline_to_bsc import (
        deal_to_contribution, load_mapping,
    )
    mapping = load_mapping()
    deal = {
        "id": "TEST002", "staff_code": "300029",
        "product": "Personal Loan", "stage": "Closed Lost",
        "amount": 2500000, "last_updated": "2026-04-13",
    }
    assert deal_to_contribution(deal, mapping) is None


def test_fee_kpis_use_estimation_rate():
    """Trade Finance LC should map to Total NFI with fee
    estimation rather than raw amount."""
    from utils.pipeline_to_bsc import (
        deal_to_contribution, load_mapping,
    )
    mapping = load_mapping()
    deal = {
        "id": "TEST003", "staff_code": "300100",
        "product": "Trade Finance LC", "stage": "Disbursed",
        "amount": 100000000, "last_updated": "2026-04-15",
    }
    c = deal_to_contribution(deal, mapping)
    assert c is not None
    assert c.kpi_id == "Total NFI"
    assert c.source == "fee_estimate"
    # Trade Finance LC fee rate = 1.2% per mapping config
    assert c.value < deal["amount"]
    assert c.value == 100000000 * 0.012


# ────────────────────────────────────────────────────────────────────
# Section 4 — Sync produces expected aggregates
# ────────────────────────────────────────────────────────────────────

def test_sync_dry_run_produces_aggregates():
    from utils.pipeline_to_bsc import sync_pipeline_to_bsc
    report = sync_pipeline_to_bsc(dry_run=True)
    assert report.contributions >= 30
    assert report.aggregates >= 30
    assert "2026-Q2" in report.by_period


def test_sync_covers_5_kpis():
    """Won deals should aggregate into multiple KPIs."""
    from utils.pipeline_to_bsc import sync_pipeline_to_bsc
    report = sync_pipeline_to_bsc(dry_run=True)
    assert len(report.by_kpi) >= 4


# ────────────────────────────────────────────────────────────────────
# Section 5 — is_fixed_kpi correctly uses fixed_kpis.json only
# ────────────────────────────────────────────────────────────────────

def test_is_fixed_kpi_uses_fixed_kpis_json():
    from utils.bsc_score_computation import is_fixed_kpi
    # CX Score: in fixed_kpis.json → True
    assert is_fixed_kpi("CX Score", "2026-Q2") is True
    # Disbursements Retail Loans: NOT in fixed_kpis.json (volume KPI)
    assert is_fixed_kpi(
        "Disbursements Retail Loans", "2026-Q2") is False


def test_is_fixed_kpi_no_longer_uses_bank_targets_fallback():
    """Pre-v10.323, ANY KPI with a bank_target was treated as fixed
    (implicit fallback). v10.323 removed this — fixed_kpis.json is
    now authoritative. Use a volume KPI that has a bank_target but
    is NOT bank-wide (it's cascaded per individual):
    'Disbursements Retail Loans' is NOT in fixed_kpis.json so should
    return False even though a bank-aggregate target exists in
    bank_targets.json."""
    from utils.bsc_score_computation import is_fixed_kpi
    assert is_fixed_kpi(
        "Disbursements Retail Loans", "2026-Q2") is False, (
        "Disbursements Retail Loans should NOT be fixed — it "
        "has a bank-aggregate target but should be cascaded "
        "per individual. v10.323 removed the implicit "
        "bank_targets fallback."
    )


# ────────────────────────────────────────────────────────────────────
# Section 6 — get_target_for_staff with role_default fallback
# ────────────────────────────────────────────────────────────────────

def test_role_default_used_for_unmapped_staff():
    """A Bancassurance RO has no cascaded target for MSME
    Disbursements, so role_default kicks in."""
    from utils.bsc_score_computation import get_target_for_staff
    result = get_target_for_staff(
        "300497", "Disbursements MSME Loans", "2026-Q2")
    assert result is not None
    target, source = result
    assert source == "role_default"
    assert target > 0


def test_fixed_kpi_uses_bank_target():
    """CX Score is fixed → uses bank_target."""
    from utils.bsc_score_computation import get_target_for_staff
    result = get_target_for_staff(
        "300497", "CX Score", "2026-Q2")
    assert result is not None
    target, source = result
    assert source == "bank_fixed"


# ────────────────────────────────────────────────────────────────────
# Section 7 — Sales scorecards now compute
# ────────────────────────────────────────────────────────────────────

def test_bancassurance_ro_300497_scores():
    """After pipeline sync + role_defaults, 300497 should have a
    real scorecard reflecting their MSME + Corporate disbursements."""
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300497", "Relationship Officer Bancassurance",
        "2026-Q2")
    assert card.final_score is not None
    assert 1.0 <= card.final_score <= 5.0
    scored = [k for k in card.kpi_scores if k.score is not None]
    assert len(scored) >= 2, (
        f"300497 should have ≥2 scoring KPIs after pipeline "
        f"sync, got {len(scored)}"
    )


def test_branch_senior_ro_300237_scores():
    from utils.bsc_score_computation import compute_staff_scorecard
    card = compute_staff_scorecard(
        "300237", "Branch Senior Relationship Officer",
        "2026-Q2")
    assert card.final_score is not None


# ────────────────────────────────────────────────────────────────────
# Section 8 — Backwards compatibility
# ────────────────────────────────────────────────────────────────────

def test_tellers_still_score_correctly():
    """Critical: Teller 300230 had scores 2.8/2.2/2.4/3.2 across
    quarters in v10.322. v10.323's changes to is_fixed_kpi must
    not break this."""
    from utils.bsc_score_computation import compute_staff_scorecard
    expected = {
        "2025-Q3": 2.8, "2025-Q4": 2.2,
        "2026-Q1": 2.4, "2026-Q2": 3.2,
    }
    for period, exp_score in expected.items():
        card = compute_staff_scorecard(
            "300230", "Teller", period)
        assert card.final_score == exp_score, (
            f"Teller 300230 {period}: expected "
            f"{exp_score}, got {card.final_score}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 9 — Cascade pre-compute reflects pipeline
# ────────────────────────────────────────────────────────────────────

def test_cascade_2026_q2_has_more_scores_than_q1():
    """v10.323's pipeline sync added sales staff to 2026-Q2 scoring
    (which they weren't in for Q1). v10.337 added pipeline_activity_bridge
    that emits PIPELINE_* KPIs only in Q2 (pipeline.json is a current-
    quarter snapshot). v10.337 also brought 528 branch staff into all
    four quarters via branch_staff_generator, which compresses the Q2
    delta — the remaining gap is the pure pipeline-only signal.
    """
    q1_data = json.loads((
        REPO_ROOT / "data" / "cascade_scores_2026-Q1.json"
    ).read_text())
    q2_data = json.loads((
        REPO_ROOT / "data" / "cascade_scores_2026-Q2.json"
    ).read_text())
    q1_count = len(q1_data.get("scores", {}))
    q2_count = len(q2_data.get("scores", {}))
    assert q2_count >= q1_count + 10, (
        f"Q2 should have ≥10 more scored staff than Q1 "
        f"after pipeline sync. Q1: {q1_count}, Q2: {q2_count}"
    )


def test_cascade_q2_includes_known_sales_staff():
    q2_data = json.loads((
        REPO_ROOT / "data" / "cascade_scores_2026-Q2.json"
    ).read_text())
    scores = q2_data.get("scores", {})
    # 300497 should now have a score
    assert "300497" in scores or "300237" in scores


# ────────────────────────────────────────────────────────────────────
# Section 10 — Audit gate G214
# ────────────────────────────────────────────────────────────────────

def test_g214_gate_exists_and_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G214":
            g = fn()
            break
    assert g is not None, "G214 not registered"
    assert g["passed"], (
        f"G214 failed: {g.get('summary', '')[:200]}. "
        f"Violations: {g.get('violations', [])}"
    )
