"""utils/climate_treasury_limits.py — v10.37 ENH-TRS-R6.

╔════════════════════════════════════════════════════════════════════════╗
║  CLIMATE-ADJUSTED TREASURY RISK LIMITS                                 ║
║  Cat A — implements ENH-TRS-R6 — composes climate + treasury          ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-TRS-R6: treasury risk limits adjusted for climate    ║
║  exposure (physical + transition). Composes the v10.6-10 climate    ║
║  engines with v10.33-35 treasury concentration limits.              ║
║                                                                         ║
║  Pattern: cross-arc bridging. We don't replicate climate logic; we   ║
║  READ climate risk scores from utils/climate_risk.py and apply        ║
║  haircuts to treasury concentration limits per AssetClass.          ║
║                                                                         ║
║  Two haircut channels:                                                  ║
║    1. PHYSICAL: high physical-risk regions/sectors (drought,         ║
║       flood, sea-level rise) get reduced concentration limits.       ║
║       Sovereign Kenya bonds, agricultural sector lending, coastal   ║
║       infrastructure all get tighter limits.                         ║
║    2. TRANSITION: high transition-risk sectors (fossil fuels,       ║
║       cement, steel) get reduced limits as carbon prices rise per   ║
║       NGFS scenarios. Limits tighten further under Net Zero 2050.   ║
║                                                                         ║
║  Climate score → haircut mapping (deterministic):                      ║
║    score 0-25:    1% haircut (low climate risk)                      ║
║    score 26-50:   5% haircut                                         ║
║    score 51-75:   15% haircut                                        ║
║    score 76-100:  30% haircut (severe climate risk)                  ║
║                                                                         ║
║  Honesty Rule 1: every ClimateAdjustedLimit surfaces base_limit_pct + ║
║  physical_haircut + transition_haircut + adjusted_limit_pct +        ║
║  source_assessments + framework_refs.                                ║
║  Honesty Rule 7: this is a facade — it READS climate engine but      ║
║  doesn't mutate. If climate engine has no assessment for a sector,  ║
║  the limit returns no climate adjustment + a notes flag.            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    BCBS Principles for Climate-Related Financial Risks 2022           ║
║    NGFS Climate Scenarios — Net Zero 2050, Below 2°C, Hot House      ║
║    IFRS S2 — Climate-related Disclosures                             ║
║    CBK CRDF — Climate Risk Disclosure Framework Kenya                ║
║    TCFD Recommendations — climate financial risk reporting            ║
║    EBA EBA/REP/2021/03 — climate risk integration                    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "ClimateTreasuryLimitsEngine implements ENH-TRS-R6 — composes "
    "climate_risk + treasury concentration limits. Two haircut "
    "channels: PHYSICAL + TRANSITION. Per Rule 7, this is a READ-ONLY "
    "facade — it never mutates the climate engine. Per Rule 1, every "
    "adjusted limit surfaces base + haircuts + adjusted + sources."
)


# ════════════════════════════════════════════════════════════════════════
# Climate score → haircut mapping
# ════════════════════════════════════════════════════════════════════════

# (score_inclusive_max, haircut_pct)
CLIMATE_HAIRCUT_BANDS: Tuple[Tuple[Decimal, Decimal], ...] = (
    (Decimal("25"), Decimal("1")),
    (Decimal("50"), Decimal("5")),
    (Decimal("75"), Decimal("15")),
    (Decimal("100"), Decimal("30")),
)


def haircut_for_score(score: Decimal) -> Decimal:
    """Map a climate risk score (0-100) to a haircut %."""
    if score < Decimal("0"):
        score = Decimal("0")
    if score > Decimal("100"):
        score = Decimal("100")
    for bound, haircut in CLIMATE_HAIRCUT_BANDS:
        if score <= bound:
            return haircut
    return Decimal("30")


# ════════════════════════════════════════════════════════════════════════
# Asset class taxonomy (mirrors treasury_unified_platform)
# ════════════════════════════════════════════════════════════════════════

class TreasuryAssetClass(Enum):
    """Asset classes for climate-adjusted treasury limits."""
    SOVEREIGN_KENYA = "SOVEREIGN_KENYA"        # KE bonds/bills
    SOVEREIGN_OTHER = "SOVEREIGN_OTHER"
    CORPORATE_FOSSIL = "CORPORATE_FOSSIL"
    CORPORATE_HEAVY_INDUSTRY = "CORPORATE_HEAVY_INDUSTRY"
    CORPORATE_AGRICULTURE = "CORPORATE_AGRICULTURE"
    CORPORATE_RENEWABLE = "CORPORATE_RENEWABLE"
    CORPORATE_FINANCIALS = "CORPORATE_FINANCIALS"
    CORPORATE_OTHER = "CORPORATE_OTHER"
    REAL_ESTATE_COASTAL = "REAL_ESTATE_COASTAL"
    REAL_ESTATE_OTHER = "REAL_ESTATE_OTHER"


# Default base concentration limits as % of treasury portfolio.
# These are illustrative; production values come from risk policy.
DEFAULT_BASE_LIMIT_PCT: Mapping[TreasuryAssetClass, Decimal] = {
    TreasuryAssetClass.SOVEREIGN_KENYA: Decimal("40"),
    TreasuryAssetClass.SOVEREIGN_OTHER: Decimal("20"),
    TreasuryAssetClass.CORPORATE_FOSSIL: Decimal("5"),
    TreasuryAssetClass.CORPORATE_HEAVY_INDUSTRY: Decimal("8"),
    TreasuryAssetClass.CORPORATE_AGRICULTURE: Decimal("10"),
    TreasuryAssetClass.CORPORATE_RENEWABLE: Decimal("15"),
    TreasuryAssetClass.CORPORATE_FINANCIALS: Decimal("12"),
    TreasuryAssetClass.CORPORATE_OTHER: Decimal("10"),
    TreasuryAssetClass.REAL_ESTATE_COASTAL: Decimal("3"),
    TreasuryAssetClass.REAL_ESTATE_OTHER: Decimal("8"),
}


# Asset class → sectors that contribute to physical/transition scoring
ASSET_CLASS_TO_SECTORS: Mapping[
    TreasuryAssetClass, Tuple[str, ...]] = {
    TreasuryAssetClass.SOVEREIGN_KENYA: ("government_kenya",),
    TreasuryAssetClass.SOVEREIGN_OTHER: ("government_foreign",),
    TreasuryAssetClass.CORPORATE_FOSSIL: (
        "oil_and_gas", "coal_mining", "petroleum"),
    TreasuryAssetClass.CORPORATE_HEAVY_INDUSTRY: (
        "cement", "steel", "chemicals"),
    TreasuryAssetClass.CORPORATE_AGRICULTURE: (
        "agriculture", "agribusiness"),
    TreasuryAssetClass.CORPORATE_RENEWABLE: (
        "renewable_energy", "solar", "wind"),
    TreasuryAssetClass.CORPORATE_FINANCIALS: ("banking", "insurance"),
    TreasuryAssetClass.CORPORATE_OTHER: ("services", "manufacturing"),
    TreasuryAssetClass.REAL_ESTATE_COASTAL: (
        "real_estate_coastal",),
    TreasuryAssetClass.REAL_ESTATE_OTHER: ("real_estate",),
}


# ════════════════════════════════════════════════════════════════════════
# Result dataclass
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ClimateAdjustedLimit:
    """Climate-adjusted concentration limit for one asset class."""
    limit_id: str
    asset_class: TreasuryAssetClass
    base_limit_pct: Decimal
    physical_haircut_pct: Decimal           # subtracted from base
    transition_haircut_pct: Decimal
    adjusted_limit_pct: Decimal             # base × (1 - max(haircut))
    physical_score: Optional[Decimal]      # None if no assessment
    transition_score: Optional[Decimal]
    source_physical_assessments: int
    source_transition_assessments: int
    framework_refs: Tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class LimitBreachReport:
    """Outcome of checking actual exposure vs adjusted limit."""
    asset_class: TreasuryAssetClass
    actual_exposure_pct: Decimal
    adjusted_limit_pct: Decimal
    base_limit_pct: Decimal
    within_adjusted_limit: bool
    within_base_limit: bool
    headroom_pct: Decimal                  # vs adjusted
    breach_severity: str                    # 'NONE', 'WARNING', 'BREACH'


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class ClimateTreasuryLimitsEngine:
    """Composes climate engine + treasury limits into adjusted limits.

    READ-ONLY facade. Climate engine is consulted via methods that
    enumerate physical + transition assessments per sector. Without
    a wired climate engine, limits return base values with notes
    flag indicating no climate adjustment.
    """

    def __init__(
        self, *, entity_name: str = "Ecobank Kenya",
        climate_engine: Any = None,
        custom_base_limits: Optional[
            Mapping[TreasuryAssetClass, Decimal]] = None,
    ):
        self.entity_name = entity_name
        self.climate_engine = climate_engine
        self.base_limits: Mapping[TreasuryAssetClass, Decimal] = (
            dict(DEFAULT_BASE_LIMIT_PCT)
            if custom_base_limits is None
            else dict(custom_base_limits))
        self._adjusted_limits: Dict[
            TreasuryAssetClass, ClimateAdjustedLimit] = {}

    @property
    def has_climate_engine(self) -> bool:
        return self.climate_engine is not None

    def _aggregate_climate_scores(
        self, asset_class: TreasuryAssetClass,
    ) -> Tuple[
        Optional[Decimal], Optional[Decimal], int, int]:
        """Return (avg_physical, avg_transition, n_phys, n_trans)
        for sectors mapped to this asset class.

        If climate engine isn't wired or no assessments → (None, None, 0, 0).
        """
        if self.climate_engine is None:
            return (None, None, 0, 0)
        sectors = ASSET_CLASS_TO_SECTORS.get(asset_class, ())
        if not sectors:
            return (None, None, 0, 0)
        # Try standard accessors on the engine
        # ClimateRiskEngine stores assessments internally; we use
        # board_summary as a public read surface.
        summary = self.climate_engine.board_summary()
        # We'll need direct access to assessments if available
        phys_scores: List[Decimal] = []
        trans_scores: List[Decimal] = []
        # Climate engine internal storage (best-effort access)
        for attr_name in ("_physical_assessments", "_physicals"):
            if hasattr(self.climate_engine, attr_name):
                store = getattr(self.climate_engine, attr_name)
                if isinstance(store, dict):
                    for assess in store.values():
                        if (hasattr(assess, "sector")
                                and hasattr(assess, "risk_score")
                                and assess.sector in sectors):
                            phys_scores.append(assess.risk_score)
                break
        for attr_name in ("_transition_assessments", "_transitions"):
            if hasattr(self.climate_engine, attr_name):
                store = getattr(self.climate_engine, attr_name)
                if isinstance(store, dict):
                    for assess in store.values():
                        if (hasattr(assess, "sector")
                                and hasattr(assess, "risk_score")
                                and assess.sector in sectors):
                            trans_scores.append(assess.risk_score)
                break
        avg_phys = (
            sum(phys_scores, Decimal("0")) / Decimal(len(phys_scores))
            if phys_scores else None)
        avg_trans = (
            sum(trans_scores, Decimal("0"))
            / Decimal(len(trans_scores))
            if trans_scores else None)
        if avg_phys is not None:
            avg_phys = avg_phys.quantize(Decimal("0.01"))
        if avg_trans is not None:
            avg_trans = avg_trans.quantize(Decimal("0.01"))
        return (avg_phys, avg_trans,
                len(phys_scores), len(trans_scores))

    def compute_adjusted_limit(
        self, asset_class: TreasuryAssetClass, *,
        limit_id: Optional[str] = None,
    ) -> ClimateAdjustedLimit:
        """Compute climate-adjusted limit for one asset class."""
        if asset_class not in self.base_limits:
            raise KeyError(
                f"no base limit configured for {asset_class.value}")
        base = self.base_limits[asset_class]
        phys, trans, n_phys, n_trans = (
            self._aggregate_climate_scores(asset_class))
        if phys is None and trans is None:
            phys_haircut = Decimal("0")
            trans_haircut = Decimal("0")
            adjusted = base
            notes = (
                "no climate assessments for this asset class; "
                "base limit applied unadjusted"
                if self.has_climate_engine
                else "climate engine not wired; base limit applied")
        else:
            phys_haircut = (
                haircut_for_score(phys)
                if phys is not None else Decimal("0"))
            trans_haircut = (
                haircut_for_score(trans)
                if trans is not None else Decimal("0"))
            # Apply the larger haircut (worst-of channel)
            applied_haircut = max(phys_haircut, trans_haircut)
            adjusted = (
                base * (Decimal("100") - applied_haircut)
                / Decimal("100")).quantize(Decimal("0.0001"))
            notes = (
                f"applied {applied_haircut}% haircut "
                f"(phys={phys_haircut}%, trans={trans_haircut}%); "
                f"max-of channel")
        result = ClimateAdjustedLimit(
            limit_id=(
                limit_id
                if limit_id is not None
                else f"limit-{asset_class.value}"),
            asset_class=asset_class,
            base_limit_pct=base,
            physical_haircut_pct=phys_haircut,
            transition_haircut_pct=trans_haircut,
            adjusted_limit_pct=adjusted,
            physical_score=phys,
            transition_score=trans,
            source_physical_assessments=n_phys,
            source_transition_assessments=n_trans,
            framework_refs=(
                "BCBS Climate Principles 2022",
                "IFRS S2", "CBK CRDF", "NGFS"),
            notes=notes)
        self._adjusted_limits[asset_class] = result
        return result

    def compute_all_limits(
        self,
    ) -> Tuple[ClimateAdjustedLimit, ...]:
        return tuple(
            self.compute_adjusted_limit(ac)
            for ac in self.base_limits)

    def check_breach(
        self, *, asset_class: TreasuryAssetClass,
        actual_exposure_pct: Decimal,
    ) -> LimitBreachReport:
        """Check actual exposure against the climate-adjusted limit."""
        if asset_class not in self._adjusted_limits:
            self.compute_adjusted_limit(asset_class)
        limit = self._adjusted_limits[asset_class]
        within_adjusted = (
            actual_exposure_pct <= limit.adjusted_limit_pct)
        within_base = (
            actual_exposure_pct <= limit.base_limit_pct)
        headroom = (
            limit.adjusted_limit_pct - actual_exposure_pct
        ).quantize(Decimal("0.0001"))
        if within_adjusted:
            severity = "NONE"
        elif within_base:
            severity = "WARNING"    # over climate limit but under base
        else:
            severity = "BREACH"
        return LimitBreachReport(
            asset_class=asset_class,
            actual_exposure_pct=actual_exposure_pct.quantize(
                Decimal("0.0001")),
            adjusted_limit_pct=limit.adjusted_limit_pct,
            base_limit_pct=limit.base_limit_pct,
            within_adjusted_limit=within_adjusted,
            within_base_limit=within_base,
            headroom_pct=headroom,
            breach_severity=severity)

    @property
    def n_limits_computed(self) -> int:
        return len(self._adjusted_limits)

    def board_summary(self) -> Dict[str, Any]:
        return {
            "entity": self.entity_name,
            "n_asset_classes_configured": len(self.base_limits),
            "n_limits_computed": self.n_limits_computed,
            "climate_engine_wired": self.has_climate_engine,
            "default_base_limits_summary": {
                ac.value: str(v)
                for ac, v in self.base_limits.items()},
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

class _MockAssessment:
    def __init__(self, sector, risk_score):
        self.sector = sector
        self.risk_score = Decimal(str(risk_score))


class _MockClimateEngine:
    """Stub providing _physical_assessments + _transition_assessments."""
    def __init__(self, physicals=(), transitions=()):
        self._physical_assessments = {
            f"p{i}": a for i, a in enumerate(physicals)}
        self._transition_assessments = {
            f"t{i}": a for i, a in enumerate(transitions)}

    def board_summary(self):
        return {
            "n_physical": len(self._physical_assessments),
            "n_transition": len(self._transition_assessments)}


def _test_haircut_low_score():
    assert haircut_for_score(Decimal("10")) == Decimal("1")
    assert haircut_for_score(Decimal("25")) == Decimal("1")


def _test_haircut_severe_score():
    assert haircut_for_score(Decimal("90")) == Decimal("30")


def _test_haircut_mid_band():
    assert haircut_for_score(Decimal("60")) == Decimal("15")


def _test_haircut_clamps_negative():
    assert haircut_for_score(Decimal("-5")) == Decimal("1")


def _test_no_climate_engine_returns_base():
    eng = ClimateTreasuryLimitsEngine()
    limit = eng.compute_adjusted_limit(
        TreasuryAssetClass.CORPORATE_FOSSIL)
    assert limit.adjusted_limit_pct == limit.base_limit_pct
    assert limit.physical_haircut_pct == Decimal("0")
    assert "not wired" in limit.notes


def _test_with_climate_engine_no_assessments_for_class():
    """Climate engine wired but no assessments → base limit."""
    climate = _MockClimateEngine()
    eng = ClimateTreasuryLimitsEngine(climate_engine=climate)
    limit = eng.compute_adjusted_limit(
        TreasuryAssetClass.CORPORATE_FOSSIL)
    assert limit.adjusted_limit_pct == limit.base_limit_pct
    assert "no climate assessments" in limit.notes


def _test_high_transition_risk_tightens_fossil_limit():
    """Fossil with avg transition risk 80 → 30% haircut."""
    climate = _MockClimateEngine(
        transitions=(
            _MockAssessment("oil_and_gas", 80),
            _MockAssessment("coal_mining", 80)))
    eng = ClimateTreasuryLimitsEngine(climate_engine=climate)
    limit = eng.compute_adjusted_limit(
        TreasuryAssetClass.CORPORATE_FOSSIL)
    # base 5% × (1 - 30%) = 3.5%
    assert limit.transition_haircut_pct == Decimal("30")
    assert limit.adjusted_limit_pct == Decimal("3.5000")


def _test_high_physical_risk_tightens_agri_limit():
    """Agri with high physical risk (drought) → 15% haircut."""
    climate = _MockClimateEngine(
        physicals=(
            _MockAssessment("agriculture", 60),))
    eng = ClimateTreasuryLimitsEngine(climate_engine=climate)
    limit = eng.compute_adjusted_limit(
        TreasuryAssetClass.CORPORATE_AGRICULTURE)
    # 60 → 15% haircut
    assert limit.physical_haircut_pct == Decimal("15")
    # base 10% × (1 - 15%) = 8.5%
    assert limit.adjusted_limit_pct == Decimal("8.5000")


def _test_max_of_channel_uses_worse_haircut():
    """Both physical (15%) + transition (5%) → uses max (15%)."""
    climate = _MockClimateEngine(
        physicals=(_MockAssessment("oil_and_gas", 60),),
        transitions=(_MockAssessment("oil_and_gas", 30),))
    eng = ClimateTreasuryLimitsEngine(climate_engine=climate)
    limit = eng.compute_adjusted_limit(
        TreasuryAssetClass.CORPORATE_FOSSIL)
    # max(15%, 5%) = 15% applied
    # base 5% × (1 - 15%) = 4.25%
    assert limit.adjusted_limit_pct == Decimal("4.2500")


def _test_breach_severity_within_adjusted():
    eng = ClimateTreasuryLimitsEngine()
    breach = eng.check_breach(
        asset_class=TreasuryAssetClass.CORPORATE_FOSSIL,
        actual_exposure_pct=Decimal("3"))
    # base 5% no haircut applied → 5% limit
    assert breach.within_adjusted_limit is True
    assert breach.breach_severity == "NONE"


def _test_breach_severity_warning_when_over_adjusted_under_base():
    """Apply haircut so adjusted < actual < base → WARNING."""
    climate = _MockClimateEngine(
        transitions=(_MockAssessment("oil_and_gas", 60),))
    eng = ClimateTreasuryLimitsEngine(climate_engine=climate)
    eng.compute_adjusted_limit(TreasuryAssetClass.CORPORATE_FOSSIL)
    # base 5%, transition 60 → 15% haircut → adjusted 4.25%
    breach = eng.check_breach(
        asset_class=TreasuryAssetClass.CORPORATE_FOSSIL,
        actual_exposure_pct=Decimal("4.5"))    # over adj, under base
    assert breach.breach_severity == "WARNING"
    assert breach.within_base_limit is True
    assert breach.within_adjusted_limit is False


def _test_breach_severity_breach_when_over_base():
    eng = ClimateTreasuryLimitsEngine()
    breach = eng.check_breach(
        asset_class=TreasuryAssetClass.CORPORATE_FOSSIL,
        actual_exposure_pct=Decimal("8"))    # over base 5%
    assert breach.breach_severity == "BREACH"
    assert breach.within_base_limit is False


def _test_compute_all_returns_full_set():
    eng = ClimateTreasuryLimitsEngine()
    all_limits = eng.compute_all_limits()
    assert len(all_limits) == len(DEFAULT_BASE_LIMIT_PCT)


def _test_unknown_asset_class_raises():
    eng = ClimateTreasuryLimitsEngine(
        custom_base_limits={
            TreasuryAssetClass.CORPORATE_FOSSIL: Decimal("5")})
    try:
        eng.compute_adjusted_limit(
            TreasuryAssetClass.SOVEREIGN_KENYA)
        assert False
    except KeyError:
        pass


def _test_board_summary():
    eng = ClimateTreasuryLimitsEngine()
    s = eng.board_summary()
    assert s["climate_engine_wired"] is False
    assert s["n_asset_classes_configured"] >= 10


def self_test() -> None:
    tests = [
        _test_haircut_low_score,
        _test_haircut_severe_score,
        _test_haircut_mid_band,
        _test_haircut_clamps_negative,
        _test_no_climate_engine_returns_base,
        _test_with_climate_engine_no_assessments_for_class,
        _test_high_transition_risk_tightens_fossil_limit,
        _test_high_physical_risk_tightens_agri_limit,
        _test_max_of_channel_uses_worse_haircut,
        _test_breach_severity_within_adjusted,
        _test_breach_severity_warning_when_over_adjusted_under_base,
        _test_breach_severity_breach_when_over_base,
        _test_compute_all_returns_full_set,
        _test_unknown_asset_class_raises,
        _test_board_summary,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ climate_treasury_limits self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ climate_treasury_limits self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
