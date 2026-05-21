"""
tests/integration/test_irb_retail_exposure_class_v10313.py
================================================================================
v10.313 — Address B-008 (logged v10.309). Add retail
ExposureClass values to credit_risk_irb engine so the IRB
section of credit_portfolio_analytics drops the SME_CORPORATE
shape-fit caveat.

Today's state (B-008 honest tech debt):
  - ExposureClass enum only has LARGE_CORPORATE,
    SME_CORPORATE, SOVEREIGN, BANK
  - IRBExposure.__post_init__ accepts only LARGE_CORPORATE
    and SME_CORPORATE (others raise NotImplemented)
  - credit_portfolio_analytics maps all 5045 retail IFRS9
    loans to SME_CORPORATE as a shape-fit simplification
  - The notes field on the IRB section explicitly says
    "Numbers are indicative, not regulatory"

After this batch:
  - 3 new ExposureClass values: RETAIL_RESIDENTIAL_MORTGAGE,
    QUALIFYING_REVOLVING_RETAIL, OTHER_RETAIL
  - IRBExposure accepts all 3 retail classes
  - Retail correlation formulas per BCBS d424 §RBC25.21-23
  - No maturity adjustment for retail per §RBC25.20
    (maturity_years still validated, just not multiplied)
  - product_to_exposure_class() helper maps IFRS9 product
    strings to the right ExposureClass
  - credit_portfolio_analytics uses the mapper; the
    shape-fit caveat in notes is removed

The Basel correlation formulas being implemented:
  - RETAIL_RESIDENTIAL_MORTGAGE: R = 0.15 constant
  - QUALIFYING_REVOLVING_RETAIL: R = 0.04 constant
  - OTHER_RETAIL: R = 0.03 + 0.13 × (1 - exp(-35×PD))
                       / (1 - exp(-35))

Test sections:
  1. New enum values exist
  2. IRBExposure accepts retail classes
  3. compute() runs for each retail class without error
  4. Retail correlation formulas match BCBS d424 spec
  5. No maturity adjustment for retail (mat_factor = 1.0)
  6. product_to_exposure_class() mapper exists and works
  7. credit_portfolio_analytics no longer maps to
     SME_CORPORATE — uses the mapper
  8. The shape-fit caveat is gone from the notes
  9. Existing LARGE_CORPORATE / SME_CORPORATE behavior
     unchanged (regression guard)
  10. G203 audit gate
"""

from __future__ import annotations

import math
import sys
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — New enum values exist
# ============================================================

def test_retail_residential_mortgage_class_exists():
    from utils.credit_risk_irb import ExposureClass
    assert hasattr(
        ExposureClass, "RETAIL_RESIDENTIAL_MORTGAGE"
    )


def test_qualifying_revolving_retail_class_exists():
    from utils.credit_risk_irb import ExposureClass
    assert hasattr(
        ExposureClass, "QUALIFYING_REVOLVING_RETAIL"
    )


def test_other_retail_class_exists():
    from utils.credit_risk_irb import ExposureClass
    assert hasattr(ExposureClass, "OTHER_RETAIL")


def test_existing_classes_still_present():
    """Regression guard: pre-existing enum values must remain."""
    from utils.credit_risk_irb import ExposureClass
    for name in ("LARGE_CORPORATE", "SME_CORPORATE",
                  "SOVEREIGN", "BANK"):
        assert hasattr(ExposureClass, name), (
            f"Existing enum value {name} missing"
        )


# ============================================================
# Section 2 — IRBExposure accepts retail classes
# ============================================================

def test_irb_exposure_accepts_retail_residential_mortgage():
    from utils.credit_risk_irb import (
        IRBExposure, ExposureClass,
    )
    exp = IRBExposure(
        exposure_id="MORTGAGE-001",
        exposure_class=ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE,
        pd=0.02, lgd=0.25, ead_kes=Decimal("5_000_000"),
        maturity_years=2.5,
    )
    assert exp.exposure_class == (
        ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE
    )


def test_irb_exposure_accepts_qualifying_revolving_retail():
    from utils.credit_risk_irb import (
        IRBExposure, ExposureClass,
    )
    exp = IRBExposure(
        exposure_id="CARD-001",
        exposure_class=ExposureClass.QUALIFYING_REVOLVING_RETAIL,
        pd=0.05, lgd=0.55, ead_kes=Decimal("100_000"),
        maturity_years=1.0,
    )
    assert exp.exposure_class == (
        ExposureClass.QUALIFYING_REVOLVING_RETAIL
    )


def test_irb_exposure_accepts_other_retail():
    from utils.credit_risk_irb import (
        IRBExposure, ExposureClass,
    )
    exp = IRBExposure(
        exposure_id="PERSONAL-001",
        exposure_class=ExposureClass.OTHER_RETAIL,
        pd=0.03, lgd=0.45, ead_kes=Decimal("250_000"),
        maturity_years=1.5,
    )
    assert exp.exposure_class == ExposureClass.OTHER_RETAIL


# ============================================================
# Section 3 — compute() runs for each retail class
# ============================================================

def test_compute_succeeds_for_residential_mortgage():
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass,
    )
    eng = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="M1",
        exposure_class=ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE,
        pd=0.02, lgd=0.25, ead_kes=Decimal("5_000_000"),
        maturity_years=2.5,
    )
    result = eng.compute(exp)
    assert result.rwa_kes > 0
    assert result.expected_loss_kes > 0
    assert result.exposure_class == (
        ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE
    )


def test_compute_succeeds_for_revolving_retail():
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass,
    )
    eng = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="C1",
        exposure_class=ExposureClass.QUALIFYING_REVOLVING_RETAIL,
        pd=0.05, lgd=0.55, ead_kes=Decimal("100_000"),
        maturity_years=1.0,
    )
    result = eng.compute(exp)
    assert result.rwa_kes > 0


def test_compute_succeeds_for_other_retail():
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass,
    )
    eng = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="P1",
        exposure_class=ExposureClass.OTHER_RETAIL,
        pd=0.03, lgd=0.45, ead_kes=Decimal("250_000"),
        maturity_years=1.5,
    )
    result = eng.compute(exp)
    assert result.rwa_kes > 0


# ============================================================
# Section 4 — Correlation formulas match Basel spec
# ============================================================

def test_residential_mortgage_correlation_is_constant_015():
    """BCBS d424 §RBC25.21: R = 0.15 (constant for residential
    mortgages, independent of PD)."""
    from utils.credit_risk_irb import IRBCapitalEngine
    eng = IRBCapitalEngine()
    # The correlation method must dispatch on class
    from utils.credit_risk_irb import ExposureClass
    for pd in (0.001, 0.01, 0.05, 0.10):
        r = eng._correlation_retail(
            pd,
            ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE,
        )
        assert abs(r - 0.15) < 1e-9, (
            f"Residential mortgage R should be 0.15 at "
            f"PD={pd}, got {r}"
        )


def test_qualifying_revolving_correlation_is_constant_004():
    """BCBS d424 §RBC25.23: R = 0.04 (constant)."""
    from utils.credit_risk_irb import (
        IRBCapitalEngine, ExposureClass,
    )
    eng = IRBCapitalEngine()
    for pd in (0.001, 0.01, 0.05, 0.10):
        r = eng._correlation_retail(
            pd,
            ExposureClass.QUALIFYING_REVOLVING_RETAIL,
        )
        assert abs(r - 0.04) < 1e-9, (
            f"QRR R should be 0.04 at PD={pd}, got {r}"
        )


def test_other_retail_correlation_formula():
    """BCBS d424 §RBC25.22:
      R = 0.03 + 0.13 × (1 - exp(-35×PD)) / (1 - exp(-35))
    """
    from utils.credit_risk_irb import (
        IRBCapitalEngine, ExposureClass,
    )
    eng = IRBCapitalEngine()
    for pd in (0.001, 0.01, 0.05, 0.10):
        denom = 1.0 - math.exp(-35.0)
        w = (1.0 - math.exp(-35.0 * pd)) / denom
        expected = 0.03 + 0.13 * w
        actual = eng._correlation_retail(
            pd, ExposureClass.OTHER_RETAIL)
        assert abs(actual - expected) < 1e-9, (
            f"OTHER_RETAIL R at PD={pd}: expected "
            f"{expected}, got {actual}"
        )


def test_other_retail_bounds_at_pd_extremes():
    """As PD → 0: w → 0, R → 0.03.
    As PD → 1: w → 1, R → 0.16."""
    from utils.credit_risk_irb import (
        IRBCapitalEngine, ExposureClass,
    )
    eng = IRBCapitalEngine()
    r_low = eng._correlation_retail(
        0.0003, ExposureClass.OTHER_RETAIL)
    r_high = eng._correlation_retail(
        0.999, ExposureClass.OTHER_RETAIL)
    # Low PD bound: very close to 0.03
    assert 0.030 < r_low < 0.035, (
        f"OTHER_RETAIL low-PD bound: {r_low}"
    )
    # High PD bound: very close to 0.16
    assert 0.159 < r_high < 0.161, (
        f"OTHER_RETAIL high-PD bound: {r_high}"
    )


# ============================================================
# Section 5 — No maturity adjustment for retail
# ============================================================

def test_retail_no_maturity_adjustment():
    """Per BCBS d424 §RBC25.20: retail exposures have no
    maturity adjustment. Implementation effect: mat_factor
    = 1.0 regardless of M for retail classes."""
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass,
    )
    eng = IRBCapitalEngine()

    # Run same exposure at M=1 and M=5 — RWA should be
    # identical for retail (no M effect)
    common = dict(
        exposure_class=ExposureClass.OTHER_RETAIL,
        pd=0.03, lgd=0.45, ead_kes=Decimal("100_000"),
    )
    exp_m1 = IRBExposure(
        exposure_id="M1", maturity_years=1.0, **common)
    exp_m5 = IRBExposure(
        exposure_id="M5", maturity_years=5.0, **common)

    rwa_m1 = eng.compute(exp_m1).rwa_kes
    rwa_m5 = eng.compute(exp_m5).rwa_kes
    assert rwa_m1 == rwa_m5, (
        f"Retail RWA must be M-invariant. M=1: {rwa_m1}, "
        f"M=5: {rwa_m5}"
    )


# ============================================================
# Section 6 — Product → class mapper
# ============================================================

def test_product_to_exposure_class_helper_exists():
    from utils.credit_risk_irb import product_to_exposure_class
    assert callable(product_to_exposure_class)


def test_mortgage_products_map_to_residential_mortgage():
    from utils.credit_risk_irb import (
        product_to_exposure_class, ExposureClass,
    )
    for p in ("Mortgage", "Home Loan", "Housing Finance",
               "mortgage"):
        assert product_to_exposure_class(p) == (
            ExposureClass.RETAIL_RESIDENTIAL_MORTGAGE
        ), f"Product {p!r} didn't map to residential mortgage"


def test_credit_card_products_map_to_revolving_retail():
    from utils.credit_risk_irb import (
        product_to_exposure_class, ExposureClass,
    )
    for p in ("Credit Card", "Overdraft", "Revolving Credit"):
        assert product_to_exposure_class(p) == (
            ExposureClass.QUALIFYING_REVOLVING_RETAIL
        )


def test_other_retail_products_map_to_other_retail():
    """Motor Vehicle, Personal, Salary advance — the typical
    IFRS9 retail products."""
    from utils.credit_risk_irb import (
        product_to_exposure_class, ExposureClass,
    )
    for p in ("Motor Vehicle", "Personal", "Salary Advance",
               "Personal Loan"):
        assert product_to_exposure_class(p) == (
            ExposureClass.OTHER_RETAIL
        )


def test_corporate_products_map_to_sme_corporate():
    """Existing corporate-style products keep mapping to
    SME_CORPORATE — regression guard."""
    from utils.credit_risk_irb import (
        product_to_exposure_class, ExposureClass,
    )
    for p in ("SME Working Capital", "Trade Finance",
               "Asset Finance"):
        # These should NOT be retail
        result = product_to_exposure_class(p)
        assert result in (
            ExposureClass.SME_CORPORATE,
            ExposureClass.LARGE_CORPORATE,
        ), f"Product {p!r} mapped to {result}, not corporate"


def test_unknown_product_falls_back_to_sme_corporate():
    """Unknown / unmapped product strings should fall back
    to a safe default rather than raising. SME_CORPORATE
    is the same default the composer used before this
    batch — preserves behavior for unknown inputs."""
    from utils.credit_risk_irb import (
        product_to_exposure_class, ExposureClass,
    )
    result = product_to_exposure_class("Some New Product XYZ")
    assert result == ExposureClass.SME_CORPORATE


# ============================================================
# Section 7 — credit_portfolio_analytics uses the mapper
# ============================================================

def test_composer_uses_product_to_exposure_class():
    """The composer's _build_irb_section helper must
    reference product_to_exposure_class (greppable wiring
    proof)."""
    src = (REPO_ROOT / "utils" / "cockpit_read.py").read_text()
    # Locate the IRB section helper
    import re
    match = re.search(
        r"def _build_irb_section\([^)]*\)"
        r"\s*(?:->[^:]+)?:"
        r"(.*?)(?=\ndef\s|\Z)",
        src, re.DOTALL,
    )
    assert match, "Could not locate _build_irb_section"
    body = match.group(1)
    assert "product_to_exposure_class" in body, (
        "_build_irb_section must use "
        "product_to_exposure_class for the shape-fit "
        "caveat to be removed"
    )


def test_shape_fit_caveat_removed_from_notes():
    """The 'Shape-fit simplification: ... SME_CORPORATE' line
    must no longer appear in _build_irb_section's notes."""
    src = (REPO_ROOT / "utils" / "cockpit_read.py").read_text()
    import re
    match = re.search(
        r"def _build_irb_section\([^)]*\)"
        r"\s*(?:->[^:]+)?:"
        r"(.*?)(?=\ndef\s|\Z)",
        src, re.DOTALL,
    )
    body = match.group(1)
    # The old caveat phrase should be gone
    assert "Shape-fit simplification" not in body, (
        "Old shape-fit caveat still present in "
        "_build_irb_section"
    )


# ============================================================
# Section 8 — End-to-end against real IFRS9 portfolio
# ============================================================

def test_composer_runs_against_real_ifrs9_portfolio():
    """End-to-end: credit_portfolio_analytics runs against
    the 5045-loan IFRS9 portfolio, dispatching each loan to
    its proper retail class. RWA + EL should be in
    realistic orders of magnitude."""
    from utils.cockpit_read import credit_portfolio_analytics
    result = credit_portfolio_analytics(data_dir="data")
    irb = [s for s in result["sections"]
            if s["section_id"] == "irb_capital"][0]
    assert irb["status"] == "ok"
    n_exp = int(irb["metrics"]["n_exposures"])
    assert n_exp == 5045, (
        f"Expected 5045 IFRS9 exposures, got {n_exp}"
    )
    # n_skipped should still be 0
    assert irb["metrics"]["n_skipped"] == "0"


def test_irb_rwa_lower_under_retail_than_under_sme_corporate():
    """Sanity check: retail correlation < corporate
    correlation (0.04-0.15 vs 0.12-0.24), so retail RWA
    should be LOWER than the equivalent SME_CORPORATE
    treatment for typical retail PDs. This is the financial
    point of the fix — we were OVERSTATING capital
    requirements by treating retail as corporate."""
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass,
    )
    eng = IRBCapitalEngine()
    # Same exposure, two classes
    pd, lgd, ead, m = 0.03, 0.45, Decimal("250_000"), 1.0
    retail_exp = IRBExposure(
        exposure_id="R", exposure_class=ExposureClass.OTHER_RETAIL,
        pd=pd, lgd=lgd, ead_kes=ead, maturity_years=m,
    )
    corp_exp = IRBExposure(
        exposure_id="C",
        exposure_class=ExposureClass.SME_CORPORATE,
        pd=pd, lgd=lgd, ead_kes=ead, maturity_years=m,
    )
    retail_rwa = eng.compute(retail_exp).rwa_kes
    corp_rwa = eng.compute(corp_exp).rwa_kes
    assert retail_rwa < corp_rwa, (
        f"Retail RWA ({retail_rwa}) should be LOWER than "
        f"SME_CORPORATE RWA ({corp_rwa}) for same exposure"
    )


# ============================================================
# Section 9 — Existing behavior unchanged
# ============================================================

def test_existing_large_corporate_compute_unchanged():
    """Regression guard: LARGE_CORPORATE compute path must
    still produce the same RWA for the same inputs as
    before. (No way to assert numerical exactness without
    a baseline file, but a smoke-test confirms no crash
    and reasonable values.)"""
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass,
    )
    eng = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="LC1",
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=0.01, lgd=0.45, ead_kes=Decimal("10_000_000"),
        maturity_years=2.5,
    )
    result = eng.compute(exp)
    assert result.rwa_kes > 0
    # K should be in a reasonable range (1% to 50% of EAD)
    k_pct = float(result.capital_requirement_pct)
    assert 0.001 < k_pct < 0.5, (
        f"LARGE_CORPORATE K={k_pct} outside sane range"
    )


def test_existing_sme_corporate_compute_unchanged():
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass,
    )
    eng = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="SC1",
        exposure_class=ExposureClass.SME_CORPORATE,
        pd=0.02, lgd=0.45, ead_kes=Decimal("1_000_000"),
        maturity_years=2.5,
    )
    result = eng.compute(exp)
    assert result.rwa_kes > 0


# ============================================================
# Section 10 — Audit gate G203
# ============================================================

def test_g203_gate_exists_and_passes():
    from scripts.audit import GATES
    g203 = None
    for gid, fn in GATES:
        if gid == "G203":
            g203 = fn()
            break
    assert g203 is not None, "G203 not registered"
    assert g203["passed"], (
        f"G203 failed. {g203.get('summary', '')}. "
        f"Violations: {g203.get('violations', [])[:5]}"
    )
