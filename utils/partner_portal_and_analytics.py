"""
================================================================================
A2Z MIS 360 — Standards #374 + #375: Partner Portal API + Ecosystem Analytics
================================================================================

Risk classification: Cat C (security — partner-facing API contract)
                     + Cat B (deterministic analytics)

Combined module:
    #374: Partner Portal API contract — what a partner can read/write
          via their self-service portal. RBAC + scope contract; UI is
          downstream.
    #375: Ecosystem analytics — cross-partner aggregations (top
          performers, geographic + segment coverage, profitability).

Public API (#374 — Partner Portal):
    portal_can_read(partner_id, resource, target_partner_id) -> {allowed, reason}
    portal_can_write(partner_id, resource, target_partner_id) -> {allowed, reason}
    portal_dashboard_payload(partner_id) -> read-scoped data bundle
    portal_role_definition() -> frozen role config

Public API (#375 — Ecosystem Analytics):
    top_performers(period, n=10) -> ranked partners
    underperformers(period, threshold_score=45) -> at-risk partners
    geographic_coverage() -> {country: partner_count}
    segment_coverage() -> {segment: partner_count}
    profitability_by_partner(period) -> commission cost vs attributed revenue

PORTAL_RESOURCES byte-for-byte (#374):
    LEAD_SUBMIT          -- POST new lead
    LEAD_STATUS          -- GET own leads' status
    COMMISSION_STATEMENT -- GET own commission statements
    DOCUMENTS            -- GET shared documents (read-only)
    TRAINING_RESOURCES   -- GET training content
    OTHER_PARTNER_DATA   -- always DENY (cross-partner isolation)

PORTAL_PERMISSION_MATRIX (own_partner = portal user's own partner_id):
    LEAD_SUBMIT          -- read=DENY, write=OWN_PARTNER
    LEAD_STATUS          -- read=OWN_PARTNER, write=DENY
    COMMISSION_STATEMENT -- read=OWN_PARTNER, write=DENY
    DOCUMENTS            -- read=OWN_PARTNER, write=DENY
    TRAINING_RESOURCES   -- read=ALL, write=DENY  (training is broadly available)
    OTHER_PARTNER_DATA   -- read=DENY, write=DENY  (hard isolation)

Honesty rules:
    Rule 6: cross-partner access denied by default; unknown resource denied
    Rule 1: top_performers returns [] when no scorecards in period
            (NOT None)

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.partner_master import PartnerMasterEngine
from utils.partner_scorecard import PartnerScorecardEngine
from utils.partner_leads_commissions import (
    LeadTrackingEngine, CommissionEngine,
)

getcontext().prec = 28


# ────────────────────────────────────────────────────────────────────
# Portal API (#374) — byte-for-byte
# ────────────────────────────────────────────────────────────────────

PORTAL_ROLE_NAME: str = "PARTNER_PORTAL_USER"

PORTAL_RESOURCES: Tuple[str, ...] = (
    "LEAD_SUBMIT",
    "LEAD_STATUS",
    "COMMISSION_STATEMENT",
    "DOCUMENTS",
    "TRAINING_RESOURCES",
    "OTHER_PARTNER_DATA",
)

PORTAL_PERMISSION_MATRIX: Dict[str, Dict[str, str]] = {
    "LEAD_SUBMIT":          {"read": "DENY",         "write": "OWN_PARTNER"},
    "LEAD_STATUS":          {"read": "OWN_PARTNER", "write": "DENY"},
    "COMMISSION_STATEMENT": {"read": "OWN_PARTNER", "write": "DENY"},
    "DOCUMENTS":            {"read": "OWN_PARTNER", "write": "DENY"},
    "TRAINING_RESOURCES":   {"read": "ALL",          "write": "DENY"},
    "OTHER_PARTNER_DATA":   {"read": "DENY",         "write": "DENY"},
}


def portal_role_definition() -> Dict[str, Any]:
    return {
        "role_name": PORTAL_ROLE_NAME,
        "description": (
            "Partner-facing self-service portal user. Can submit leads, "
            "view own lead status, view own commission statements, "
            "access shared documents, and consume training resources. "
            "Cannot view any other partner's data."
        ),
        "permission_matrix": dict(PORTAL_PERMISSION_MATRIX),
        "scope": "PER_PARTNER",
        "data_isolation": "OWN_PARTNER_ONLY",
        "spec_ref": "Continuation.docx #374",
    }


def portal_can_read(
    portal_user_partner_id: str,
    resource: str,
    target_partner_id: str,
) -> Dict[str, Any]:
    if resource not in PORTAL_PERMISSION_MATRIX:
        return {"allowed": False, "reason": f"unknown_resource:{resource}"}
    rule = PORTAL_PERMISSION_MATRIX[resource].get("read", "DENY")
    if rule == "DENY":
        return {"allowed": False, "reason": "read_denied_by_matrix"}
    if rule == "ALL":
        return {"allowed": True, "reason": "training_open_to_all"}
    if rule == "OWN_PARTNER":
        if portal_user_partner_id == target_partner_id:
            return {"allowed": True, "reason": "own_partner"}
        return {
            "allowed": False,
            "reason": f"cross_partner_denied:{portal_user_partner_id}_vs_{target_partner_id}",
        }
    return {"allowed": False, "reason": f"unknown_rule:{rule}"}


def portal_can_write(
    portal_user_partner_id: str,
    resource: str,
    target_partner_id: str,
) -> Dict[str, Any]:
    if resource not in PORTAL_PERMISSION_MATRIX:
        return {"allowed": False, "reason": f"unknown_resource:{resource}"}
    rule = PORTAL_PERMISSION_MATRIX[resource].get("write", "DENY")
    if rule == "DENY":
        return {"allowed": False, "reason": "write_denied_by_matrix"}
    if rule == "OWN_PARTNER":
        if portal_user_partner_id == target_partner_id:
            return {"allowed": True, "reason": "own_partner_write_allowed"}
        return {"allowed": False, "reason": "cross_partner_write_denied"}
    return {"allowed": False, "reason": f"unknown_rule:{rule}"}


# ────────────────────────────────────────────────────────────────────
# Combined engine (#374 + #375)
# ────────────────────────────────────────────────────────────────────

class PartnerPortalAndAnalyticsEngine:
    """Partner portal data bundle + ecosystem analytics."""

    def __init__(
        self,
        master: Optional[PartnerMasterEngine] = None,
        scorecard: Optional[PartnerScorecardEngine] = None,
        leads: Optional[LeadTrackingEngine] = None,
        commissions: Optional[CommissionEngine] = None,
    ):
        self.master = master or PartnerMasterEngine()
        self.scorecard = scorecard or PartnerScorecardEngine()
        self.leads = leads or LeadTrackingEngine()
        self.commissions = commissions or CommissionEngine(lead_engine=self.leads)

    # ── #374 Portal payload ────────────────────────────────────────

    def portal_dashboard_payload(self, partner_id: str) -> Dict[str, Any]:
        """Read-scoped data bundle for a partner's portal landing page."""
        partner = self.master.get_partner(partner_id)
        if not partner:
            return {"error": f"unknown_partner:{partner_id}"}

        lead_records = self.leads._load()
        own_leads = [
            l for l in lead_records if l.get("partner_id") == partner_id
        ]

        # Latest scorecard
        all_sc = self.scorecard._load()
        own_periods = sorted({
            r["period"] for r in all_sc if r.get("partner_id") == partner_id
        })
        latest = None
        if own_periods:
            latest = self.scorecard.compute_scorecard(
                partner_id, own_periods[-1]
            )

        return {
            "partner_id": partner_id,
            "partner_name": partner.get("partner_name"),
            "state": partner.get("state"),
            "tier": latest.get("tier") if latest else None,
            "lead_count_total": len(own_leads),
            "lead_count_won": sum(1 for l in own_leads if l.get("state") == "WON"),
            "latest_scorecard_period": own_periods[-1] if own_periods else None,
            "latest_scorecard_composite": latest.get("composite") if latest else None,
            "_meta": {
                "data_isolation": "OWN_PARTNER_ONLY",
                "role": PORTAL_ROLE_NAME,
            },
        }

    # ── #375 Ecosystem analytics ───────────────────────────────────

    def top_performers(
        self, period: str, n: int = 10
    ) -> List[Dict[str, Any]]:
        """Top N partners by composite score in period."""
        ranked = self.scorecard.rank_partners(period)
        return ranked[:n]

    def underperformers(
        self,
        period: str,
        threshold_score: Decimal = Decimal("45"),
    ) -> List[Dict[str, Any]]:
        """Partners with composite below threshold (AT_RISK + BRONZE-borderline)."""
        ranked = self.scorecard.rank_partners(period)
        return [
            r for r in ranked
            if r["composite"] is not None and Decimal(r["composite"]) < threshold_score
        ]

    def geographic_coverage(self) -> Dict[str, Any]:
        """Partner count by country."""
        partners = self.master._load()
        countries = Counter(
            p.get("country", "UNKNOWN") for p in partners
            if p.get("state") in ("ACTIVE", "SUSPENDED")
        )
        return {
            "by_country": dict(countries),
            "total_active_or_suspended": sum(countries.values()),
            "countries_count": len(countries),
        }

    def segment_coverage(self) -> Dict[str, Any]:
        """Lead-coverage by customer_segment across all partners."""
        leads = self.leads._load()
        segments = Counter(
            l.get("customer_segment", "UNKNOWN") for l in leads
        )
        return {
            "by_segment": dict(segments),
            "total_leads": sum(segments.values()),
            "segments_count": len(segments),
        }

    def profitability_by_partner(
        self,
        period_start: str,
        period_end: str,
        split_pct: Decimal = Decimal("10"),
    ) -> List[Dict[str, Any]]:
        """
        Per-partner profitability: attributed revenue minus commission.

        Returns list sorted by net contribution descending.
        """
        partners = self.master.list_partners(state=None)
        partner_ids = [p["partner_id"] for p in partners]

        out = []
        for pid in partner_ids:
            comp = self.commissions.compute_commissions(
                pid, period_start, period_end, split_pct
            )
            if not comp.get("status"):
                continue
            rev = Decimal(comp["total_attributed_revenue_kes"])
            comm = Decimal(comp["commission_amount_kes"])
            net = rev - comm
            out.append({
                "partner_id": pid,
                "won_lead_count": comp["won_lead_count"],
                "attributed_revenue_kes": str(rev.quantize(Decimal("0.01"))),
                "commission_kes": str(comm.quantize(Decimal("0.01"))),
                "net_contribution_kes": str(net.quantize(Decimal("0.01"))),
            })

        out.sort(
            key=lambda x: Decimal(x["net_contribution_kes"]),
            reverse=True,
        )
        return out


def _self_test() -> None:
    import tempfile

    # === Portal API tests ===
    # Test 1: own partner read allowed
    r = portal_can_read("P-001", "LEAD_STATUS", "P-001")
    assert r["allowed"]
    assert r["reason"] == "own_partner"

    # Test 2: cross-partner read denied
    r = portal_can_read("P-001", "LEAD_STATUS", "P-002")
    assert not r["allowed"]
    assert "cross_partner_denied" in r["reason"]

    # Test 3: TRAINING is open to all
    r = portal_can_read("P-001", "TRAINING_RESOURCES", "P-002")
    assert r["allowed"]
    assert r["reason"] == "training_open_to_all"

    # Test 4: OTHER_PARTNER_DATA always denied
    r = portal_can_read("P-001", "OTHER_PARTNER_DATA", "P-001")
    assert not r["allowed"]

    # Test 5: write LEAD_SUBMIT for own partner allowed
    r = portal_can_write("P-001", "LEAD_SUBMIT", "P-001")
    assert r["allowed"]

    # Test 6: write LEAD_STATUS denied (read-only)
    r = portal_can_write("P-001", "LEAD_STATUS", "P-001")
    assert not r["allowed"]

    # Test 7: unknown resource denied
    r = portal_can_read("P-001", "INVALID_RESOURCE", "P-001")
    assert not r["allowed"]

    # Test 8: role definition
    role = portal_role_definition()
    assert role["role_name"] == "PARTNER_PORTAL_USER"
    assert role["data_isolation"] == "OWN_PARTNER_ONLY"

    # === Combined engine tests ===
    with tempfile.TemporaryDirectory() as tmpdir:
        master = PartnerMasterEngine(partners_path=Path(tmpdir) / "p.json")
        scorecard = PartnerScorecardEngine(
            scorecards_path=Path(tmpdir) / "sc.json"
        )
        leads = LeadTrackingEngine(leads_path=Path(tmpdir) / "l.json")
        commissions = CommissionEngine(
            commissions_path=Path(tmpdir) / "c.json", lead_engine=leads
        )

        # Seed: 2 partners
        master.register_partner(
            {"partner_id": "P-001", "partner_name": "ACME",
             "partner_type": "REFERRAL", "country": "KE"},
            actor="bd", reason="reg",
        )
        master.transition_state("P-001", "ONBOARDING", "bd", "contract")
        master.transition_state("P-001", "ACTIVE", "bd", "live")

        master.register_partner(
            {"partner_id": "P-002", "partner_name": "Beta",
             "partner_type": "DISTRIBUTION", "country": "UG"},
            actor="bd", reason="reg",
        )

        # Seed: 1 WON lead for P-001
        leads.submit_lead(
            "P-001",
            {"lead_id": "L-001", "customer_name": "X Corp",
             "customer_segment": "SME",
             "submitted_date": "2026-04-01"},
            actor="rm",
        )
        leads.transition_lead_state("L-001", "QUALIFIED", "rm", "ok")
        leads.transition_lead_state("L-001", "IN_PIPELINE", "rm", "selling")
        leads.transition_lead_state(
            "L-001", "WON", "rm", "closed",
            actual_revenue_kes=Decimal("1000000"),
        )

        # Seed: complete scorecard for P-001
        for d, v in [("REVENUE_KES", "8000000"),
                       ("LEADS_DELIVERED", "80"),
                       ("CONVERSION_RATE", "75"),
                       ("CSAT_SCORE", "90"),
                       ("COMPLIANCE_SCORE", "95")]:
            scorecard.record_score_dimension(
                "P-001", "2026-Q1", d, Decimal(v), actor="ops"
            )

        engine = PartnerPortalAndAnalyticsEngine(
            master=master, scorecard=scorecard,
            leads=leads, commissions=commissions,
        )

        # Test 9: portal payload — own partner
        payload = engine.portal_dashboard_payload("P-001")
        assert payload["partner_id"] == "P-001"
        assert payload["lead_count_total"] == 1
        assert payload["lead_count_won"] == 1
        assert payload["tier"] == "GOLD"

        # Test 10: portal payload for unknown partner
        bad = engine.portal_dashboard_payload("UNKNOWN")
        assert "error" in bad

        # Test 11: top_performers
        top = engine.top_performers("2026-Q1", n=5)
        assert len(top) == 1
        assert top[0]["partner_id"] == "P-001"

        # Test 12: underperformers (none below 45)
        under = engine.underperformers("2026-Q1")
        assert len(under) == 0

        # Test 13: geographic_coverage
        geo = engine.geographic_coverage()
        # Only P-001 is ACTIVE; P-002 still PROSPECT
        assert geo["total_active_or_suspended"] == 1
        assert "KE" in geo["by_country"]

        # Test 14: segment_coverage
        seg = engine.segment_coverage()
        assert seg["total_leads"] == 1
        assert "SME" in seg["by_segment"]

        # Test 15: profitability_by_partner
        prof = engine.profitability_by_partner(
            "2026-04-01", "2026-12-31", split_pct=Decimal("10")
        )
        # Only P-001 has revenue; commission = 100k; net = 900k
        p1 = next(p for p in prof if p["partner_id"] == "P-001")
        assert Decimal(p1["attributed_revenue_kes"]) == Decimal("1000000")
        assert Decimal(p1["commission_kes"]) == Decimal("100000")
        assert Decimal(p1["net_contribution_kes"]) == Decimal("900000")

    print("  ✅ partner_portal_and_analytics self-test PASS")


if __name__ == "__main__":
    _self_test()
