"""
================================================================================
A2Z MIS 360 — Standard #88: Pillar 3 Disclosure Generator
================================================================================

Risk classification: Cat B (deterministic Basel Pillar 3 disclosure assembly)

Generates Basel III Pillar 3 quantitative + qualitative disclosures
(per BCBS 309 + BCBS 356 — revised Pillar 3 disclosure requirements):
    - generate_km1_key_metrics(...)         -- KM1 Key Prudential Metrics table
    - generate_ov1_overview_rwa(...)        -- OV1 RWA overview
    - generate_lr1_leverage(...)            -- LR1 Leverage Ratio
    - generate_pillar3_pack(...)            -- assemble full pack with completeness check

12 PILLAR_3_TABLES byte-for-byte (BCBS standard tables):
    KM1   : Key Prudential Metrics (CET1, Tier1, Total CAR, Leverage, LCR, NSFR)
    OV1   : Overview of RWA
    CR1   : Credit Risk — exposures and provisions
    CR3   : Credit Risk Mitigation
    CR4   : Standardised Approach — credit risk exposure and CRM effects
    CR5   : Standardised Approach — exposures by asset class and risk weight
    LIQ1  : Liquidity Coverage Ratio
    LIQ2  : Net Stable Funding Ratio
    LR1   : Leverage Ratio — exposure breakdown
    MR1   : Market Risk — Standardised Approach
    OR1   : Operational Risk — disclosure
    REM1  : Remuneration awarded during the financial year

3 DISCLOSURE_FREQUENCIES byte-for-byte: ANNUAL, SEMI_ANNUAL, QUARTERLY

BCBS frequency mapping byte-for-byte:
    KM1, OV1, LIQ1, LIQ2 : QUARTERLY (large banks) / SEMI_ANNUAL (others)
    CR1, CR3, CR4, CR5   : SEMI_ANNUAL
    LR1, MR1, OR1        : SEMI_ANNUAL
    REM1                 : ANNUAL

Asset threshold (CBK + Basel "large bank" definition for quarterly): KES 100B.

Honesty rules applied:
    Rule 1: ratios = None when components missing
    Rule 6: missing required tables surfaced; pack NOT distributed if incomplete

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 12 PILLAR 3 TABLES byte-for-byte (BCBS 309/356)
PILLAR_3_TABLES: Tuple[str, ...] = (
    "KM1", "OV1", "CR1", "CR3", "CR4", "CR5",
    "LIQ1", "LIQ2", "LR1", "MR1", "OR1", "REM1",
)

# 3 DISCLOSURE FREQUENCIES byte-for-byte
DISCLOSURE_FREQUENCIES: Tuple[str, ...] = ("ANNUAL", "SEMI_ANNUAL", "QUARTERLY")

# BCBS frequency mapping byte-for-byte
TABLE_FREQUENCIES_LARGE_BANK: Dict[str, str] = {
    "KM1": "QUARTERLY",
    "OV1": "QUARTERLY",
    "CR1": "SEMI_ANNUAL",
    "CR3": "SEMI_ANNUAL",
    "CR4": "SEMI_ANNUAL",
    "CR5": "SEMI_ANNUAL",
    "LIQ1": "QUARTERLY",
    "LIQ2": "QUARTERLY",
    "LR1": "SEMI_ANNUAL",
    "MR1": "SEMI_ANNUAL",
    "OR1": "SEMI_ANNUAL",
    "REM1": "ANNUAL",
}

# Default frequency mapping for non-large banks (some downgrade to SEMI_ANNUAL)
TABLE_FREQUENCIES_OTHER_BANK: Dict[str, str] = {
    "KM1": "SEMI_ANNUAL",
    "OV1": "SEMI_ANNUAL",
    "CR1": "SEMI_ANNUAL",
    "CR3": "SEMI_ANNUAL",
    "CR4": "SEMI_ANNUAL",
    "CR5": "SEMI_ANNUAL",
    "LIQ1": "SEMI_ANNUAL",
    "LIQ2": "SEMI_ANNUAL",
    "LR1": "SEMI_ANNUAL",
    "MR1": "SEMI_ANNUAL",
    "OR1": "SEMI_ANNUAL",
    "REM1": "ANNUAL",
}

# Large-bank threshold (Basel + CBK definition) byte-for-byte
LARGE_BANK_ASSET_THRESHOLD_KES = Decimal("100000000000")  # KES 100B

# KM1 minimum mandatory metrics (per BCBS 309)
KM1_MANDATORY_METRICS: Tuple[str, ...] = (
    "cet1_capital_kes",
    "tier1_capital_kes",
    "total_capital_kes",
    "rwa_kes",
    "cet1_ratio_pct",
    "tier1_ratio_pct",
    "total_car_pct",
    "leverage_ratio_pct",
    "lcr_pct",
    "nsfr_pct",
)


@dataclass
class Pillar3Inputs:
    reporting_period_end: Optional[date] = None
    total_assets_kes: Optional[Decimal] = None
    cet1_capital_kes: Optional[Decimal] = None
    tier1_capital_kes: Optional[Decimal] = None
    total_capital_kes: Optional[Decimal] = None
    rwa_kes: Optional[Decimal] = None
    leverage_exposures_kes: Optional[Decimal] = None
    lcr_hqla_kes: Optional[Decimal] = None
    lcr_net_outflows_kes: Optional[Decimal] = None
    nsfr_asf_kes: Optional[Decimal] = None
    nsfr_rsf_kes: Optional[Decimal] = None


class Pillar3Engine:
    """Deterministic Basel Pillar 3 disclosure assembly."""

    @staticmethod
    def is_large_bank(total_assets_kes: Optional[Decimal]) -> Optional[bool]:
        """Rule 1: None when total_assets missing."""
        if total_assets_kes is None:
            return None
        return total_assets_kes >= LARGE_BANK_ASSET_THRESHOLD_KES

    @staticmethod
    def generate_km1_key_metrics(inputs: Pillar3Inputs) -> Dict[str, Any]:
        """
        KM1 — Key Prudential Metrics.
        Rule 1: ratios = None when denominator missing/zero.
        Rule 6: missing required metrics surfaced.
        """
        if inputs.reporting_period_end is None:
            return {
                "table_id": "KM1",
                "generated": False,
                "validation_errors": ["missing_reporting_period_end"],
            }

        # CAR ratios (Rule 1)
        if inputs.rwa_kes is None or inputs.rwa_kes <= 0:
            cet1_ratio = None
            tier1_ratio = None
            total_car = None
        else:
            cet1_ratio = ((inputs.cet1_capital_kes / inputs.rwa_kes) * Decimal("100")
                          if inputs.cet1_capital_kes else None)
            tier1_ratio = ((inputs.tier1_capital_kes / inputs.rwa_kes) * Decimal("100")
                           if inputs.tier1_capital_kes else None)
            total_car = ((inputs.total_capital_kes / inputs.rwa_kes) * Decimal("100")
                         if inputs.total_capital_kes else None)

        # Leverage (Rule 1)
        if (inputs.leverage_exposures_kes is None
                or inputs.leverage_exposures_kes <= 0
                or inputs.tier1_capital_kes is None):
            leverage_ratio = None
        else:
            leverage_ratio = (inputs.tier1_capital_kes / inputs.leverage_exposures_kes
                              * Decimal("100"))

        # LCR (Rule 1)
        if (inputs.lcr_net_outflows_kes is None
                or inputs.lcr_net_outflows_kes <= 0
                or inputs.lcr_hqla_kes is None):
            lcr = None
        else:
            lcr = (inputs.lcr_hqla_kes / inputs.lcr_net_outflows_kes
                   * Decimal("100"))

        # NSFR (Rule 1)
        if (inputs.nsfr_rsf_kes is None or inputs.nsfr_rsf_kes <= 0
                or inputs.nsfr_asf_kes is None):
            nsfr = None
        else:
            nsfr = (inputs.nsfr_asf_kes / inputs.nsfr_rsf_kes * Decimal("100"))

        # Rule 6: surface missing mandatory metrics
        metrics_dict = {
            "cet1_capital_kes": inputs.cet1_capital_kes,
            "tier1_capital_kes": inputs.tier1_capital_kes,
            "total_capital_kes": inputs.total_capital_kes,
            "rwa_kes": inputs.rwa_kes,
            "cet1_ratio_pct": cet1_ratio,
            "tier1_ratio_pct": tier1_ratio,
            "total_car_pct": total_car,
            "leverage_ratio_pct": leverage_ratio,
            "lcr_pct": lcr,
            "nsfr_pct": nsfr,
        }
        missing = [k for k in KM1_MANDATORY_METRICS if metrics_dict.get(k) is None]

        # Quantize for output
        def _q(v):
            if v is None:
                return None
            return str(v.quantize(Decimal("0.01")))

        return {
            "table_id": "KM1",
            "table_name": "Key Prudential Metrics",
            "generated": True,
            "reporting_period_end": inputs.reporting_period_end.isoformat(),
            "metrics": {
                "cet1_capital_kes": _q(inputs.cet1_capital_kes),
                "tier1_capital_kes": _q(inputs.tier1_capital_kes),
                "total_capital_kes": _q(inputs.total_capital_kes),
                "rwa_kes": _q(inputs.rwa_kes),
                "cet1_ratio_pct": _q(cet1_ratio),
                "tier1_ratio_pct": _q(tier1_ratio),
                "total_car_pct": _q(total_car),
                "leverage_ratio_pct": _q(leverage_ratio),
                "lcr_pct": _q(lcr),
                "nsfr_pct": _q(nsfr),
            },
            "missing_mandatory_metrics": missing,
            "complete": len(missing) == 0,
        }

    @staticmethod
    def generate_ov1_overview_rwa(
        inputs: Pillar3Inputs,
        credit_rwa_kes: Optional[Decimal] = None,
        market_rwa_kes: Optional[Decimal] = None,
        operational_rwa_kes: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """OV1 — RWA breakdown by risk type. Rule 6: missing components surfaced."""
        if inputs.reporting_period_end is None:
            return {
                "table_id": "OV1",
                "generated": False,
                "validation_errors": ["missing_reporting_period_end"],
            }

        components = {
            "credit_rwa_kes": credit_rwa_kes,
            "market_rwa_kes": market_rwa_kes,
            "operational_rwa_kes": operational_rwa_kes,
        }
        missing = [k for k, v in components.items() if v is None]
        present_total = sum(v for v in components.values() if v is not None)

        return {
            "table_id": "OV1",
            "table_name": "Overview of RWA",
            "generated": True,
            "reporting_period_end": inputs.reporting_period_end.isoformat(),
            "credit_rwa_kes": str(credit_rwa_kes.quantize(Decimal("0.01"))) if credit_rwa_kes else None,
            "market_rwa_kes": str(market_rwa_kes.quantize(Decimal("0.01"))) if market_rwa_kes else None,
            "operational_rwa_kes": str(operational_rwa_kes.quantize(Decimal("0.01"))) if operational_rwa_kes else None,
            "total_rwa_kes": str(present_total.quantize(Decimal("0.01"))) if present_total else "0",
            "missing_components": missing,
            "complete": len(missing) == 0,
        }

    @staticmethod
    def generate_lr1_leverage(
        inputs: Pillar3Inputs,
    ) -> Dict[str, Any]:
        """LR1 — Leverage ratio with on/off balance sheet breakdown."""
        if inputs.reporting_period_end is None:
            return {
                "table_id": "LR1",
                "generated": False,
                "validation_errors": ["missing_reporting_period_end"],
            }
        if (inputs.leverage_exposures_kes is None
                or inputs.leverage_exposures_kes <= 0
                or inputs.tier1_capital_kes is None):
            ratio = None
        else:
            ratio = (inputs.tier1_capital_kes / inputs.leverage_exposures_kes
                     * Decimal("100"))
        return {
            "table_id": "LR1",
            "table_name": "Leverage Ratio",
            "generated": True,
            "reporting_period_end": inputs.reporting_period_end.isoformat(),
            "tier1_capital_kes": str(inputs.tier1_capital_kes.quantize(Decimal("0.01"))) if inputs.tier1_capital_kes else None,
            "total_exposures_kes": str(inputs.leverage_exposures_kes.quantize(Decimal("0.01"))) if inputs.leverage_exposures_kes else None,
            "leverage_ratio_pct": str(ratio.quantize(Decimal("0.01"))) if ratio else None,
            "minimum_required_pct": "3.00",
        }

    @staticmethod
    def generate_pillar3_pack(
        inputs: Pillar3Inputs,
        provided_table_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Assemble full Pillar 3 pack with completeness validation.
        Rule 6: missing required tables surfaced; pack not distributed if incomplete.
        """
        if inputs.reporting_period_end is None:
            return {
                "pack_type": "PILLAR_3",
                "generated": False,
                "validation_errors": ["missing_reporting_period_end"],
            }

        large_bank = Pillar3Engine.is_large_bank(inputs.total_assets_kes)
        bank_class = ("LARGE_BANK" if large_bank
                      else ("OTHER_BANK" if large_bank is False else "UNKNOWN"))

        # All 12 tables required for full pack
        provided_set = set(provided_table_ids)
        missing_tables = [t for t in PILLAR_3_TABLES if t not in provided_set]
        complete = len(missing_tables) == 0

        # Frequency table per bank class
        if large_bank is True:
            freq_map = TABLE_FREQUENCIES_LARGE_BANK
        else:
            freq_map = TABLE_FREQUENCIES_OTHER_BANK

        return {
            "pack_type": "PILLAR_3",
            "generated": True,
            "reporting_period_end": inputs.reporting_period_end.isoformat(),
            "bank_class": bank_class,
            "total_assets_kes": str(inputs.total_assets_kes) if inputs.total_assets_kes else None,
            "large_bank_threshold_kes": str(LARGE_BANK_ASSET_THRESHOLD_KES),
            "required_tables_count": len(PILLAR_3_TABLES),
            "provided_tables": list(provided_set),
            "missing_tables": missing_tables,
            "complete": complete,
            "table_frequencies": freq_map,
            "eligible_for_distribution": complete,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _inputs(**kw):
    defaults = dict(
        reporting_period_end=date(2026, 4, 30),
        total_assets_kes=Decimal("150000000000"),  # 150B → large bank
        cet1_capital_kes=Decimal("12000000000"),
        tier1_capital_kes=Decimal("13000000000"),
        total_capital_kes=Decimal("15000000000"),
        rwa_kes=Decimal("90000000000"),
        leverage_exposures_kes=Decimal("250000000000"),
        lcr_hqla_kes=Decimal("20000000000"),
        lcr_net_outflows_kes=Decimal("15000000000"),
        nsfr_asf_kes=Decimal("100000000000"),
        nsfr_rsf_kes=Decimal("90000000000"),
    )
    defaults.update(kw)
    return Pillar3Inputs(**defaults)


def _test_tables_byte_for_byte():
    expected = ("KM1", "OV1", "CR1", "CR3", "CR4", "CR5",
                "LIQ1", "LIQ2", "LR1", "MR1", "OR1", "REM1")
    for t in expected:
        assert t in PILLAR_3_TABLES
    assert len(PILLAR_3_TABLES) == 12


def _test_frequencies_byte_for_byte():
    expected = ("ANNUAL", "SEMI_ANNUAL", "QUARTERLY")
    for f in expected:
        assert f in DISCLOSURE_FREQUENCIES


def _test_large_bank_freq_map_byte_for_byte():
    assert TABLE_FREQUENCIES_LARGE_BANK["KM1"] == "QUARTERLY"
    assert TABLE_FREQUENCIES_LARGE_BANK["OV1"] == "QUARTERLY"
    assert TABLE_FREQUENCIES_LARGE_BANK["LIQ1"] == "QUARTERLY"
    assert TABLE_FREQUENCIES_LARGE_BANK["LIQ2"] == "QUARTERLY"
    assert TABLE_FREQUENCIES_LARGE_BANK["REM1"] == "ANNUAL"
    assert TABLE_FREQUENCIES_LARGE_BANK["CR1"] == "SEMI_ANNUAL"


def _test_other_bank_freq_map_byte_for_byte():
    """Other banks downgrade KM1/OV1/LIQ to SEMI_ANNUAL."""
    assert TABLE_FREQUENCIES_OTHER_BANK["KM1"] == "SEMI_ANNUAL"
    assert TABLE_FREQUENCIES_OTHER_BANK["LIQ1"] == "SEMI_ANNUAL"


def _test_large_bank_threshold_byte_for_byte():
    assert LARGE_BANK_ASSET_THRESHOLD_KES == Decimal("100000000000")


def _test_km1_mandatory_metrics_byte_for_byte():
    expected = ("cet1_capital_kes", "tier1_capital_kes", "total_capital_kes",
                "rwa_kes", "cet1_ratio_pct", "tier1_ratio_pct", "total_car_pct",
                "leverage_ratio_pct", "lcr_pct", "nsfr_pct")
    for m in expected:
        assert m in KM1_MANDATORY_METRICS
    assert len(KM1_MANDATORY_METRICS) == 10


def _test_is_large_bank():
    assert Pillar3Engine.is_large_bank(Decimal("150000000000")) is True
    assert Pillar3Engine.is_large_bank(Decimal("50000000000")) is False
    assert Pillar3Engine.is_large_bank(None) is None  # Rule 1


def _test_km1_full_complete():
    r = Pillar3Engine.generate_km1_key_metrics(_inputs())
    assert r["complete"] is True
    # CET1: 12/90 = 13.33%
    assert r["metrics"]["cet1_ratio_pct"] == "13.33"
    # Total CAR: 15/90 = 16.67%
    assert r["metrics"]["total_car_pct"] == "16.67"
    # Leverage: 13/250 = 5.20%
    assert r["metrics"]["leverage_ratio_pct"] == "5.20"
    # LCR: 20/15 = 133.33%
    assert r["metrics"]["lcr_pct"] == "133.33"
    # NSFR: 100/90 = 111.11%
    assert r["metrics"]["nsfr_pct"] == "111.11"


def _test_km1_zero_rwa_rule1():
    r = Pillar3Engine.generate_km1_key_metrics(_inputs(rwa_kes=Decimal("0")))
    assert r["metrics"]["total_car_pct"] is None


def _test_km1_missing_period_rule6():
    r = Pillar3Engine.generate_km1_key_metrics(_inputs(reporting_period_end=None))
    assert r["generated"] is False


def _test_km1_missing_metrics_surfaced():
    r = Pillar3Engine.generate_km1_key_metrics(_inputs(nsfr_asf_kes=None))
    assert "nsfr_pct" in r["missing_mandatory_metrics"]


def _test_ov1_full_complete():
    r = Pillar3Engine.generate_ov1_overview_rwa(
        _inputs(),
        credit_rwa_kes=Decimal("70000000000"),
        market_rwa_kes=Decimal("5000000000"),
        operational_rwa_kes=Decimal("15000000000"),
    )
    assert r["complete"] is True
    assert r["total_rwa_kes"] == "90000000000.00"


def _test_ov1_missing_components_rule6():
    r = Pillar3Engine.generate_ov1_overview_rwa(
        _inputs(),
        credit_rwa_kes=Decimal("70000000000"),
        # market and operational missing
    )
    assert "market_rwa_kes" in r["missing_components"]
    assert "operational_rwa_kes" in r["missing_components"]
    assert r["complete"] is False


def _test_lr1_basic():
    r = Pillar3Engine.generate_lr1_leverage(_inputs())
    # 13B / 250B = 5.20%
    assert r["leverage_ratio_pct"] == "5.20"


def _test_lr1_zero_exposures_rule1():
    r = Pillar3Engine.generate_lr1_leverage(_inputs(leverage_exposures_kes=Decimal("0")))
    assert r["leverage_ratio_pct"] is None


def _test_pillar3_pack_complete():
    """All 12 tables provided → complete + eligible."""
    r = Pillar3Engine.generate_pillar3_pack(
        _inputs(), provided_table_ids=list(PILLAR_3_TABLES))
    assert r["complete"] is True
    assert r["bank_class"] == "LARGE_BANK"
    assert r["eligible_for_distribution"] is True


def _test_pillar3_pack_missing_tables_rule6():
    """Provide only KM1 + OV1 → 10 missing."""
    r = Pillar3Engine.generate_pillar3_pack(
        _inputs(), provided_table_ids=["KM1", "OV1"])
    assert r["complete"] is False
    assert r["eligible_for_distribution"] is False
    assert len(r["missing_tables"]) == 10


def _test_pillar3_pack_other_bank():
    inp = _inputs(total_assets_kes=Decimal("50000000000"))  # 50B < 100B
    r = Pillar3Engine.generate_pillar3_pack(
        inp, provided_table_ids=list(PILLAR_3_TABLES))
    assert r["bank_class"] == "OTHER_BANK"
    assert r["table_frequencies"]["KM1"] == "SEMI_ANNUAL"


def _test_pillar3_pack_unknown_class():
    inp = _inputs(total_assets_kes=None)  # missing
    r = Pillar3Engine.generate_pillar3_pack(
        inp, provided_table_ids=list(PILLAR_3_TABLES))
    assert r["bank_class"] == "UNKNOWN"


def self_test() -> bool:
    tests = [
        _test_tables_byte_for_byte,
        _test_frequencies_byte_for_byte,
        _test_large_bank_freq_map_byte_for_byte,
        _test_other_bank_freq_map_byte_for_byte,
        _test_large_bank_threshold_byte_for_byte,
        _test_km1_mandatory_metrics_byte_for_byte,
        _test_is_large_bank,
        _test_km1_full_complete,
        _test_km1_zero_rwa_rule1,
        _test_km1_missing_period_rule6,
        _test_km1_missing_metrics_surfaced,
        _test_ov1_full_complete,
        _test_ov1_missing_components_rule6,
        _test_lr1_basic,
        _test_lr1_zero_exposures_rule1,
        _test_pillar3_pack_complete,
        _test_pillar3_pack_missing_tables_rule6,
        _test_pillar3_pack_other_bank,
        _test_pillar3_pack_unknown_class,
    ]
    print("=" * 60)
    print("Pillar 3 Disclosure Generator — Self-Tests (#88)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
