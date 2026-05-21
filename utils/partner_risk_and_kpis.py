"""
================================================================================
A2Z MIS 360 — Standards #377 + #378: Partner Risk + Ecosystem KPIs
================================================================================

Risk classification: Cat C (third-party risk monitoring; IIA 2026)
                     + Cat B (deterministic ecosystem KPIs)

Combined module:
    #377: Per-partner risk monitoring (financial health, regulatory
          standing, cyber posture, customer complaints) with auto-alert
          on degradation. References vendor_risk engine pattern.
    #378: Aggregate partnership KPIs — ecosystem revenue, share of new
          acquisitions, customer-LTV from partners, NPS of partner-
          acquired customers.

Public API (#377 — Risk Management):
    record_risk_indicator(partner_id, dimension, score, actor)
    risk_assessment(partner_id) -> {composite, tier, indicators}
    detect_degradation(partner_id, lookback_periods=3) -> {alerts}
    risk_dashboard() -> all partners ranked by composite

Public API (#378 — KPIs):
    ecosystem_revenue_total(period_start, period_end)
    share_of_new_acquisitions(period_start, period_end) -> {pct, partner_acquired}
    customer_ltv_from_partners(partner_id=None) -> aggregate or per-partner
    nps_of_partner_acquired_customers(partner_id=None)

RISK_DIMENSIONS byte-for-byte (Continuation.docx #377 + IIA 2026 third-party):
    FINANCIAL_HEALTH    -- balance sheet + liquidity score (0-100)
    REGULATORY_STANDING -- regulatory penalties / actions (0-100, higher better)
    CYBER_POSTURE       -- security audit + incident score (0-100)
    CUSTOMER_COMPLAINTS -- complaint volume + resolution score (0-100)

RISK_DIMENSION_WEIGHTS byte-for-byte (sum=100):
    FINANCIAL_HEALTH    = 30
    REGULATORY_STANDING = 30
    CYBER_POSTURE       = 25
    CUSTOMER_COMPLAINTS = 15

RISK_ALERT_LEVELS byte-for-byte:
    GREEN   -- composite ≥ 80; routine monitoring
    AMBER   -- composite ≥ 60; quarterly enhanced review
    RED     -- composite < 60; immediate investigation
    CRITICAL -- any single dimension < 40 OR composite < 40

DEGRADATION_DROP_THRESHOLD = Decimal("15") -- 15-point drop triggers alert

Honesty rules:
    Rule 1: composite = None when any dimension missing
    Rule 6: invalid dimension / score range rejected
    Rule 4: actor mandatory on records

================================================================================
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.partner_master import PartnerMasterEngine
from utils.partner_leads_commissions import (
    LeadTrackingEngine, CommissionEngine,
)

getcontext().prec = 28


RISK_DIMENSIONS: Tuple[str, ...] = (
    "FINANCIAL_HEALTH",
    "REGULATORY_STANDING",
    "CYBER_POSTURE",
    "CUSTOMER_COMPLAINTS",
)

RISK_DIMENSION_WEIGHTS: Dict[str, Decimal] = {
    "FINANCIAL_HEALTH":    Decimal("30"),
    "REGULATORY_STANDING": Decimal("30"),
    "CYBER_POSTURE":       Decimal("25"),
    "CUSTOMER_COMPLAINTS": Decimal("15"),
}

RISK_ALERT_LEVELS: Tuple[str, ...] = (
    "GREEN", "AMBER", "RED", "CRITICAL",
)

ALERT_GREEN_THRESHOLD:    Decimal = Decimal("80")
ALERT_AMBER_THRESHOLD:    Decimal = Decimal("60")
ALERT_CRITICAL_THRESHOLD: Decimal = Decimal("40")

DEGRADATION_DROP_THRESHOLD: Decimal = Decimal("15")


def classify_alert_level(
    composite: Optional[Decimal],
    dimension_scores: Optional[Dict[str, Decimal]] = None,
) -> Optional[str]:
    """Classify alert level. Returns None when composite is None."""
    if composite is None:
        return None
    # CRITICAL trumps composite tier when any dimension < 40
    if dimension_scores:
        if any(s < ALERT_CRITICAL_THRESHOLD for s in dimension_scores.values()):
            return "CRITICAL"
    if composite < ALERT_CRITICAL_THRESHOLD:
        return "CRITICAL"
    if composite < ALERT_AMBER_THRESHOLD:
        return "RED"
    if composite < ALERT_GREEN_THRESHOLD:
        return "AMBER"
    return "GREEN"


# ────────────────────────────────────────────────────────────────────
# Combined engine
# ────────────────────────────────────────────────────────────────────

class PartnerRiskAndKpisEngine:
    """Partner risk monitoring (#377) + ecosystem KPIs (#378)."""

    def __init__(
        self,
        risk_path: Optional[Path] = None,
        master: Optional[PartnerMasterEngine] = None,
        leads: Optional[LeadTrackingEngine] = None,
        commissions: Optional[CommissionEngine] = None,
    ):
        self.risk_path = (
            risk_path
            if risk_path is not None
            else Path(__file__).parent.parent / "data" / "partner_risk.json"
        )
        self.master = master or PartnerMasterEngine()
        self.leads = leads or LeadTrackingEngine()
        self.commissions = commissions or CommissionEngine(lead_engine=self.leads)

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.risk_path,
                table="partner_risk",
                index_cols=("partner_id", "period", "dimension"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.risk_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.risk_path,
                data=records,
                table="partner_risk",
                pk_col="partner_id")
            return True
        except Exception:
            return False

    # ── #377 Risk indicators ───────────────────────────────────────

    def record_risk_indicator(
        self,
        partner_id: str,
        period: str,
        dimension: str,
        score: Decimal,
        actor: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Record a risk dimension score."""
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if dimension not in RISK_DIMENSIONS:
            return {
                "recorded": False,
                "error": f"invalid_dimension:{dimension}",
                "valid_dimensions": list(RISK_DIMENSIONS),
            }

        try:
            v = Decimal(str(score))
        except (ValueError, TypeError):
            return {"recorded": False, "error": "score_not_decimal"}

        if v < 0 or v > 100:
            return {
                "recorded": False,
                "error": f"score_out_of_0_100:{v}",
            }

        records = self._load()
        # Replace existing
        for r in records:
            if (r.get("partner_id") == partner_id
                    and r.get("period") == period
                    and r.get("dimension") == dimension):
                r["score"] = str(v)
                r["actor"] = actor
                r["notes"] = notes
                r["recorded_at"] = datetime.utcnow().isoformat()
                ok = self._save(records)
                return {"recorded": ok, "replaced": True}

        records.append({
            "partner_id": partner_id,
            "period": period,
            "dimension": dimension,
            "score": str(v),
            "actor": actor,
            "notes": notes,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(records)
        return {"recorded": ok, "replaced": False}

    def risk_assessment(
        self,
        partner_id: str,
        period: str,
    ) -> Dict[str, Any]:
        """Composite risk assessment for partner-period."""
        records = self._load()
        period_recs = [
            r for r in records
            if r.get("partner_id") == partner_id and r.get("period") == period
        ]

        dim_scores: Dict[str, Decimal] = {}
        for r in period_recs:
            d = r.get("dimension")
            if d in RISK_DIMENSIONS:
                try:
                    dim_scores[d] = Decimal(str(r["score"]))
                except (ValueError, TypeError):
                    continue

        # Rule 1: missing dimensions → composite=None
        missing = [d for d in RISK_DIMENSIONS if d not in dim_scores]
        if missing:
            return {
                "partner_id": partner_id,
                "period": period,
                "composite": None,
                "tier": None,
                "missing_dimensions": missing,
                "dimensions": {d: str(dim_scores[d]) for d in dim_scores},
                "reason": "missing_dimensions",
            }

        composite = Decimal("0")
        for d in RISK_DIMENSIONS:
            composite += dim_scores[d] * RISK_DIMENSION_WEIGHTS[d] / Decimal("100")
        composite = composite.quantize(Decimal("0.01"))
        tier = classify_alert_level(composite, dim_scores)

        return {
            "partner_id": partner_id,
            "period": period,
            "composite": str(composite),
            "tier": tier,
            "dimensions": {d: str(v) for d, v in dim_scores.items()},
            "weights": {d: str(w) for d, w in RISK_DIMENSION_WEIGHTS.items()},
        }

    def detect_degradation(
        self,
        partner_id: str,
        periods: List[str],
    ) -> Dict[str, Any]:
        """
        Detect degradation across consecutive periods. Alert when
        composite drops by ≥ DEGRADATION_DROP_THRESHOLD.

        Rule 1: alerts list empty when fewer than 2 complete assessments.
        """
        assessments = []
        for p in periods:
            a = self.risk_assessment(partner_id, p)
            if a.get("composite") is not None:
                assessments.append({
                    "period": p,
                    "composite": Decimal(a["composite"]),
                    "tier": a["tier"],
                })

        if len(assessments) < 2:
            return {
                "partner_id": partner_id,
                "alerts": [],
                "complete_assessments": len(assessments),
                "reason": "insufficient_consecutive_assessments",
            }

        alerts = []
        for i in range(1, len(assessments)):
            prev = assessments[i - 1]
            curr = assessments[i]
            drop = prev["composite"] - curr["composite"]
            if drop >= DEGRADATION_DROP_THRESHOLD:
                alerts.append({
                    "period": curr["period"],
                    "previous_period": prev["period"],
                    "drop_points": str(drop.quantize(Decimal("0.01"))),
                    "from_composite": str(prev["composite"]),
                    "to_composite": str(curr["composite"]),
                    "from_tier": prev["tier"],
                    "to_tier": curr["tier"],
                })

        return {
            "partner_id": partner_id,
            "alerts": alerts,
            "complete_assessments": len(assessments),
            "threshold_points": str(DEGRADATION_DROP_THRESHOLD),
        }

    def risk_dashboard(self, period: str) -> List[Dict[str, Any]]:
        """All partners ranked by composite (descending)."""
        records = self._load()
        partner_ids = sorted({
            r["partner_id"] for r in records if r.get("period") == period
        })
        out = []
        for pid in partner_ids:
            a = self.risk_assessment(pid, period)
            if a.get("composite") is not None:
                out.append(a)
        out.sort(key=lambda x: Decimal(x["composite"]), reverse=True)
        return out

    # ── #378 Ecosystem KPIs ────────────────────────────────────────

    def ecosystem_revenue_total(
        self,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Total revenue attributed to all partners in period."""
        leads_records = self.leads._load()
        won = [
            r for r in leads_records
            if r.get("state") == "WON"
            and r.get("closed_date", "") >= period_start
            and r.get("closed_date", "") <= period_end
        ]

        total = Decimal("0")
        per_partner = defaultdict(lambda: Decimal("0"))
        for r in won:
            try:
                rev = Decimal(str(r.get("actual_revenue_kes") or "0"))
            except (ValueError, TypeError):
                continue
            total += rev
            per_partner[r.get("partner_id", "UNKNOWN")] += rev

        return {
            "period_start": period_start,
            "period_end": period_end,
            "total_kes": str(total.quantize(Decimal("0.01"))),
            "won_lead_count": len(won),
            "by_partner_kes": {
                k: str(v.quantize(Decimal("0.01")))
                for k, v in per_partner.items()
            },
        }

    def share_of_new_acquisitions(
        self,
        period_start: str,
        period_end: str,
        total_new_customers: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Partner-acquired share of new customers.

        Rule 6: total_new_customers must be passed in (cannot be inferred
        from leads engine alone — leads engine only has partner-sourced
        leads). When None, surface explicit reason.
        """
        leads_records = self.leads._load()
        partner_acquired = sum(
            1 for r in leads_records
            if r.get("state") == "WON"
            and r.get("closed_date", "") >= period_start
            and r.get("closed_date", "") <= period_end
        )

        if total_new_customers is None:
            return {
                "period_start": period_start,
                "period_end": period_end,
                "partner_acquired_count": partner_acquired,
                "total_new_customers": None,
                "share_pct": None,
                "reason": "total_new_customers_required_for_share_pct",
            }

        if total_new_customers <= 0:
            return {
                "period_start": period_start,
                "period_end": period_end,
                "partner_acquired_count": partner_acquired,
                "total_new_customers": total_new_customers,
                "share_pct": None,
                "reason": "total_new_customers_not_positive",
            }

        pct = (Decimal(partner_acquired) / Decimal(total_new_customers) * Decimal("100")).quantize(Decimal("0.01"))
        return {
            "period_start": period_start,
            "period_end": period_end,
            "partner_acquired_count": partner_acquired,
            "total_new_customers": total_new_customers,
            "share_pct": str(pct),
        }

    def customer_ltv_from_partners(
        self,
        partner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate LTV (using actual_revenue_kes as LTV proxy from leads).

        Rule 1: ltv_per_customer = None when zero customers.
        """
        leads_records = self.leads._load()
        if partner_id:
            won = [r for r in leads_records
                     if r.get("state") == "WON" and r.get("partner_id") == partner_id]
        else:
            won = [r for r in leads_records if r.get("state") == "WON"]

        total_ltv = Decimal("0")
        for r in won:
            try:
                total_ltv += Decimal(str(r.get("actual_revenue_kes") or "0"))
            except (ValueError, TypeError):
                continue

        n = len(won)
        if n == 0:
            return {
                "partner_id": partner_id,
                "customer_count": 0,
                "total_ltv_kes": "0",
                "ltv_per_customer_kes": None,
                "reason": "no_customers_acquired",
            }

        ltv_per = (total_ltv / Decimal(n)).quantize(Decimal("0.01"))
        return {
            "partner_id": partner_id,
            "customer_count": n,
            "total_ltv_kes": str(total_ltv.quantize(Decimal("0.01"))),
            "ltv_per_customer_kes": str(ltv_per),
        }

    def nps_of_partner_acquired_customers(
        self,
        partner_id: Optional[str] = None,
        nps_data: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        NPS aggregate. Requires nps_data (lead_id → NPS score 0-10) since
        leads engine doesn't store NPS surveys.

        Rule 6: nps_data missing → explicit reason; never silently zero.
        """
        if nps_data is None:
            return {
                "partner_id": partner_id,
                "nps": None,
                "reason": "nps_data_not_provided",
            }

        leads_records = self.leads._load()
        won = [
            r for r in leads_records
            if r.get("state") == "WON"
            and (partner_id is None or r.get("partner_id") == partner_id)
        ]
        won_ids = {r["lead_id"] for r in won}

        scored = {k: v for k, v in nps_data.items() if k in won_ids}
        if not scored:
            return {
                "partner_id": partner_id,
                "nps": None,
                "reason": "no_overlapping_nps_data",
            }

        promoters = sum(1 for s in scored.values() if s >= 9)
        detractors = sum(1 for s in scored.values() if s <= 6)
        n = len(scored)
        nps = ((promoters - detractors) / n) * 100

        return {
            "partner_id": partner_id,
            "respondent_count": n,
            "promoters": promoters,
            "detractors": detractors,
            "passives": n - promoters - detractors,
            "nps": round(nps, 2),
        }


def _self_test() -> None:
    import tempfile

    # Weight sum check
    assert sum(RISK_DIMENSION_WEIGHTS.values()) == Decimal("100")

    # Alert classification
    assert classify_alert_level(Decimal("85")) == "GREEN"
    assert classify_alert_level(Decimal("70")) == "AMBER"
    assert classify_alert_level(Decimal("55")) == "RED"
    assert classify_alert_level(Decimal("35")) == "CRITICAL"
    assert classify_alert_level(None) is None

    # Single dimension < 40 forces CRITICAL even with high composite
    assert classify_alert_level(
        Decimal("75"),
        {"FINANCIAL_HEALTH": Decimal("85"),
         "REGULATORY_STANDING": Decimal("85"),
         "CYBER_POSTURE": Decimal("30"),  # critical dimension
         "CUSTOMER_COMPLAINTS": Decimal("85")},
    ) == "CRITICAL"

    with tempfile.TemporaryDirectory() as tmpdir:
        master = PartnerMasterEngine(partners_path=Path(tmpdir) / "p.json")
        leads = LeadTrackingEngine(leads_path=Path(tmpdir) / "l.json")
        commissions = CommissionEngine(
            commissions_path=Path(tmpdir) / "c.json", lead_engine=leads
        )
        engine = PartnerRiskAndKpisEngine(
            risk_path=Path(tmpdir) / "r.json",
            master=master, leads=leads, commissions=commissions,
        )

        # === Risk tests ===

        # Test 1: record all 4 dimensions
        for d, v in [("FINANCIAL_HEALTH", "85"),
                       ("REGULATORY_STANDING", "90"),
                       ("CYBER_POSTURE", "75"),
                       ("CUSTOMER_COMPLAINTS", "80")]:
            engine.record_risk_indicator(
                "P-001", "2026-Q1", d, Decimal(v), actor="risk_team"
            )

        # Test 2: risk_assessment composite
        a = engine.risk_assessment("P-001", "2026-Q1")
        assert a["composite"] is not None
        # 85*0.30 + 90*0.30 + 75*0.25 + 80*0.15
        # = 25.5 + 27 + 18.75 + 12 = 83.25 → GREEN
        assert abs(Decimal(a["composite"]) - Decimal("83.25")) < Decimal("0.05")
        assert a["tier"] == "GREEN"

        # Test 3: missing dimension → composite None
        engine.record_risk_indicator(
            "P-002", "2026-Q1", "FINANCIAL_HEALTH",
            Decimal("70"), actor="risk_team"
        )
        a = engine.risk_assessment("P-002", "2026-Q1")
        assert a["composite"] is None
        assert len(a["missing_dimensions"]) == 3

        # Test 4: invalid dimension rejected
        r = engine.record_risk_indicator(
            "P-003", "2026-Q1", "INVALID", Decimal("80"), actor="risk_team"
        )
        assert not r["recorded"]

        # Test 5: out-of-range rejected
        r = engine.record_risk_indicator(
            "P-003", "2026-Q1", "CYBER_POSTURE",
            Decimal("150"), actor="risk_team"
        )
        assert not r["recorded"]

        # Test 6: degradation detection
        # Q2 — drop CYBER_POSTURE significantly
        for d, v in [("FINANCIAL_HEALTH", "82"),
                       ("REGULATORY_STANDING", "85"),
                       ("CYBER_POSTURE", "30"),  # major drop
                       ("CUSTOMER_COMPLAINTS", "70")]:
            engine.record_risk_indicator(
                "P-001", "2026-Q2", d, Decimal(v), actor="risk_team"
            )

        deg = engine.detect_degradation("P-001", ["2026-Q1", "2026-Q2"])
        # Q1 composite = 83.25; Q2 composite ≈
        # 82*0.30 + 85*0.30 + 30*0.25 + 70*0.15 = 24.6 + 25.5 + 7.5 + 10.5 = 68.1
        # Drop = 83.25 - 68.1 = 15.15 → triggers (≥15)
        assert len(deg["alerts"]) == 1
        assert deg["alerts"][0]["from_tier"] == "GREEN"
        # Q2 with cyber_posture < 40 → CRITICAL
        assert deg["alerts"][0]["to_tier"] == "CRITICAL"

        # Test 7: insufficient assessments
        deg2 = engine.detect_degradation("P-002", ["2026-Q1"])
        assert deg2["alerts"] == []
        assert deg2["reason"] == "insufficient_consecutive_assessments"

        # Test 8: risk_dashboard
        dash = engine.risk_dashboard("2026-Q1")
        assert len(dash) == 1  # only P-001 has complete assessment
        assert dash[0]["partner_id"] == "P-001"

        # === KPI tests ===

        # Seed: 1 WON lead worth 1M for P-001
        leads.submit_lead(
            "P-001",
            {"lead_id": "L-001", "customer_name": "X",
             "submitted_date": "2026-04-01"},
            actor="rm",
        )
        leads.transition_lead_state("L-001", "QUALIFIED", "rm", "ok")
        leads.transition_lead_state("L-001", "IN_PIPELINE", "rm", "selling")
        leads.transition_lead_state(
            "L-001", "WON", "rm", "closed",
            actual_revenue_kes=Decimal("1000000"),
        )

        # Test 9: ecosystem_revenue_total
        rev = engine.ecosystem_revenue_total("2026-04-01", "2026-12-31")
        assert Decimal(rev["total_kes"]) == Decimal("1000000.00")
        assert rev["won_lead_count"] == 1

        # Test 10: share_of_new_acquisitions — total provided
        share = engine.share_of_new_acquisitions(
            "2026-04-01", "2026-12-31", total_new_customers=10
        )
        assert share["share_pct"] == "10.00"
        assert share["partner_acquired_count"] == 1

        # Test 11: Rule 6 — total missing → explicit reason
        share_missing = engine.share_of_new_acquisitions(
            "2026-04-01", "2026-12-31"
        )
        assert share_missing["share_pct"] is None
        assert "required" in share_missing["reason"]

        # Test 12: customer_ltv_from_partners
        ltv = engine.customer_ltv_from_partners("P-001")
        assert ltv["customer_count"] == 1
        assert Decimal(ltv["ltv_per_customer_kes"]) == Decimal("1000000.00")

        # Test 13: Rule 1 — no customers → ltv None
        ltv_empty = engine.customer_ltv_from_partners("P-NONEXISTENT")
        assert ltv_empty["ltv_per_customer_kes"] is None

        # Test 14: NPS without data
        nps_none = engine.nps_of_partner_acquired_customers("P-001")
        assert nps_none["nps"] is None
        assert nps_none["reason"] == "nps_data_not_provided"

        # Test 15: NPS with data
        nps = engine.nps_of_partner_acquired_customers(
            "P-001", nps_data={"L-001": 9}
        )
        assert nps["nps"] == 100.0  # 1 promoter / 1 = 100
        assert nps["promoters"] == 1

    print("  ✅ partner_risk_and_kpis self-test PASS")


if __name__ == "__main__":
    _self_test()
