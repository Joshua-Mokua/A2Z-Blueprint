"""Integration tests for v10.338 — SBU Drill-Down + Canonical Segment Lock.

15 tests across 6 sections:
  Section 1 — Segment config + classifier (3 tests)
  Section 2 — Customer migration integrity (3 tests)
  Section 3 — Business customer synthesis (2 tests)
  Section 4 — SBU rollup engine (3 tests)
  Section 5 — Balance sheet engine (2 tests)
  Section 6 — Audit gate G227 (2 tests)
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(modname):
    for k in list(sys.modules):
        if k.startswith(modname):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — segment_config + classifier
# ────────────────────────────────────────────────────────────────────

def test_v10338_segment_config_locked_codes():
    """Canonical codes locked; display names + thresholds present."""
    cfg = json.loads((REPO / "data" / "segment_config.json").read_text())
    ind_codes = {t["code"] for t in cfg["individual_tiers"]}
    biz_codes = {t["code"] for t in cfg["business_tiers"]}
    assert ind_codes == {"AFFLUENT", "CORE_MIDDLE", "MASS"}
    assert biz_codes == {"MICRO", "SMALL", "MEDIUM", "CORPORATE"}
    # Every tier has thresholds + display_name
    for t in cfg["individual_tiers"]:
        assert "trb_min_kes" in t
        assert "display_name" in t
    for t in cfg["business_tiers"]:
        assert "turnover_min_kes" in t
        assert "display_name" in t
        assert "in_msme" in t


def test_v10338_classifier_smoke():
    """Threshold classification works in all bands."""
    _reimport("utils.segment_classifier")
    from utils.segment_classifier import (
        classify_individual, classify_business, UNCLASSIFIED,
    )
    # Individual
    assert classify_individual(10_000_000) == "AFFLUENT"
    assert classify_individual(1_000_000) == "CORE_MIDDLE"
    assert classify_individual(50_000) == "MASS"
    assert classify_individual(None) == UNCLASSIFIED
    # Business
    assert classify_business(10_000_000) == "MICRO"
    assert classify_business(50_000_000) == "SMALL"
    assert classify_business(250_000_000) == "MEDIUM"
    assert classify_business(1_000_000_000) == "CORPORATE"
    assert classify_business("not a number") == UNCLASSIFIED


def test_v10338_msme_membership():
    """MSME = Micro + Small + Medium. Corporate is NOT MSME."""
    _reimport("utils.segment_classifier")
    from utils.segment_classifier import is_in_msme
    for code in ("MICRO", "SMALL", "MEDIUM"):
        assert is_in_msme(code), f"{code} should be in MSME"
    assert not is_in_msme("CORPORATE"), "CORPORATE not in MSME"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Customer migration integrity
# ────────────────────────────────────────────────────────────────────

def test_v10338_individual_migration_complete():
    """Every individual customer has a canonical segment_code."""
    cis = json.loads(
        (REPO / "data" / "customer_intelligence.json").read_text()
    )
    valid = {"AFFLUENT", "CORE_MIDDLE", "MASS"}
    invalid = [
        cif for cif, r in cis.items()
        if isinstance(r, dict)
        and r.get("customer_type", "individual") == "individual"
        and r.get("segment_code") not in valid
    ]
    assert not invalid, f"{len(invalid)} customers without canonical code"


def test_v10338_migration_reversible():
    """Migration tags _v10338_previous_segment on every record."""
    cis = json.loads(
        (REPO / "data" / "customer_intelligence.json").read_text()
    )
    untagged = [
        cif for cif, r in cis.items()
        if isinstance(r, dict)
        and r.get("customer_type", "individual") == "individual"
        and "_v10338_previous_segment" not in r
    ]
    assert not untagged, f"{len(untagged)} records lack rollback tag"

    # Rollback log exists
    rollback = json.loads(
        (REPO / "data" / "_v10338_segment_migration.json").read_text()
    )
    assert rollback["shipped"] == "v10.338"
    assert "mapping_used" in rollback


def test_v10338_segment_distribution_reasonable():
    """After migration, no segment has zero customers."""
    cis = json.loads(
        (REPO / "data" / "customer_intelligence.json").read_text()
    )
    from collections import Counter
    counts = Counter(
        r.get("segment_code") for r in cis.values()
        if isinstance(r, dict)
        and r.get("customer_type", "individual") == "individual"
    )
    for code in ("AFFLUENT", "CORE_MIDDLE", "MASS"):
        assert counts[code] > 0, f"{code} has zero customers"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Business customer synthesis
# ────────────────────────────────────────────────────────────────────

def test_v10338_business_dataset_present():
    """≥150 business customers synthesized from pipeline."""
    biz_path = REPO / "data" / "customer_intelligence_business.json"
    assert biz_path.exists()
    biz = json.loads(biz_path.read_text())
    assert len(biz) >= 150, f"only {len(biz)} business customers"
    # Every record has the required fields
    for cif, rec in biz.items():
        assert rec.get("customer_type") == "business"
        assert rec.get("segment_code") in {
            "MICRO", "SMALL", "MEDIUM", "CORPORATE", "UNCLASSIFIED"
        }
        assert "cbk_sector" in rec
        assert "annual_turnover_kes" in rec


def test_v10338_businesses_span_msme_and_corporate():
    """Synthesis produces customers in BOTH MSME and Corporate."""
    biz = json.loads(
        (REPO / "data" / "customer_intelligence_business.json").read_text()
    )
    codes = {r.get("segment_code") for r in biz.values()}
    msme_present = bool(codes & {"MICRO", "SMALL", "MEDIUM"})
    assert msme_present, "no MSME businesses"
    assert "CORPORATE" in codes, "no Corporate businesses"


# ────────────────────────────────────────────────────────────────────
# Section 4 — SBU rollup engine
# ────────────────────────────────────────────────────────────────────

def test_v10338_rollup_by_segment_returns_all_codes():
    """rollup_by_segment covers every canonical code with data."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import rollup_by_segment
    segs = rollup_by_segment("2026-Q2")
    for code in ("AFFLUENT", "CORE_MIDDLE", "MASS",
                 "MICRO", "SMALL", "MEDIUM", "CORPORATE"):
        assert code in segs, f"{code} missing from rollup"
        assert segs[code]["customer_count"] > 0


def test_v10338_segment_reconciles_to_bank():
    """Q5(a) integrity — segment sum reconciles to bank total."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import reconcile_to_bank
    rec = reconcile_to_bank("2026-Q2")
    assert rec["reconciles"], (
        f"delta={rec['delta_kes']}, tolerance={rec['tolerance_kes']}"
    )


def test_v10338_proposition_rollup_view_only_meta():
    """Proposition overlay flagged view-only per Q3(a)."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import rollup_meta
    m = rollup_meta()
    assert m["proposition_rollup_view_only"] is True
    # Bank-total reconciliation = TRUE for primary segments;
    # propositions are explicitly excluded from that contract
    assert m["reconciles_to_bank_total"] is True


# ────────────────────────────────────────────────────────────────────
# Section 5 — Balance sheet
# ────────────────────────────────────────────────────────────────────

def test_v10338_balance_sheet_bcbs_capital_allocation():
    """Equity = RWA × 12.5% (BCBS standardised)."""
    _reimport("utils.segment_balance_sheet")
    from utils.segment_balance_sheet import bank_balance_sheet
    bank = bank_balance_sheet("2026-Q2")
    # Within rounding, equity = 12.5% of RWA
    rwa = bank["rwa"]
    eq = bank["equity"]
    if rwa > 0:
        ratio = eq / rwa * 100.0
        assert abs(ratio - 12.5) < 0.01, f"ratio={ratio}"


def test_v10338_capital_adequacy_present():
    """Bank-wide capital adequacy meets BCBS minimum on virtual bank data."""
    _reimport("utils.segment_balance_sheet")
    from utils.segment_balance_sheet import capital_adequacy_check
    ca = capital_adequacy_check("2026-Q2")
    assert ca["ratio_pct"] is not None
    assert ca["minimum_pct"] == 12.5
    # By construction (equity = RWA × 12.5%), ratio is exactly 12.5
    assert ca["adequate"] is True


# ────────────────────────────────────────────────────────────────────
# Section 6 — G227 gate
# ────────────────────────────────────────────────────────────────────

def test_v10338_g227_gate_passes():
    """G227 audit gate registered and passing."""
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_sbu_drilldown_integration
    result = gate_sbu_drilldown_integration()
    assert result["passed"], (
        f"G227 violations: {result.get('violations')}"
    )
    assert result["id"] == "G227"
    assert result["name"] == "sbu_drilldown_integration"


def test_v10338_drilldown_page_registered():
    """114_sbu_drilldown.py present + in manifest with ≤7 tabs."""
    page_path = REPO / "pages" / "114_sbu_drilldown.py"
    assert page_path.exists()
    text = page_path.read_text()
    import re
    idx = text.find("st.tabs([")
    assert idx >= 0
    end = text.find("])", idx)
    entries = re.findall(r'"[^"]+"|\'[^\']+\'', text[idx:end])
    assert len(entries) <= 7, f"tab count={len(entries)}"
    # Manifest registration
    mfst = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "114_sbu_drilldown.py" in mfst.get("pages", {})
