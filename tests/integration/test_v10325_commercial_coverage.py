"""tests/integration/test_v10325_commercial_coverage.py

v10.325 — Commercial line pipeline coverage expansion.

Locks:
  - 8 strategic won deals seeded across CCMO subtree
  - pipeline_kpi_mapping extended with 7 new products
  - 2 missing role_default_targets added
  - All 4 CCMO sales Heads have scoring subordinates
  - MD score derived from 3 Chiefs
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Pipeline data expansion
# ────────────────────────────────────────────────────────────────────

def test_pipeline_has_v10325_seed_deals():
    """8 v10.325-tagged deals exist in pipeline."""
    pipe = json.loads(
        (REPO_ROOT / "data" / "pipeline.json").read_text())
    seeded = [d for d in pipe if d.get("_v10325_seed")]
    assert len(seeded) == 8, (
        f"Expected 8 v10.325 seeded deals, found {len(seeded)}"
    )


def test_seeded_deals_all_disbursed():
    """All 8 seeded deals are in Disbursed stage."""
    pipe = json.loads(
        (REPO_ROOT / "data" / "pipeline.json").read_text())
    seeded = [d for d in pipe if d.get("_v10325_seed")]
    for d in seeded:
        assert d.get("stage") == "Disbursed", (
            f"Deal {d.get('id')} stage is {d.get('stage')}, "
            f"expected Disbursed"
        )


def test_seeded_deals_under_ccmo():
    """All 8 seeded deals are under the CCMO subtree."""
    from utils.manager_rollup import _all_subordinate_codes
    ccmo_subs = set(_all_subordinate_codes("EXEC-CCMO-001"))
    pipe = json.loads(
        (REPO_ROOT / "data" / "pipeline.json").read_text())
    seeded = [d for d in pipe if d.get("_v10325_seed")]
    for d in seeded:
        sc = d.get("staff_code")
        assert sc in ccmo_subs, (
            f"Deal {d.get('id')} owner {sc} not in CCMO subtree"
        )


def test_pipeline_won_deals_increased():
    """Total won/disbursed deals ≥44 (was 36 pre-v10.325)."""
    pipe = json.loads(
        (REPO_ROOT / "data" / "pipeline.json").read_text())
    won_stages = {"Disbursed", "Closed Won", "Signed", "Documentation"}
    won = sum(1 for d in pipe if d.get("stage") in won_stages)
    assert won >= 44, f"Only {won} won deals, expected ≥44"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Configuration extensions
# ────────────────────────────────────────────────────────────────────

def test_pipeline_kpi_mapping_extended():
    """pipeline_kpi_mapping has 7 new product types."""
    m = json.loads(
        (REPO_ROOT / "data" / "pipeline_kpi_mapping.json").read_text())
    ptk = m.get("product_to_kpi", {})
    assert len(ptk) >= 38, (
        f"pipeline_kpi_mapping has only {len(ptk)} entries"
    )
    required = {
        "Corporate Loan": "Disbursements Corporate Loans",
        "SME Term Loan": "Disbursements MSME Loans",
        "Letter of Credit": "Total NFI",
        "Term Loan": "Disbursements Corporate Loans",
        "Working Capital Loan": "Disbursements Corporate Loans",
        "Bank Guarantee": "Total NFI",
        "Trade Loan": "Disbursements Corporate Loans",
    }
    for product, expected_kpi in required.items():
        assert ptk.get(product) == expected_kpi, (
            f"{product} maps to {ptk.get(product)}, "
            f"expected {expected_kpi}"
        )


def test_role_default_targets_extended():
    """role_default_targets has RM SME and RM Corporate."""
    rdt = json.loads(
        (REPO_ROOT / "data" / "role_default_targets.json").read_text())
    qtbr = rdt.get("quarterly_targets_by_role", {})
    assert "Relationship Manager - SME" in qtbr
    assert "Relationship Manager - Corporate Banking" in qtbr
    # Sanity check values
    rm_sme = qtbr["Relationship Manager - SME"]
    assert rm_sme.get("Disbursements MSME Loans") == 100000000
    rm_corp = qtbr["Relationship Manager - Corporate Banking"]
    assert rm_corp.get("Disbursements Corporate Loans") == 400000000


# ────────────────────────────────────────────────────────────────────
# Section 3 — Bridge picks up new deals
# ────────────────────────────────────────────────────────────────────

def test_bridge_contributions_include_ccmo():
    """Pipeline → BSC bridge produces contributions for CCMO RMs."""
    from utils.pipeline_to_bsc import all_contributions
    from utils.manager_rollup import _all_subordinate_codes
    contribs = all_contributions()
    ccmo_subs = set(_all_subordinate_codes("EXEC-CCMO-001"))
    ccmo_contribs = [c for c in contribs if c.staff_code in ccmo_subs]
    assert len(ccmo_contribs) >= 10, (
        f"Only {len(ccmo_contribs)} CCMO contributions, "
        f"expected ≥10 after v10.325"
    )


def test_corporate_loan_routed_to_corporate_kpi():
    """Corporate Loan deals must route to Disbursements Corporate Loans."""
    from utils.pipeline_to_bsc import (
        load_pipeline, load_mapping, deal_to_contribution
    )
    mapping = load_mapping()
    pipe = load_pipeline()
    found = False
    for d in pipe:
        if d.get("product") == "Corporate Loan" and d.get(
                "_v10325_seed"):
            c = deal_to_contribution(d, mapping)
            if c:
                assert c.kpi_id == "Disbursements Corporate Loans"
                found = True
                break
    assert found, "No Corporate Loan deal found to verify routing"


# ────────────────────────────────────────────────────────────────────
# Section 4 — CCMO subtree visibility in cascade
# ────────────────────────────────────────────────────────────────────

def test_all_four_ccmo_sales_heads_score():
    """Corporates, MSME, GIB, Trade Finance Heads all have scores."""
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    scores = cs.get("scores", {})
    sales_heads = {
        "300017": "Head of Corporates",
        "300018": "Head of MSME",
        "300019": "Head of GIB",
        "300043": "SRM Trade Finance Specialist",
    }
    for code, name in sales_heads.items():
        s = scores.get(code)
        assert s is not None, f"{name} ({code}) has no Q2 score"
        assert 1.0 <= s <= 5.0


def test_ccmo_recursive_score_in_range():
    """CCMO has a valid recursive score."""
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    ccmo = cs.get("scores", {}).get("EXEC-CCMO-001")
    assert ccmo is not None
    assert 1.0 <= ccmo <= 5.0


def test_md_score_derived_from_three_chiefs():
    """MD has scoring direct reports for Retail + Bancassurance + Commercial."""
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
    assert len(scoring) >= 3, (
        f"Only {len(scoring)} MD direct reports have scores"
    )


def test_ccmo_lowest_chief_score_for_demo_narrative():
    """For the demo, CCMO should be the lowest of the 3 scoring Chiefs
    — reflects thinner Commercial pipeline conversion. This isn't a
    hard invariant, but if it changes the narrative changes too."""
    cs = json.loads(
        (REPO_ROOT / "data" / "cascade_scores_2026-Q2.json").read_text())
    scores = cs.get("scores", {})
    ccmo = scores.get("EXEC-CCMO-001")
    cro = scores.get("EXEC-CRO-001")
    bancassurance = scores.get("300178")
    chiefs = [s for s in (ccmo, cro, bancassurance) if s is not None]
    assert len(chiefs) >= 3
    # Soft check: CCMO should be at or below median
    assert ccmo <= sorted(chiefs)[1], (
        f"CCMO {ccmo} unexpectedly above median chief score"
    )


# ────────────────────────────────────────────────────────────────────
# Section 5 — Individual scorecards sanity
# ────────────────────────────────────────────────────────────────────

def test_corporate_rm_scorecard_includes_disbursements():
    """A Corporate RM with a Disbursed deal should score on
    Disbursements Corporate Loans."""
    from utils.bsc_score_computation import compute_staff_scorecard
    # 300024 — RM Corporate, has 380M Corporate Loan in v10.325 seed
    card = compute_staff_scorecard(
        "300024", "Relationship Manager - Corporate Banking",
        "2026-Q2"
    )
    disb = [
        k for k in card.kpi_scores
        if k.canonical_id == "Disbursements Corporate Loans"
    ]
    assert disb, "RM Corporate scorecard missing DISB_CORPORATE KPI"
    assert disb[0].actual == 380000000.0


def test_sme_rm_scorecard_includes_msme_disbursements():
    """RM SME with seeded MSME deal should score on Disbursements MSME."""
    from utils.bsc_score_computation import compute_staff_scorecard
    # 300033 — RM SME, has 22.5M SME Term Loan in v10.325 seed
    card = compute_staff_scorecard(
        "300033", "Relationship Manager - SME", "2026-Q2"
    )
    disb = [
        k for k in card.kpi_scores
        if k.canonical_id == "Disbursements MSME Loans"
    ]
    assert disb, "RM SME scorecard missing DISB_MSME KPI"
    assert disb[0].actual == 22500000.0
    assert disb[0].target == 100000000.0  # role default
    assert disb[0].score == 1.0  # 22.5% achievement


# ────────────────────────────────────────────────────────────────────
# Section 6 — Audit gate G216
# ────────────────────────────────────────────────────────────────────

def test_g216_gate_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G216":
            g = fn()
            break
    assert g is not None, "G216 not registered"
    assert g["passed"], (
        f"G216 failed: violations={g.get('violations', [])}"
    )
