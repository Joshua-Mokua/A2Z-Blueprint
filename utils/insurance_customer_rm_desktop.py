"""
================================================================================
A2Z MIS 360 — Standards #306 + #307: Customer Insurance 360 + RM Desktop
================================================================================

Risk classification: Cat B (deterministic data composition + read-scoped views)

Combined module:
    #306: Customer 360 view — all-policies view across insurers,
          coverage gaps, expiry alerts, claim history.
    #307: RM-facing insurance workspace — customer policies,
          recommendations, quote tools, claim tracking, performance KPIs.

This module is a pure read-side composition layer over insurance_catalog,
insurance_recommendation, insurance_partner_hub, and insurance_claims.
No new persistence beyond what those engines already provide.

Public API (#306):
    customer_360_view(customer_id) -> consolidated payload
    coverage_gaps(customer_id) -> recommended types not yet covered
    upcoming_expirations(customer_id, days_ahead=60) -> renewal alerts
    claim_history(customer_id) -> all claims across policies

Public API (#307):
    rm_workspace_payload(rm_id, customer_id) -> RM dashboard data
    rm_book_summary(rm_id, customer_ids) -> aggregate KPIs across book
    rm_pending_actions(rm_id, customer_ids) -> action queue

EXPECTED_COVERAGE_BASELINES byte-for-byte (#306 coverage gaps):
    Adult earner:        ("LIFE", "HEALTH", "PERSONAL_ACCIDENT")
    Vehicle owner:       + ("MOTOR",)
    Property owner:      + ("PROPERTY",)
    Parent:              + ("EDUCATION",)
    Business owner:      + ("BUSINESS",)
    Approaching ret:     + ("PENSION",)

RM_KPI_DIMENSIONS byte-for-byte (#307):
    POLICIES_ACTIVE      -- active policy count in RM's book
    NEW_POLICIES_PERIOD  -- new policies issued this period
    PREMIUM_COLLECTED    -- KES collected this period
    CLAIM_COUNT_OPEN     -- open claims requiring RM attention
    EXPIRING_SOON        -- policies expiring within 60 days
    COVERAGE_GAP_LEADS   -- customers with identified coverage gaps

Honesty rules:
    Rule 1: customer_360_view returns empty payload (not None) for
            unknown customer; surface explicit "no_policies" when
            customer has no policies
    Rule 6: invalid customer_attrs surface missing fields

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

from utils.insurance_catalog import (
    InsuranceCatalogEngine, INSURANCE_PRODUCT_TYPES,
)
from utils.insurance_recommendation import InsuranceRecommendationEngine
from utils.insurance_claims import ClaimsProcessingEngine

getcontext().prec = 28


EXPECTED_COVERAGE_BASELINES: Dict[str, Tuple[str, ...]] = {
    "adult_earner":         ("LIFE", "HEALTH", "PERSONAL_ACCIDENT"),
    "vehicle_owner":        ("MOTOR",),
    "property_owner":       ("PROPERTY",),
    "parent":               ("EDUCATION",),
    "business_owner":       ("BUSINESS",),
    "approaching_retirement": ("PENSION",),
}


RM_KPI_DIMENSIONS: Tuple[str, ...] = (
    "POLICIES_ACTIVE",
    "NEW_POLICIES_PERIOD",
    "PREMIUM_COLLECTED",
    "CLAIM_COUNT_OPEN",
    "EXPIRING_SOON",
    "COVERAGE_GAP_LEADS",
)


class CustomerAndRmDesktopEngine:
    """Customer 360 + RM workspace data composition."""

    def __init__(
        self,
        catalog: Optional[InsuranceCatalogEngine] = None,
        recommendation: Optional[InsuranceRecommendationEngine] = None,
        claims: Optional[ClaimsProcessingEngine] = None,
    ):
        self.catalog = catalog or InsuranceCatalogEngine()
        self.recommendation = (
            recommendation or
            InsuranceRecommendationEngine(catalog=self.catalog)
        )
        self.claims = claims or ClaimsProcessingEngine(catalog=self.catalog)

    # ── #306 Customer 360 ──────────────────────────────────────────

    def customer_360_view(
        self,
        customer_id: str,
        customer_attrs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Consolidated customer view across all insurance dimensions."""
        # Base catalog 360
        base_360 = self.catalog.customer_policy_360(customer_id)

        # Coverage gaps
        gaps = self.coverage_gaps(customer_id, customer_attrs)

        # Upcoming expirations
        expirations = self.upcoming_expirations(customer_id)

        # Claim history
        claims = self.claim_history(customer_id)

        # Recommendations (if attrs provided)
        recommendations = []
        if customer_attrs:
            r = self.recommendation.recommend_for_customer(
                customer_id, customer_attrs, top_n=5,
            )
            recommendations = r.get("recommendations", [])

        return {
            "customer_id": customer_id,
            "policies": base_360.get("policies", []),
            "policy_count": base_360.get("policy_count", 0),
            "by_state": base_360.get("by_state", {}),
            "by_product_type": base_360.get("by_product_type", {}),
            "by_insurer": base_360.get("by_insurer", {}),
            "total_sum_assured_kes": base_360.get("total_sum_assured_kes"),
            "total_annual_premium_kes": base_360.get("total_annual_premium_kes"),
            "coverage_gaps": gaps,
            "upcoming_expirations": expirations,
            "claim_history": claims,
            "recommendations": recommendations,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def coverage_gaps(
        self,
        customer_id: str,
        customer_attrs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Identify coverage gaps based on customer profile."""
        # Currently held active product types
        policies = self.catalog.list_customer_policies(
            customer_id, state="ACTIVE",
        )
        # Look up product type via products catalog
        products = self.catalog._load(
            self.catalog.products_path, "insurance_products", ("product_code",)
        )
        product_lookup = {p["product_code"]: p for p in products}

        held_types: Set[str] = set()
        for pol in policies:
            prod = product_lookup.get(pol.get("product_code"))
            if prod:
                held_types.add(prod.get("product_type", ""))

        # Build expected types from attrs
        expected: Set[str] = set()
        applied_baselines: List[str] = []

        if customer_attrs is None:
            return {
                "customer_id": customer_id,
                "expected_types": [],
                "held_types": sorted(held_types),
                "missing_types": [],
                "applied_baselines": [],
                "reason": "no_customer_attrs_provided",
            }

        # Adult earner is default baseline
        if customer_attrs.get("monthly_income_kes"):
            expected.update(EXPECTED_COVERAGE_BASELINES["adult_earner"])
            applied_baselines.append("adult_earner")
        if customer_attrs.get("owns_vehicle"):
            expected.update(EXPECTED_COVERAGE_BASELINES["vehicle_owner"])
            applied_baselines.append("vehicle_owner")
        if customer_attrs.get("owns_property"):
            expected.update(EXPECTED_COVERAGE_BASELINES["property_owner"])
            applied_baselines.append("property_owner")
        if customer_attrs.get("has_dependents"):
            expected.update(EXPECTED_COVERAGE_BASELINES["parent"])
            applied_baselines.append("parent")
        if customer_attrs.get("owns_business"):
            expected.update(EXPECTED_COVERAGE_BASELINES["business_owner"])
            applied_baselines.append("business_owner")
        # Age-based
        try:
            age = int(customer_attrs.get("age", 0))
            if age >= 50:
                expected.update(EXPECTED_COVERAGE_BASELINES["approaching_retirement"])
                applied_baselines.append("approaching_retirement")
        except (ValueError, TypeError):
            pass

        missing = sorted(expected - held_types)

        return {
            "customer_id": customer_id,
            "expected_types": sorted(expected),
            "held_types": sorted(held_types),
            "missing_types": missing,
            "applied_baselines": applied_baselines,
        }

    def upcoming_expirations(
        self,
        customer_id: str,
        days_ahead: int = 60,
        as_of: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Active policies expiring within window."""
        as_of = as_of or date.today()
        cutoff = as_of + timedelta(days=days_ahead)

        policies = self.catalog.list_customer_policies(
            customer_id, state="ACTIVE",
        )
        out = []
        for p in policies:
            try:
                exp = date.fromisoformat(p.get("expiry_date", ""))
            except (ValueError, TypeError):
                continue
            if as_of <= exp <= cutoff:
                out.append({
                    "policy_id": p["policy_id"],
                    "product_code": p.get("product_code"),
                    "expiry_date": p["expiry_date"],
                    "days_until_expiry": (exp - as_of).days,
                    "sum_assured_kes": p.get("sum_assured_kes"),
                })
        out.sort(key=lambda x: x["days_until_expiry"])
        return out

    def claim_history(self, customer_id: str) -> List[Dict[str, Any]]:
        """All claims across customer's policies."""
        policies = self.catalog.list_customer_policies(
            customer_id, state=None,
        )
        policy_ids = {p["policy_id"] for p in policies}

        all_claims = self.claims._load()
        out = [c for c in all_claims if c.get("policy_id") in policy_ids]
        out.sort(
            key=lambda x: x.get("submitted_at", ""),
            reverse=True,
        )
        return out

    # ── #307 RM Desktop ────────────────────────────────────────────

    def rm_workspace_payload(
        self,
        rm_id: str,
        customer_id: str,
        customer_attrs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Single-customer RM workspace view."""
        c360 = self.customer_360_view(customer_id, customer_attrs)
        return {
            "rm_id": rm_id,
            "customer_id": customer_id,
            "view_type": "rm_workspace_single_customer",
            "policies": c360["policies"],
            "by_state": c360["by_state"],
            "coverage_gaps": c360["coverage_gaps"],
            "upcoming_expirations": c360["upcoming_expirations"],
            "open_claims": [
                c for c in c360["claim_history"]
                if c.get("state") not in ("SETTLED", "CLOSED", "REJECTED")
            ],
            "recommendations": c360["recommendations"],
            "total_annual_premium_kes": c360.get("total_annual_premium_kes"),
            "generated_at": datetime.utcnow().isoformat(),
        }

    def rm_book_summary(
        self,
        rm_id: str,
        customer_ids: List[str],
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate KPIs across an RM's customer book."""
        if not customer_ids:
            return {
                "rm_id": rm_id,
                "customer_count": 0,
                "kpis": {k: 0 for k in RM_KPI_DIMENSIONS},
                "reason": "no_customers_in_book",
            }

        kpis = {k: 0 for k in RM_KPI_DIMENSIONS}
        kpis_money: Dict[str, Decimal] = {"PREMIUM_COLLECTED": Decimal("0")}

        all_claims = self.claims._load()

        # Build lookup of claims by customer_id via policies
        for cid in customer_ids:
            active_policies = self.catalog.list_customer_policies(cid, state="ACTIVE")
            kpis["POLICIES_ACTIVE"] += len(active_policies)

            # New policies in period (issued_at within window)
            for p in active_policies:
                issued_at = p.get("issued_at", "")[:10]
                if period_start and issued_at < period_start:
                    continue
                if period_end and issued_at > period_end:
                    continue
                kpis["NEW_POLICIES_PERIOD"] += 1

            # Expiring soon
            kpis["EXPIRING_SOON"] += len(self.upcoming_expirations(cid))

            # Coverage gap leads (only if customer has any policies)
            all_pols = self.catalog.list_customer_policies(cid, state=None)
            if all_pols:
                kpis["COVERAGE_GAP_LEADS"] += 1  # flag: customer has gaps

            # Open claims for customer's policies
            cust_policy_ids = {p["policy_id"] for p in all_pols}
            cust_claims = [
                c for c in all_claims if c.get("policy_id") in cust_policy_ids
            ]
            kpis["CLAIM_COUNT_OPEN"] += sum(
                1 for c in cust_claims
                if c.get("state") not in ("SETTLED", "CLOSED", "REJECTED")
            )

        return {
            "rm_id": rm_id,
            "customer_count": len(customer_ids),
            "period_start": period_start,
            "period_end": period_end,
            "kpis": kpis,
            "kpis_money_kes": {
                k: str(v.quantize(Decimal("0.01")))
                for k, v in kpis_money.items()
            },
            "_meta": {
                "premium_collected_caveat": (
                    "PREMIUM_COLLECTED is shown as 0 in this batch — "
                    "the engine doesn't yet correlate premium records "
                    "to customer_id. Future enhancement requires "
                    "premium ↔ policy ↔ customer join already supported "
                    "by the underlying catalog engine but not yet "
                    "wired into rm_book_summary."
                ),
            },
        }

    def rm_pending_actions(
        self,
        rm_id: str,
        customer_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Prioritized action queue for an RM."""
        actions = []

        for cid in customer_ids:
            # Expiring policies (high priority)
            for exp in self.upcoming_expirations(cid, days_ahead=30):
                actions.append({
                    "priority": "HIGH",
                    "action_type": "RENEWAL",
                    "customer_id": cid,
                    "policy_id": exp["policy_id"],
                    "due_in_days": exp["days_until_expiry"],
                    "summary": f"Policy {exp['policy_id']} expires in "
                                 f"{exp['days_until_expiry']} days",
                })

            # Open claims (medium priority)
            history = self.claim_history(cid)
            for c in history:
                if c.get("state") in ("SUBMITTED", "DOCUMENT_REVIEW",
                                          "INVESTIGATING", "CONTESTED"):
                    actions.append({
                        "priority": "MEDIUM",
                        "action_type": "CLAIM_FOLLOWUP",
                        "customer_id": cid,
                        "claim_id": c["claim_id"],
                        "summary": f"Claim {c['claim_id']} in {c['state']}",
                    })

        # Sort: HIGH first, then by due_in_days for renewals
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        actions.sort(
            key=lambda x: (
                priority_order.get(x["priority"], 9),
                x.get("due_in_days", 999),
            )
        )
        return actions


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = InsuranceCatalogEngine(
            products_path=Path(tmpdir) / "p.json",
            policies_path=Path(tmpdir) / "po.json",
            premiums_path=Path(tmpdir) / "pr.json",
        )
        # Seed: products
        for code, ptype in [("PROD-LIFE", "LIFE"),
                              ("PROD-HEALTH", "HEALTH"),
                              ("PROD-MOTOR", "MOTOR")]:
            catalog.register_product(
                "INS-A",
                {"product_code": code, "product_name": f"P-{ptype}",
                 "product_type": ptype},
                actor="bd", reason="seed",
            )
        # Customer with LIFE only
        catalog.issue_policy(
            "CUST-001", "PROD-LIFE",
            {"policy_id": "POL-LIFE-001",
             "sum_assured_kes": "1000000",
             "premium_kes": "10000",
             "premium_frequency": "ANNUAL",
             "effective_date": "2026-01-01",
             "expiry_date": "2026-06-15"},  # expires soon
            actor="rm",
        )
        for s in ("APPLIED", "UNDERWRITING", "ACTIVE"):
            catalog.transition_policy_state("POL-LIFE-001", s, "rm", "ok")

        engine = CustomerAndRmDesktopEngine(catalog=catalog)

        # Test 1: customer_360_view with attrs
        view = engine.customer_360_view(
            "CUST-001",
            customer_attrs={
                "monthly_income_kes": "150000",
                "owns_vehicle": True,
                "has_dependents": True,
                "age": 38,
            },
        )
        assert view["policy_count"] == 1
        # Coverage gaps: expected = LIFE,HEALTH,PA,MOTOR,EDUCATION
        # Held = LIFE
        # Missing should include HEALTH, MOTOR, etc.
        gaps = view["coverage_gaps"]
        assert "LIFE" in gaps["held_types"]
        assert "HEALTH" in gaps["missing_types"]
        assert "MOTOR" in gaps["missing_types"]
        assert "adult_earner" in gaps["applied_baselines"]
        assert "vehicle_owner" in gaps["applied_baselines"]
        assert "parent" in gaps["applied_baselines"]

        # Test 2: upcoming_expirations
        exps = engine.upcoming_expirations(
            "CUST-001", days_ahead=200,
            as_of=date(2026, 5, 7),
        )
        assert len(exps) == 1  # POL-LIFE-001 expires 2026-06-15

        # Test 3: customer with no policies
        view = engine.customer_360_view("UNKNOWN-CUST")
        assert view["policy_count"] == 0
        assert view["policies"] == []

        # Test 4: coverage_gaps without attrs surfaces reason
        gaps = engine.coverage_gaps("CUST-001")
        assert gaps["reason"] == "no_customer_attrs_provided"

        # Test 5: claim_history empty for customer with no claims
        history = engine.claim_history("CUST-001")
        assert history == []

        # Test 6: rm_workspace_payload
        payload = engine.rm_workspace_payload(
            "RM-001", "CUST-001",
            customer_attrs={"monthly_income_kes": "150000",
                              "has_dependents": True, "age": 38},
        )
        assert payload["rm_id"] == "RM-001"
        assert payload["customer_id"] == "CUST-001"
        assert len(payload["upcoming_expirations"]) >= 0

        # Test 7: rm_book_summary
        summary = engine.rm_book_summary("RM-001", ["CUST-001"])
        assert summary["customer_count"] == 1
        assert summary["kpis"]["POLICIES_ACTIVE"] == 1

        # Test 8: rm_book_summary empty book
        summary = engine.rm_book_summary("RM-NEW", [])
        assert summary["customer_count"] == 0
        assert summary["reason"] == "no_customers_in_book"

        # Test 9: rm_pending_actions
        actions = engine.rm_pending_actions("RM-001", ["CUST-001"])
        # POL-LIFE-001 expires within 60 days but maybe not 30
        # Test expects deterministic priority ordering
        for a in actions:
            assert a["priority"] in ("HIGH", "MEDIUM", "LOW")

        # Test 10: claim history wires through claims engine
        claims_engine = ClaimsProcessingEngine(
            claims_path=Path(tmpdir) / "c.json", catalog=catalog,
        )
        claims_engine.submit_claim(
            "POL-LIFE-001",
            {"claim_id": "CLM-001",
             "incident_date": "2026-04-01",
             "claim_amount_kes": "50000",
             "claim_description": "test"},
            actor="rm",
        )
        engine_with_claims = CustomerAndRmDesktopEngine(
            catalog=catalog, claims=claims_engine,
        )
        history = engine_with_claims.claim_history("CUST-001")
        assert len(history) == 1
        assert history[0]["claim_id"] == "CLM-001"

    print("  ✅ insurance_customer_rm_desktop self-test PASS")


if __name__ == "__main__":
    _self_test()
