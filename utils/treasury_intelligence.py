"""utils.treasury_intelligence — Treasury Intelligence
(Standard #46, v5.52). Volume Seven — Finance Intelligence.

Per v6 spec §7:
    TreasuryIntelligenceEngine: income by instrument + LCR/NSFR + ALM + yield curve

WHAT THIS MODULE SHIPS
----------------------
1. TreasuryIntelligenceEngine class with:
   - income_by_instrument(period) — treasury income decomposition
   - liquidity_metrics(as_of_date) — LCR + NSFR per Basel III
   - alm_dashboard_data(as_of_date) — Asset-Liability Management metrics
   - yield_curve(as_of_date, currency) — points for chart rendering

2. INSTRUMENTS catalog: 6 instruments per spec
3. Decimal-internal precision 28
4. Basel III formulas with documented thresholds

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - LCR returns None (NOT 0 or False) when net_outflows ≤ 0
  - NSFR returns None when required_stable_funding ≤ 0
  - Decimal-internal precision 28

Rule 6 — No silent fallback:
  - Basel III thresholds documented in code (LCR ≥ 100%, NSFR ≥ 100%)
  - Compliance status surfaced explicitly with passes_threshold flag
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.treasury_intelligence")
getcontext().prec = 28

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §7 #46)
# ─────────────────────────────────────────────────────────────────────

INSTRUMENTS: List[str] = [
    "T_BILL", "T_BOND", "FX_SPOT", "FX_FORWARD", "REPO", "INTERBANK",
]

# Basel III regulatory minimums
# v7.0.1: Sourced from system_invariants registry (single source of truth).
# Defensive fallback per Rule 6.
try:
    from utils.system_invariants import get_threshold as _get_invariant
    _lcr_from_registry = _get_invariant("LCR_MIN")
    _nsfr_from_registry = _get_invariant("NSFR_MIN")
    LCR_MIN_THRESHOLD_PCT = (
        _lcr_from_registry if _lcr_from_registry is not None
        else Decimal("100")
    )
    NSFR_MIN_THRESHOLD_PCT = (
        _nsfr_from_registry if _nsfr_from_registry is not None
        else Decimal("100")
    )
except ImportError:
    LCR_MIN_THRESHOLD_PCT = Decimal("100")
    NSFR_MIN_THRESHOLD_PCT = Decimal("100")


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class TreasuryIntelligenceEngine:
    """Treasury income + liquidity + ALM analytics."""

    INSTRUMENTS = INSTRUMENTS

    def __init__(
        self,
        instrument_income_fn:   Optional[Callable[[str], List[dict]]] = None,
        lcr_inputs_fn:          Optional[Callable[[str], Dict[str, Any]]] = None,
        nsfr_inputs_fn:         Optional[Callable[[str], Dict[str, Any]]] = None,
        alm_position_fn:        Optional[Callable[[str], Dict[str, Any]]] = None,
        yield_curve_fn:         Optional[Callable[[str, str], List[dict]]] = None,
    ):
        """All collaborators injectable.

        instrument_income_fn(period) → list[dict] with: income, instrument
        lcr_inputs_fn(date) → {"hqla": Decimal, "net_outflows_30d": Decimal}
        nsfr_inputs_fn(date) → {"available_stable_funding": Decimal,
                                 "required_stable_funding": Decimal}
        alm_position_fn(date) → {"assets_by_bucket": dict, "liabilities_by_bucket": dict}
        yield_curve_fn(date, currency) → list[{"tenor_days": int, "yield_pct": float}]
        """
        self._inst_income = instrument_income_fn or (lambda p: [])
        self._lcr_inputs  = lcr_inputs_fn        or (lambda d: {})
        self._nsfr_inputs = nsfr_inputs_fn       or (lambda d: {})
        self._alm         = alm_position_fn      or (lambda d: {})
        self._yield_curve = yield_curve_fn       or (lambda d, c: [])

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: income_by_instrument
    # ──────────────────────────────────────────────────────────────────

    def income_by_instrument(self, period: str) -> Dict[str, Any]:
        """Treasury income decomposition by instrument.

        Returns:
            {
              "period": str,
              "instruments": {instrument: {"income": float, "share_pct": float | None}},
              "total_income": float,
              "meta": {...}
            }
        """
        if not period:
            return {}

        rows = self._inst_income(period) or []
        income_by_inst: Dict[str, Decimal] = {i: ZERO for i in INSTRUMENTS}
        unknown_instruments: List[str] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            inst = row.get("instrument")
            try:
                amt = Decimal(str(row.get("income", 0)))
            except Exception:
                continue
            if inst in INSTRUMENTS:
                income_by_inst[inst] += amt
            elif inst:
                unknown_instruments.append(inst)

        total = sum(income_by_inst.values())
        results: Dict[str, Dict[str, Any]] = {}
        for inst in INSTRUMENTS:
            inc = income_by_inst[inst]
            share_pct = float(inc / total * Decimal("100")) if total > 0 else None
            results[inst] = {
                "income":    _money(inc),
                "share_pct": round(share_pct, 2) if share_pct is not None else None,
            }

        return {
            "period":       period,
            "instruments":  results,
            "total_income": _money(total),
            "meta": {
                "rows_processed":     len(rows),
                "unknown_instruments": sorted(set(unknown_instruments)),
                "instruments_in_spec": list(INSTRUMENTS),
                "generated_at":        datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: liquidity_metrics (LCR + NSFR)
    # ──────────────────────────────────────────────────────────────────

    def liquidity_metrics(self, as_of_date: str) -> Dict[str, Any]:
        """Compute LCR and NSFR per Basel III.

        LCR = HQLA / Net Cash Outflows over next 30 days × 100
              Threshold: ≥ 100%

        NSFR = Available Stable Funding / Required Stable Funding × 100
               Threshold: ≥ 100%

        HONESTY: returns ratio=None when denominator is zero (Rule 1 —
        undefined math, NOT 0 or False).

        Returns:
            {
              "as_of_date": str,
              "lcr": {hqla, net_outflows, lcr_pct, passes_threshold},
              "nsfr": {available, required, nsfr_pct, passes_threshold},
              "meta": {...}
            }
        """
        if not as_of_date:
            return {}

        # ── LCR ─────────────────────────────────────────────────────
        lcr_in = self._lcr_inputs(as_of_date) or {}
        try:
            hqla    = Decimal(str(lcr_in.get("hqla", 0)))
            outflows = Decimal(str(lcr_in.get("net_outflows_30d", 0)))
        except Exception:
            hqla = ZERO
            outflows = ZERO

        if outflows <= 0:
            lcr_pct = None
            lcr_passes = None    # Rule 1 — undefined
        else:
            lcr_pct = float(hqla / outflows * Decimal("100"))
            lcr_passes = Decimal(str(lcr_pct)) >= LCR_MIN_THRESHOLD_PCT

        # ── NSFR ────────────────────────────────────────────────────
        nsfr_in = self._nsfr_inputs(as_of_date) or {}
        try:
            asf = Decimal(str(nsfr_in.get("available_stable_funding", 0)))
            rsf = Decimal(str(nsfr_in.get("required_stable_funding", 0)))
        except Exception:
            asf = ZERO
            rsf = ZERO

        if rsf <= 0:
            nsfr_pct = None
            nsfr_passes = None
        else:
            nsfr_pct = float(asf / rsf * Decimal("100"))
            nsfr_passes = Decimal(str(nsfr_pct)) >= NSFR_MIN_THRESHOLD_PCT

        return {
            "as_of_date": as_of_date,
            "lcr": {
                "hqla":              _money(hqla),
                "net_outflows_30d":  _money(outflows),
                "lcr_pct":           round(lcr_pct, 2) if lcr_pct is not None else None,
                "passes_threshold":  lcr_passes,
                "threshold_pct":     float(LCR_MIN_THRESHOLD_PCT),
            },
            "nsfr": {
                "available_stable_funding": _money(asf),
                "required_stable_funding":  _money(rsf),
                "nsfr_pct":                 round(nsfr_pct, 2) if nsfr_pct is not None else None,
                "passes_threshold":         nsfr_passes,
                "threshold_pct":            float(NSFR_MIN_THRESHOLD_PCT),
            },
            "meta": {
                "basel_iii_lcr_min":  100,
                "basel_iii_nsfr_min": 100,
                "generated_at":       datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: alm_dashboard_data
    # ──────────────────────────────────────────────────────────────────

    def alm_dashboard_data(self, as_of_date: str) -> Dict[str, Any]:
        """Asset-Liability Management dashboard metrics.

        Computes maturity-bucketed gap analysis (assets - liabilities per bucket)
        and cumulative gap.

        Returns:
            {
              "as_of_date": str,
              "buckets": [
                  {bucket, assets, liabilities, gap, cumulative_gap}
              ],
              "meta": {...}
            }
        """
        if not as_of_date:
            return {}

        position = self._alm(as_of_date) or {}
        assets_by_bucket = position.get("assets_by_bucket", {})
        liab_by_bucket   = position.get("liabilities_by_bucket", {})

        # Standard maturity buckets
        BUCKETS = ["O/N", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y", "5Y+"]
        results: List[Dict[str, Any]] = []
        cumulative = ZERO
        for bucket in BUCKETS:
            try:
                a = Decimal(str(assets_by_bucket.get(bucket, 0)))
                l = Decimal(str(liab_by_bucket.get(bucket, 0)))
            except Exception:
                continue
            gap = a - l
            cumulative += gap
            results.append({
                "bucket":         bucket,
                "assets":         _money(a),
                "liabilities":    _money(l),
                "gap":            _money(gap),
                "cumulative_gap": _money(cumulative),
            })

        return {
            "as_of_date": as_of_date,
            "buckets":    results,
            "meta": {
                "buckets_in_spec": BUCKETS,
                "generated_at":    datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: yield_curve
    # ──────────────────────────────────────────────────────────────────

    def yield_curve(self, as_of_date: str, currency: str = "KES") -> Dict[str, Any]:
        """Yield curve points for given currency.

        Returns:
            {
              "as_of_date": str,
              "currency": str,
              "points": [{tenor_days, yield_pct}, ...]
                # sorted by tenor_days
            }
        """
        if not as_of_date:
            return {}
        points = self._yield_curve(as_of_date, currency) or []
        # Validate + sort
        valid_points: List[Dict[str, Any]] = []
        for p in points:
            if not isinstance(p, dict):
                continue
            try:
                tenor = int(p["tenor_days"])
                yld   = float(p["yield_pct"])
                valid_points.append({"tenor_days": tenor, "yield_pct": yld})
            except (KeyError, ValueError, TypeError):
                continue
        valid_points.sort(key=lambda x: x["tenor_days"])

        return {
            "as_of_date": as_of_date,
            "currency":   currency,
            "points":     valid_points,
            "meta": {
                "point_count":  len(valid_points),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
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
    print("A2Z MIS 360 — utils.treasury_intelligence self-test")

    # ── Spec literals ─────────────────────────────────────────────────
    assert len(INSTRUMENTS) == 6
    assert INSTRUMENTS == ["T_BILL", "T_BOND", "FX_SPOT", "FX_FORWARD", "REPO", "INTERBANK"]
    print(f"  ✅ spec literals: 6 instruments {INSTRUMENTS}")
    assert LCR_MIN_THRESHOLD_PCT == Decimal("100")
    assert NSFR_MIN_THRESHOLD_PCT == Decimal("100")
    print(f"  ✅ Basel III thresholds: LCR ≥ 100%, NSFR ≥ 100%")

    # ── Empty inputs → {} ─────────────────────────────────────────────
    eng = TreasuryIntelligenceEngine()
    assert eng.income_by_instrument("") == {}
    assert eng.liquidity_metrics("") == {}
    assert eng.alm_dashboard_data("") == {}
    assert eng.yield_curve("") == {}
    print(f"  ✅ empty inputs → {{}}")

    # ── Income by instrument ─────────────────────────────────────────
    income = [
        {"income": 500_000_000, "instrument": "T_BILL"},
        {"income": 300_000_000, "instrument": "T_BOND"},
        {"income":  50_000_000, "instrument": "FX_SPOT"},
        {"income": 150_000_000, "instrument": "INTERBANK"},
    ]
    eng2 = TreasuryIntelligenceEngine(instrument_income_fn=lambda p: income)
    r = eng2.income_by_instrument("2026-04")
    assert r["total_income"] == 1_000_000_000.00
    assert r["instruments"]["T_BILL"]["income"] == 500_000_000.00
    assert r["instruments"]["T_BILL"]["share_pct"] == 50.0
    print(f"  ✅ income aggregation: total={r['total_income']:,.2f}, "
          f"T_BILL share={r['instruments']['T_BILL']['share_pct']}%")

    # ── LCR computation passes threshold ─────────────────────────────
    eng3 = TreasuryIntelligenceEngine(
        lcr_inputs_fn=lambda d: {"hqla": "5000000000", "net_outflows_30d": "4000000000"},
        nsfr_inputs_fn=lambda d: {"available_stable_funding": "10000000000",
                                   "required_stable_funding": "8000000000"},
    )
    r = eng3.liquidity_metrics("2026-04-29")
    # LCR = 5B/4B = 125%
    assert r["lcr"]["lcr_pct"] == 125.00
    assert r["lcr"]["passes_threshold"] is True
    # NSFR = 10B/8B = 125%
    assert r["nsfr"]["nsfr_pct"] == 125.00
    assert r["nsfr"]["passes_threshold"] is True
    print(f"  ✅ LCR/NSFR pass: LCR={r['lcr']['lcr_pct']}%, NSFR={r['nsfr']['nsfr_pct']}%")

    # ── LCR fails threshold ──────────────────────────────────────────
    eng4 = TreasuryIntelligenceEngine(
        lcr_inputs_fn=lambda d: {"hqla": "3000000000", "net_outflows_30d": "4000000000"},
    )
    r = eng4.liquidity_metrics("2026-04-29")
    # LCR = 3B/4B = 75%
    assert r["lcr"]["lcr_pct"] == 75.00
    assert r["lcr"]["passes_threshold"] is False
    print(f"  ✅ LCR fails: {r['lcr']['lcr_pct']}% < 100% threshold")

    # ── LCR ratio = None when net_outflows = 0 (Rule 1) ──────────────
    eng5 = TreasuryIntelligenceEngine(
        lcr_inputs_fn=lambda d: {"hqla": "5000000000", "net_outflows_30d": "0"},
    )
    r = eng5.liquidity_metrics("2026-04-29")
    assert r["lcr"]["lcr_pct"] is None
    assert r["lcr"]["passes_threshold"] is None
    print(f"  ✅ LCR=None when outflows=0 (Rule 1 — undefined ratio)")

    # ── NSFR ratio = None when required = 0 ──────────────────────────
    eng6 = TreasuryIntelligenceEngine(
        nsfr_inputs_fn=lambda d: {"available_stable_funding": "10000000000",
                                   "required_stable_funding": "0"},
    )
    r = eng6.liquidity_metrics("2026-04-29")
    assert r["nsfr"]["nsfr_pct"] is None
    assert r["nsfr"]["passes_threshold"] is None
    print(f"  ✅ NSFR=None when required=0 (Rule 1 — undefined ratio)")

    # ── ALM gap analysis ─────────────────────────────────────────────
    alm_position = {
        "assets_by_bucket":      {"O/N": 1_000_000_000, "1M": 5_000_000_000, "1Y": 10_000_000_000},
        "liabilities_by_bucket": {"O/N": 2_000_000_000, "1M": 3_000_000_000, "1Y":  8_000_000_000},
    }
    eng7 = TreasuryIntelligenceEngine(alm_position_fn=lambda d: alm_position)
    r = eng7.alm_dashboard_data("2026-04-29")
    on_bucket = next(b for b in r["buckets"] if b["bucket"] == "O/N")
    # O/N: 1B - 2B = -1B
    assert on_bucket["gap"] == -1_000_000_000.00
    one_y = next(b for b in r["buckets"] if b["bucket"] == "1Y")
    # Cumulative through 1Y: -1B + 2B + 2B = 3B
    assert one_y["cumulative_gap"] == 3_000_000_000.00
    print(f"  ✅ ALM gap: O/N={on_bucket['gap']:,.2f}, "
          f"1Y cumulative={one_y['cumulative_gap']:,.2f}")

    # ── Yield curve sorted ────────────────────────────────────────────
    points_in = [
        {"tenor_days": 365, "yield_pct": 12.5},
        {"tenor_days":  91, "yield_pct": 11.2},
        {"tenor_days":  30, "yield_pct": 10.8},
    ]
    eng8 = TreasuryIntelligenceEngine(yield_curve_fn=lambda d, c: points_in)
    r = eng8.yield_curve("2026-04-29", "KES")
    assert len(r["points"]) == 3
    assert r["points"][0]["tenor_days"] == 30
    assert r["points"][2]["tenor_days"] == 365
    print(f"  ✅ yield curve: {len(r['points'])} points sorted by tenor")

    # ── Unknown instrument exposed ────────────────────────────────────
    income_unk = income + [{"income": 1_000_000, "instrument": "DERIVATIVE"}]
    eng9 = TreasuryIntelligenceEngine(instrument_income_fn=lambda p: income_unk)
    r = eng9.income_by_instrument("2026-04")
    assert "DERIVATIVE" in r["meta"]["unknown_instruments"]
    print(f"  ✅ unknown instrument exposed: {r['meta']['unknown_instruments']}")

    # ── KES-billion precision ────────────────────────────────────────
    huge = [
        {"income": "11500000000.50", "instrument": "T_BILL"},
        {"income": "11500000000.51", "instrument": "T_BILL"},
    ]
    eng10 = TreasuryIntelligenceEngine(instrument_income_fn=lambda p: huge)
    r = eng10.income_by_instrument("2026-04")
    assert r["total_income"] == 23_000_000_001.01
    print(f"  ✅ KES-billion precision: total={r['total_income']:,.2f}")

    print("\n  ALL TESTS PASSED")
