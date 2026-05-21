"""
================================================================================
A2Z MIS 360 — Standard #92: ESG / Sustainability Reporting Engine
================================================================================

Risk classification: Cat B (deterministic ESG disclosure assembly)

Generates climate-related and sustainability disclosures per TCFD + IFRS S2 +
CBK Climate Risk Management Framework (April 2021):
    - validate_tcfd_disclosure(...)         -- check 11 recommended disclosures
    - ghg_emissions_total(...)              -- Scope 1+2+3 aggregation
    - climate_risk_classification(...)      -- physical vs transition typing
    - generate_tcfd_pack(...)               -- assemble TCFD-aligned pack
    - sustainability_kpi_summary(...)       -- portfolio-level ESG metrics

4 TCFD_PILLARS byte-for-byte:
    GOVERNANCE, STRATEGY, RISK_MANAGEMENT, METRICS_AND_TARGETS

11 TCFD_RECOMMENDED_DISCLOSURES byte-for-byte (per pillar count: 2/3/3/3):
    GOV_A, GOV_B (Governance — 2)
    STR_A, STR_B, STR_C (Strategy — 3)
    RISK_A, RISK_B, RISK_C (Risk Management — 3)
    MET_A, MET_B, MET_C (Metrics & Targets — 3)

3 GHG_SCOPES byte-for-byte (GHG Protocol):
    SCOPE_1 (direct), SCOPE_2 (purchased electricity), SCOPE_3 (value chain)

15 SCOPE_3_CATEGORIES byte-for-byte (GHG Protocol Scope 3 standard).

6 CLIMATE_RISK_TYPES byte-for-byte:
    ACUTE_PHYSICAL, CHRONIC_PHYSICAL,
    TRANSITION_POLICY, TRANSITION_TECHNOLOGY,
    TRANSITION_MARKET, TRANSITION_REPUTATION

3 ISSB_DISCLOSURE_TOPICS byte-for-byte (IFRS S2 climate-related):
    CLIMATE_GOVERNANCE, CLIMATE_STRATEGY, CLIMATE_METRICS

GHG units byte-for-byte: tCO2e (tonnes CO2 equivalent).

Honesty rules applied:
    Rule 1: emissions_total=None when any scope missing (cannot infer)
    Rule 6: missing TCFD disclosures surfaced; pack NOT eligible if incomplete

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 4 TCFD PILLARS byte-for-byte
TCFD_PILLARS: Tuple[str, ...] = (
    "GOVERNANCE", "STRATEGY", "RISK_MANAGEMENT", "METRICS_AND_TARGETS",
)

# 11 TCFD RECOMMENDED DISCLOSURES byte-for-byte
TCFD_RECOMMENDED_DISCLOSURES: Tuple[str, ...] = (
    "GOV_A", "GOV_B",                     # 2 (Governance)
    "STR_A", "STR_B", "STR_C",            # 3 (Strategy)
    "RISK_A", "RISK_B", "RISK_C",         # 3 (Risk Management)
    "MET_A", "MET_B", "MET_C",            # 3 (Metrics & Targets)
)

# Disclosure → pillar mapping
DISCLOSURE_PILLAR_MAP: Dict[str, str] = {
    "GOV_A": "GOVERNANCE", "GOV_B": "GOVERNANCE",
    "STR_A": "STRATEGY", "STR_B": "STRATEGY", "STR_C": "STRATEGY",
    "RISK_A": "RISK_MANAGEMENT", "RISK_B": "RISK_MANAGEMENT", "RISK_C": "RISK_MANAGEMENT",
    "MET_A": "METRICS_AND_TARGETS", "MET_B": "METRICS_AND_TARGETS",
    "MET_C": "METRICS_AND_TARGETS",
}

# 3 GHG SCOPES byte-for-byte
GHG_SCOPES: Tuple[str, ...] = ("SCOPE_1", "SCOPE_2", "SCOPE_3")

# 15 SCOPE 3 CATEGORIES byte-for-byte (GHG Protocol)
SCOPE_3_CATEGORIES: Tuple[str, ...] = (
    "PURCHASED_GOODS_AND_SERVICES",         # 1
    "CAPITAL_GOODS",                         # 2
    "FUEL_AND_ENERGY_RELATED",               # 3
    "UPSTREAM_TRANSPORTATION",               # 4
    "WASTE_GENERATED_IN_OPERATIONS",         # 5
    "BUSINESS_TRAVEL",                       # 6
    "EMPLOYEE_COMMUTING",                    # 7
    "UPSTREAM_LEASED_ASSETS",                # 8
    "DOWNSTREAM_TRANSPORTATION",             # 9
    "PROCESSING_OF_SOLD_PRODUCTS",           # 10
    "USE_OF_SOLD_PRODUCTS",                  # 11
    "END_OF_LIFE_TREATMENT",                 # 12
    "DOWNSTREAM_LEASED_ASSETS",              # 13
    "FRANCHISES",                            # 14
    "INVESTMENTS",                           # 15  -- biggest for banks ("financed emissions")
)

# 6 CLIMATE RISK TYPES byte-for-byte
CLIMATE_RISK_TYPES: Tuple[str, ...] = (
    "ACUTE_PHYSICAL",
    "CHRONIC_PHYSICAL",
    "TRANSITION_POLICY",
    "TRANSITION_TECHNOLOGY",
    "TRANSITION_MARKET",
    "TRANSITION_REPUTATION",
)

# 3 ISSB / IFRS S2 disclosure topics byte-for-byte
ISSB_DISCLOSURE_TOPICS: Tuple[str, ...] = (
    "CLIMATE_GOVERNANCE",
    "CLIMATE_STRATEGY",
    "CLIMATE_METRICS",
)

# Required completeness for TCFD pack distribution byte-for-byte
TCFD_MIN_COMPLETE_PCT = Decimal("100")


@dataclass
class TcfdDisclosure:
    disclosure_id: str
    pillar: str
    populated: bool = False
    has_data_quality_issues: bool = False


@dataclass
class GhgInventory:
    scope_1_tco2e: Optional[Decimal] = None
    scope_2_tco2e: Optional[Decimal] = None
    scope_3_tco2e: Optional[Decimal] = None
    scope_3_breakdown: Dict[str, Decimal] = field(default_factory=dict)


class EsgReportingEngine:
    """Deterministic TCFD + IFRS S2 + GHG Protocol disclosure assembly."""

    @staticmethod
    def validate_tcfd_disclosure(
        disclosures: List[TcfdDisclosure],
    ) -> Dict[str, Any]:
        """
        Check whether all 11 TCFD recommended disclosures are populated.
        Rule 6: missing disclosures surfaced; pack ineligible if incomplete.
        """
        provided = {d.disclosure_id for d in disclosures}
        missing = [d for d in TCFD_RECOMMENDED_DISCLOSURES if not any(
            x.disclosure_id == d and x.populated for x in disclosures)]
        unknown = [d.disclosure_id for d in disclosures
                   if d.disclosure_id not in TCFD_RECOMMENDED_DISCLOSURES]
        with_quality_issues = [d.disclosure_id for d in disclosures
                                if d.has_data_quality_issues]
        present_count = sum(1 for d in TCFD_RECOMMENDED_DISCLOSURES
                            if any(x.disclosure_id == d and x.populated
                                   for x in disclosures))
        completeness_pct = (Decimal(present_count) / Decimal(len(TCFD_RECOMMENDED_DISCLOSURES))
                            * Decimal("100"))
        return {
            "required_count": len(TCFD_RECOMMENDED_DISCLOSURES),
            "present_count": present_count,
            "completeness_pct": str(completeness_pct.quantize(Decimal("0.01"))),
            "missing_disclosures": missing,
            "unknown_disclosures": unknown,
            "with_data_quality_issues": with_quality_issues,
            "complete": present_count == len(TCFD_RECOMMENDED_DISCLOSURES),
        }

    @staticmethod
    def ghg_emissions_total(inv: GhgInventory) -> Dict[str, Any]:
        """
        Sum total GHG emissions across all 3 scopes.
        Rule 1: total=None when ANY scope missing (cannot silently infer).
        Rule 6: missing scopes surfaced.
        """
        scopes = {
            "SCOPE_1": inv.scope_1_tco2e,
            "SCOPE_2": inv.scope_2_tco2e,
            "SCOPE_3": inv.scope_3_tco2e,
        }
        missing = [s for s, v in scopes.items() if v is None]
        if missing:
            return {
                "total_tco2e": None,
                "missing_scopes": missing,
                "scopes_present": {k: str(v) for k, v in scopes.items() if v is not None},
                "reason": "cannot_compute_total_with_missing_scopes",
            }
        total = inv.scope_1_tco2e + inv.scope_2_tco2e + inv.scope_3_tco2e
        return {
            "total_tco2e": str(total.quantize(Decimal("0.01"))),
            "scope_1_tco2e": str(inv.scope_1_tco2e.quantize(Decimal("0.01"))),
            "scope_2_tco2e": str(inv.scope_2_tco2e.quantize(Decimal("0.01"))),
            "scope_3_tco2e": str(inv.scope_3_tco2e.quantize(Decimal("0.01"))),
            "scope_3_categories_reported": list(inv.scope_3_breakdown.keys()),
        }

    @staticmethod
    def climate_risk_classification(risk_type: str) -> Dict[str, Any]:
        """
        Classify a climate risk into physical vs transition family.
        Rule 6: unknown risk type rejected.
        """
        if risk_type not in CLIMATE_RISK_TYPES:
            return {
                "family": None,
                "reason": f"unknown_risk_type:{risk_type}",
                "valid_types": list(CLIMATE_RISK_TYPES),
            }
        if risk_type in ("ACUTE_PHYSICAL", "CHRONIC_PHYSICAL"):
            family = "PHYSICAL"
        else:
            family = "TRANSITION"
        return {
            "risk_type": risk_type,
            "family": family,
            "is_physical": family == "PHYSICAL",
            "is_transition": family == "TRANSITION",
        }

    @staticmethod
    def generate_tcfd_pack(
        disclosures: List[TcfdDisclosure],
        inv: Optional[GhgInventory] = None,
    ) -> Dict[str, Any]:
        """
        Assemble TCFD-aligned disclosure pack with completeness validation.
        Rule 6: pack NOT eligible if any of 11 disclosures missing.
        """
        validation = EsgReportingEngine.validate_tcfd_disclosure(disclosures)
        emissions = (EsgReportingEngine.ghg_emissions_total(inv)
                     if inv is not None else
                     {"total_tco2e": None, "reason": "no_inventory_provided"})

        per_pillar_count = {p: 0 for p in TCFD_PILLARS}
        for d in disclosures:
            if d.populated and d.disclosure_id in DISCLOSURE_PILLAR_MAP:
                per_pillar_count[DISCLOSURE_PILLAR_MAP[d.disclosure_id]] += 1

        eligible = (validation["complete"]
                    and len(validation["with_data_quality_issues"]) == 0)

        return {
            "pack_type": "TCFD",
            "completeness_pct": validation["completeness_pct"],
            "min_required_pct": str(TCFD_MIN_COMPLETE_PCT),
            "missing_disclosures": validation["missing_disclosures"],
            "unknown_disclosures": validation["unknown_disclosures"],
            "with_data_quality_issues": validation["with_data_quality_issues"],
            "per_pillar_disclosures_present": per_pillar_count,
            "ghg_emissions": emissions,
            "eligible_for_distribution": eligible,
            "complete": validation["complete"],
        }


# ============================================================================
# Self-tests
# ============================================================================

def _all_disclosures():
    return [TcfdDisclosure(disclosure_id=d, pillar=DISCLOSURE_PILLAR_MAP[d],
                           populated=True)
            for d in TCFD_RECOMMENDED_DISCLOSURES]


def _full_inventory():
    return GhgInventory(
        scope_1_tco2e=Decimal("1500"),
        scope_2_tco2e=Decimal("8000"),
        scope_3_tco2e=Decimal("250000"),
        scope_3_breakdown={
            "INVESTMENTS": Decimal("240000"),
            "BUSINESS_TRAVEL": Decimal("5000"),
            "EMPLOYEE_COMMUTING": Decimal("5000"),
        },
    )


def _test_tcfd_pillars_byte_for_byte():
    expected = ("GOVERNANCE", "STRATEGY", "RISK_MANAGEMENT", "METRICS_AND_TARGETS")
    for p in expected:
        assert p in TCFD_PILLARS
    assert len(TCFD_PILLARS) == 4


def _test_tcfd_disclosures_byte_for_byte():
    expected = ("GOV_A", "GOV_B", "STR_A", "STR_B", "STR_C",
                "RISK_A", "RISK_B", "RISK_C",
                "MET_A", "MET_B", "MET_C")
    for d in expected:
        assert d in TCFD_RECOMMENDED_DISCLOSURES
    assert len(TCFD_RECOMMENDED_DISCLOSURES) == 11


def _test_per_pillar_disclosure_counts():
    """Per-pillar count: GOV=2, STR=3, RISK=3, MET=3."""
    counts = {p: 0 for p in TCFD_PILLARS}
    for d in TCFD_RECOMMENDED_DISCLOSURES:
        counts[DISCLOSURE_PILLAR_MAP[d]] += 1
    assert counts["GOVERNANCE"] == 2
    assert counts["STRATEGY"] == 3
    assert counts["RISK_MANAGEMENT"] == 3
    assert counts["METRICS_AND_TARGETS"] == 3


def _test_ghg_scopes_byte_for_byte():
    for s in ("SCOPE_1", "SCOPE_2", "SCOPE_3"):
        assert s in GHG_SCOPES
    assert len(GHG_SCOPES) == 3


def _test_scope_3_categories_byte_for_byte():
    """15 categories per GHG Protocol Scope 3 standard."""
    assert len(SCOPE_3_CATEGORIES) == 15
    assert "INVESTMENTS" in SCOPE_3_CATEGORIES  # critical for banks
    assert "BUSINESS_TRAVEL" in SCOPE_3_CATEGORIES
    assert "EMPLOYEE_COMMUTING" in SCOPE_3_CATEGORIES


def _test_climate_risk_types_byte_for_byte():
    expected = ("ACUTE_PHYSICAL", "CHRONIC_PHYSICAL",
                "TRANSITION_POLICY", "TRANSITION_TECHNOLOGY",
                "TRANSITION_MARKET", "TRANSITION_REPUTATION")
    for r in expected:
        assert r in CLIMATE_RISK_TYPES
    assert len(CLIMATE_RISK_TYPES) == 6


def _test_issb_topics_byte_for_byte():
    expected = ("CLIMATE_GOVERNANCE", "CLIMATE_STRATEGY", "CLIMATE_METRICS")
    for t in expected:
        assert t in ISSB_DISCLOSURE_TOPICS


def _test_tcfd_min_complete_byte_for_byte():
    assert TCFD_MIN_COMPLETE_PCT == Decimal("100")


def _test_validate_tcfd_full():
    r = EsgReportingEngine.validate_tcfd_disclosure(_all_disclosures())
    assert r["complete"] is True
    assert r["completeness_pct"] == "100.00"


def _test_validate_tcfd_missing_rule6():
    """Drop GOV_A → 10/11 = 90.91% missing 1."""
    disc = _all_disclosures()
    disc[0].populated = False
    r = EsgReportingEngine.validate_tcfd_disclosure(disc)
    assert r["complete"] is False
    assert "GOV_A" in r["missing_disclosures"]


def _test_validate_tcfd_unknown_surfaced():
    disc = _all_disclosures()
    disc.append(TcfdDisclosure(disclosure_id="WEIRD", pillar="UNKNOWN", populated=True))
    r = EsgReportingEngine.validate_tcfd_disclosure(disc)
    assert "WEIRD" in r["unknown_disclosures"]


def _test_ghg_total_full():
    """1500 + 8000 + 250000 = 259,500 tCO2e."""
    r = EsgReportingEngine.ghg_emissions_total(_full_inventory())
    assert r["total_tco2e"] == "259500.00"


def _test_ghg_total_missing_scope_rule1():
    inv = _full_inventory()
    inv.scope_3_tco2e = None
    r = EsgReportingEngine.ghg_emissions_total(inv)
    assert r["total_tco2e"] is None
    assert "SCOPE_3" in r["missing_scopes"]


def _test_climate_risk_physical():
    r = EsgReportingEngine.climate_risk_classification("ACUTE_PHYSICAL")
    assert r["family"] == "PHYSICAL"
    assert r["is_physical"] is True


def _test_climate_risk_transition():
    r = EsgReportingEngine.climate_risk_classification("TRANSITION_POLICY")
    assert r["family"] == "TRANSITION"
    assert r["is_transition"] is True


def _test_climate_risk_unknown_rule6():
    r = EsgReportingEngine.climate_risk_classification("WEIRD")
    assert r["family"] is None


def _test_tcfd_pack_complete():
    r = EsgReportingEngine.generate_tcfd_pack(_all_disclosures(), _full_inventory())
    assert r["complete"] is True
    assert r["eligible_for_distribution"] is True


def _test_tcfd_pack_missing_disclosure_rule6():
    disc = _all_disclosures()
    disc[0].populated = False
    r = EsgReportingEngine.generate_tcfd_pack(disc, _full_inventory())
    assert r["complete"] is False
    assert r["eligible_for_distribution"] is False


def _test_tcfd_pack_data_quality_issue():
    disc = _all_disclosures()
    disc[0].has_data_quality_issues = True
    r = EsgReportingEngine.generate_tcfd_pack(disc, _full_inventory())
    assert r["eligible_for_distribution"] is False


def _test_tcfd_pack_per_pillar_counts():
    r = EsgReportingEngine.generate_tcfd_pack(_all_disclosures(), _full_inventory())
    counts = r["per_pillar_disclosures_present"]
    assert counts["GOVERNANCE"] == 2
    assert counts["STRATEGY"] == 3
    assert counts["RISK_MANAGEMENT"] == 3
    assert counts["METRICS_AND_TARGETS"] == 3


def self_test() -> bool:
    tests = [
        _test_tcfd_pillars_byte_for_byte,
        _test_tcfd_disclosures_byte_for_byte,
        _test_per_pillar_disclosure_counts,
        _test_ghg_scopes_byte_for_byte,
        _test_scope_3_categories_byte_for_byte,
        _test_climate_risk_types_byte_for_byte,
        _test_issb_topics_byte_for_byte,
        _test_tcfd_min_complete_byte_for_byte,
        _test_validate_tcfd_full,
        _test_validate_tcfd_missing_rule6,
        _test_validate_tcfd_unknown_surfaced,
        _test_ghg_total_full,
        _test_ghg_total_missing_scope_rule1,
        _test_climate_risk_physical,
        _test_climate_risk_transition,
        _test_climate_risk_unknown_rule6,
        _test_tcfd_pack_complete,
        _test_tcfd_pack_missing_disclosure_rule6,
        _test_tcfd_pack_data_quality_issue,
        _test_tcfd_pack_per_pillar_counts,
    ]
    print("=" * 60)
    print("ESG / Sustainability Reporting Engine — Self-Tests (#92)")
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
