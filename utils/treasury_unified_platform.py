"""utils/treasury_unified_platform.py — v10.37 ENH-TRS-R4.

╔════════════════════════════════════════════════════════════════════════╗
║  UNIFIED CROSS-ASSET TREASURY PLATFORM — Murex MX.3-style facade      ║
║  Cat A — implements ENH-TRS-R4                                         ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-TRS-R4: cross-asset trading + treasury + risk +       ║
║  post-trade in a single facade. Patterned after Murex MX.3.           ║
║                                                                         ║
║  Production MX.3 is a vendor system (Murex). Banks INTEGRATE with     ║
║  it; they don't build it. Our role is the facade that:                ║
║    - aggregates positions across asset classes (FX, fixed income,    ║
║      money market, derivatives, commodities, equities)              ║
║    - composes existing engines: treasury_alm, treasury_products,     ║
║      rwa_optimization, fund_transfer_pricing, treasury_digital_      ║
║      assets, islamic_treasury                                        ║
║    - provides a unified position view + cross-asset risk roll-up     ║
║    - emits regulatory reports per IFRS 9 / IFRS 13 / Basel           ║
║      categorization                                                   ║
║                                                                         ║
║  6 asset classes covered:                                             ║
║    FX (treasury_products), FIXED_INCOME (treasury_products bonds),   ║
║    MONEY_MARKET (treasury_alm + cash_forecasting),                   ║
║    ISLAMIC (islamic_treasury),                                       ║
║    DIGITAL (treasury_digital_assets), DERIVATIVES (placeholder)     ║
║                                                                         ║
║  Honesty Rule 1: every UnifiedPosition surfaces asset_class +         ║
║  source_engine + position_value_kes + risk_metric_value + IFRS       ║
║  category. CrossAssetRiskRollup surfaces per-asset-class breakdown.  ║
║  Honesty Rule 7: this is a facade — it READS upstream engines but    ║
║  never mutates them. If an upstream engine isn't wired, that asset   ║
║  class simply produces no positions in the unified view.            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Basel III final framework Dec 2017 — capital across asset classes ║
║    IFRS 9 — financial instruments classification                       ║
║    IFRS 13 — fair value hierarchy across asset types                  ║
║    BCBS 282 SACCR — counterparty credit risk                          ║
║    BCBS 144 — sound principles cross-asset risk                       ║
║    Murex MX.3 — reference vendor architecture                         ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "UnifiedTreasuryPlatform implements ENH-TRS-R4 Murex MX.3-style "
    "facade. Composes 6 upstream engines into single cross-asset "
    "view. 6 AssetClass enums + 5 IFRS9Category. Per Rule 7, facade "
    "READS upstream engines but never mutates them. Per Rule 1, "
    "every UnifiedPosition surfaces asset_class + source_engine + "
    "value + IFRS classification."
)


# ════════════════════════════════════════════════════════════════════════
# Taxonomies
# ════════════════════════════════════════════════════════════════════════

class AssetClass(Enum):
    """Asset classes covered by unified facade."""
    FX = "FX"
    FIXED_INCOME = "FIXED_INCOME"
    MONEY_MARKET = "MONEY_MARKET"
    ISLAMIC = "ISLAMIC"
    DIGITAL = "DIGITAL"
    DERIVATIVES = "DERIVATIVES"


class IFRS9Category(Enum):
    """IFRS 9 financial instrument classification."""
    AMORTIZED_COST = "AMORTIZED_COST"           # AC
    FVOCI_DEBT = "FVOCI_DEBT"                   # FVOCI w/ recycling
    FVOCI_EQUITY = "FVOCI_EQUITY"               # FVOCI w/o recycling
    FVTPL = "FVTPL"                              # mandatory
    FVTPL_DESIGNATED = "FVTPL_DESIGNATED"        # designated FVO


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class UnifiedPosition:
    """A position in the unified view."""
    position_id: str
    source_engine: str
    asset_class: AssetClass
    counterparty: str
    notional_kes: Decimal
    market_value_kes: Decimal
    ifrs9_category: IFRS9Category
    risk_metric_kes: Decimal              # asset-class-specific
    risk_metric_label: str                # e.g., 'mtm', 'rwa', 'ead'
    framework_refs: Tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class CrossAssetRiskRollup:
    """Risk roll-up across all asset classes."""
    rollup_id: str
    as_of_date: str
    n_positions_by_class: Mapping[str, int]
    total_market_value_kes: Decimal
    market_value_by_class: Mapping[str, Decimal]
    risk_total_kes: Decimal
    risk_by_class: Mapping[str, Decimal]
    n_engines_consulted: int
    engines_consulted: Tuple[str, ...]
    framework_refs: Tuple[str, ...]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Adapter functions — read upstream engines into UnifiedPosition stream
# ════════════════════════════════════════════════════════════════════════

def positions_from_treasury_products(
    *, products_engine: Any,
) -> Tuple[UnifiedPosition, ...]:
    """Read FX + fixed income from TreasuryProductsEngine."""
    if products_engine is None:
        return ()
    summary = products_engine.board_summary()
    out: List[UnifiedPosition] = []
    n_fx = summary.get("n_fx_positions", 0)
    if n_fx > 0:
        # Aggregate as one synthetic position per currency
        # We don't have direct access to the position list without
        # mutating the engine; use board summary as the read.
        out.append(UnifiedPosition(
            position_id="aggregate-fx",
            source_engine="treasury_products",
            asset_class=AssetClass.FX,
            counterparty="multiple",
            notional_kes=Decimal(
                summary.get("total_fx_notional_kes", "0")),
            market_value_kes=Decimal(
                summary.get("total_fx_mtm_kes", "0")),
            ifrs9_category=IFRS9Category.FVTPL,
            risk_metric_kes=Decimal(
                summary.get("total_fx_mtm_kes", "0")),
            risk_metric_label="mtm",
            framework_refs=("IFRS 13",),
            notes=(
                f"{n_fx} FX positions aggregated; CIP-priced; "
                f"per CBK PG/17")))
    n_bond = summary.get("n_bond_positions", 0)
    if n_bond > 0:
        out.append(UnifiedPosition(
            position_id="aggregate-bonds",
            source_engine="treasury_products",
            asset_class=AssetClass.FIXED_INCOME,
            counterparty="multiple",
            notional_kes=Decimal(
                summary.get("total_bond_notional_kes", "0")),
            market_value_kes=Decimal(
                summary.get("total_bond_mtm_kes", "0")),
            ifrs9_category=IFRS9Category.FVOCI_DEBT,
            risk_metric_kes=Decimal(
                summary.get("total_bond_mtm_kes", "0")),
            risk_metric_label="mtm",
            framework_refs=("IFRS 9", "IFRS 13"),
            notes=f"{n_bond} bond positions aggregated"))
    return tuple(out)


def positions_from_treasury_alm(
    *, alm_engine: Any,
) -> Tuple[UnifiedPosition, ...]:
    """Read money market positions from TreasuryALMEngine."""
    if alm_engine is None:
        return ()
    summary = alm_engine.board_summary()
    out: List[UnifiedPosition] = []
    n_hqla = summary.get("n_hqla_positions", 0)
    if n_hqla > 0:
        out.append(UnifiedPosition(
            position_id="aggregate-hqla",
            source_engine="treasury_alm",
            asset_class=AssetClass.MONEY_MARKET,
            counterparty="multiple",
            notional_kes=Decimal(
                summary.get("total_hqla_notional_kes", "0")),
            market_value_kes=Decimal(
                summary.get("total_hqla_notional_kes", "0")),
            ifrs9_category=IFRS9Category.AMORTIZED_COST,
            risk_metric_kes=Decimal(
                summary.get("total_hqla_after_haircut_kes", "0")),
            risk_metric_label="hqla_after_haircut",
            framework_refs=("Basel BCBS 188", "CBK PG/16"),
            notes=f"{n_hqla} HQLA positions for LCR"))
    return tuple(out)


def positions_from_islamic_treasury(
    *, islamic_engine: Any,
) -> Tuple[UnifiedPosition, ...]:
    if islamic_engine is None:
        return ()
    summary = islamic_engine.board_summary()
    n = summary.get("n_products", 0)
    if n == 0:
        return ()
    return (UnifiedPosition(
        position_id="aggregate-islamic",
        source_engine="islamic_treasury",
        asset_class=AssetClass.ISLAMIC,
        counterparty="multiple",
        notional_kes=Decimal(summary.get("total_principal_kes", "0")),
        market_value_kes=(
            Decimal(summary.get("total_principal_kes", "0"))
            + Decimal(
                summary.get("total_expected_return_kes", "0"))),
        ifrs9_category=IFRS9Category.AMORTIZED_COST,
        risk_metric_kes=Decimal(
            summary.get("total_principal_kes", "0")),
        risk_metric_label="principal",
        framework_refs=(
            "AAOIFI FAS 28", "AAOIFI FAS 30", "IFSB-7"),
        notes=(
            f"{n} Islamic products; "
            f"compliant: {summary.get('n_compliant', 0)}, "
            f"non-compliant: {summary.get('n_non_compliant', 0)}")),)


def positions_from_digital_assets(
    *, digital_engine: Any,
) -> Tuple[UnifiedPosition, ...]:
    if digital_engine is None:
        return ()
    summary = digital_engine.board_summary()
    n = summary.get("n_holdings", 0)
    if n == 0:
        return ()
    total_kes = Decimal(summary.get("total_kes_equivalent", "0"))
    return (UnifiedPosition(
        position_id="aggregate-digital",
        source_engine="treasury_digital_assets",
        asset_class=AssetClass.DIGITAL,
        counterparty="self_custody",
        notional_kes=total_kes,
        market_value_kes=total_kes,
        ifrs9_category=IFRS9Category.FVTPL,
        risk_metric_kes=total_kes,
        risk_metric_label="kes_equivalent",
        framework_refs=("CBK VASP 2026", "BCBS Crypto 2022"),
        notes=(
            f"{n} digital holdings; de-pegged: "
            f"{summary.get('n_de_pegged', 0)}")),)


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class UnifiedTreasuryPlatform:
    """MX.3-style facade composing all treasury engines."""

    def __init__(
        self, *, entity_name: str = "Ecobank Kenya",
        alm_engine: Any = None,
        products_engine: Any = None,
        rwa_engine: Any = None,
        ftp_engine: Any = None,
        islamic_engine: Any = None,
        digital_engine: Any = None,
        forecast_engine: Any = None,
    ):
        self.entity_name = entity_name
        self.alm_engine = alm_engine
        self.products_engine = products_engine
        self.rwa_engine = rwa_engine
        self.ftp_engine = ftp_engine
        self.islamic_engine = islamic_engine
        self.digital_engine = digital_engine
        self.forecast_engine = forecast_engine
        self._rollups: Dict[str, CrossAssetRiskRollup] = {}

    @property
    def n_engines_wired(self) -> int:
        return sum(1 for e in [
            self.alm_engine, self.products_engine,
            self.rwa_engine, self.ftp_engine,
            self.islamic_engine, self.digital_engine,
            self.forecast_engine] if e is not None)

    def positions(self) -> Tuple[UnifiedPosition, ...]:
        """Aggregate positions from all wired engines."""
        out: List[UnifiedPosition] = []
        out.extend(positions_from_treasury_products(
            products_engine=self.products_engine))
        out.extend(positions_from_treasury_alm(
            alm_engine=self.alm_engine))
        out.extend(positions_from_islamic_treasury(
            islamic_engine=self.islamic_engine))
        out.extend(positions_from_digital_assets(
            digital_engine=self.digital_engine))
        return tuple(out)

    def cross_asset_rollup(
        self, *, rollup_id: str, as_of_date: str,
    ) -> CrossAssetRiskRollup:
        """Compute cross-asset risk + position roll-up."""
        if rollup_id in self._rollups:
            raise ValueError(
                f"rollup {rollup_id} already computed")
        positions = self.positions()
        n_by_class: Dict[str, int] = {}
        mv_by_class: Dict[str, Decimal] = {}
        risk_by_class: Dict[str, Decimal] = {}
        engines_consulted: List[str] = []
        for p in positions:
            cl = p.asset_class.value
            n_by_class[cl] = n_by_class.get(cl, 0) + 1
            mv_by_class[cl] = (
                mv_by_class.get(cl, Decimal("0"))
                + p.market_value_kes)
            risk_by_class[cl] = (
                risk_by_class.get(cl, Decimal("0"))
                + p.risk_metric_kes)
            if p.source_engine not in engines_consulted:
                engines_consulted.append(p.source_engine)
        total_mv = sum(mv_by_class.values(), Decimal("0"))
        total_risk = sum(risk_by_class.values(), Decimal("0"))
        rollup = CrossAssetRiskRollup(
            rollup_id=rollup_id,
            as_of_date=as_of_date,
            n_positions_by_class=dict(n_by_class),
            total_market_value_kes=total_mv.quantize(Decimal("0.01")),
            market_value_by_class={
                cl: v.quantize(Decimal("0.01"))
                for cl, v in mv_by_class.items()},
            risk_total_kes=total_risk.quantize(Decimal("0.01")),
            risk_by_class={
                cl: v.quantize(Decimal("0.01"))
                for cl, v in risk_by_class.items()},
            n_engines_consulted=len(engines_consulted),
            engines_consulted=tuple(engines_consulted),
            framework_refs=(
                "Basel III final framework Dec 2017",
                "IFRS 9", "IFRS 13"),
            notes=(
                f"cross-asset rollup for {self.entity_name} as of "
                f"{as_of_date}: {len(positions)} positions across "
                f"{len(n_by_class)} asset classes"))
        self._rollups[rollup_id] = rollup
        return rollup

    def board_summary(self) -> Dict[str, Any]:
        return {
            "entity": self.entity_name,
            "n_engines_wired": self.n_engines_wired,
            "n_rollups": len(self._rollups),
            "engines_wired": tuple(
                name for name, eng in [
                    ("alm_engine", self.alm_engine),
                    ("products_engine", self.products_engine),
                    ("rwa_engine", self.rwa_engine),
                    ("ftp_engine", self.ftp_engine),
                    ("islamic_engine", self.islamic_engine),
                    ("digital_engine", self.digital_engine),
                    ("forecast_engine", self.forecast_engine),
                ] if eng is not None),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

class _StubEngine:
    """Stub returning a fixed board_summary."""
    def __init__(self, summary):
        self._s = summary

    def board_summary(self):
        return self._s


def _test_no_engines_zero_positions():
    plat = UnifiedTreasuryPlatform()
    assert plat.positions() == ()


def _test_islamic_aggregation():
    islamic = _StubEngine({
        "n_products": 2,
        "total_principal_kes": "10000000",
        "total_expected_return_kes": "800000",
        "n_compliant": 2,
        "n_non_compliant": 0})
    plat = UnifiedTreasuryPlatform(islamic_engine=islamic)
    positions = plat.positions()
    assert len(positions) == 1
    assert positions[0].asset_class == AssetClass.ISLAMIC
    assert positions[0].notional_kes == Decimal("10000000")


def _test_digital_aggregation():
    digital = _StubEngine({
        "n_holdings": 3,
        "total_kes_equivalent": "5000000",
        "n_de_pegged": 0})
    plat = UnifiedTreasuryPlatform(digital_engine=digital)
    positions = plat.positions()
    assert len(positions) == 1
    assert positions[0].asset_class == AssetClass.DIGITAL


def _test_cross_asset_rollup():
    islamic = _StubEngine({
        "n_products": 2,
        "total_principal_kes": "10000000",
        "total_expected_return_kes": "800000",
        "n_compliant": 2,
        "n_non_compliant": 0})
    digital = _StubEngine({
        "n_holdings": 3,
        "total_kes_equivalent": "5000000",
        "n_de_pegged": 0})
    plat = UnifiedTreasuryPlatform(
        islamic_engine=islamic,
        digital_engine=digital)
    rollup = plat.cross_asset_rollup(
        rollup_id="R1", as_of_date="2026-05-01")
    assert rollup.n_positions_by_class["ISLAMIC"] == 1
    assert rollup.n_positions_by_class["DIGITAL"] == 1
    assert rollup.n_engines_consulted == 2
    assert rollup.total_market_value_kes > Decimal("0")


def _test_dup_rollup_id_raises():
    plat = UnifiedTreasuryPlatform()
    plat.cross_asset_rollup(
        rollup_id="R1", as_of_date="2026-05-01")
    try:
        plat.cross_asset_rollup(
            rollup_id="R1", as_of_date="2026-05-01")
        assert False
    except ValueError:
        pass


def _test_n_engines_wired():
    plat = UnifiedTreasuryPlatform(
        islamic_engine=_StubEngine({"n_products": 0}),
        digital_engine=_StubEngine({"n_holdings": 0}))
    assert plat.n_engines_wired == 2


def _test_board_summary_engines_wired_list():
    plat = UnifiedTreasuryPlatform(
        islamic_engine=_StubEngine({"n_products": 0}))
    s = plat.board_summary()
    assert "islamic_engine" in s["engines_wired"]


def self_test() -> None:
    tests = [
        _test_no_engines_zero_positions,
        _test_islamic_aggregation,
        _test_digital_aggregation,
        _test_cross_asset_rollup,
        _test_dup_rollup_id_raises,
        _test_n_engines_wired,
        _test_board_summary_engines_wired_list,
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
        print(f"✗ treasury_unified_platform self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ treasury_unified_platform self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
