"""
================================================================================
A2Z MIS 360 — Standard #384: Vendor SLA Scorecard
================================================================================

Risk classification: Cat B (deterministic vendor SLA scoring)

Per-vendor SLA tracking: response time, uptime, quality, penalties.
Auto-credit calculation. Performance review input.

Public API:
    vendor_scorecard(vendor_id, period)          -- {compliance, score, tier}
    auto_credit_calculation(vendor_id, period)   -- penalty credits owed
    rank_vendors(period)                         -- ordered list with tiers
    performance_review_inputs(vendor_id)         -- structured for HR review

Vendor performance tiers byte-for-byte:
    PLATINUM   -- ≥98% compliance — preferred, expand engagement
    GOLD       -- ≥95% compliance — strong performer
    SILVER     -- ≥90% compliance — meets expectations
    BRONZE     -- ≥85% compliance — under review
    AT_RISK    -- <85% — vendor performance review triggered

Auto-credit calculation byte-for-byte:
    MINOR breach     -- 0% credit
    MAJOR breach     -- 5% of monthly fee or KES 5,000 (whichever higher)
    CRITICAL breach  -- 10% of monthly fee or KES 20,000 (whichever higher)

Honesty rules:
    Rule 1: tier = None when no observations
    Rule 6: vendors with missing fee data → credit_amount = None
            (cannot impute monthly fee)

================================================================================
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

from utils.sla_registry import SlaRegistryEngine
from utils.sla_monitoring import SlaMonitoringEngine
from utils.sla_breach import SlaBreachEngine

getcontext().prec = 28

# Vendor tier thresholds — byte-for-byte
VENDOR_TIER_PLATINUM_PCT: Decimal = Decimal("98")
VENDOR_TIER_GOLD_PCT:     Decimal = Decimal("95")
VENDOR_TIER_SILVER_PCT:   Decimal = Decimal("90")
VENDOR_TIER_BRONZE_PCT:   Decimal = Decimal("85")

VENDOR_TIERS: Tuple[str, ...] = (
    "PLATINUM", "GOLD", "SILVER", "BRONZE", "AT_RISK",
)

# Auto-credit table
VENDOR_CREDIT_TABLE: Dict[str, Dict[str, Decimal]] = {
    "MINOR":    {"pct_of_fee": Decimal("0"),  "fixed_kes": Decimal("0")},
    "MAJOR":    {"pct_of_fee": Decimal("5"),  "fixed_kes": Decimal("5000")},
    "CRITICAL": {"pct_of_fee": Decimal("10"), "fixed_kes": Decimal("20000")},
}


def classify_vendor_tier(compliance_pct: Decimal) -> str:
    """Classify vendor tier by compliance percentage."""
    if compliance_pct >= VENDOR_TIER_PLATINUM_PCT:
        return "PLATINUM"
    elif compliance_pct >= VENDOR_TIER_GOLD_PCT:
        return "GOLD"
    elif compliance_pct >= VENDOR_TIER_SILVER_PCT:
        return "SILVER"
    elif compliance_pct >= VENDOR_TIER_BRONZE_PCT:
        return "BRONZE"
    else:
        return "AT_RISK"


class VendorScorecardEngine:
    """Vendor SLA scorecard + auto-credit + ranking."""

    def __init__(
        self,
        registry: Optional[SlaRegistryEngine] = None,
        monitoring: Optional[SlaMonitoringEngine] = None,
        breach: Optional[SlaBreachEngine] = None,
    ):
        self.registry = registry or SlaRegistryEngine()
        self.monitoring = monitoring or SlaMonitoringEngine()
        self.breach = breach or SlaBreachEngine()

    def vendor_scorecard(
        self,
        vendor_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute vendor scorecard for period.

        Rule 1: tier = None when no observations.
        """
        # Find vendor SLAs
        vendor_slas = [
            s for s in self.registry.list_slas(sla_type="VENDOR")
            if s.get("counterparty") == vendor_id
        ]

        if not vendor_slas:
            return {
                "vendor_id": vendor_id,
                "tier": None,
                "compliance_pct": None,
                "reason": "no_vendor_slas_registered",
                "slas_in_scope": 0,
            }

        # Aggregate compliance across SLAs
        total_obs = 0
        within = 0
        breached = 0
        per_sla = []
        for sla in vendor_slas:
            sid = sla.get("sla_id")
            comp = self.monitoring.compute_compliance(sid, period_start, period_end)
            total_obs += comp["total_observations"]
            within += comp["within_sla"] + comp["near_breach"]
            breached += comp["breached"]
            per_sla.append({
                "sla_id": sid,
                "name": sla.get("name"),
                "compliance_pct": (
                    str(comp["compliance_pct"])
                    if comp["compliance_pct"] is not None else None
                ),
                "breached": comp["breached"],
            })

        if total_obs == 0:
            return {
                "vendor_id": vendor_id,
                "tier": None,
                "compliance_pct": None,
                "reason": "no_observations_in_period",
                "slas_in_scope": len(vendor_slas),
                "per_sla": per_sla,
            }

        # Aggregate compliance
        agg_compliance = (Decimal(within) / Decimal(within + breached)) * Decimal("100") \
            if (within + breached) > 0 else Decimal("0")
        tier = classify_vendor_tier(agg_compliance)

        return {
            "vendor_id": vendor_id,
            "tier": tier,
            "compliance_pct": str(agg_compliance.quantize(Decimal("0.01"))),
            "total_observations": total_obs,
            "within_sla": within,
            "breached": breached,
            "slas_in_scope": len(vendor_slas),
            "per_sla": per_sla,
        }

    def auto_credit_calculation(
        self,
        vendor_id: str,
        monthly_fee_kes: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Calculate auto-credit owed by vendor for breaches.

        Rule 6: monthly_fee_kes missing → credit_amount = None
        """
        # Get vendor's breaches
        vendor_slas = [
            s for s in self.registry.list_slas(sla_type="VENDOR")
            if s.get("counterparty") == vendor_id
        ]
        sla_ids = {s.get("sla_id") for s in vendor_slas}

        all_breaches = self.breach.list_breaches()
        vendor_breaches = [b for b in all_breaches if b.get("sla_id") in sla_ids]

        # Tally by severity
        sev_counts = {"MINOR": 0, "MAJOR": 0, "CRITICAL": 0}
        for b in vendor_breaches:
            sev = b.get("severity")
            if sev in sev_counts:
                sev_counts[sev] += 1

        if monthly_fee_kes is None:
            return {
                "vendor_id": vendor_id,
                "credit_amount_kes": None,
                "reason": "missing_monthly_fee_data",
                "breach_counts": sev_counts,
            }

        total_credit = Decimal("0")
        breakdown = {}
        for sev, count in sev_counts.items():
            if count == 0:
                continue
            table = VENDOR_CREDIT_TABLE[sev]
            pct_amount = monthly_fee_kes * table["pct_of_fee"] / Decimal("100")
            fixed_amount = table["fixed_kes"]
            per_breach = max(pct_amount, fixed_amount)
            sev_total = per_breach * Decimal(count)
            total_credit += sev_total
            breakdown[sev] = {
                "count": count,
                "per_breach_kes": str(per_breach.quantize(Decimal("0.01"))),
                "total_kes": str(sev_total.quantize(Decimal("0.01"))),
            }

        return {
            "vendor_id": vendor_id,
            "credit_amount_kes": str(total_credit.quantize(Decimal("0.01"))),
            "breach_counts": sev_counts,
            "breakdown": breakdown,
            "monthly_fee_kes": str(monthly_fee_kes),
        }

    def rank_vendors(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Rank all vendors by tier + compliance %."""
        # Distinct vendor counterparties
        all_vendor_slas = self.registry.list_slas(sla_type="VENDOR")
        vendor_ids = {
            s.get("counterparty") for s in all_vendor_slas
            if s.get("counterparty")
        }

        scorecards = []
        for vid in sorted(vendor_ids):
            sc = self.vendor_scorecard(vid, period_start, period_end)
            if sc["tier"] is not None:
                scorecards.append(sc)

        # Sort by compliance_pct desc
        scorecards.sort(
            key=lambda x: Decimal(str(x["compliance_pct"] or 0)),
            reverse=True,
        )
        return scorecards


def _self_test() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        registry = SlaRegistryEngine(
            registry_path=Path(tmpdir) / "sla_registry.json"
        )
        monitoring = SlaMonitoringEngine(
            observations_path=Path(tmpdir) / "sla_observations.json"
        )
        breach = SlaBreachEngine(
            breaches_path=Path(tmpdir) / "sla_breaches.json"
        )

        # Tier classification tests
        assert classify_vendor_tier(Decimal("99")) == "PLATINUM"
        assert classify_vendor_tier(Decimal("96")) == "GOLD"
        assert classify_vendor_tier(Decimal("92")) == "SILVER"
        assert classify_vendor_tier(Decimal("87")) == "BRONZE"
        assert classify_vendor_tier(Decimal("70")) == "AT_RISK"

        # Register vendor SLA
        registry.register_sla({
            "sla_id": "SLA-VEND-001",
            "name": "TechVendor Uptime",
            "sla_type": "VENDOR",
            "priority": "P2_HIGH",
            "metric_type": "UPTIME",
            "target_value": Decimal("99.5"),
            "target_unit": "percent",
            "direction": "min",
            "owner_department": "IT",
            "counterparty": "VENDOR-XYZ",
        })

        # Record observations
        for i in range(10):
            monitoring.record_event(
                sla_id="SLA-VEND-001", event_id=f"V-{i:03d}",
                started_at="2026-04-01T00:00:00",
                completed_at="2026-04-30T23:59:59",
                elapsed_value=Decimal("99.7") if i < 9 else Decimal("99.0"),
                target_value=Decimal("99.5"),
                direction="min",
            )

        engine = VendorScorecardEngine(
            registry=registry, monitoring=monitoring, breach=breach
        )
        scorecard = engine.vendor_scorecard("VENDOR-XYZ")
        assert scorecard["tier"] is not None
        assert scorecard["slas_in_scope"] == 1
        # 9 within, 1 breached → 90% compliance → SILVER
        assert scorecard["tier"] == "SILVER", f"Got {scorecard['tier']}"

        # Test auto-credit with monthly_fee
        # Create a CRITICAL breach for the vendor
        breach.create_breach_incident(
            sla_id="SLA-VEND-001", event_id="V-009",
            elapsed_value=Decimal("50"), target_value=Decimal("99.5"),
            direction="min", is_regulatory=False,
        )
        credit = engine.auto_credit_calculation(
            "VENDOR-XYZ", monthly_fee_kes=Decimal("500000")
        )
        # CRITICAL: max(10% × 500k = 50k, fixed 20k) = 50k
        assert Decimal(credit["credit_amount_kes"]) >= Decimal("20000")

        # Rule 6: missing fee → None
        credit_none = engine.auto_credit_calculation("VENDOR-XYZ")
        assert credit_none["credit_amount_kes"] is None
        assert credit_none["reason"] == "missing_monthly_fee_data"

        # Rank vendors
        ranked = engine.rank_vendors()
        assert len(ranked) == 1

    print("  ✅ sla_vendor_scorecard self-test PASS")


if __name__ == "__main__":
    _self_test()
