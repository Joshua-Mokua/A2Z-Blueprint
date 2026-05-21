"""utils/liquidity_stress.py — v10.44: Liquidity Stress Framework.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-LR-001 — Stressed LCR with severity-tiered calibration             ║
║  Cat A — Risk arc continuation                                          ║
╠════════════════════════════════════════════════════════════════════════╣
║  Distinct from utils.liquidity_risk (Standard #73, baseline LCR/NSFR)  ║
║  and utils.stress_testing (Standard #79, capital stress). This module  ║
║  covers the LIQUIDITY-SPECIFIC STRESS dimension per BCBS d295 §40-§57:  ║
║  combined idiosyncratic + market-wide run-off scenario calibration.     ║
║                                                                          ║
║  Severity tiers (BCBS d295 + supervisory practice):                     ║
║    BASELINE             — Basel III standardised run-off rates           ║
║    MODERATE             — supervisory mild stress (~1.5× outflows)       ║
║    SEVERE               — combined idiosyncratic + market-wide (BCBS)    ║
║    BANK_RUN             — full idiosyncratic run on all retail/SME       ║
║                                                                          ║
║  Outputs:                                                                ║
║    Stressed LCR = HQLA_after_haircuts_and_caps / NCO_30d                 ║
║    NCO_30d = stressed_outflows − min(stressed_inflows,                   ║
║                                       0.75 × stressed_outflows)          ║
║    Survival horizon (days) = HQLA / daily NCO if breaching               ║
║    Breach severity ∈ {COMPLIANT, AMBER, RED, CRITICAL}                   ║
║                                                                          ║
║  HQLA caps per BCBS d295 §50:                                            ║
║    Level 2 ≤ 40% of total HQLA                                           ║
║    Level 2B ≤ 15% of total HQLA                                          ║
║                                                                          ║
║  Per Rule 1: every StressedLCRResult surfaces                            ║
║    hqla_per_level + caps_applied + outflows_per_category                 ║
║    + inflows_per_category + nco_kes + lcr_ratio                          ║
║    + breach_severity + survival_days + framework_refs                    ║
║                                                                          ║
║  Per Rule 7: engine is computational only — never auto-liquidates       ║
║  HQLA, never executes funding draws. All inputs caller-provided.        ║
║                                                                          ║
║  Pure stdlib (Decimal). No scipy.                                        ║
║                                                                          ║
║  Composes with:                                                          ║
║    - liquidity_risk (Standard #73 baseline LCR — not imported to keep   ║
║      G128 import edges minimal; constants mirrored)                     ║
║    - stress_testing (Standard #79 capital stress — orthogonal axis)     ║
║    - market_risk_limits (limit framework for breach escalation —        ║
║      future composition)                                                 ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Mapping, Optional, Tuple

SPEC_DEVIATION_NOTE = (
    "LiquidityStressEngine implements ENH-LR-001 BCBS d295 stressed "
    "LCR. Pure Decimal arithmetic. Per Rule 1, every StressedLCRResult "
    "surfaces all inputs + intermediates (HQLA per level, caps "
    "applied, per-category outflows/inflows, NCO components) + "
    "outputs (LCR ratio, breach severity, survival horizon). Per "
    "Rule 7, engine is computational only — never auto-liquidates "
    "HQLA, never executes funding draws. Severity calibration is "
    "data-driven via the SEVERITY_MULTIPLIERS table — caller can "
    "supply overrides for supervisor-mandated scenarios."
)

# ════════════════════════════════════════════════════════════════════════
# Constants per BCBS d295
# ════════════════════════════════════════════════════════════════════════

# HQLA haircuts (BCBS d295 §50)
HAIRCUT_LEVEL_1 = Decimal("0.00")
HAIRCUT_LEVEL_2A = Decimal("0.15")
HAIRCUT_LEVEL_2B = Decimal("0.50")

# HQLA composition caps (BCBS d295 §50)
LEVEL_2_CAP_PCT = Decimal("0.40")    # 40% of total HQLA
LEVEL_2B_CAP_PCT = Decimal("0.15")   # 15% of total HQLA

# Inflow cap per BCBS d295 §69 (75% of total outflows)
INFLOW_CAP_PCT = Decimal("0.75")

# LCR threshold (BCBS d295 §17)
LCR_MIN = Decimal("1.00")

# 30-day stress horizon (BCBS d295 §15)
HORIZON_DAYS = 30


class HQLALevel(Enum):
    """BCBS d295 §50 HQLA classifications."""
    LEVEL_1 = "LEVEL_1"     # 0% haircut
    LEVEL_2A = "LEVEL_2A"   # 15% haircut
    LEVEL_2B = "LEVEL_2B"   # 50% haircut


class StressSeverity(Enum):
    """Stress scenario severity tiers."""
    BASELINE = "BASELINE"        # standard Basel III run-offs
    MODERATE = "MODERATE"        # supervisory mild stress
    SEVERE = "SEVERE"            # BCBS d295 combined scenario
    BANK_RUN = "BANK_RUN"        # full idiosyncratic run


class BreachSeverity(Enum):
    """LCR breach classification."""
    COMPLIANT = "COMPLIANT"      # LCR ≥ 100%
    AMBER = "AMBER"              # 90% ≤ LCR < 100%
    RED = "RED"                  # 70% ≤ LCR < 90%
    CRITICAL = "CRITICAL"        # LCR < 70%


# ════════════════════════════════════════════════════════════════════════
# Severity multiplier table per BCBS d295 §40-§57
# Multipliers apply to the BASELINE run-off rate to produce the stressed
# rate, capped at 1.0 (cannot exceed 100%).
# ════════════════════════════════════════════════════════════════════════

SEVERITY_MULTIPLIERS: Dict[StressSeverity, Decimal] = {
    StressSeverity.BASELINE: Decimal("1.0"),
    StressSeverity.MODERATE: Decimal("1.5"),
    StressSeverity.SEVERE:   Decimal("2.0"),
    StressSeverity.BANK_RUN: Decimal("3.0"),
}

# Inflow run-in multipliers — under stress, inflows reduce
INFLOW_MULTIPLIERS: Dict[StressSeverity, Decimal] = {
    StressSeverity.BASELINE: Decimal("1.0"),
    StressSeverity.MODERATE: Decimal("0.85"),
    StressSeverity.SEVERE:   Decimal("0.65"),
    StressSeverity.BANK_RUN: Decimal("0.40"),
}


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class HQLAHolding:
    """One HQLA position pre-haircut."""
    holding_id: str
    level: HQLALevel
    market_value_kes: Decimal

    def __post_init__(self) -> None:
        if self.market_value_kes < 0:
            raise ValueError(
                f"holding {self.holding_id}: market value must be ≥ 0")


@dataclass(frozen=True)
class OutflowCategory:
    """One outflow category with baseline run-off rate (Decimal-fraction)."""
    category_id: str
    label: str
    balance_kes: Decimal
    base_run_off_rate: Decimal      # in [0, 1]

    def __post_init__(self) -> None:
        if self.balance_kes < 0:
            raise ValueError(
                f"{self.category_id}: balance must be ≥ 0")
        if not (Decimal("0") <= self.base_run_off_rate <= Decimal("1")):
            raise ValueError(
                f"{self.category_id}: base_run_off_rate "
                f"{self.base_run_off_rate} outside [0, 1]")


@dataclass(frozen=True)
class InflowCategory:
    """One inflow category with baseline run-in rate."""
    category_id: str
    label: str
    balance_kes: Decimal
    base_run_in_rate: Decimal       # in [0, 1]

    def __post_init__(self) -> None:
        if self.balance_kes < 0:
            raise ValueError(
                f"{self.category_id}: balance must be ≥ 0")
        if not (Decimal("0") <= self.base_run_in_rate <= Decimal("1")):
            raise ValueError(
                f"{self.category_id}: base_run_in_rate "
                f"{self.base_run_in_rate} outside [0, 1]")


@dataclass(frozen=True)
class StressedFlow:
    """One outflow or inflow after stress multiplier applied."""
    category_id: str
    label: str
    balance_kes: Decimal
    base_rate: Decimal
    stress_multiplier: Decimal
    stressed_rate: Decimal      # capped at 1.0
    stressed_kes: Decimal


@dataclass(frozen=True)
class HQLABreakdown:
    """Per-level HQLA after haircut, before caps."""
    level: HQLALevel
    gross_kes: Decimal
    haircut_pct: Decimal
    after_haircut_kes: Decimal


@dataclass(frozen=True)
class StressedLCRResult:
    """Output of a stressed LCR computation. Per Rule 1, surfaces all
    inputs + intermediates + outputs."""
    severity: StressSeverity
    hqla_breakdown: Tuple[HQLABreakdown, ...]
    hqla_total_pre_cap_kes: Decimal
    hqla_level2_capped_kes: Decimal
    hqla_level2b_capped_kes: Decimal
    hqla_total_after_caps_kes: Decimal
    outflows: Tuple[StressedFlow, ...]
    inflows: Tuple[StressedFlow, ...]
    total_outflows_kes: Decimal
    total_inflows_kes: Decimal
    inflows_capped_kes: Decimal
    nco_30d_kes: Decimal
    lcr_ratio: Optional[Decimal]   # None when NCO ≤ 0
    breach_severity: BreachSeverity
    survival_days: Optional[Decimal]   # None when LCR ≥ 100%
    framework_refs: Tuple[str, ...]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class LiquidityStressEngine:
    """BCBS d295 stressed LCR engine.

    Per Rule 7, computational only. The engine never:
      - auto-liquidates HQLA
      - executes funding draws
      - rebalances category assignments
    """

    HAIRCUTS = {
        HQLALevel.LEVEL_1: HAIRCUT_LEVEL_1,
        HQLALevel.LEVEL_2A: HAIRCUT_LEVEL_2A,
        HQLALevel.LEVEL_2B: HAIRCUT_LEVEL_2B,
    }

    # ── HQLA computation with caps ────────────────────────────────────
    def _hqla_per_level(
        self, holdings: Tuple[HQLAHolding, ...],
    ) -> Tuple[HQLABreakdown, ...]:
        by_level: Dict[HQLALevel, Decimal] = {
            lvl: Decimal("0") for lvl in HQLALevel}
        for h in holdings:
            by_level[h.level] += h.market_value_kes
        return tuple(
            HQLABreakdown(
                level=lvl,
                gross_kes=by_level[lvl].quantize(Decimal("0.01")),
                haircut_pct=self.HAIRCUTS[lvl],
                after_haircut_kes=(
                    by_level[lvl] * (Decimal("1") - self.HAIRCUTS[lvl])
                ).quantize(Decimal("0.01")))
            for lvl in HQLALevel)

    def _apply_caps(
        self, breakdown: Tuple[HQLABreakdown, ...],
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """Apply Level 2 ≤ 40% and Level 2B ≤ 15% caps.

        Caps are computed against TOTAL HQLA after caps, which the
        BCBS d295 §50 'unwind' approach approximates by:
          1. Compute pre-cap totals.
          2. Cap L2B at 15% of post-cap total ≡ 15/85 of L1+L2A_after_haircut.
          3. Cap L2 at 40% of post-cap total ≡ 2/3 of L1.

        Returns (level1, level2a_capped, level2b_capped, total).
        """
        l1 = next(
            b.after_haircut_kes for b in breakdown
            if b.level == HQLALevel.LEVEL_1)
        l2a = next(
            b.after_haircut_kes for b in breakdown
            if b.level == HQLALevel.LEVEL_2A)
        l2b = next(
            b.after_haircut_kes for b in breakdown
            if b.level == HQLALevel.LEVEL_2B)

        # L2B cap: ≤ 15% of total HQLA after cap.
        # Equivalently: L2B_cap = (15/85) × (L1 + L2A_capped + 0)
        # Iterative: first cap L2B against L1+L2A unwind cap.
        # 15/85 ≈ 0.176470588...
        l2b_max_first_pass = (Decimal("15") / Decimal("85")) * (l1 + l2a)
        l2b_capped = min(l2b, l2b_max_first_pass)

        # L2 cap: L2A + L2B_capped ≤ 40% of total HQLA after cap.
        # Equivalently: L2_cap = (40/60) × L1 = (2/3) × L1
        l2_max = (Decimal("40") / Decimal("60")) * l1
        l2_total_uncapped = l2a + l2b_capped
        if l2_total_uncapped <= l2_max:
            l2a_final = l2a
            l2b_final = l2b_capped
        else:
            # Reduce proportionally — preserve L2A first (lower haircut)
            # by capping L2B first, then trimming L2A if still over
            if l2b_capped <= l2_max:
                # L2A must absorb the rest of the cap
                l2b_final = l2b_capped
                l2a_final = l2_max - l2b_capped
            else:
                # Even L2B alone exceeds cap — rare edge
                l2b_final = l2_max
                l2a_final = Decimal("0")

        total = (l1 + l2a_final + l2b_final).quantize(Decimal("0.01"))
        return (
            l1.quantize(Decimal("0.01")),
            l2a_final.quantize(Decimal("0.01")),
            l2b_final.quantize(Decimal("0.01")),
            total)

    # ── Stressed flows ────────────────────────────────────────────────
    def _stress_outflows(
        self, outflows: Tuple[OutflowCategory, ...],
        severity: StressSeverity,
        rate_overrides: Mapping[str, Decimal],
    ) -> Tuple[StressedFlow, ...]:
        mult = SEVERITY_MULTIPLIERS[severity]
        flows: List[StressedFlow] = []
        for cat in outflows:
            base = rate_overrides.get(cat.category_id, cat.base_run_off_rate)
            stressed = min(base * mult, Decimal("1"))
            flows.append(StressedFlow(
                category_id=cat.category_id,
                label=cat.label,
                balance_kes=cat.balance_kes,
                base_rate=base,
                stress_multiplier=mult,
                stressed_rate=stressed,
                stressed_kes=(cat.balance_kes * stressed).quantize(
                    Decimal("0.01"))))
        return tuple(flows)

    def _stress_inflows(
        self, inflows: Tuple[InflowCategory, ...],
        severity: StressSeverity,
    ) -> Tuple[StressedFlow, ...]:
        mult = INFLOW_MULTIPLIERS[severity]
        flows: List[StressedFlow] = []
        for cat in inflows:
            stressed = min(cat.base_run_in_rate * mult, Decimal("1"))
            flows.append(StressedFlow(
                category_id=cat.category_id,
                label=cat.label,
                balance_kes=cat.balance_kes,
                base_rate=cat.base_run_in_rate,
                stress_multiplier=mult,
                stressed_rate=stressed,
                stressed_kes=(cat.balance_kes * stressed).quantize(
                    Decimal("0.01"))))
        return tuple(flows)

    # ── NCO + breach classification ───────────────────────────────────
    def _classify_breach(
        self, lcr: Optional[Decimal],
    ) -> BreachSeverity:
        if lcr is None or lcr >= LCR_MIN:
            return BreachSeverity.COMPLIANT
        if lcr >= Decimal("0.90"):
            return BreachSeverity.AMBER
        if lcr >= Decimal("0.70"):
            return BreachSeverity.RED
        return BreachSeverity.CRITICAL

    # ── Public API ────────────────────────────────────────────────────
    def compute(
        self, holdings: Tuple[HQLAHolding, ...],
        outflows: Tuple[OutflowCategory, ...],
        inflows: Tuple[InflowCategory, ...],
        severity: StressSeverity = StressSeverity.SEVERE,
        outflow_rate_overrides: Optional[Mapping[str, Decimal]] = None,
        notes: str = "",
    ) -> StressedLCRResult:
        """Compute stressed LCR + survival horizon + breach severity."""
        overrides = outflow_rate_overrides or {}

        # 1. HQLA per level + caps
        breakdown = self._hqla_per_level(holdings)
        pre_cap_total = sum(
            (b.after_haircut_kes for b in breakdown), Decimal("0")
        ).quantize(Decimal("0.01"))
        l1, l2a, l2b, hqla_total = self._apply_caps(breakdown)

        # 2. Stressed flows
        out_flows = self._stress_outflows(outflows, severity, overrides)
        in_flows = self._stress_inflows(inflows, severity)
        total_out = sum(
            (f.stressed_kes for f in out_flows), Decimal("0")
        ).quantize(Decimal("0.01"))
        total_in = sum(
            (f.stressed_kes for f in in_flows), Decimal("0")
        ).quantize(Decimal("0.01"))
        capped_in = min(total_in, INFLOW_CAP_PCT * total_out).quantize(
            Decimal("0.01"))
        nco = (total_out - capped_in).quantize(Decimal("0.01"))

        # 3. LCR + breach + survival
        if nco <= 0:
            lcr_ratio: Optional[Decimal] = None
        else:
            lcr_ratio = (hqla_total / nco).quantize(Decimal("0.000001"))
        breach = self._classify_breach(lcr_ratio)
        if lcr_ratio is None or lcr_ratio >= LCR_MIN:
            survival: Optional[Decimal] = None
        else:
            # Daily run-off proxy: NCO / 30, days = HQLA / daily_burn
            daily = nco / Decimal(HORIZON_DAYS)
            survival = (
                hqla_total / daily).quantize(Decimal("0.1"))

        return StressedLCRResult(
            severity=severity,
            hqla_breakdown=breakdown,
            hqla_total_pre_cap_kes=pre_cap_total,
            hqla_level2_capped_kes=(l2a + l2b).quantize(Decimal("0.01")),
            hqla_level2b_capped_kes=l2b,
            hqla_total_after_caps_kes=hqla_total,
            outflows=out_flows,
            inflows=in_flows,
            total_outflows_kes=total_out,
            total_inflows_kes=total_in,
            inflows_capped_kes=capped_in,
            nco_30d_kes=nco,
            lcr_ratio=lcr_ratio,
            breach_severity=breach,
            survival_days=survival,
            framework_refs=(
                "BCBS d295 §40-§69 LCR",
                "Basel III Liquidity Framework",
                "CBK PG/12 Liquidity Risk Management"),
            notes=notes)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _h(hid, lvl, mv):
    return HQLAHolding(
        holding_id=hid, level=lvl,
        market_value_kes=Decimal(str(mv)))


def _o(cid, bal, rate, label="x"):
    return OutflowCategory(
        category_id=cid, label=label,
        balance_kes=Decimal(str(bal)),
        base_run_off_rate=Decimal(str(rate)))


def _i(cid, bal, rate, label="x"):
    return InflowCategory(
        category_id=cid, label=label,
        balance_kes=Decimal(str(bal)),
        base_run_in_rate=Decimal(str(rate)))


def _test_holding_validates_non_negative():
    try:
        _h("bad", HQLALevel.LEVEL_1, -1)
        assert False
    except ValueError:
        pass


def _test_outflow_validates_rate_in_range():
    try:
        _o("bad", 1000, 1.5)
        assert False
    except ValueError:
        pass


def _test_inflow_validates_rate_in_range():
    try:
        _i("bad", 1000, -0.1)
        assert False
    except ValueError:
        pass


def _test_haircuts_applied_per_level():
    eng = LiquidityStressEngine()
    holdings = (
        _h("l1", HQLALevel.LEVEL_1, 1000),
        _h("l2a", HQLALevel.LEVEL_2A, 1000),
        _h("l2b", HQLALevel.LEVEL_2B, 1000))
    bd = eng._hqla_per_level(holdings)
    by_lvl = {b.level: b for b in bd}
    assert by_lvl[HQLALevel.LEVEL_1].after_haircut_kes == Decimal("1000.00")
    assert by_lvl[HQLALevel.LEVEL_2A].after_haircut_kes == Decimal("850.00")
    assert by_lvl[HQLALevel.LEVEL_2B].after_haircut_kes == Decimal("500.00")


def _test_level2b_cap_15pct_of_total():
    """Heavy L2B holdings get capped at 15% of total HQLA."""
    eng = LiquidityStressEngine()
    holdings = (
        _h("l1", HQLALevel.LEVEL_1, 1000000),
        _h("l2b", HQLALevel.LEVEL_2B, 100000000))
    r = eng.compute(
        holdings, outflows=(_o("a", 1000, 1.0),), inflows=(),
        severity=StressSeverity.BASELINE)
    # L2B was capped (raw L2B-after-haircut = 50m, but only ~176k allowed)
    # Expected cap value: (15/85) × L1 = (15/85) × 1m ≈ 176,470.59
    expected = (Decimal("15") / Decimal("85")) * Decimal("1000000")
    diff = abs(r.hqla_level2b_capped_kes - expected)
    assert diff < Decimal("1"), (
        f"L2B cap {r.hqla_level2b_capped_kes} != expected "
        f"{expected.quantize(Decimal('0.01'))} (diff {diff})")
    # And the share is at or below 15% within quantization tolerance
    total = r.hqla_total_after_caps_kes
    share = r.hqla_level2b_capped_kes / total
    assert share <= Decimal("0.151"), (
        f"L2B share {share} materially exceeds 15% cap")


def _test_level2_cap_40pct_of_total():
    """Heavy L2 (A+B) holdings get capped at 40% of total HQLA."""
    eng = LiquidityStressEngine()
    holdings = (
        _h("l1", HQLALevel.LEVEL_1, 1000000),
        _h("l2a", HQLALevel.LEVEL_2A, 10000000))
    r = eng.compute(
        holdings, outflows=(_o("a", 1000, 1.0),), inflows=(),
        severity=StressSeverity.BASELINE)
    # L2 cap: (40/60) × L1 = (2/3) × 1m ≈ 666,666.67
    expected_l2_cap = (Decimal("40") / Decimal("60")) * Decimal("1000000")
    actual_l2 = r.hqla_level2_capped_kes
    diff = abs(actual_l2 - expected_l2_cap)
    assert diff < Decimal("1"), (
        f"L2 cap {actual_l2} != expected "
        f"{expected_l2_cap.quantize(Decimal('0.01'))} (diff {diff})")
    total = r.hqla_total_after_caps_kes
    share = actual_l2 / total
    assert share <= Decimal("0.401"), (
        f"L2 share {share} materially exceeds 40% cap")


def _test_inflow_cap_75pct_of_outflows():
    """Inflows above 75% of outflows are capped."""
    eng = LiquidityStressEngine()
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 1000),),
        outflows=(_o("o", 1000, 0.5),),     # outflow = 500
        inflows=(_i("i", 10000, 0.5),),     # inflow = 5000 → capped at 375
        severity=StressSeverity.BASELINE)
    expected_cap = Decimal("375.00")  # 0.75 × 500
    assert r.inflows_capped_kes == expected_cap, (
        f"capped inflow {r.inflows_capped_kes}, expected {expected_cap}")


def _test_severity_multiplier_increases_outflows():
    eng = LiquidityStressEngine()
    holdings = (_h("l1", HQLALevel.LEVEL_1, 1000),)
    out = (_o("retail", 10000, 0.05),)
    inf = ()
    base = eng.compute(holdings, out, inf, StressSeverity.BASELINE)
    sev = eng.compute(holdings, out, inf, StressSeverity.SEVERE)
    assert sev.total_outflows_kes > base.total_outflows_kes


def _test_severity_multiplier_capped_at_one():
    """Stressed rate cannot exceed 100%."""
    eng = LiquidityStressEngine()
    # Base 50% × 3 (BANK_RUN) = 150% → capped at 100%
    holdings = (_h("l1", HQLALevel.LEVEL_1, 1000),)
    out = (_o("financial", 1000, 0.50),)
    r = eng.compute(holdings, out, (), StressSeverity.BANK_RUN)
    assert r.outflows[0].stressed_rate == Decimal("1.0")
    assert r.outflows[0].stressed_kes == Decimal("1000.00")


def _test_lcr_compliant_returns_compliant_severity():
    eng = LiquidityStressEngine()
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 100000),),
        outflows=(_o("o", 1000, 0.05),),
        inflows=(),
        severity=StressSeverity.BASELINE)
    assert r.breach_severity == BreachSeverity.COMPLIANT
    assert r.lcr_ratio is not None and r.lcr_ratio >= Decimal("1")
    assert r.survival_days is None


def _test_lcr_amber_band():
    """LCR in [90%, 100%) → AMBER."""
    eng = LiquidityStressEngine()
    # HQLA = 950, NCO = 1000 → LCR = 0.95
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 950),),
        outflows=(_o("o", 1000, 1.0),),
        inflows=(),
        severity=StressSeverity.BASELINE)
    assert r.lcr_ratio == Decimal("0.950000")
    assert r.breach_severity == BreachSeverity.AMBER
    assert r.survival_days is not None


def _test_lcr_red_band():
    """LCR in [70%, 90%) → RED."""
    eng = LiquidityStressEngine()
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 800),),
        outflows=(_o("o", 1000, 1.0),),
        inflows=(),
        severity=StressSeverity.BASELINE)
    assert r.lcr_ratio == Decimal("0.800000")
    assert r.breach_severity == BreachSeverity.RED


def _test_lcr_critical_band():
    """LCR < 70% → CRITICAL."""
    eng = LiquidityStressEngine()
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 500),),
        outflows=(_o("o", 1000, 1.0),),
        inflows=(),
        severity=StressSeverity.BASELINE)
    assert r.breach_severity == BreachSeverity.CRITICAL


def _test_zero_nco_returns_none_lcr():
    """Per Rule 1: LCR = None when NCO ≤ 0 (cannot compute ratio)."""
    eng = LiquidityStressEngine()
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 1000),),
        outflows=(_o("o", 0, 0.5),),    # zero balance → zero outflow
        inflows=(),
        severity=StressSeverity.BASELINE)
    assert r.lcr_ratio is None
    assert r.breach_severity == BreachSeverity.COMPLIANT
    assert r.survival_days is None


def _test_survival_days_uses_30day_horizon():
    """Survival = HQLA / (NCO/30) when breaching."""
    eng = LiquidityStressEngine()
    # HQLA = 600, NCO = 1000, daily burn ≈ 33.33, survival ≈ 18 days
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 600),),
        outflows=(_o("o", 1000, 1.0),),
        inflows=(),
        severity=StressSeverity.BASELINE)
    assert r.survival_days is not None
    # 600 / (1000/30) = 18
    assert abs(r.survival_days - Decimal("18.0")) < Decimal("0.5")


def _test_outflow_rate_override_takes_precedence():
    """Caller-supplied override replaces base rate before stress mult."""
    eng = LiquidityStressEngine()
    out = (_o("retail", 1000, 0.05),)
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 100000),),
        outflows=out, inflows=(),
        severity=StressSeverity.BASELINE,
        outflow_rate_overrides={"retail": Decimal("0.20")})
    assert r.outflows[0].base_rate == Decimal("0.20")
    assert r.outflows[0].stressed_rate == Decimal("0.20")
    assert r.outflows[0].stressed_kes == Decimal("200.00")


def _test_result_surfaces_full_provenance():
    """Per Rule 1: full provenance on every StressedLCRResult."""
    eng = LiquidityStressEngine()
    r = eng.compute(
        holdings=(_h("l1", HQLALevel.LEVEL_1, 1000),
                  _h("l2a", HQLALevel.LEVEL_2A, 500)),
        outflows=(_o("o1", 1000, 0.4),),
        inflows=(_i("i1", 500, 0.5),),
        severity=StressSeverity.SEVERE)
    assert len(r.hqla_breakdown) == 3   # all 3 levels surfaced
    assert r.hqla_total_pre_cap_kes > 0
    assert r.severity == StressSeverity.SEVERE
    assert any("BCBS d295" in ref for ref in r.framework_refs)
    assert r.outflows[0].stress_multiplier == SEVERITY_MULTIPLIERS[
        StressSeverity.SEVERE]


def _test_inflow_multiplier_reduces_inflows_under_stress():
    eng = LiquidityStressEngine()
    inf = (_i("i", 1000, 0.50),)
    out = (_o("o", 10000, 0.10),)
    holdings = (_h("l1", HQLALevel.LEVEL_1, 100),)
    base = eng.compute(holdings, out, inf, StressSeverity.BASELINE)
    sev = eng.compute(holdings, out, inf, StressSeverity.SEVERE)
    assert sev.total_inflows_kes < base.total_inflows_kes


def self_test() -> None:
    tests = [
        _test_holding_validates_non_negative,
        _test_outflow_validates_rate_in_range,
        _test_inflow_validates_rate_in_range,
        _test_haircuts_applied_per_level,
        _test_level2b_cap_15pct_of_total,
        _test_level2_cap_40pct_of_total,
        _test_inflow_cap_75pct_of_outflows,
        _test_severity_multiplier_increases_outflows,
        _test_severity_multiplier_capped_at_one,
        _test_lcr_compliant_returns_compliant_severity,
        _test_lcr_amber_band,
        _test_lcr_red_band,
        _test_lcr_critical_band,
        _test_zero_nco_returns_none_lcr,
        _test_survival_days_uses_30day_horizon,
        _test_outflow_rate_override_takes_precedence,
        _test_result_surfaces_full_provenance,
        _test_inflow_multiplier_reduces_inflows_under_stress,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ liquidity_stress self-test: {len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ liquidity_stress self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
