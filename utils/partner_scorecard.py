"""
================================================================================
A2Z MIS 360 — Standard #371: Partner Performance Scorecard
================================================================================

Risk classification: Cat B (deterministic scoring + tier classification)

Per-partner performance scorecard: revenue, leads delivered, conversion
rate, customer satisfaction, compliance score. Aggregates upstream
data into 5 dimensions and a composite tier.

Public API:
    record_score_dimension(partner_id, period, dimension, value, actor)
    compute_scorecard(partner_id, period) -> {dimensions, composite, tier}
    rank_partners(period) -> ordered scorecards
    historical_trend(partner_id, periods=4)

SCORECARD_DIMENSIONS byte-for-byte (Continuation.docx #371):
    REVENUE_KES         -- gross revenue attributed to partner (period)
    LEADS_DELIVERED     -- total leads / referrals submitted
    CONVERSION_RATE     -- leads converted / leads delivered (percent)
    CSAT_SCORE          -- customer satisfaction (0-100 scale)
    COMPLIANCE_SCORE    -- compliance breaches / actions (0-100 scale)

DIMENSION_WEIGHTS byte-for-byte (sum=100):
    REVENUE_KES         = 30
    LEADS_DELIVERED     = 20
    CONVERSION_RATE     = 20
    CSAT_SCORE          = 15
    COMPLIANCE_SCORE    = 15

PARTNER_TIERS byte-for-byte (composite score → tier):
    PLATINUM   -- >= 85 — preferred; expand engagement
    GOLD       -- >= 75 — strong performer
    SILVER     -- >= 60 — meets expectations
    BRONZE     -- >= 45 — under review
    AT_RISK    -- < 45 — formal review triggered

Honesty rules:
    Rule 1: composite = None when any dimension missing (no imputation)
    Rule 6: invalid dimension rejected; invalid scale value rejected

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28


SCORECARD_DIMENSIONS: Tuple[str, ...] = (
    "REVENUE_KES",
    "LEADS_DELIVERED",
    "CONVERSION_RATE",
    "CSAT_SCORE",
    "COMPLIANCE_SCORE",
)

DIMENSION_WEIGHTS: Dict[str, Decimal] = {
    "REVENUE_KES":      Decimal("30"),
    "LEADS_DELIVERED":  Decimal("20"),
    "CONVERSION_RATE":  Decimal("20"),
    "CSAT_SCORE":       Decimal("15"),
    "COMPLIANCE_SCORE": Decimal("15"),
}

PARTNER_TIERS: Tuple[str, ...] = (
    "PLATINUM", "GOLD", "SILVER", "BRONZE", "AT_RISK",
)

TIER_PLATINUM_THRESHOLD: Decimal = Decimal("85")
TIER_GOLD_THRESHOLD:     Decimal = Decimal("75")
TIER_SILVER_THRESHOLD:   Decimal = Decimal("60")
TIER_BRONZE_THRESHOLD:   Decimal = Decimal("45")


def classify_partner_tier(composite_score: Decimal) -> str:
    if composite_score >= TIER_PLATINUM_THRESHOLD:
        return "PLATINUM"
    if composite_score >= TIER_GOLD_THRESHOLD:
        return "GOLD"
    if composite_score >= TIER_SILVER_THRESHOLD:
        return "SILVER"
    if composite_score >= TIER_BRONZE_THRESHOLD:
        return "BRONZE"
    return "AT_RISK"


class PartnerScorecardEngine:
    """Per-partner performance scorecard."""

    def __init__(self, scorecards_path: Optional[Path] = None):
        self.scorecards_path = (
            scorecards_path
            if scorecards_path is not None
            else Path(__file__).parent.parent / "data" / "partner_scorecards.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.scorecards_path,
                table="partner_scorecards",
                index_cols=("partner_id", "period", "dimension"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.scorecards_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.scorecards_path,
                data=records,
                table="partner_scorecards",
                pk_col="partner_id")
            return True
        except Exception:
            return False

    def record_score_dimension(
        self,
        partner_id: str,
        period: str,
        dimension: str,
        value: Decimal,
        actor: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Record a dimension value for a partner-period."""
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if dimension not in SCORECARD_DIMENSIONS:
            return {
                "recorded": False,
                "error": f"invalid_dimension:{dimension}",
                "valid_dimensions": list(SCORECARD_DIMENSIONS),
            }

        try:
            v = Decimal(str(value))
        except (ValueError, TypeError):
            return {"recorded": False, "error": "value_not_decimal"}

        # Range checks for percent-style dimensions
        if dimension in ("CONVERSION_RATE", "CSAT_SCORE", "COMPLIANCE_SCORE"):
            if v < 0 or v > 100:
                return {
                    "recorded": False,
                    "error": f"value_out_of_0_100_range:{v}",
                }
        elif dimension in ("REVENUE_KES", "LEADS_DELIVERED"):
            if v < 0:
                return {
                    "recorded": False,
                    "error": f"value_negative:{v}",
                }

        records = self._load()
        # Replace existing partner-period-dimension if present
        for r in records:
            if (r.get("partner_id") == partner_id
                    and r.get("period") == period
                    and r.get("dimension") == dimension):
                r["value"] = str(v)
                r["actor"] = actor
                r["reason"] = reason
                r["recorded_at"] = datetime.utcnow().isoformat()
                ok = self._save(records)
                return {"recorded": ok, "replaced": True}

        records.append({
            "partner_id": partner_id,
            "period": period,
            "dimension": dimension,
            "value": str(v),
            "actor": actor,
            "reason": reason,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(records)
        return {"recorded": ok, "replaced": False}

    def _normalize_dimension(
        self, dimension: str, raw_value: Decimal,
        revenue_baseline: Decimal = Decimal("10000000"),
        leads_baseline: int = 100,
    ) -> Decimal:
        """
        Normalize raw dimension value to 0-100 scale for composite scoring.

        - REVENUE_KES: linear up to revenue_baseline = 100; capped 100
        - LEADS_DELIVERED: linear up to leads_baseline = 100; capped 100
        - Already-normalized dimensions returned as-is, capped at 100
        """
        if dimension == "REVENUE_KES":
            if revenue_baseline <= 0:
                return Decimal("0")
            normalized = (raw_value / revenue_baseline) * Decimal("100")
            return min(normalized, Decimal("100"))
        if dimension == "LEADS_DELIVERED":
            if leads_baseline <= 0:
                return Decimal("0")
            normalized = (raw_value / Decimal(leads_baseline)) * Decimal("100")
            return min(normalized, Decimal("100"))
        # CONVERSION_RATE, CSAT_SCORE, COMPLIANCE_SCORE — already 0-100
        return min(raw_value, Decimal("100"))

    def compute_scorecard(
        self,
        partner_id: str,
        period: str,
        revenue_baseline: Decimal = Decimal("10000000"),
        leads_baseline: int = 100,
    ) -> Dict[str, Any]:
        """Composite scorecard for a partner-period."""
        records = self._load()
        period_records = [
            r for r in records
            if r.get("partner_id") == partner_id and r.get("period") == period
        ]

        # Build dimension → value map
        dim_values: Dict[str, Decimal] = {}
        for r in period_records:
            d = r.get("dimension")
            if d in SCORECARD_DIMENSIONS:
                try:
                    dim_values[d] = Decimal(str(r["value"]))
                except (ValueError, TypeError):
                    continue

        # Rule 1: missing dimensions surfaced; composite=None
        missing = [d for d in SCORECARD_DIMENSIONS if d not in dim_values]
        if missing:
            return {
                "partner_id": partner_id,
                "period": period,
                "composite": None,
                "tier": None,
                "missing_dimensions": missing,
                "dimensions": {
                    d: str(dim_values[d]) for d in dim_values
                },
                "reason": "missing_dimensions",
            }

        # Compute weighted composite
        composite = Decimal("0")
        normalized = {}
        for d in SCORECARD_DIMENSIONS:
            n = self._normalize_dimension(d, dim_values[d],
                                            revenue_baseline, leads_baseline)
            normalized[d] = n
            composite += n * DIMENSION_WEIGHTS[d] / Decimal("100")

        composite = composite.quantize(Decimal("0.01"))
        tier = classify_partner_tier(composite)

        return {
            "partner_id": partner_id,
            "period": period,
            "composite": str(composite),
            "tier": tier,
            "dimensions_raw": {d: str(v) for d, v in dim_values.items()},
            "dimensions_normalized": {d: str(v.quantize(Decimal("0.01")))
                                          for d, v in normalized.items()},
            "weights": {d: str(w) for d, w in DIMENSION_WEIGHTS.items()},
        }

    def rank_partners(
        self,
        period: str,
        revenue_baseline: Decimal = Decimal("10000000"),
    ) -> List[Dict[str, Any]]:
        """Rank all partners with complete scorecards in period."""
        records = self._load()
        partner_ids = sorted({
            r["partner_id"] for r in records
            if r.get("period") == period
        })

        scorecards = []
        for pid in partner_ids:
            sc = self.compute_scorecard(pid, period, revenue_baseline)
            if sc["composite"] is not None:
                scorecards.append(sc)

        scorecards.sort(
            key=lambda x: Decimal(x["composite"]),
            reverse=True,
        )
        return scorecards

    def historical_trend(
        self,
        partner_id: str,
        periods: List[str],
    ) -> Dict[str, Any]:
        """Composite scores across multiple periods."""
        series = []
        for p in periods:
            sc = self.compute_scorecard(partner_id, p)
            series.append({
                "period": p,
                "composite": sc.get("composite"),
                "tier": sc.get("tier"),
                "complete": sc.get("composite") is not None,
            })
        return {
            "partner_id": partner_id,
            "periods": periods,
            "series": series,
        }


def _self_test() -> None:
    import tempfile

    # Tier classification
    assert classify_partner_tier(Decimal("90")) == "PLATINUM"
    assert classify_partner_tier(Decimal("80")) == "GOLD"
    assert classify_partner_tier(Decimal("65")) == "SILVER"
    assert classify_partner_tier(Decimal("50")) == "BRONZE"
    assert classify_partner_tier(Decimal("30")) == "AT_RISK"

    # Weight sum check
    assert sum(DIMENSION_WEIGHTS.values()) == Decimal("100")

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = PartnerScorecardEngine(
            scorecards_path=Path(tmpdir) / "sc.json"
        )

        # Record all 5 dimensions for P-001 in 2026-Q1
        engine.record_score_dimension(
            "P-001", "2026-Q1", "REVENUE_KES",
            Decimal("8000000"), actor="ops")
        engine.record_score_dimension(
            "P-001", "2026-Q1", "LEADS_DELIVERED",
            Decimal("80"), actor="ops")
        engine.record_score_dimension(
            "P-001", "2026-Q1", "CONVERSION_RATE",
            Decimal("75"), actor="ops")
        engine.record_score_dimension(
            "P-001", "2026-Q1", "CSAT_SCORE",
            Decimal("90"), actor="ops")
        engine.record_score_dimension(
            "P-001", "2026-Q1", "COMPLIANCE_SCORE",
            Decimal("95"), actor="ops")

        sc = engine.compute_scorecard("P-001", "2026-Q1")
        assert sc["composite"] is not None
        assert sc["tier"] in PARTNER_TIERS
        # Composite computed: 80*0.30 + 80*0.20 + 75*0.20 + 90*0.15 + 95*0.15
        # = 24 + 16 + 15 + 13.5 + 14.25 = 82.75 → GOLD
        assert sc["tier"] == "GOLD"
        assert abs(Decimal(sc["composite"]) - Decimal("82.75")) < Decimal("0.05")

        # Test 2: Rule 1 — missing dimensions surfaced, composite=None
        engine.record_score_dimension(
            "P-002", "2026-Q1", "REVENUE_KES",
            Decimal("5000000"), actor="ops")
        sc = engine.compute_scorecard("P-002", "2026-Q1")
        assert sc["composite"] is None
        assert sc["tier"] is None
        assert len(sc["missing_dimensions"]) == 4

        # Test 3: invalid dimension rejected
        r = engine.record_score_dimension(
            "P-003", "2026-Q1", "INVALID",
            Decimal("100"), actor="ops")
        assert not r["recorded"]

        # Test 4: out-of-range value rejected (0-100 scale)
        r = engine.record_score_dimension(
            "P-003", "2026-Q1", "CSAT_SCORE",
            Decimal("150"), actor="ops")
        assert not r["recorded"]

        # Test 5: negative revenue rejected
        r = engine.record_score_dimension(
            "P-003", "2026-Q1", "REVENUE_KES",
            Decimal("-1000"), actor="ops")
        assert not r["recorded"]

        # Test 6: actor required
        r = engine.record_score_dimension(
            "P-003", "2026-Q1", "REVENUE_KES",
            Decimal("1000"), actor="")
        assert not r["recorded"]

        # Test 7: replacement updates existing record
        engine.record_score_dimension(
            "P-001", "2026-Q1", "CSAT_SCORE",
            Decimal("85"), actor="ops_v2", reason="recompute")
        sc = engine.compute_scorecard("P-001", "2026-Q1")
        # 80*0.30 + 80*0.20 + 75*0.20 + 85*0.15 + 95*0.15
        # = 24 + 16 + 15 + 12.75 + 14.25 = 82.0
        assert abs(Decimal(sc["composite"]) - Decimal("82.0")) < Decimal("0.05")

        # Test 8: rank_partners
        ranked = engine.rank_partners("2026-Q1")
        assert len(ranked) == 1  # only P-001 has complete scorecard
        assert ranked[0]["partner_id"] == "P-001"

        # Test 9: historical_trend
        trend = engine.historical_trend("P-001", ["2026-Q1", "2026-Q2"])
        assert len(trend["series"]) == 2
        assert trend["series"][0]["complete"] is True
        assert trend["series"][1]["complete"] is False

    print("  ✅ partner_scorecard self-test PASS")


if __name__ == "__main__":
    _self_test()
