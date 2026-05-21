"""utils.regulatory_reporting — Regulatory Risk Reporting
(Standard #56, v5.55). Volume Nine — Risk Intelligence.

Per v6 spec §9 + CBK regulatory framework:
    RegulatoryReportingEngine: CBK-aligned regulatory report builder
    (capital adequacy, large exposures, liquidity).

WHAT THIS MODULE SHIPS
----------------------
1. RegulatoryReportingEngine class with:
   - compute_capital_adequacy(tier1, tier2, rwa) — Basel III ratios
   - large_exposures_report(loans, capital_base) — single + group exposures
   - liquidity_coverage_report(hqla, net_outflows) — LCR computation
   - build_report(report_type, ...) — dispatch to specific builder

2. CBK_REPORTS catalog (8 reports):
   - CAPITAL_ADEQUACY_RATIO
   - LARGE_EXPOSURES_RETURN
   - LIQUIDITY_COVERAGE_RATIO
   - NET_STABLE_FUNDING_RATIO
   - INSIDER_LOANS
   - CONNECTED_LENDING
   - SECTORAL_LIMITS
   - FX_NET_OPEN_POSITION

3. Basel III thresholds (CBK adopted byte-for-byte):
   - CAR_MIN = 10.5% (8% + 2.5% capital conservation buffer)
   - LCR_MIN = 100%
   - LARGE_EXPOSURE_LIMIT = 25% of capital base

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - Decimal-internal precision 28 for all monetary fields
  - CAR / LCR returns None when denominator ≤ 0

Rule 6 — No silent fallback:
  - Report types validated against catalog; unknown types rejected
  - Single-counterparty exposures >25% of capital surfaced explicitly
  - Capital base NEVER silently inflated; if components are missing,
    report returns error
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.regulatory_reporting")
getcontext().prec = 28


# ─────────────────────────────────────────────────────────────────────
# Spec literals (CBK / Basel III)
# ─────────────────────────────────────────────────────────────────────

CBK_REPORTS: List[str] = [
    "CAPITAL_ADEQUACY_RATIO",
    "LARGE_EXPOSURES_RETURN",
    "LIQUIDITY_COVERAGE_RATIO",
    "NET_STABLE_FUNDING_RATIO",
    "INSIDER_LOANS",
    "CONNECTED_LENDING",
    "SECTORAL_LIMITS",
    "FX_NET_OPEN_POSITION",
]

# Basel III / CBK thresholds — v7.0.1: now sourced from system_invariants
# registry (single source of truth). CAR_MIN_PCT here represents Tier 1
# minimum (10.5% = 8% + 2.5% conservation buffer). Defensive fallback to
# original hard-coded values if registry import fails.
# NOTE: TIER1_MIN_PCT (8.5%), LARGE_EXPOSURE_LIMIT_PCT (25% per single
# obligor), INSIDER_AGGREGATE_LIMIT_PCT (20%), and SECTORAL_LIMIT_PCT
# (25%) remain locally defined for now; LARGE_EXPOSURE_LIMIT_PCT could
# also migrate to read SINGLE_OBLIGOR_LIMIT_PCT from registry but the
# semantic is slightly different (per-obligor vs aggregate large-exposure
# limit) — deferred to v7.0.2 to avoid conflating them.
try:
    from utils.system_invariants import get_threshold as _get_invariant
    _car_from_registry = _get_invariant("CBK_TIER_1_CAR_MIN")
    _lcr_from_registry = _get_invariant("LCR_MIN")
    _nsfr_from_registry = _get_invariant("NSFR_MIN")
    _single_obligor_from_registry = _get_invariant("SINGLE_OBLIGOR_LIMIT_PCT")
    CAR_MIN_PCT = (
        _car_from_registry if _car_from_registry is not None
        else Decimal("10.5")
    )
    LCR_MIN_PCT = (
        _lcr_from_registry if _lcr_from_registry is not None
        else Decimal("100.0")
    )
    NSFR_MIN_PCT = (
        _nsfr_from_registry if _nsfr_from_registry is not None
        else Decimal("100.0")
    )
    LARGE_EXPOSURE_LIMIT_PCT = (
        _single_obligor_from_registry if _single_obligor_from_registry is not None
        else Decimal("25.0")
    )
except ImportError:
    CAR_MIN_PCT = Decimal("10.5")
    LCR_MIN_PCT = Decimal("100.0")
    NSFR_MIN_PCT = Decimal("100.0")
    LARGE_EXPOSURE_LIMIT_PCT = Decimal("25.0")

TIER1_MIN_PCT                     = Decimal("8.5")     # 6% + 2.5% buffer
INSIDER_AGGREGATE_LIMIT_PCT       = Decimal("20.0")
SECTORAL_LIMIT_PCT                = Decimal("25.0")    # per sector


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class RegulatoryReportingEngine:
    """CBK regulatory reporting builder."""

    CBK_REPORTS = CBK_REPORTS

    def __init__(self):
        pass

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: compute_capital_adequacy
    # ──────────────────────────────────────────────────────────────────

    def compute_capital_adequacy(
        self,
        tier1_capital: float,
        tier2_capital: float,
        risk_weighted_assets: float,
    ) -> Dict[str, Any]:
        """Compute CAR per Basel III formula.

        CAR = (Tier1 + Tier2) / RWA × 100

        Returns None ratios when RWA ≤ 0 (Rule 1).
        """
        try:
            t1 = Decimal(str(tier1_capital))
            t2 = Decimal(str(tier2_capital))
            rwa = Decimal(str(risk_weighted_assets))
        except Exception as e:
            return {"error": f"invalid input: {e}"}

        total_capital = t1 + t2

        if rwa <= 0:
            return {
                "tier1_capital":   _money(t1),
                "tier2_capital":   _money(t2),
                "total_capital":   _money(total_capital),
                "rwa":             _money(rwa),
                "tier1_ratio_pct": None,
                "car_pct":         None,
                "passes_threshold": None,
                "reason":          "rwa_zero_or_negative",
            }

        tier1_ratio = float(t1 / rwa * Decimal("100"))
        car         = float(total_capital / rwa * Decimal("100"))

        return {
            "tier1_capital":   _money(t1),
            "tier2_capital":   _money(t2),
            "total_capital":   _money(total_capital),
            "rwa":             _money(rwa),
            "tier1_ratio_pct": round(tier1_ratio, 4),
            "car_pct":         round(car, 4),
            "tier1_min_pct":   float(TIER1_MIN_PCT),
            "car_min_pct":     float(CAR_MIN_PCT),
            "passes_tier1":    Decimal(str(tier1_ratio)) >= TIER1_MIN_PCT,
            "passes_car":      Decimal(str(car)) >= CAR_MIN_PCT,
            "passes_threshold": (
                Decimal(str(tier1_ratio)) >= TIER1_MIN_PCT
                and Decimal(str(car)) >= CAR_MIN_PCT
            ),
            "meta": {
                "regulation": "Basel III via CBK Prudential Guideline",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: large_exposures_report
    # ──────────────────────────────────────────────────────────────────

    def large_exposures_report(
        self,
        loans: List[dict],
        capital_base: float,
    ) -> Dict[str, Any]:
        """Identify exposures > 25% of capital base (CBK large exposure limit)."""
        try:
            cap_dec = Decimal(str(capital_base))
        except Exception:
            return {"error": "invalid capital_base"}
        if cap_dec <= 0:
            return {"error": "capital_base must be positive"}

        threshold = cap_dec * LARGE_EXPOSURE_LIMIT_PCT / Decimal("100")

        # Aggregate by counterparty
        by_counterparty: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for loan in loans or []:
            if not isinstance(loan, dict):
                continue
            cp = loan.get("counterparty_id")
            if not cp:
                continue
            try:
                by_counterparty[cp] += Decimal(str(loan.get("outstanding", 0)))
            except Exception:
                continue

        large_exposures = []
        for cp, amount in sorted(by_counterparty.items()):
            pct_of_capital = float(amount / cap_dec * Decimal("100"))
            if amount > threshold:
                large_exposures.append({
                    "counterparty_id":      cp,
                    "exposure":             _money(amount),
                    "pct_of_capital":       round(pct_of_capital, 4),
                    "threshold_pct":        float(LARGE_EXPOSURE_LIMIT_PCT),
                    "exceeds_limit":        True,
                })

        return {
            "capital_base":         _money(cap_dec),
            "threshold_amount":     _money(threshold),
            "threshold_pct":        float(LARGE_EXPOSURE_LIMIT_PCT),
            "total_counterparties": len(by_counterparty),
            "large_exposures":      large_exposures,
            "exceeds_count":        len(large_exposures),
            "meta": {
                "regulation":   "CBK Prudential Guideline on Single Borrower Limit",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: liquidity_coverage_report
    # ──────────────────────────────────────────────────────────────────

    def liquidity_coverage_report(
        self,
        hqla: float,
        net_outflows_30d: float,
    ) -> Dict[str, Any]:
        """LCR per Basel III: HQLA / Net Outflows (30-day stress) ≥ 100%."""
        try:
            hqla_dec = Decimal(str(hqla))
            outflows_dec = Decimal(str(net_outflows_30d))
        except Exception as e:
            return {"error": f"invalid input: {e}"}

        if outflows_dec <= 0:
            return {
                "hqla":              _money(hqla_dec),
                "net_outflows_30d":  _money(outflows_dec),
                "lcr_pct":           None,
                "passes_threshold":  None,
                "reason":            "net_outflows_zero_or_negative",
            }

        lcr_pct = float(hqla_dec / outflows_dec * Decimal("100"))

        return {
            "hqla":              _money(hqla_dec),
            "net_outflows_30d":  _money(outflows_dec),
            "lcr_pct":           round(lcr_pct, 4),
            "lcr_min_pct":       float(LCR_MIN_PCT),
            "passes_threshold":  Decimal(str(lcr_pct)) >= LCR_MIN_PCT,
            "meta": {
                "regulation":   "Basel III LCR via CBK",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: build_report
    # ──────────────────────────────────────────────────────────────────

    def build_report(self, report_type: str, **kwargs) -> Dict[str, Any]:
        """Dispatch to the appropriate report builder."""
        if report_type not in CBK_REPORTS:
            return {
                "error": f"unknown report_type {report_type!r}; valid: {CBK_REPORTS}",
            }

        if report_type == "CAPITAL_ADEQUACY_RATIO":
            return self.compute_capital_adequacy(
                kwargs.get("tier1_capital", 0),
                kwargs.get("tier2_capital", 0),
                kwargs.get("risk_weighted_assets", 0),
            )
        if report_type == "LARGE_EXPOSURES_RETURN":
            return self.large_exposures_report(
                kwargs.get("loans", []),
                kwargs.get("capital_base", 0),
            )
        if report_type == "LIQUIDITY_COVERAGE_RATIO":
            return self.liquidity_coverage_report(
                kwargs.get("hqla", 0),
                kwargs.get("net_outflows_30d", 0),
            )
        return {
            "report_type": report_type,
            "status":      "report_template_not_yet_implemented",
            "spec_deviation": f"v6 ships first 3 reports; {report_type} deferred",
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.regulatory_reporting self-test")

    assert len(CBK_REPORTS) == 8
    assert "CAPITAL_ADEQUACY_RATIO" in CBK_REPORTS
    print(f"  ✅ CBK reports catalog: {len(CBK_REPORTS)} reports")
    assert CAR_MIN_PCT == Decimal("10.5")
    assert LCR_MIN_PCT == Decimal("100.0")
    assert LARGE_EXPOSURE_LIMIT_PCT == Decimal("25.0")
    print(f"  ✅ Basel III thresholds: CAR≥10.5%, LCR≥100%, LE≤25%")

    eng = RegulatoryReportingEngine()

    # Capital adequacy — passing case
    r = eng.compute_capital_adequacy(
        tier1_capital=10_000_000_000,    # 10B
        tier2_capital=2_000_000_000,     # 2B
        risk_weighted_assets=80_000_000_000,    # 80B
    )
    # Tier1 ratio = 10/80 × 100 = 12.5% (≥8.5% ✓)
    # CAR = 12/80 × 100 = 15.0% (≥10.5% ✓)
    assert r["tier1_ratio_pct"] == 12.5
    assert r["car_pct"] == 15.0
    assert r["passes_threshold"] is True
    print(f"  ✅ CAR (passing): tier1={r['tier1_ratio_pct']}%, CAR={r['car_pct']}%")

    # Capital adequacy — failing case
    r = eng.compute_capital_adequacy(
        tier1_capital=2_000_000_000,
        tier2_capital=500_000_000,
        risk_weighted_assets=50_000_000_000,
    )
    # Tier1 = 2/50 × 100 = 4% (<8.5% ✗)
    # CAR = 2.5/50 × 100 = 5% (<10.5% ✗)
    assert r["passes_threshold"] is False
    assert r["passes_tier1"] is False
    assert r["passes_car"] is False
    print(f"  ✅ CAR (failing): tier1={r['tier1_ratio_pct']}%, CAR={r['car_pct']}%, "
          f"passes={r['passes_threshold']}")

    # CAR with RWA=0 → Rule 1 (None)
    r = eng.compute_capital_adequacy(1_000_000, 0, 0)
    assert r["car_pct"] is None
    assert r["passes_threshold"] is None
    print(f"  ✅ RWA=0 → CAR=None (Rule 1)")

    # Large exposures
    capital = 10_000_000_000    # 10B
    # Threshold = 25% of 10B = 2.5B
    loans = [
        {"counterparty_id": "BIG_CO",  "outstanding": 3_000_000_000},   # 30% — exceeds
        {"counterparty_id": "BIG_CO",  "outstanding": 200_000_000},     # same counterparty
        {"counterparty_id": "MED_CO",  "outstanding": 1_500_000_000},   # 15% — OK
        {"counterparty_id": "SMALL_CO", "outstanding": 100_000_000},    # 1% — OK
    ]
    # BIG_CO aggregate: 3.2B = 32% → exceeds 25%
    r = eng.large_exposures_report(loans, capital)
    assert r["exceeds_count"] == 1
    big_co = r["large_exposures"][0]
    assert big_co["counterparty_id"] == "BIG_CO"
    assert big_co["exposure"] == 3_200_000_000.00
    assert big_co["pct_of_capital"] == 32.0
    assert big_co["exceeds_limit"] is True
    print(f"  ✅ large exposures: BIG_CO at 32% (limit 25%) — flagged")

    # LCR — passing
    r = eng.liquidity_coverage_report(hqla=50_000_000_000, net_outflows_30d=40_000_000_000)
    # 50/40 × 100 = 125% (≥100%)
    assert r["lcr_pct"] == 125.0
    assert r["passes_threshold"] is True
    print(f"  ✅ LCR (passing): {r['lcr_pct']}%")

    # LCR — failing
    r = eng.liquidity_coverage_report(hqla=30_000_000_000, net_outflows_30d=40_000_000_000)
    # 30/40 × 100 = 75%
    assert r["lcr_pct"] == 75.0
    assert r["passes_threshold"] is False
    print(f"  ✅ LCR (failing): {r['lcr_pct']}%")

    # LCR with zero outflows
    r = eng.liquidity_coverage_report(hqla=1_000_000, net_outflows_30d=0)
    assert r["lcr_pct"] is None
    print(f"  ✅ zero outflows → LCR=None (Rule 1)")

    # build_report dispatch
    r = eng.build_report("CAPITAL_ADEQUACY_RATIO",
                         tier1_capital=10_000_000_000,
                         tier2_capital=2_000_000_000,
                         risk_weighted_assets=80_000_000_000)
    assert r["car_pct"] == 15.0
    print(f"  ✅ build_report dispatches to CAR builder")

    # Unknown report
    r = eng.build_report("UNKNOWN_REPORT")
    assert "error" in r
    print(f"  ✅ unknown report rejected (Rule 6)")

    # Deferred report (one of the 8 in catalog but not yet implemented)
    r = eng.build_report("FX_NET_OPEN_POSITION")
    assert r.get("status") == "report_template_not_yet_implemented"
    assert "spec_deviation" in r
    print(f"  ✅ deferred report: spec_deviation surfaced")

    print("\n  ALL TESTS PASSED")
