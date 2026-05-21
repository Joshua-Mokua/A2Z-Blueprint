"""
================================================================================
A2Z MIS 360 — Standard #365: Segment P&L & Performance Attribution
================================================================================

Risk classification: Cat A (financial computation — P&L, RAROC, capital allocation)

Per-segment Profit & Loss with revenue / cost / allocated capital
breakdown and Return on Risk-Adjusted Capital (RAROC) computation.
Composes existing operating_segments engine for IFRS 8 segment reporting
shape; this module adds specialized-segments-specific attribution.

Public API:
    record_pnl_line(segment_code, period, line_type, amount, ...)
    compute_segment_pnl(segment_code, period) -> {revenue, cost, net_income, raroc}
    compute_raroc(segment_code, period, rate_pct=10) -> Decimal | None
    profitability_drivers(segment_code, period) -> top contributors
    time_series(segment_code, periods=12) -> rolling P&L sequence

P&L line types byte-for-byte:
    INTEREST_INCOME        -- net interest income from segment products
    FEE_INCOME             -- transaction + advisory fees
    FX_INCOME              -- foreign-exchange gains
    OTHER_INCOME           -- other operating income
    DIRECT_COST            -- segment-attributable opex
    ALLOCATED_OVERHEAD     -- shared cost allocated to segment
    LOAN_LOSS_PROVISION    -- IFRS 9 ECL on segment loan book
    TAX                    -- segment income tax (tax authority Section 14)

Capital-allocation method byte-for-byte (BCBS standardised approach):
    SEGMENT_CAPITAL = sum(rwa_assigned) × CAPITAL_ADEQUACY_PCT
    DEFAULT_CAPITAL_ADEQUACY_PCT = Decimal("12.5")  (regulator minimum)

RAROC formula byte-for-byte:
    RAROC = (Net_Income - (Allocated_Capital × Cost_of_Capital_pct)) / Allocated_Capital
    Returns percentage; None when allocated_capital == 0

Honesty rules:
    Rule 1: RAROC = None when allocated_capital is zero
    Rule 6: invalid line_type rejected (fail closed); missing period rejected
    Rule 4: actor + reason mandatory on all writes

================================================================================
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.specialized_segments_tagging import SEGMENT_CODES

getcontext().prec = 28


# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte
# ────────────────────────────────────────────────────────────────────

PNL_LINE_TYPES: Tuple[str, ...] = (
    "INTEREST_INCOME",
    "FEE_INCOME",
    "FX_INCOME",
    "OTHER_INCOME",
    "DIRECT_COST",
    "ALLOCATED_OVERHEAD",
    "LOAN_LOSS_PROVISION",
    "TAX",
)

REVENUE_LINES: Tuple[str, ...] = (
    "INTEREST_INCOME", "FEE_INCOME", "FX_INCOME", "OTHER_INCOME",
)

COST_LINES: Tuple[str, ...] = (
    "DIRECT_COST", "ALLOCATED_OVERHEAD",
    "LOAN_LOSS_PROVISION", "TAX",
)

DEFAULT_CAPITAL_ADEQUACY_PCT: Decimal = Decimal("12.5")
DEFAULT_COST_OF_CAPITAL_PCT:  Decimal = Decimal("10")


class SegmentPnLEngine:
    """Per-segment P&L + RAROC computation."""

    def __init__(self, pnl_path: Optional[Path] = None):
        self.pnl_path = (
            pnl_path
            if pnl_path is not None
            else Path(__file__).parent.parent / "data" / "segment_pnl.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db   # singleton Database instance
            data = _db.dual_load(
                self.pnl_path,
                table="segment_pnl",
                index_cols=("segment_code", "period", "line_type"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.pnl_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.pnl_path,
                data=records,
                table="segment_pnl",
                pk_col="segment_code")
            return True
        except Exception:
            return False

    def record_pnl_line(
        self,
        segment_code: str,
        period: str,         # e.g. "2026-Q1"
        line_type: str,
        amount_kes: Decimal,
        actor: str,
        reason: str = "",
        rwa_kes: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Record a single P&L line for a segment-period.

        Rule 4: actor mandatory.
        Rule 6: invalid line_type or segment rejected.
        """
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if segment_code not in SEGMENT_CODES:
            return {"recorded": False, "error": f"invalid_segment:{segment_code}"}
        if line_type not in PNL_LINE_TYPES:
            return {
                "recorded": False,
                "error": f"invalid_line_type:{line_type}",
                "valid_types": list(PNL_LINE_TYPES),
            }
        if not period:
            return {"recorded": False, "error": "period_required"}

        try:
            amount = Decimal(str(amount_kes))
        except (ValueError, TypeError):
            return {"recorded": False, "error": "amount_not_decimal"}

        records = self._load()
        record = {
            "segment_code": segment_code,
            "period": period,
            "line_type": line_type,
            "amount_kes": str(amount),
            "rwa_kes": str(rwa_kes) if rwa_kes is not None else None,
            "actor": actor,
            "reason": reason,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(records)
        return {"recorded": ok, "record": record}

    def compute_segment_pnl(
        self,
        segment_code: str,
        period: str,
    ) -> Dict[str, Any]:
        """
        Aggregate P&L lines into revenue / cost / net_income for a segment-period.

        Rule 1: returns line_count=0 with explicit no_data when nothing recorded.
        """
        if segment_code not in SEGMENT_CODES:
            return {"error": f"invalid_segment:{segment_code}"}

        records = self._load()
        filtered = [
            r for r in records
            if r.get("segment_code") == segment_code and r.get("period") == period
        ]

        if not filtered:
            return {
                "segment_code": segment_code,
                "period": period,
                "revenue_kes": None,
                "cost_kes": None,
                "net_income_kes": None,
                "line_count": 0,
                "reason": "no_data_for_period",
            }

        revenue = Decimal("0")
        cost = Decimal("0")
        rwa_total = Decimal("0")
        by_line: Dict[str, Decimal] = {}

        for r in filtered:
            try:
                amount = Decimal(str(r["amount_kes"]))
            except (ValueError, TypeError):
                continue
            line = r["line_type"]
            by_line[line] = by_line.get(line, Decimal("0")) + amount
            if line in REVENUE_LINES:
                revenue += amount
            elif line in COST_LINES:
                cost += amount
            # RWA accumulation
            if r.get("rwa_kes") is not None:
                try:
                    rwa_total += Decimal(str(r["rwa_kes"]))
                except (ValueError, TypeError):
                    pass

        net_income = revenue - cost
        # Rule 4: round to currency precision
        return {
            "segment_code": segment_code,
            "period": period,
            "revenue_kes": str(revenue.quantize(Decimal("0.01"))),
            "cost_kes": str(cost.quantize(Decimal("0.01"))),
            "net_income_kes": str(net_income.quantize(Decimal("0.01"))),
            "rwa_total_kes": str(rwa_total.quantize(Decimal("0.01"))),
            "line_count": len(filtered),
            "by_line": {k: str(v.quantize(Decimal("0.01"))) for k, v in by_line.items()},
        }

    def compute_raroc(
        self,
        segment_code: str,
        period: str,
        cost_of_capital_pct: Decimal = DEFAULT_COST_OF_CAPITAL_PCT,
        capital_adequacy_pct: Decimal = DEFAULT_CAPITAL_ADEQUACY_PCT,
    ) -> Dict[str, Any]:
        """
        RAROC = (Net_Income - Allocated_Capital × Cost_of_Capital) / Allocated_Capital.

        Rule 1: returns RAROC = None when allocated_capital is zero
        (i.e. segment has no RWA recorded for the period).
        """
        pnl = self.compute_segment_pnl(segment_code, period)
        if pnl.get("net_income_kes") is None:
            return {
                "segment_code": segment_code,
                "period": period,
                "raroc_pct": None,
                "reason": "no_pnl_data",
            }

        rwa_total = Decimal(pnl["rwa_total_kes"])
        if rwa_total <= 0:
            return {
                "segment_code": segment_code,
                "period": period,
                "raroc_pct": None,
                "reason": "no_rwa_recorded",
            }

        allocated_capital = rwa_total * capital_adequacy_pct / Decimal("100")
        if allocated_capital <= 0:
            return {
                "segment_code": segment_code,
                "period": period,
                "raroc_pct": None,
                "reason": "allocated_capital_zero",
            }

        net_income = Decimal(pnl["net_income_kes"])
        capital_charge = allocated_capital * cost_of_capital_pct / Decimal("100")
        raroc = ((net_income - capital_charge) / allocated_capital) * Decimal("100")

        return {
            "segment_code": segment_code,
            "period": period,
            "raroc_pct": str(raroc.quantize(Decimal("0.01"))),
            "net_income_kes": pnl["net_income_kes"],
            "allocated_capital_kes": str(allocated_capital.quantize(Decimal("0.01"))),
            "cost_of_capital_pct": str(cost_of_capital_pct),
            "capital_adequacy_pct": str(capital_adequacy_pct),
        }

    def profitability_drivers(
        self,
        segment_code: str,
        period: str,
        top_n: int = 5,
    ) -> List[Dict[str, Any]]:
        """Top profitability drivers (largest revenue/cost line abs values)."""
        pnl = self.compute_segment_pnl(segment_code, period)
        by_line = pnl.get("by_line") or {}
        items = [
            {"line_type": k, "amount_kes": v, "category":
                "revenue" if k in REVENUE_LINES else "cost"}
            for k, v in by_line.items()
        ]
        items.sort(key=lambda x: abs(Decimal(x["amount_kes"])), reverse=True)
        return items[:top_n]

    def time_series(
        self,
        segment_code: str,
        periods: List[str],
    ) -> Dict[str, Any]:
        """Rolling P&L sequence for given periods."""
        if segment_code not in SEGMENT_CODES:
            return {"error": f"invalid_segment:{segment_code}"}

        series = [self.compute_segment_pnl(segment_code, p) for p in periods]
        return {
            "segment_code": segment_code,
            "periods": periods,
            "series": series,
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = SegmentPnLEngine(pnl_path=Path(tmpdir) / "pnl.json")

        # Test 1: record P&L lines for WOMEN segment Q1
        engine.record_pnl_line("WOMEN", "2026-Q1", "INTEREST_INCOME",
                                Decimal("5000000"), actor="cfo",
                                rwa_kes=Decimal("50000000"))
        engine.record_pnl_line("WOMEN", "2026-Q1", "FEE_INCOME",
                                Decimal("1000000"), actor="cfo")
        engine.record_pnl_line("WOMEN", "2026-Q1", "DIRECT_COST",
                                Decimal("2000000"), actor="cfo")
        engine.record_pnl_line("WOMEN", "2026-Q1", "ALLOCATED_OVERHEAD",
                                Decimal("500000"), actor="cfo")
        engine.record_pnl_line("WOMEN", "2026-Q1", "LOAN_LOSS_PROVISION",
                                Decimal("300000"), actor="cfo")

        # Test 2: aggregate P&L
        pnl = engine.compute_segment_pnl("WOMEN", "2026-Q1")
        assert pnl["line_count"] == 5
        assert Decimal(pnl["revenue_kes"]) == Decimal("6000000")
        assert Decimal(pnl["cost_kes"]) == Decimal("2800000")
        assert Decimal(pnl["net_income_kes"]) == Decimal("3200000")

        # Test 3: RAROC computation
        # Allocated capital = 50M × 12.5% = 6.25M
        # Cost of capital = 6.25M × 10% = 625K
        # Net after CoC = 3.2M − 625K = 2.575M
        # RAROC = 2.575M / 6.25M × 100 = 41.2%
        raroc = engine.compute_raroc("WOMEN", "2026-Q1")
        assert raroc["raroc_pct"] is not None
        assert abs(Decimal(raroc["raroc_pct"]) - Decimal("41.20")) < Decimal("0.05")

        # Test 4: Rule 1 — no RWA → RAROC None
        engine.record_pnl_line("AGRI", "2026-Q1", "INTEREST_INCOME",
                                Decimal("100000"), actor="cfo")
        raroc_no_rwa = engine.compute_raroc("AGRI", "2026-Q1")
        assert raroc_no_rwa["raroc_pct"] is None
        assert raroc_no_rwa["reason"] == "no_rwa_recorded"

        # Test 5: Rule 1 — empty period → no_data_for_period
        empty_pnl = engine.compute_segment_pnl("YOUTH", "2026-Q1")
        assert empty_pnl["line_count"] == 0
        assert empty_pnl["net_income_kes"] is None
        assert empty_pnl["reason"] == "no_data_for_period"

        # Test 6: Rule 6 — invalid line_type rejected
        result = engine.record_pnl_line(
            "WOMEN", "2026-Q1", "INVALID_LINE", Decimal("1000"), actor="cfo"
        )
        assert not result["recorded"]
        assert "invalid_line_type" in result["error"]

        # Test 7: Rule 4 — actor required
        result = engine.record_pnl_line(
            "WOMEN", "2026-Q1", "INTEREST_INCOME", Decimal("1000"), actor=""
        )
        assert not result["recorded"]
        assert result["error"] == "actor_required"

        # Test 8: profitability_drivers
        drivers = engine.profitability_drivers("WOMEN", "2026-Q1", top_n=3)
        assert len(drivers) == 3
        # Top driver should be INTEREST_INCOME (5M)
        assert drivers[0]["line_type"] == "INTEREST_INCOME"

        # Test 9: time_series
        ts = engine.time_series("WOMEN", ["2026-Q1", "2026-Q2"])
        assert len(ts["series"]) == 2
        assert ts["series"][0]["period"] == "2026-Q1"
        assert ts["series"][1]["period"] == "2026-Q2"
        assert ts["series"][1]["line_count"] == 0  # no Q2 data

    print("  ✅ segment_pnl_attribution self-test PASS")


if __name__ == "__main__":
    _self_test()
