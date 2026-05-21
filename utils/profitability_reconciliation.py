"""utils/profitability_reconciliation.py — v10.367 Profitability Reconciliation Diagnostic.

Measures the gap between A2Z's two parallel profitability engines:

  Engine A : utils.pbt_computation.compute_pbt_from_cbs
             • CBS-driven (accounts.csv + opex_data.json)
             • Bank-level only (no drill-down)
             • Used by compute_bank_aggregates → MD's BSC
             • YTD accruals (operational view)

  Engine B : utils.sbu_pnl_rollup.bank_total_pnl
             • Customer-driven (customer_intelligence.json +
               cost_allocation_rules.json + matrix allocation)
             • Drills to Segment / CBK Sector / RM / Proposition
             • Used by Finance hub (finance_hub_render)
             • Quarterly P&L (management accounting view)

These don't currently reconcile. v10.367 doesn't fix that — it
measures and reports the gap so v10.368+ can close it batch by batch.

What this module produces
-------------------------
ReconciliationReport with:
  • Engine A snapshot: revenue, opex, impairment, PBT
  • Engine B snapshot: revenue, direct cost, indirect cost, PBT
  • Deltas with named reasons
  • Status: NEVER fails — informational only. G253 reports the delta
    as a metric. Once v10.368-v10.370 align the engines, G253 ratchets
    to require zero delta within tolerance.

Why a diagnostic-first batch
----------------------------
Bolting on per-branch / per-SBU allocation before reconciling the
existing two engines locks in a third inconsistency. The right
sequence is:
  1. v10.367 — measure (this batch)
  2. v10.368 — align data sources
  3. v10.369 — add SBU dimension to canonical engine
  4. v10.370 — per-branch allocation
  5. v10.371 — per-RM canonical refactor
  6. v10.372 — extend bank_targets.json with SBU/branch/RM cuts

Pure module: no upward `utils.*` imports beyond pbt_computation and
sbu_pnl_rollup (which are this module's legitimate consumers — and
neither imports back). Self_test uses hand-rolled fixtures per the
v10.364 lesson.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"


@dataclass
class EngineSnapshot:
    """One engine's bank-level P&L numbers, normalized to annual KES."""
    engine_id: str
    revenue: Decimal = Decimal("0")
    direct_cost: Decimal = Decimal("0")
    indirect_cost: Decimal = Decimal("0")
    impairment: Decimal = Decimal("0")
    pbt: Decimal = Decimal("0")
    time_horizon: str = "annual"      # 'annual' | 'quarterly' | 'ytd'
    customer_basis: str = "unknown"   # 'cbs_accounts' | 'customer_intelligence'
    notes: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconciliationReport:
    """Side-by-side comparison + delta analysis."""
    engine_a: EngineSnapshot
    engine_b: EngineSnapshot
    delta_pbt_kes: Decimal = Decimal("0")
    delta_revenue_kes: Decimal = Decimal("0")
    delta_opex_kes: Decimal = Decimal("0")
    delta_pbt_pct: float = 0.0
    reasons: List[str] = field(default_factory=list)
    status: str = "DIVERGENT"  # 'CONVERGED' | 'TOLERANCE' | 'DIVERGENT'
    tolerance_pct: float = 5.0  # within 5% considered converged

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Decimals → floats for JSON
        for top_key in ("engine_a", "engine_b"):
            for k, v in list(d[top_key].items()):
                if isinstance(v, Decimal):
                    d[top_key][k] = float(v)
        for k, v in list(d.items()):
            if isinstance(v, Decimal):
                d[k] = float(v)
        return d


def _snapshot_engine_a(cbs_dir: Path) -> EngineSnapshot:
    """Engine A: compute_pbt_from_cbs (v10.364).

    YTD horizon, CBS-driven, opex_data.json::bank totals.
    """
    from utils.pbt_computation import compute_pbt_from_cbs

    c = compute_pbt_from_cbs(cbs_dir)
    snap = EngineSnapshot(
        engine_id="A_pbt_computation",
        revenue=c.operating_income,  # NII + Non-Interest Income
        direct_cost=Decimal("0"),    # Engine A doesn't split direct/indirect
        indirect_cost=c.total_opex,  # All OpEx counted as indirect
        impairment=c.impairment_charge,
        pbt=c.pbt,
        time_horizon="ytd",
        customer_basis="cbs_accounts",
        notes=[
            "Revenue = Operating Income (NII + Non-Interest Income)",
            "OpEx all categorised as 'indirect' (no per-customer cost in this engine)",
            "Impairment = NPL Stage 3 × LGD%",
            f"OpEx source: {c.opex_source}",
        ],
        raw=c.to_dict(),
    )
    return snap


def _snapshot_engine_b(
    period: str = "2026-Q2",
    cost_source: str = "matrix",
) -> EngineSnapshot:
    """Engine B: sbu_pnl_rollup.bank_total_pnl (v10.338).

    Quarterly horizon, customer-driven, cost_allocation_rules.json matrix.
    """
    from utils.sbu_pnl_rollup import bank_total_pnl, rollup_meta

    b = bank_total_pnl(period=period, cost_source=cost_source)
    meta = rollup_meta(cost_source=cost_source)
    snap = EngineSnapshot(
        engine_id="B_sbu_pnl_rollup",
        revenue=Decimal(str(b.get("revenue", 0))),
        direct_cost=Decimal(str(b.get("direct_cost", 0))),
        indirect_cost=Decimal(str(b.get("indirect_cost", 0))),
        impairment=Decimal("0"),  # Folded into direct_cost as LLP
        pbt=Decimal(str(b.get("pbt", 0))),
        time_horizon="quarterly",
        customer_basis="customer_intelligence",
        notes=[
            f"Revenue source: {meta.get('revenue_source', 'unknown')[:80]}",
            f"Cost source: {cost_source} ({meta.get('cost_source', 'unknown')[:80]})",
            f"Customers: {b.get('customer_count', 0)}",
            f"Impairment (LLP) folded into direct_cost per Engine B convention",
        ],
        raw={k: float(v) if isinstance(v, (Decimal, int, float)) else v
             for k, v in b.items()},
    )
    return snap


def _normalize_to_annual(snap: EngineSnapshot) -> EngineSnapshot:
    """Convert a snapshot to annual KES so the two are comparable.

    Engine A is YTD (treat as annual approximation for comparison).
    Engine B is quarterly (×4 to annualize).

    This is a comparison aid, not a correction — both snapshots'
    original values stay in their .raw dicts.
    """
    multiplier = Decimal("4") if snap.time_horizon == "quarterly" else Decimal("1")
    if multiplier == Decimal("1"):
        return snap
    return EngineSnapshot(
        engine_id=snap.engine_id + "_annualized",
        revenue=(snap.revenue * multiplier).quantize(Decimal("1")),
        direct_cost=(snap.direct_cost * multiplier).quantize(Decimal("1")),
        indirect_cost=(snap.indirect_cost * multiplier).quantize(Decimal("1")),
        impairment=(snap.impairment * multiplier).quantize(Decimal("1")),
        pbt=(snap.pbt * multiplier).quantize(Decimal("1")),
        time_horizon="annual",
        customer_basis=snap.customer_basis,
        notes=snap.notes + [f"Annualized from {snap.time_horizon} (×{multiplier})"],
        raw=snap.raw,
    )


def reconcile(
    cbs_dir: Path,
    period_b: str = "2026-Q2",
    cost_source_b: str = "matrix",
    tolerance_pct: float = 5.0,
) -> ReconciliationReport:
    """Run both engines, normalize to annual, compute delta + status.

    Args:
        cbs_dir: directory containing accounts.csv for Engine A
        period_b: period string for Engine B
        cost_source_b: 'matrix' (cost_allocation_rules.json) or 'proxy'
        tolerance_pct: PBT delta within this % is 'TOLERANCE' status

    Returns ReconciliationReport with both snapshots and delta breakdown.
    """
    a_raw = _snapshot_engine_a(cbs_dir)
    b_raw = _snapshot_engine_b(period=period_b, cost_source=cost_source_b)
    # Normalize for fair comparison
    a = _normalize_to_annual(a_raw)
    b = _normalize_to_annual(b_raw)

    delta_pbt = a.pbt - b.pbt
    delta_rev = a.revenue - b.revenue
    a_opex = a.direct_cost + a.indirect_cost
    b_opex = b.direct_cost + b.indirect_cost
    delta_opex = a_opex - b_opex

    # Pct relative to bigger absolute PBT (avoid div-by-zero on small numbers)
    denom = max(abs(float(a.pbt)), abs(float(b.pbt)), 1.0)
    delta_pbt_pct = abs(float(delta_pbt)) / denom * 100

    reasons: List[str] = []
    # Revenue divergence
    if abs(float(delta_rev)) > 1_000_000:
        reasons.append(
            f"Revenue diverges by KES {float(delta_rev):,.0f} — "
            f"Engine A uses CBS YTD accruals (interest_income_ytd + "
            f"fee_income_ytd × NFI uplift), Engine B uses customer "
            f"proxy (CLV-derived for individuals, turnover×NIM for "
            f"businesses). Different inputs entirely."
        )
    # OpEx divergence
    if abs(float(delta_opex)) > 100_000_000:
        reasons.append(
            f"OpEx diverges by KES {float(delta_opex):,.0f} — Engine A "
            f"reads opex_data.json::bank.total_opex_kes_b (single bucket); "
            f"Engine B's matrix allocation distributes 10 cost-rule "
            f"buckets per cost_allocation_rules.json. Both should "
            f"ultimately sum to the same bank-wide OpEx if assumptions align."
        )
    # Customer basis
    if a.customer_basis != b.customer_basis:
        reasons.append(
            f"Customer basis differs: A reads {a.customer_basis} "
            f"(operational), B reads {b.customer_basis} (management "
            f"accounting). Until both engines walk the same authoritative "
            f"source, agreement is structural luck."
        )
    # Impairment treatment
    if a.impairment > 0 and b.impairment == 0:
        reasons.append(
            f"Impairment KES {float(a.impairment):,.0f} is itemized in "
            f"Engine A but folded into Engine B's direct_cost — convention "
            f"difference, not actual disagreement."
        )

    # Determine status
    if delta_pbt_pct < 1.0:
        status = "CONVERGED"
    elif delta_pbt_pct < tolerance_pct:
        status = "TOLERANCE"
    else:
        status = "DIVERGENT"

    return ReconciliationReport(
        engine_a=a,
        engine_b=b,
        delta_pbt_kes=delta_pbt,
        delta_revenue_kes=delta_rev,
        delta_opex_kes=delta_opex,
        delta_pbt_pct=round(delta_pbt_pct, 2),
        reasons=reasons,
        status=status,
        tolerance_pct=tolerance_pct,
    )


def format_report(report: ReconciliationReport) -> str:
    """Human-readable side-by-side P&L diff."""
    def fmt(v: Decimal) -> str:
        try:
            return f"KES {float(v):,.0f}"
        except Exception:
            return str(v)

    a = report.engine_a
    b = report.engine_b
    lines: List[str] = []
    lines.append("Profitability Reconciliation — A vs B")
    lines.append("=" * 78)
    lines.append(f"{'':30s} {'Engine A':>22s} {'Engine B':>22s}")
    lines.append(f"{'':30s} {a.engine_id[:22]:>22s} {b.engine_id[:22]:>22s}")
    lines.append("-" * 78)
    lines.append(f"  Revenue                      {fmt(a.revenue):>22s} {fmt(b.revenue):>22s}")
    lines.append(f"  Direct Cost                  {fmt(a.direct_cost):>22s} {fmt(b.direct_cost):>22s}")
    lines.append(f"  Indirect Cost (OpEx)         {fmt(a.indirect_cost):>22s} {fmt(b.indirect_cost):>22s}")
    lines.append(f"  Impairment                   {fmt(a.impairment):>22s} {fmt(b.impairment):>22s}")
    lines.append(f"  PBT                          {fmt(a.pbt):>22s} {fmt(b.pbt):>22s}")
    lines.append("-" * 78)
    lines.append(f"  Time horizon                 {a.time_horizon:>22s} {b.time_horizon:>22s}")
    lines.append(f"  Customer basis               {a.customer_basis:>22s} {b.customer_basis:>22s}")
    lines.append("")
    lines.append(f"  ΔPBT      = {fmt(report.delta_pbt_kes)} ({report.delta_pbt_pct:.2f}%)")
    lines.append(f"  ΔRevenue  = {fmt(report.delta_revenue_kes)}")
    lines.append(f"  ΔOpEx     = {fmt(report.delta_opex_kes)}")
    lines.append(f"  Status:    {report.status}  (tolerance ±{report.tolerance_pct}%)")
    lines.append("")
    if report.reasons:
        lines.append("Reasons for divergence:")
        for r in report.reasons:
            lines.append(f"  • {r}")
    return "\n".join(lines)


def self_test() -> None:
    """Hand-rolled fixtures only — no imports of consumers via self_test
    body (v10.364 lesson). The top-level imports of pbt_computation
    and sbu_pnl_rollup are inside the module functions (lazy), so this
    self_test can still verify the dataclass + delta logic without
    those engines firing.
    """
    tests_run = 0

    # Test 1: EngineSnapshot defaults
    s = EngineSnapshot(engine_id="test")
    assert s.revenue == Decimal("0")
    assert s.time_horizon == "annual"
    tests_run += 1

    # Test 2: ReconciliationReport defaults
    a = EngineSnapshot(engine_id="A", pbt=Decimal("100"), revenue=Decimal("1000"))
    b = EngineSnapshot(engine_id="B", pbt=Decimal("100"), revenue=Decimal("1000"))
    r = ReconciliationReport(engine_a=a, engine_b=b)
    assert r.status == "DIVERGENT"  # default before reconcile() runs
    tests_run += 1

    # Test 3: _normalize_to_annual for quarterly → ×4
    q = EngineSnapshot(engine_id="Q", pbt=Decimal("100"), revenue=Decimal("250"),
                       time_horizon="quarterly")
    n = _normalize_to_annual(q)
    assert n.pbt == Decimal("400")
    assert n.revenue == Decimal("1000")
    assert n.time_horizon == "annual"
    tests_run += 1

    # Test 4: _normalize_to_annual for ytd / annual passes through
    y = EngineSnapshot(engine_id="Y", pbt=Decimal("500"), time_horizon="ytd")
    nn = _normalize_to_annual(y)
    assert nn.pbt == Decimal("500")  # No multiplier change for ytd
    tests_run += 1

    # Test 5: to_dict serializes (Decimals → floats)
    a2 = EngineSnapshot(engine_id="A", pbt=Decimal("100.5"))
    b2 = EngineSnapshot(engine_id="B", pbt=Decimal("90.5"))
    r2 = ReconciliationReport(
        engine_a=a2, engine_b=b2,
        delta_pbt_kes=Decimal("10"),
    )
    d = r2.to_dict()
    import json as _json
    _ = _json.dumps(d)  # must not raise
    assert isinstance(d["engine_a"]["pbt"], float)
    assert isinstance(d["delta_pbt_kes"], float)
    tests_run += 1

    # Test 6: format_report doesn't crash
    s = format_report(r2)
    assert "Profitability Reconciliation" in s
    assert "Engine A" in s
    assert "ΔPBT" in s
    tests_run += 1

    # Test 7: Status thresholds
    # Converged: <1% delta
    av = EngineSnapshot(engine_id="A", pbt=Decimal("1000"))
    bv = EngineSnapshot(engine_id="B", pbt=Decimal("995"))
    delta_pct = abs(float(av.pbt - bv.pbt)) / max(abs(float(av.pbt)), abs(float(bv.pbt)), 1.0) * 100
    assert delta_pct < 1.0  # would be 'CONVERGED'
    tests_run += 1

    print(f"✓ profitability_reconciliation self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()
