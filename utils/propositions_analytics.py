"""
================================================================================
A2Z MIS 360 — Standard #354: Proposition Performance Analytics
================================================================================

Risk classification: Cat C (deterministic per-proposition KPI computation
                              over impressions + take-up + revenue records)

Per-proposition KPIs: take-up rate, revenue, profitability, customer
satisfaction, attrition. Cohort analysis. Composes
proposition_orchestration impressions, take-up records (new), and
revenue records.

Public API:
    record_take_up(prop_id, customer_id, channel, actor) -> take-up event
    record_attrition(prop_id, customer_id, reason, actor)
    record_revenue(prop_id, customer_id, amount_kes, actor)
    record_satisfaction(prop_id, customer_id, score, actor)
    proposition_kpis(prop_id, period_start, period_end) -> 6 KPI dict
    cohort_analysis(prop_id, cohort_period_start, cohort_period_end, weeks_ahead=8)

PROPOSITION_KPIS byte-for-byte:
    IMPRESSIONS               -- total times shown
    TAKE_UPS                  -- total customer accepts
    TAKE_UP_RATE_PCT          -- take_ups / impressions
    REVENUE_KES               -- total revenue attributable
    AVG_REVENUE_PER_TAKE_UP   -- revenue / take_ups
    ATTRITION_COUNT           -- customers who left after take-up

ATTRITION_REASONS byte-for-byte:
    PRICING                  -- left due to price
    SERVICE                  -- service quality issue
    COMPETITIVE              -- moved to competitor
    LIFE_EVENT               -- life event change (death, relocation, etc.)
    UNKNOWN                  -- attrition observed without surfaced reason

NPS_RANGE: 0-10 inclusive (per industry standard)

Honesty rules:
    Rule 1: KPIs return None when divisor is zero (avoid fabricated 0%)
    Rule 6: invalid attrition_reason rejected
    Rule 4: actor mandatory on every recording
    Rule 1: cohort_analysis returns reason="empty_cohort" rather than
            fabricated retention curves

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.propositions_catalog import PropositionsCatalogEngine
from utils.propositions_orchestration import PropositionOrchestrationEngine

getcontext().prec = 28


PROPOSITION_KPIS: Tuple[str, ...] = (
    "IMPRESSIONS", "TAKE_UPS", "TAKE_UP_RATE_PCT",
    "REVENUE_KES", "AVG_REVENUE_PER_TAKE_UP", "ATTRITION_COUNT",
)

ATTRITION_REASONS: Tuple[str, ...] = (
    "PRICING", "SERVICE", "COMPETITIVE", "LIFE_EVENT", "UNKNOWN",
)


class PropositionAnalyticsEngine:
    """Per-proposition KPI computation + cohort analysis."""

    def __init__(
        self,
        catalog: Optional[PropositionsCatalogEngine] = None,
        orchestration: Optional[PropositionOrchestrationEngine] = None,
        take_ups_path: Optional[Path] = None,
        attritions_path: Optional[Path] = None,
        revenues_path: Optional[Path] = None,
        satisfactions_path: Optional[Path] = None,
    ):
        self.catalog = catalog or PropositionsCatalogEngine()
        self.orchestration = orchestration or PropositionOrchestrationEngine(
            catalog=self.catalog,
        )
        base = Path(__file__).parent.parent / "data"
        self.take_ups_path = take_ups_path or base / "proposition_take_ups.json"
        self.attritions_path = attritions_path or base / "proposition_attritions.json"
        self.revenues_path = revenues_path or base / "proposition_revenues.json"
        self.satisfactions_path = satisfactions_path or base / "proposition_satisfactions.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    def record_take_up(
        self,
        prop_id: str,
        customer_id: str,
        channel: str,
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if not prop_id or not customer_id:
            return {"recorded": False, "error": "prop_and_customer_required"}
        records = self._load(self.take_ups_path,
                                "proposition_take_ups", ("take_up_id",))
        # Reject duplicate (prop, customer)
        if any(r.get("proposition_id") == prop_id
                 and r.get("customer_id") == customer_id for r in records):
            return {"recorded": False, "error": "already_taken_up"}
        take_up_id = (f"TUP-{prop_id}-{customer_id}-"
                          f"{int(datetime.utcnow().timestamp())}")
        records.append({
            "take_up_id": take_up_id,
            "proposition_id": prop_id,
            "customer_id": customer_id,
            "channel": channel,
            "actor": actor,
            "taken_up_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.take_ups_path, records,
                          "proposition_take_ups", "take_up_id")
        return {"recorded": ok, "take_up_id": take_up_id}

    def record_attrition(
        self,
        prop_id: str,
        customer_id: str,
        reason: str,
        actor: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if reason not in ATTRITION_REASONS:
            return {
                "recorded": False,
                "error": f"invalid_reason:{reason}",
                "valid_reasons": list(ATTRITION_REASONS),
            }
        records = self._load(self.attritions_path,
                                "proposition_attritions", ("attrition_id",))
        attrition_id = (f"ATR-{prop_id}-{customer_id}-"
                            f"{int(datetime.utcnow().timestamp())}")
        records.append({
            "attrition_id": attrition_id,
            "proposition_id": prop_id,
            "customer_id": customer_id,
            "reason": reason,
            "notes": notes,
            "actor": actor,
            "attrited_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.attritions_path, records,
                          "proposition_attritions", "attrition_id")
        return {"recorded": ok, "attrition_id": attrition_id}

    def record_revenue(
        self,
        prop_id: str,
        customer_id: str,
        amount_kes: Decimal,
        actor: str,
        revenue_type: str = "RECURRING",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        try:
            amt = Decimal(str(amount_kes))
            if amt < 0:
                return {"recorded": False, "error": "amount_negative"}
        except (ValueError, TypeError):
            return {"recorded": False, "error": "invalid_amount"}
        records = self._load(self.revenues_path,
                                "proposition_revenues", ("revenue_id",))
        revenue_id = (f"REV-{prop_id}-{customer_id}-"
                          f"{int(datetime.utcnow().timestamp())}")
        records.append({
            "revenue_id": revenue_id,
            "proposition_id": prop_id,
            "customer_id": customer_id,
            "amount_kes": str(amt.quantize(Decimal("0.01"))),
            "revenue_type": revenue_type,
            "actor": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.revenues_path, records,
                          "proposition_revenues", "revenue_id")
        return {"recorded": ok, "revenue_id": revenue_id}

    def record_satisfaction(
        self,
        prop_id: str,
        customer_id: str,
        nps_score: int,
        actor: str,
        comment: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        try:
            n = int(nps_score)
        except (ValueError, TypeError):
            return {"recorded": False, "error": "nps_not_integer"}
        if n < 0 or n > 10:
            return {"recorded": False, "error": "nps_out_of_0_10"}

        records = self._load(self.satisfactions_path,
                                "proposition_satisfactions",
                                ("satisfaction_id",))
        sat_id = (f"SAT-{prop_id}-{customer_id}-"
                      f"{int(datetime.utcnow().timestamp())}")
        records.append({
            "satisfaction_id": sat_id,
            "proposition_id": prop_id,
            "customer_id": customer_id,
            "nps_score": n,
            "comment": comment,
            "actor": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.satisfactions_path, records,
                          "proposition_satisfactions", "satisfaction_id")
        return {"recorded": ok, "satisfaction_id": sat_id}

    # ── Analytics ──────────────────────────────────────────────────

    def proposition_kpis(
        self,
        prop_id: str,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        # Impressions (from orchestration)
        impressions = self.orchestration._load_impressions()
        impr_count = sum(
            1 for i in impressions
            if i.get("proposition_id") == prop_id
            and period_start <= i.get("shown_at", "") <= period_end
        )

        # Take-ups
        take_ups = self._load(self.take_ups_path,
                                  "proposition_take_ups", ("take_up_id",))
        take_up_count = sum(
            1 for t in take_ups
            if t.get("proposition_id") == prop_id
            and period_start <= t.get("taken_up_at", "") <= period_end
        )

        # Revenue
        revenues = self._load(self.revenues_path,
                                  "proposition_revenues", ("revenue_id",))
        total_rev = Decimal("0")
        for r in revenues:
            if (r.get("proposition_id") == prop_id
                    and period_start <= r.get("recorded_at", "") <= period_end):
                try:
                    total_rev += Decimal(r["amount_kes"])
                except (ValueError, TypeError, KeyError):
                    continue

        # Attrition
        attritions = self._load(self.attritions_path,
                                     "proposition_attritions", ("attrition_id",))
        attrition_count = sum(
            1 for a in attritions
            if a.get("proposition_id") == prop_id
            and period_start <= a.get("attrited_at", "") <= period_end
        )

        # NPS
        sats = self._load(self.satisfactions_path,
                              "proposition_satisfactions", ("satisfaction_id",))
        period_scores = [
            int(s["nps_score"]) for s in sats
            if s.get("proposition_id") == prop_id
            and period_start <= s.get("recorded_at", "") <= period_end
        ]
        nps_value = None
        if period_scores:
            n = len(period_scores)
            promoters = sum(1 for x in period_scores if x >= 9)
            detractors = sum(1 for x in period_scores if x <= 6)
            nps_value = round(((promoters - detractors) / n) * 100, 2)

        # Compute derived KPIs honestly
        take_up_rate_pct = None
        if impr_count > 0:
            take_up_rate_pct = str(
                (Decimal(take_up_count) / Decimal(impr_count) *
                  Decimal("100")).quantize(Decimal("0.01"))
            )

        avg_rev_per_take_up = None
        if take_up_count > 0:
            avg_rev_per_take_up = str(
                (total_rev / Decimal(take_up_count)).quantize(Decimal("0.01"))
            )

        return {
            "proposition_id": prop_id,
            "period_start": period_start,
            "period_end": period_end,
            "IMPRESSIONS": impr_count,
            "TAKE_UPS": take_up_count,
            "TAKE_UP_RATE_PCT": take_up_rate_pct,
            "REVENUE_KES": str(total_rev.quantize(Decimal("0.01"))),
            "AVG_REVENUE_PER_TAKE_UP": avg_rev_per_take_up,
            "ATTRITION_COUNT": attrition_count,
            "NPS": nps_value,
            "respondent_count": len(period_scores),
        }

    def cohort_analysis(
        self,
        prop_id: str,
        cohort_period_start: str,
        cohort_period_end: str,
        weeks_ahead: int = 8,
    ) -> Dict[str, Any]:
        """Cohort retention: customers who took up in window + their N-week
        active rate based on revenue records."""
        if weeks_ahead <= 0:
            return {"reason": "weeks_ahead_must_be_positive"}

        take_ups = self._load(self.take_ups_path,
                                  "proposition_take_ups", ("take_up_id",))
        cohort = [
            t for t in take_ups
            if t.get("proposition_id") == prop_id
            and cohort_period_start <= t.get("taken_up_at", "") <= cohort_period_end
        ]
        if not cohort:
            return {
                "proposition_id": prop_id,
                "cohort_size": 0,
                "weeks": [],
                "reason": "empty_cohort",
            }

        # Per-customer first take-up time
        first_takeup: Dict[str, str] = {}
        for t in cohort:
            cid = t["customer_id"]
            ts = t.get("taken_up_at", "")
            if cid not in first_takeup or ts < first_takeup[cid]:
                first_takeup[cid] = ts

        # For each customer, identify which week buckets had revenue
        revenues = self._load(self.revenues_path,
                                  "proposition_revenues", ("revenue_id",))
        cust_active_weeks: Dict[str, set] = defaultdict(set)
        for r in revenues:
            if r.get("proposition_id") != prop_id:
                continue
            cid = r.get("customer_id")
            if cid not in first_takeup:
                continue
            try:
                t = datetime.fromisoformat(r["recorded_at"].replace("Z", ""))
                start = datetime.fromisoformat(
                    first_takeup[cid].replace("Z", "")
                )
            except (ValueError, KeyError, AttributeError):
                continue
            week_idx = (t - start).days // 7
            if 0 <= week_idx < weeks_ahead:
                cust_active_weeks[cid].add(week_idx)

        # Aggregate
        week_counts = [0] * weeks_ahead
        for cid, weeks in cust_active_weeks.items():
            for w in weeks:
                week_counts[w] += 1

        cohort_size = len(first_takeup)
        weeks_out = []
        for w in range(weeks_ahead):
            pct = (Decimal(week_counts[w]) / Decimal(cohort_size) *
                     Decimal("100")).quantize(Decimal("0.01"))
            weeks_out.append({
                "week_index": w,
                "active_count": week_counts[w],
                "active_pct": str(pct),
            })

        return {
            "proposition_id": prop_id,
            "cohort_period_start": cohort_period_start,
            "cohort_period_end": cohort_period_end,
            "cohort_size": cohort_size,
            "weeks": weeks_out,
        }


def _self_test() -> None:
    import tempfile
    from utils.propositions_catalog import APPROVAL_LEVELS

    assert "TAKE_UP_RATE_PCT" in PROPOSITION_KPIS
    assert "PRICING" in ATTRITION_REASONS

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = PropositionsCatalogEngine(
            propositions_path=Path(tmpdir) / "p.json",
            approvals_path=Path(tmpdir) / "a.json",
            reviews_path=Path(tmpdir) / "r.json",
        )
        orch = PropositionOrchestrationEngine(
            catalog=catalog,
            impressions_path=Path(tmpdir) / "imp.json",
        )
        engine = PropositionAnalyticsEngine(
            catalog=catalog, orchestration=orch,
            take_ups_path=Path(tmpdir) / "tu.json",
            attritions_path=Path(tmpdir) / "atr.json",
            revenues_path=Path(tmpdir) / "rev.json",
            satisfactions_path=Path(tmpdir) / "sat.json",
        )

        # Setup proposition
        catalog.register_proposition(
            {"proposition_id": "PROP-A", "name": "A",
             "owner_role": "h"},
            actor="x",
        )

        # Test 1: record take-up
        r = engine.record_take_up(
            "PROP-A", "C-1", "MOBILE_APP", actor="orchestrator",
        )
        assert r["recorded"]

        # Test 2: duplicate take-up rejected
        r = engine.record_take_up(
            "PROP-A", "C-1", "MOBILE_APP", actor="orchestrator",
        )
        assert not r["recorded"]
        assert r["error"] == "already_taken_up"

        # Test 3: invalid attrition reason
        r = engine.record_attrition(
            "PROP-A", "C-1", "INVALID", actor="x",
        )
        assert not r["recorded"]

        # Test 4: valid attrition
        r = engine.record_attrition(
            "PROP-A", "C-1", "PRICING", actor="rm",
        )
        assert r["recorded"]

        # Test 5: invalid revenue (negative)
        r = engine.record_revenue(
            "PROP-A", "C-1", Decimal("-100"), actor="finance",
        )
        assert not r["recorded"]

        # Test 6: valid revenue
        r = engine.record_revenue(
            "PROP-A", "C-1", Decimal("500"), actor="finance",
        )
        assert r["recorded"]

        # Test 7: NPS 0-10 enforced
        r = engine.record_satisfaction(
            "PROP-A", "C-1", 15, actor="rm",
        )
        assert not r["recorded"]
        r = engine.record_satisfaction(
            "PROP-A", "C-1", 9, actor="rm",
        )
        assert r["recorded"]

        # Test 8: KPIs computation
        # Add impressions to orchestration
        orch.record_impression("C-1", "PROP-A", "MOBILE_APP", actor="x")
        orch.record_impression("C-2", "PROP-A", "MOBILE_APP", actor="x")
        engine.record_take_up("PROP-A", "C-2", "MOBILE_APP", actor="x")
        engine.record_revenue("PROP-A", "C-2", Decimal("750"), actor="x")
        engine.record_satisfaction("PROP-A", "C-2", 4, actor="x")

        kpis = engine.proposition_kpis(
            "PROP-A", "2026-01-01", "2027-12-31",
        )
        assert kpis["IMPRESSIONS"] == 2
        assert kpis["TAKE_UPS"] == 2
        # take_up_rate = 2/2 = 100.00
        assert kpis["TAKE_UP_RATE_PCT"] == "100.00"
        # Revenue = 500 + 750 = 1250
        assert Decimal(kpis["REVENUE_KES"]) == Decimal("1250.00")
        # avg = 1250/2 = 625
        assert Decimal(kpis["AVG_REVENUE_PER_TAKE_UP"]) == Decimal("625.00")
        # 1 attrition
        assert kpis["ATTRITION_COUNT"] == 1
        # NPS: 9 + 4 → promoter + detractor → 0
        assert kpis["NPS"] == 0

        # Test 9: zero impressions → take_up_rate None (Rule 1)
        catalog.register_proposition(
            {"proposition_id": "PROP-EMPTY", "name": "Z", "owner_role": "h"},
            actor="x",
        )
        kpis = engine.proposition_kpis(
            "PROP-EMPTY", "2026-01-01", "2026-12-31",
        )
        assert kpis["TAKE_UP_RATE_PCT"] is None
        assert kpis["AVG_REVENUE_PER_TAKE_UP"] is None
        # Revenue = 0 (not None), since sum of zero records is zero
        assert Decimal(kpis["REVENUE_KES"]) == Decimal("0.00")

        # Test 10: cohort_analysis empty
        c = engine.cohort_analysis(
            "PROP-EMPTY", "2026-01-01", "2026-12-31", weeks_ahead=4,
        )
        assert c["cohort_size"] == 0
        assert c["reason"] == "empty_cohort"

        # Test 11: cohort_analysis populated
        c = engine.cohort_analysis(
            "PROP-A", "2026-01-01", "2027-12-31", weeks_ahead=4,
        )
        assert c["cohort_size"] >= 1

        # Test 12: invalid weeks_ahead
        c = engine.cohort_analysis("PROP-A", "2026", "2027", weeks_ahead=0)
        assert "must_be_positive" in c["reason"]

    print("  ✅ propositions_analytics self-test PASS")


if __name__ == "__main__":
    _self_test()
