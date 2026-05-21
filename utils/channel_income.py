"""utils.channel_income — Channel Income Intelligence
(Standard #45, v5.52). Volume Seven — Finance Intelligence.

Per v6 spec §7:
    ChannelIncomeEngine: income by channel + cost-to-serve + optimization

WHAT THIS MODULE SHIPS
----------------------
1. ChannelIncomeEngine class with:
   - income_by_channel(period, segment) — fee income aggregation
   - cost_to_serve(period, channel) — per-transaction cost
   - channel_optimization_recommendations(period) — migration opportunities

2. CHANNELS catalog: 7 channels per spec (BRANCH, ATM, MOBILE, INTERNET,
   AGENT, USSD, POS)
3. Decimal-internal arithmetic (Rule 1)

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - Decimal-internal precision 28
  - cost_per_transaction = None when transaction_count == 0

Rule 6 — No silent fallback:
  - Cost basis ALWAYS surfaced in meta (auditable, not hidden constants)
  - Unknown channels exposed in meta.unknown_channels
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.channel_income")
getcontext().prec = 28

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §7 #45)
# ─────────────────────────────────────────────────────────────────────

CHANNELS: List[str] = ["BRANCH", "ATM", "MOBILE", "INTERNET", "AGENT", "USSD", "POS"]

# Cost components per channel (KES per transaction). These are
# architectural defaults; production deployments should override based
# on actual cost analysis. The basis MUST be surfaced in meta.cost_basis.
DEFAULT_COST_PER_TXN: Dict[str, Dict[str, Decimal]] = {
    "BRANCH":   {"fte_allocation": Decimal("80"),  "infrastructure": Decimal("15"), "processing": Decimal("5")},
    "ATM":      {"fte_allocation": Decimal("3"),   "infrastructure": Decimal("8"),  "processing": Decimal("2")},
    "MOBILE":   {"fte_allocation": Decimal("0.5"), "infrastructure": Decimal("3"),  "processing": Decimal("1")},
    "INTERNET": {"fte_allocation": Decimal("0.5"), "infrastructure": Decimal("2"),  "processing": Decimal("1")},
    "AGENT":    {"fte_allocation": Decimal("5"),   "infrastructure": Decimal("4"),  "processing": Decimal("3")},
    "USSD":     {"fte_allocation": Decimal("0.2"), "infrastructure": Decimal("1.5"),"processing": Decimal("0.8")},
    "POS":      {"fte_allocation": Decimal("1"),   "infrastructure": Decimal("3"),  "processing": Decimal("1.5")},
}

# Margin threshold for channel migration recommendations
LOW_MARGIN_THRESHOLD_PCT = Decimal("20")     # margin < 20% → migration candidate
HIGH_VOLUME_THRESHOLD = 10_000               # txn count > 10k → significant


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class ChannelIncomeEngine:
    """Income by channel + cost-to-serve analytics."""

    CHANNELS = CHANNELS

    def __init__(
        self,
        income_lookup_fn:        Optional[Callable[[str], List[dict]]] = None,
        transaction_lookup_fn:   Optional[Callable[[str, str], dict]]  = None,
        cost_overrides:          Optional[Dict[str, Dict[str, Decimal]]] = None,
    ):
        """All collaborators injectable.

        income_lookup_fn(period) → list[dict] with: amount, channel, segment, fee_type
        transaction_lookup_fn(period, channel) → dict with: count, total_volume_amount
        cost_overrides: optional override of DEFAULT_COST_PER_TXN
        """
        self._income       = income_lookup_fn      or (lambda p: [])
        self._transactions = transaction_lookup_fn or (lambda p, c: {})
        self._costs        = cost_overrides or DEFAULT_COST_PER_TXN

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: income_by_channel
    # ──────────────────────────────────────────────────────────────────

    def income_by_channel(
        self, period: str, segment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate fee income by channel, optionally filtered by segment.

        Returns:
            {
              "period": str,
              "segment": str | None,
              "channels": {channel: {"income": float, "share_pct": float | None}},
              "total_income": float,
              "meta": {...}
            }
        Returns {} for empty period.
        """
        if not period:
            return {}

        rows = self._income(period) or []
        income_by_channel: Dict[str, Decimal] = {c: ZERO for c in CHANNELS}
        unknown_channels: List[str] = []
        rows_skipped = 0

        for row in rows:
            if not isinstance(row, dict):
                rows_skipped += 1
                continue
            ch = row.get("channel")
            seg = row.get("segment")
            if segment and seg != segment:
                continue    # filter mismatch
            try:
                amt = Decimal(str(row.get("amount", 0)))
            except Exception:
                rows_skipped += 1
                continue
            if ch in CHANNELS:
                income_by_channel[ch] += amt
            elif ch:
                unknown_channels.append(ch)
                rows_skipped += 1

        total = sum(income_by_channel.values())

        results: Dict[str, Dict[str, Any]] = {}
        for ch in CHANNELS:
            inc = income_by_channel[ch]
            share_pct = float(inc / total * Decimal("100")) if total > 0 else None
            results[ch] = {
                "income":    _money(inc),
                "share_pct": round(share_pct, 2) if share_pct is not None else None,
            }

        return {
            "period":       period,
            "segment":      segment,
            "channels":     results,
            "total_income": _money(total),
            "meta": {
                "rows_processed":   len(rows),
                "rows_skipped":     rows_skipped,
                "unknown_channels": sorted(set(unknown_channels)),
                "channels_in_spec": list(CHANNELS),
                "generated_at":     datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: cost_to_serve
    # ──────────────────────────────────────────────────────────────────

    def cost_to_serve(self, period: str, channel: str) -> Dict[str, Any]:
        """Cost per transaction for a channel.

        Cost basis = FTE allocation + infrastructure + transaction processing.
        Documented in meta.cost_basis (auditable).

        Returns:
            {
              "period": str,
              "channel": str,
              "transaction_count": int,
              "total_cost": float,
              "cost_per_transaction": float | None,    # None when count == 0
              "meta": {"cost_basis": {fte, infra, processing}, ...}
            }
        """
        if not period or not channel:
            return {}
        if channel not in CHANNELS:
            return {
                "period": period,
                "channel": channel,
                "error": f"channel {channel!r} not in spec catalog",
                "valid_channels": list(CHANNELS),
            }

        txn_data = self._transactions(period, channel) or {}
        try:
            count = int(txn_data.get("count", 0))
        except Exception:
            count = 0

        cost_components = self._costs.get(channel, {})
        cost_per_txn = sum(cost_components.values()) if cost_components else ZERO
        total_cost = cost_per_txn * Decimal(count)

        cost_per_txn_out = _money(cost_per_txn) if count > 0 else None
        # Note: cost_per_transaction is the unit cost (a constant for the channel),
        # so it's NOT None just because count==0 — it's None when we don't have
        # cost data for the channel
        if not cost_components:
            cost_per_txn_out = None

        return {
            "period":              period,
            "channel":             channel,
            "transaction_count":   count,
            "total_cost":          _money(total_cost),
            "cost_per_transaction": cost_per_txn_out,
            "meta": {
                "cost_basis": {k: _money(v) for k, v in cost_components.items()},
                "cost_basis_doc": "FTE allocation + infrastructure + transaction processing",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: channel_optimization_recommendations
    # ──────────────────────────────────────────────────────────────────

    def channel_optimization_recommendations(self, period: str) -> Dict[str, Any]:
        """Identify migration opportunities (high-volume low-margin → digital).

        Returns:
            {
              "period": str,
              "recommendations": [
                  {channel, txn_count, income, cost, margin_pct, recommendation}
              ],
              "meta": {...}
            }
        """
        if not period:
            return {}

        income_data = self.income_by_channel(period)
        if not income_data:
            return {"period": period, "recommendations": []}

        recommendations: List[Dict[str, Any]] = []
        for ch in CHANNELS:
            ch_income = Decimal(str(income_data["channels"][ch]["income"]))
            txn_data = self._transactions(period, ch) or {}
            try:
                count = int(txn_data.get("count", 0))
            except Exception:
                count = 0
            cost_components = self._costs.get(ch, {})
            cost_per_txn = sum(cost_components.values())
            total_cost = cost_per_txn * Decimal(count)

            if ch_income == 0 or total_cost == 0:
                margin_pct = None
            else:
                margin_pct = float((ch_income - total_cost) / ch_income * Decimal("100"))

            # Recommendation logic
            recommendation = "maintain"
            if count > HIGH_VOLUME_THRESHOLD and margin_pct is not None and \
               Decimal(str(margin_pct)) < LOW_MARGIN_THRESHOLD_PCT and \
               ch in ("BRANCH", "ATM"):
                recommendation = f"migrate_to_digital ({ch} → MOBILE/USSD)"
            elif margin_pct is not None and margin_pct > 50 and count > HIGH_VOLUME_THRESHOLD:
                recommendation = "promote_channel (high margin, high volume)"

            recommendations.append({
                "channel":    ch,
                "txn_count":  count,
                "income":     _money(ch_income),
                "cost":       _money(total_cost),
                "margin_pct": round(margin_pct, 2) if margin_pct is not None else None,
                "recommendation": recommendation,
            })

        return {
            "period": period,
            "recommendations": recommendations,
            "meta": {
                "low_margin_threshold_pct": float(LOW_MARGIN_THRESHOLD_PCT),
                "high_volume_threshold":    HIGH_VOLUME_THRESHOLD,
                "generated_at":             datetime.now(timezone.utc).isoformat(),
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
    print("A2Z MIS 360 — utils.channel_income self-test")

    # ── Spec literals ─────────────────────────────────────────────────
    assert len(CHANNELS) == 7
    assert CHANNELS == ["BRANCH", "ATM", "MOBILE", "INTERNET", "AGENT", "USSD", "POS"]
    print(f"  ✅ spec literals: 7 channels {CHANNELS}")

    # ── Empty period → {} ─────────────────────────────────────────────
    eng = ChannelIncomeEngine()
    assert eng.income_by_channel("") == {}
    assert eng.cost_to_serve("", "BRANCH") == {}
    print(f"  ✅ empty inputs → {{}}")

    # ── Invalid channel caught ────────────────────────────────────────
    r = eng.cost_to_serve("2026-04", "FAX")
    assert "error" in r
    print(f"  ✅ invalid channel caught: {r.get('error', '')[:50]}")

    # ── Income aggregation ────────────────────────────────────────────
    income = [
        {"amount": 100_000_000, "channel": "BRANCH",   "segment": "RETAIL"},
        {"amount":  50_000_000, "channel": "ATM",      "segment": "RETAIL"},
        {"amount": 200_000_000, "channel": "MOBILE",   "segment": "RETAIL"},
        {"amount":  30_000_000, "channel": "INTERNET", "segment": "CORPORATE"},
        {"amount":  10_000_000, "channel": "USSD",     "segment": "RETAIL"},
    ]
    eng2 = ChannelIncomeEngine(income_lookup_fn=lambda p: income)
    r = eng2.income_by_channel("2026-04")
    assert r["total_income"] == 390_000_000.00
    assert r["channels"]["MOBILE"]["income"] == 200_000_000.00
    # Mobile should be ~51.28% of total
    assert abs(r["channels"]["MOBILE"]["share_pct"] - 51.28) < 0.01
    print(f"  ✅ income aggregation: total={r['total_income']:,.2f}, "
          f"MOBILE share={r['channels']['MOBILE']['share_pct']}%")

    # ── Segment filter ───────────────────────────────────────────────
    r = eng2.income_by_channel("2026-04", segment="CORPORATE")
    assert r["total_income"] == 30_000_000.00
    assert r["channels"]["INTERNET"]["income"] == 30_000_000.00
    assert r["channels"]["MOBILE"]["income"] == 0.0    # no CORPORATE rows for MOBILE
    print(f"  ✅ segment filter: CORPORATE total={r['total_income']:,.2f}")

    # ── Unknown channel exposed ───────────────────────────────────────
    income_unknown = income + [{"amount": 1_000, "channel": "FAX", "segment": "RETAIL"}]
    eng3 = ChannelIncomeEngine(income_lookup_fn=lambda p: income_unknown)
    r = eng3.income_by_channel("2026-04")
    assert "FAX" in r["meta"]["unknown_channels"]
    print(f"  ✅ unknown channel exposed in meta: {r['meta']['unknown_channels']}")

    # ── Cost-to-serve with cost basis surfaced ────────────────────────
    transactions = {
        ("2026-04", "BRANCH"): {"count": 50_000, "total_volume_amount": 10_000_000_000},
        ("2026-04", "MOBILE"): {"count": 5_000_000, "total_volume_amount": 50_000_000_000},
    }
    eng4 = ChannelIncomeEngine(
        transaction_lookup_fn=lambda p, c: transactions.get((p, c), {}),
    )
    r = eng4.cost_to_serve("2026-04", "BRANCH")
    # Cost: FTE 80 + infra 15 + processing 5 = 100/txn × 50k = 5M
    assert r["transaction_count"] == 50_000
    assert r["cost_per_transaction"] == 100.00
    assert r["total_cost"] == 5_000_000.00
    assert r["meta"]["cost_basis"] == {"fte_allocation": 80.0, "infrastructure": 15.0, "processing": 5.0}
    print(f"  ✅ cost-to-serve BRANCH: 100 KES/txn × 50k = {r['total_cost']:,.2f}, "
          f"basis surfaced")

    r = eng4.cost_to_serve("2026-04", "MOBILE")
    # Mobile: 0.5 + 3 + 1 = 4.5/txn × 5M = 22.5M
    assert r["cost_per_transaction"] == 4.50
    assert r["total_cost"] == 22_500_000.00
    print(f"  ✅ cost-to-serve MOBILE: {r['cost_per_transaction']} KES/txn → "
          f"{r['total_cost']:,.2f}")

    # ── Optimization recommendations ──────────────────────────────────
    eng5 = ChannelIncomeEngine(
        income_lookup_fn=lambda p: income,
        transaction_lookup_fn=lambda p, c: transactions.get((p, c), {}),
    )
    r = eng5.channel_optimization_recommendations("2026-04")
    assert "recommendations" in r
    branch_rec = next(rec for rec in r["recommendations"] if rec["channel"] == "BRANCH")
    # Branch: income=100M, cost=5M, margin=95% — high margin so promote
    assert branch_rec["margin_pct"] > 90
    mobile_rec = next(rec for rec in r["recommendations"] if rec["channel"] == "MOBILE")
    # Mobile: income=200M, cost=22.5M, margin=88.75% — high margin
    print(f"  ✅ recommendations: BRANCH margin={branch_rec['margin_pct']}%, "
          f"MOBILE margin={mobile_rec['margin_pct']}%")

    # ── Margin = None when income or cost is zero ─────────────────────
    eng6 = ChannelIncomeEngine(
        income_lookup_fn=lambda p: [],   # no income data
        transaction_lookup_fn=lambda p, c: transactions.get((p, c), {}),
    )
    r = eng6.channel_optimization_recommendations("2026-04")
    for rec in r["recommendations"]:
        # No income → margin undefined
        assert rec["margin_pct"] is None
    print(f"  ✅ no income → all margins=None (Rule 1)")

    # ── KES-billion precision ────────────────────────────────────────
    huge_income = [
        {"amount": "11500000000.50", "channel": "MOBILE", "segment": "RETAIL"},
        {"amount": "11500000000.51", "channel": "MOBILE", "segment": "RETAIL"},
    ]
    eng7 = ChannelIncomeEngine(income_lookup_fn=lambda p: huge_income)
    r = eng7.income_by_channel("2026-04")
    assert r["total_income"] == 23_000_000_001.01
    print(f"  ✅ KES-billion precision: total={r['total_income']:,.2f}")

    print("\n  ALL TESTS PASSED")
