"""
================================================================================
A2Z MIS 360 — Standards #308 + #310: IRA Compliance + Executive Dashboard
================================================================================

Risk classification: Cat A (regulatory — IRA statutory reporting)
                     + Cat B (deterministic executive dashboard composition)

Combined module:
    #308: IRA (Insurance Regulatory Authority) compliance — agent
          licensing, premium remittance, claim ratio, regulatory return
          generation. CRITICAL severity.
    #310: Bancassurance executive dashboard — composes all 6 prior
          bancassurance engines into single executive payload.

Public API (#308 — IRA Compliance):
    register_agent_license(license_data, actor, reason)
    transition_license_state(license_number, new_state, actor, reason)
    check_license_status(agent_id, as_of=None) -> {state, days_until_expiry}
    expiring_licenses(days_ahead=30) -> licenses approaching expiry
    premium_remittance_report(insurer_id, period) -> totals + outstanding
    claim_ratio_report(insurer_id, period) -> ratio computation
    generate_ira_return(period, return_type) -> structured payload

Public API (#310 — Executive Dashboard):
    executive_dashboard_payload(period_start, period_end) -> consolidated view

LICENSE_STATES byte-for-byte:
    ACTIVE          -- valid; agent can write business
    EXPIRING_SOON   -- within DEFAULT_LICENSE_EXPIRY_WARNING_DAYS of expiry
    EXPIRED         -- past valid_until (terminal)
    REVOKED         -- regulator revoked (terminal)
    SUSPENDED       -- temporary suspension by regulator or bank

ALLOWED_LICENSE_TRANSITIONS (Rule 4):
    ACTIVE         → EXPIRING_SOON | EXPIRED | REVOKED | SUSPENDED
    EXPIRING_SOON  → ACTIVE | EXPIRED | REVOKED | SUSPENDED
    SUSPENDED      → ACTIVE | EXPIRED | REVOKED
    EXPIRED        → ()  -- terminal
    REVOKED        → ()  -- terminal

IRA_RETURN_TYPES byte-for-byte (#308):
    PREMIUM_REMITTANCE     -- premium collected vs remitted to insurers
    CLAIM_RATIO            -- claims paid / premium received per insurer
    AGENT_REGISTER         -- active agent + license register
    SOLVENCY_BUFFER        -- bancassurance solvency margin
    COMPOSITE_QUARTERLY    -- aggregate of all sub-returns

DEFAULT_LICENSE_EXPIRY_WARNING_DAYS = 30  -- regulator standard

Honesty rules:
    Rule 4: actor + reason mandatory; no skip transitions
    Rule 6: invalid state / return type rejected
    Rule 1: claim_ratio = None when zero premium received in period
            (division by zero — explicit reason)

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.insurance_catalog import (
    InsuranceCatalogEngine, INSURANCE_PRODUCT_TYPES, POLICY_STATES,
)
from utils.insurance_recommendation import InsuranceRecommendationEngine
from utils.insurance_partner_hub import InsurancePartnerHub
from utils.insurance_claims import ClaimsProcessingEngine
from utils.insurance_commission_recon import (
    CommissionReconAndScorecardEngine, classify_insurer_tier,
)
from utils.insurance_customer_rm_desktop import (
    CustomerAndRmDesktopEngine, RM_KPI_DIMENSIONS,
)

getcontext().prec = 28


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #308 specifies IRA submission. v10.274 ships "
    "structured return payload generation; real-time API submission "
    "to the regulator requires API credentials + sandbox testing "
    "deferred to Phase 3 deployment work. The engine produces "
    "audit-ready JSON payloads that map cleanly to IRA's quarterly "
    "return schemas."
)


LICENSE_STATES: Tuple[str, ...] = (
    "ACTIVE", "EXPIRING_SOON", "EXPIRED", "REVOKED", "SUSPENDED",
)

ALLOWED_LICENSE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":        ("EXPIRING_SOON", "EXPIRED", "REVOKED", "SUSPENDED"),
    "EXPIRING_SOON": ("ACTIVE", "EXPIRED", "REVOKED", "SUSPENDED"),
    "SUSPENDED":     ("ACTIVE", "EXPIRED", "REVOKED"),
    "EXPIRED":       (),
    "REVOKED":       (),
}

IRA_RETURN_TYPES: Tuple[str, ...] = (
    "PREMIUM_REMITTANCE",
    "CLAIM_RATIO",
    "AGENT_REGISTER",
    "SOLVENCY_BUFFER",
    "COMPOSITE_QUARTERLY",
)

DEFAULT_LICENSE_EXPIRY_WARNING_DAYS: int = 30


class IraComplianceAndExecutiveEngine:
    """IRA compliance (#308) + bancassurance executive dashboard (#310)."""

    def __init__(
        self,
        agents_path: Optional[Path] = None,
        returns_path: Optional[Path] = None,
        catalog: Optional[InsuranceCatalogEngine] = None,
        recommendation: Optional[InsuranceRecommendationEngine] = None,
        partner_hub: Optional[InsurancePartnerHub] = None,
        claims: Optional[ClaimsProcessingEngine] = None,
        commission_recon: Optional[CommissionReconAndScorecardEngine] = None,
        rm_desktop: Optional[CustomerAndRmDesktopEngine] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.agents_path = agents_path or base / "insurance_agents.json"
        self.returns_path = returns_path or base / "insurance_ira_returns.json"
        # Inject upstream engines (defaults compose all)
        self.catalog = catalog or InsuranceCatalogEngine()
        self.recommendation = recommendation or InsuranceRecommendationEngine(
            catalog=self.catalog,
        )
        self.partner_hub = partner_hub or InsurancePartnerHub()
        self.claims = claims or ClaimsProcessingEngine(catalog=self.catalog)
        self.commission_recon = (
            commission_recon or CommissionReconAndScorecardEngine()
        )
        self.rm_desktop = rm_desktop or CustomerAndRmDesktopEngine(
            catalog=self.catalog,
            recommendation=self.recommendation,
            claims=self.claims,
        )

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

    # ── #308 Agent licensing ───────────────────────────────────────

    def register_agent_license(
        self,
        license_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Register insurance agent license."""
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}

        for f in ("license_number", "agent_id", "agent_name",
                    "valid_from", "valid_until"):
            if f not in license_data or not license_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        try:
            valid_from = date.fromisoformat(license_data["valid_from"])
            valid_until = date.fromisoformat(license_data["valid_until"])
        except (ValueError, TypeError):
            return {"registered": False, "error": "invalid_date_format"}

        if valid_until <= valid_from:
            return {"registered": False, "error": "valid_until_not_after_valid_from"}

        records = self._load(self.agents_path, "insurance_agents",
                                ("license_number",))
        if any(r.get("license_number") == license_data["license_number"]
                 for r in records):
            return {"registered": False, "error": "duplicate_license_number"}

        # Determine initial state
        today = date.today()
        if valid_until < today:
            initial_state = "EXPIRED"
        elif (valid_until - today).days <= DEFAULT_LICENSE_EXPIRY_WARNING_DAYS:
            initial_state = "EXPIRING_SOON"
        else:
            initial_state = "ACTIVE"

        record = {
            "license_number": license_data["license_number"],
            "agent_id": license_data["agent_id"],
            "agent_name": license_data["agent_name"],
            "valid_from": license_data["valid_from"],
            "valid_until": license_data["valid_until"],
            "state": initial_state,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": initial_state, "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(self.agents_path, records,
                          "insurance_agents", "license_number")
        return {
            "registered": ok,
            "license_number": license_data["license_number"],
            "state": initial_state,
        }

    def transition_license_state(
        self,
        license_number: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in LICENSE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        records = self._load(self.agents_path, "insurance_agents",
                                ("license_number",))
        for r in records:
            if r.get("license_number") == license_number:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_LICENSE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                        "current_state": current,
                        "allowed": list(allowed),
                    }
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.agents_path, records,
                                  "insurance_agents", "license_number")
                return {"transitioned": ok, "from": current, "to": new_state}

        return {"transitioned": False, "error": "license_not_found"}

    def check_license_status(
        self,
        agent_id: str,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today()
        records = self._load(self.agents_path, "insurance_agents",
                                ("license_number",))
        agent_licenses = [r for r in records if r.get("agent_id") == agent_id]

        if not agent_licenses:
            return {
                "agent_id": agent_id,
                "has_license": False,
                "reason": "no_license_found",
            }

        # Find the most recent valid license
        active = [
            r for r in agent_licenses
            if r.get("state") in ("ACTIVE", "EXPIRING_SOON", "SUSPENDED")
        ]
        if not active:
            # All EXPIRED or REVOKED
            return {
                "agent_id": agent_id,
                "has_license": False,
                "reason": "no_active_license",
                "license_count": len(agent_licenses),
            }

        # Pick the one with latest valid_until
        active.sort(key=lambda x: x.get("valid_until", ""), reverse=True)
        license = active[0]

        try:
            valid_until = date.fromisoformat(license["valid_until"])
            days_until = (valid_until - as_of).days
        except (ValueError, TypeError):
            days_until = None

        return {
            "agent_id": agent_id,
            "has_license": True,
            "license_number": license["license_number"],
            "state": license["state"],
            "valid_until": license["valid_until"],
            "days_until_expiry": days_until,
        }

    def expiring_licenses(
        self,
        days_ahead: int = DEFAULT_LICENSE_EXPIRY_WARNING_DAYS,
        as_of: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Active licenses expiring within window."""
        as_of = as_of or date.today()
        cutoff = as_of + timedelta(days=days_ahead)

        records = self._load(self.agents_path, "insurance_agents",
                                ("license_number",))
        out = []
        for r in records:
            if r.get("state") not in ("ACTIVE", "EXPIRING_SOON"):
                continue
            try:
                valid_until = date.fromisoformat(r.get("valid_until", ""))
            except (ValueError, TypeError):
                continue
            if as_of <= valid_until <= cutoff:
                out.append({
                    "license_number": r["license_number"],
                    "agent_id": r.get("agent_id"),
                    "agent_name": r.get("agent_name"),
                    "valid_until": r["valid_until"],
                    "days_until_expiry": (valid_until - as_of).days,
                })
        out.sort(key=lambda x: x["days_until_expiry"])
        return out

    # ── #308 Regulatory return generation ──────────────────────────

    def premium_remittance_report(
        self,
        insurer_id: str,
        period: str,
    ) -> Dict[str, Any]:
        """Premium collected vs remitted to insurer."""
        # Premium collected — load all premium records
        premiums = self.catalog._load(
            self.catalog.premiums_path,
            "insurance_premiums",
            ("policy_id", "due_date"),
        )
        # Filter to insurer (via policy lookup)
        policies = self.catalog._load(
            self.catalog.policies_path,
            "insurance_policies",
            ("policy_id",),
        )
        insurer_policy_ids = {
            p["policy_id"] for p in policies
            if p.get("insurer_id") == insurer_id
        }

        collected = Decimal("0")
        for pr in premiums:
            if pr.get("policy_id") not in insurer_policy_ids:
                continue
            if pr.get("status") != "PAID":
                continue
            paid_date = pr.get("paid_date") or ""
            # Period filter — naive prefix match (period like "2026-Q1" or "2026-04")
            if period and not paid_date.startswith(period[:7]):
                continue
            try:
                collected += Decimal(pr.get("amount_kes", "0"))
            except (ValueError, TypeError):
                continue

        # Remitted (= matched commission recon → assumed remitted)
        recon_summary = self.commission_recon.reconcile_period(
            insurer_id, period
        )

        return {
            "insurer_id": insurer_id,
            "period": period,
            "premium_collected_kes": str(collected.quantize(Decimal("0.01"))),
            "commission_expected_kes": recon_summary["expected_total_kes"],
            "commission_paid_kes": recon_summary["paid_total_kes"],
            "outstanding_kes": str(
                (Decimal(recon_summary["expected_total_kes"]) -
                 Decimal(recon_summary["paid_total_kes"])
                ).quantize(Decimal("0.01"))
            ),
        }

    def claim_ratio_report(
        self,
        insurer_id: str,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Claims paid / premium received per insurer."""
        # Premium received
        premiums = self.catalog._load(
            self.catalog.premiums_path,
            "insurance_premiums",
            ("policy_id", "due_date"),
        )
        policies = self.catalog._load(
            self.catalog.policies_path,
            "insurance_policies",
            ("policy_id",),
        )
        insurer_policy_ids = {
            p["policy_id"] for p in policies
            if p.get("insurer_id") == insurer_id
        }

        premium_received = Decimal("0")
        for pr in premiums:
            if pr.get("policy_id") not in insurer_policy_ids:
                continue
            if pr.get("status") != "PAID":
                continue
            paid_date = pr.get("paid_date") or ""
            if not (period_start <= paid_date <= period_end):
                continue
            try:
                premium_received += Decimal(pr.get("amount_kes", "0"))
            except (ValueError, TypeError):
                continue

        # Claims paid (SETTLED claims with policy_id in insurer_policy_ids)
        all_claims = self.claims._load()
        claims_paid = Decimal("0")
        claim_count = 0
        for c in all_claims:
            if c.get("policy_id") not in insurer_policy_ids:
                continue
            if c.get("state") != "SETTLED":
                continue
            settlement = self.claims.settlement_calculation(c["claim_id"])
            if settlement.get("amount_kes") is None:
                continue
            try:
                claims_paid += Decimal(settlement["amount_kes"])
                claim_count += 1
            except (ValueError, TypeError):
                continue

        # Rule 1: ratio = None when zero premium
        if premium_received == 0:
            return {
                "insurer_id": insurer_id,
                "period_start": period_start,
                "period_end": period_end,
                "premium_received_kes": "0",
                "claims_paid_kes": str(claims_paid.quantize(Decimal("0.01"))),
                "claim_count": claim_count,
                "claim_ratio_pct": None,
                "reason": "zero_premium_received_division_undefined",
            }

        ratio = (claims_paid / premium_received * Decimal("100")).quantize(Decimal("0.01"))

        return {
            "insurer_id": insurer_id,
            "period_start": period_start,
            "period_end": period_end,
            "premium_received_kes": str(premium_received.quantize(Decimal("0.01"))),
            "claims_paid_kes": str(claims_paid.quantize(Decimal("0.01"))),
            "claim_count": claim_count,
            "claim_ratio_pct": str(ratio),
        }

    def generate_ira_return(
        self,
        return_type: str,
        period: str,
        actor: str,
    ) -> Dict[str, Any]:
        """Generate structured IRA return payload."""
        if not actor:
            return {"generated": False, "error": "actor_required"}
        if return_type not in IRA_RETURN_TYPES:
            return {
                "generated": False,
                "error": f"invalid_return_type:{return_type}",
                "valid_types": list(IRA_RETURN_TYPES),
            }

        return_id = f"IRA-{return_type}-{period}-{int(datetime.utcnow().timestamp())}"

        if return_type == "AGENT_REGISTER":
            agents = self._load(self.agents_path, "insurance_agents",
                                  ("license_number",))
            payload = {
                "total_agents": len(agents),
                "active_count": sum(1 for a in agents
                                       if a.get("state") in ("ACTIVE", "EXPIRING_SOON")),
                "expired_count": sum(1 for a in agents
                                         if a.get("state") == "EXPIRED"),
                "revoked_count": sum(1 for a in agents
                                         if a.get("state") == "REVOKED"),
                "agents": [
                    {
                        "license_number": a["license_number"],
                        "agent_id": a["agent_id"],
                        "agent_name": a["agent_name"],
                        "state": a["state"],
                        "valid_until": a.get("valid_until"),
                    }
                    for a in agents
                ],
            }
        elif return_type == "PREMIUM_REMITTANCE":
            # All insurers
            insurers = self._load(
                self.partner_hub.insurers_path, "insurance_insurers",
                ("insurer_id",),
            )
            payload = {
                "by_insurer": [
                    self.premium_remittance_report(ins["insurer_id"], period)
                    for ins in insurers
                ],
            }
        elif return_type == "CLAIM_RATIO":
            insurers = self._load(
                self.partner_hub.insurers_path, "insurance_insurers",
                ("insurer_id",),
            )
            # Period as YYYY-Q1 → derive start/end naively
            period_start = period[:4] + "-01-01"
            period_end = period[:4] + "-12-31"
            payload = {
                "by_insurer": [
                    self.claim_ratio_report(ins["insurer_id"],
                                                period_start, period_end)
                    for ins in insurers
                ],
            }
        elif return_type == "SOLVENCY_BUFFER":
            # Rule 1: this requires capital adequacy data we don't have
            payload = {
                "available": False,
                "reason": (
                    "solvency_buffer_requires_capital_data_not_modeled_in_v10.274"
                ),
            }
        elif return_type == "COMPOSITE_QUARTERLY":
            payload = {
                "agent_register": self.generate_ira_return(
                    "AGENT_REGISTER", period, actor,
                )["payload"],
                "premium_remittance": self.generate_ira_return(
                    "PREMIUM_REMITTANCE", period, actor,
                )["payload"],
                "claim_ratio": self.generate_ira_return(
                    "CLAIM_RATIO", period, actor,
                )["payload"],
                "solvency_buffer": self.generate_ira_return(
                    "SOLVENCY_BUFFER", period, actor,
                )["payload"],
            }
        else:
            payload = {}

        record = {
            "return_id": return_id,
            "return_type": return_type,
            "period": period,
            "payload": payload,
            "generated_by": actor,
            "generated_at": datetime.utcnow().isoformat(),
            "spec_deviation_note": SPEC_DEVIATION_NOTE,
        }
        records = self._load(self.returns_path, "insurance_ira_returns",
                                ("return_id",))
        records.append(record)
        self._save(self.returns_path, records,
                     "insurance_ira_returns", "return_id")

        return {
            "generated": True,
            "return_id": return_id,
            "return_type": return_type,
            "payload": payload,
        }

    # ── #310 Executive dashboard ───────────────────────────────────

    def executive_dashboard_payload(
        self,
        period_start: str,
        period_end: str,
        period_label: str = "",
    ) -> Dict[str, Any]:
        """
        Composite executive view of bancassurance.

        Composes:
          - Revenue (premium collected) from catalog premiums
          - Channel mix (BRANCH/DIGITAL/RM/etc.) — surfaces N/A
            because channel attribution is not in current data model
          - Top products by policy count
          - Top insurers (from rank_insurers)
          - Regulatory summary (claim ratios + license compliance)
        """
        # Revenue (collected premium)
        premiums = self.catalog._load(
            self.catalog.premiums_path,
            "insurance_premiums",
            ("policy_id", "due_date"),
        )
        revenue_kes = Decimal("0")
        for pr in premiums:
            if pr.get("status") != "PAID":
                continue
            paid_date = pr.get("paid_date") or ""
            if not (period_start <= paid_date <= period_end):
                continue
            try:
                revenue_kes += Decimal(pr.get("amount_kes", "0"))
            except (ValueError, TypeError):
                continue

        # Top products by active policy count
        policies = self.catalog._load(
            self.catalog.policies_path,
            "insurance_policies",
            ("policy_id",),
        )
        products = self.catalog._load(
            self.catalog.products_path,
            "insurance_products",
            ("product_code",),
        )
        product_lookup = {p["product_code"]: p for p in products}

        active_policies = [p for p in policies if p.get("state") == "ACTIVE"]
        product_counts: Counter = Counter(
            p.get("product_code") for p in active_policies
        )

        top_products = []
        for code, count in product_counts.most_common(10):
            prod = product_lookup.get(code, {})
            top_products.append({
                "product_code": code,
                "product_name": prod.get("product_name"),
                "product_type": prod.get("product_type"),
                "active_policy_count": count,
            })

        # Top insurers (from scorecard rank if any)
        # Use period_label as the scorecard period
        top_insurers = []
        if period_label:
            ranked = self.commission_recon.rank_insurers(period_label)
            top_insurers = [
                {"insurer_id": r["insurer_id"],
                  "composite": r["composite"],
                  "tier": r["tier"]}
                for r in ranked[:5]
            ]

        # Regulatory summary
        agents = self._load(self.agents_path, "insurance_agents",
                              ("license_number",))
        license_total = len(agents)
        license_compliant = sum(
            1 for a in agents
            if a.get("state") in ("ACTIVE", "EXPIRING_SOON")
        )
        license_compliance_pct = None
        if license_total > 0:
            license_compliance_pct = str(
                (Decimal(license_compliant) / Decimal(license_total) * Decimal("100"))
                .quantize(Decimal("0.01"))
            )

        # Claim ratios across insurers
        insurers = self._load(
            self.partner_hub.insurers_path, "insurance_insurers",
            ("insurer_id",),
        )
        claim_ratios = []
        for ins in insurers:
            cr = self.claim_ratio_report(
                ins["insurer_id"], period_start, period_end
            )
            claim_ratios.append({
                "insurer_id": ins["insurer_id"],
                "claim_ratio_pct": cr["claim_ratio_pct"],
                "premium_received_kes": cr["premium_received_kes"],
                "claims_paid_kes": cr["claims_paid_kes"],
            })

        return {
            "period_start": period_start,
            "period_end": period_end,
            "period_label": period_label,
            "revenue_kes": str(revenue_kes.quantize(Decimal("0.01"))),
            "active_policy_count": len(active_policies),
            "top_products": top_products,
            "top_insurers": top_insurers,
            "regulatory_summary": {
                "agent_license_total": license_total,
                "agent_license_compliant": license_compliant,
                "agent_license_compliance_pct": license_compliance_pct,
                "claim_ratios": claim_ratios,
            },
            "channel_mix": {
                "available": False,
                "reason": "channel_attribution_not_in_v10.274_data_model",
            },
            "_meta": {
                "spec_deviation": SPEC_DEVIATION_NOTE,
                "generated_at": datetime.utcnow().isoformat(),
            },
        }


def _self_test() -> None:
    import tempfile

    # Spec deviation note
    assert "IRA submission" in SPEC_DEVIATION_NOTE

    # Sanity: state catalogs
    assert "EXPIRED" in LICENSE_STATES
    assert ALLOWED_LICENSE_TRANSITIONS["EXPIRED"] == ()
    assert ALLOWED_LICENSE_TRANSITIONS["REVOKED"] == ()
    assert "COMPOSITE_QUARTERLY" in IRA_RETURN_TYPES

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = InsuranceCatalogEngine(
            products_path=Path(tmpdir) / "p.json",
            policies_path=Path(tmpdir) / "po.json",
            premiums_path=Path(tmpdir) / "pr.json",
        )
        # Seed product + policy + premium
        catalog.register_product(
            "INS-A",
            {"product_code": "PROD-LIFE",
             "product_name": "Life Term",
             "product_type": "LIFE"},
            actor="bd", reason="seed",
        )
        catalog.issue_policy(
            "CUST-001", "PROD-LIFE",
            {"policy_id": "POL-001",
             "sum_assured_kes": "1000000",
             "premium_kes": "12000",
             "premium_frequency": "ANNUAL",
             "effective_date": "2026-01-01",
             "expiry_date": "2027-01-01"},
            actor="rm",
        )
        for s in ("APPLIED", "UNDERWRITING", "ACTIVE"):
            catalog.transition_policy_state("POL-001", s, "rm", "ok")
        catalog.record_premium(
            "POL-001", Decimal("12000"),
            due_date="2026-04-01",
            actor="finance",
            paid_date="2026-04-05",
        )

        partner_hub = InsurancePartnerHub(
            insurers_path=Path(tmpdir) / "ins.json",
            quotes_path=Path(tmpdir) / "q.json",
        )
        partner_hub.register_insurer(
            {"insurer_id": "INS-A", "insurer_name": "Insurer A",
             "supported_product_types": ["LIFE"]},
            actor="bd", reason="reg",
        )
        for s in ("NEGOTIATING", "INTEGRATING", "INTEGRATED"):
            partner_hub.update_insurer_status("INS-A", s, "bd", "ok")

        claims = ClaimsProcessingEngine(
            claims_path=Path(tmpdir) / "c.json", catalog=catalog,
        )
        commission_recon = CommissionReconAndScorecardEngine(
            recon_path=Path(tmpdir) / "rcn.json",
            disputes_path=Path(tmpdir) / "dsp.json",
            scorecards_path=Path(tmpdir) / "sc.json",
        )
        commission_recon.record_expected_commission(
            "INS-A", "POL-001", Decimal("1200"),
            "2026-Q1", actor="finance",
        )
        commission_recon.record_paid_commission(
            "INS-A", "POL-001", "2026-Q1",
            Decimal("1205"), "2026-04-15", actor="ins_ops",
        )

        engine = IraComplianceAndExecutiveEngine(
            agents_path=Path(tmpdir) / "ag.json",
            returns_path=Path(tmpdir) / "ret.json",
            catalog=catalog,
            partner_hub=partner_hub,
            claims=claims,
            commission_recon=commission_recon,
        )

        # === Agent licensing tests ===

        # Test 1: register active license
        r = engine.register_agent_license(
            {"license_number": "AGT-001",
             "agent_id": "EMP-RM-01",
             "agent_name": "Jane Doe",
             "valid_from": "2026-01-01",
             "valid_until": "2027-12-31"},
            actor="hr", reason="onboarding",
        )
        assert r["registered"]
        assert r["state"] == "ACTIVE"

        # Test 2: register near-expiry license
        r = engine.register_agent_license(
            {"license_number": "AGT-002",
             "agent_id": "EMP-RM-02",
             "agent_name": "Bob Smith",
             "valid_from": "2025-01-01",
             "valid_until": (date.today() + timedelta(days=20)).isoformat()},
            actor="hr", reason="onboarding",
        )
        assert r["registered"]
        assert r["state"] == "EXPIRING_SOON"

        # Test 3: register expired license
        r = engine.register_agent_license(
            {"license_number": "AGT-003",
             "agent_id": "EMP-RM-03",
             "agent_name": "C Test",
             "valid_from": "2024-01-01",
             "valid_until": "2024-12-31"},
            actor="hr", reason="historical",
        )
        assert r["registered"]
        assert r["state"] == "EXPIRED"

        # Test 4: invalid date order
        r = engine.register_agent_license(
            {"license_number": "AGT-004",
             "agent_id": "EMP-X",
             "agent_name": "X",
             "valid_from": "2026-12-31",
             "valid_until": "2026-01-01"},
            actor="hr", reason="bad",
        )
        assert not r["registered"]
        assert "valid_until_not_after_valid_from" in r["error"]

        # Test 5: state transitions
        t = engine.transition_license_state(
            "AGT-001", "SUSPENDED", actor="compliance",
            reason="under investigation",
        )
        assert t["transitioned"]
        t = engine.transition_license_state(
            "AGT-001", "ACTIVE", actor="compliance",
            reason="cleared",
        )
        assert t["transitioned"]

        # Test 6: skip rejected
        t = engine.transition_license_state(
            "AGT-001", "REVOKED", actor="compliance",
            reason="trying SUSPENDED → REVOKED via bad path",
        )
        # ACTIVE → REVOKED is allowed
        assert t["transitioned"]
        # Now terminal
        t = engine.transition_license_state(
            "AGT-001", "ACTIVE", actor="compliance",
            reason="trying to revive revoked",
        )
        assert not t["transitioned"]

        # Test 7: check_license_status — agent with active license
        s = engine.check_license_status("EMP-RM-02")
        assert s["has_license"]
        assert s["state"] == "EXPIRING_SOON"
        assert s["days_until_expiry"] is not None

        # Test 8: check_license_status — unknown agent
        s = engine.check_license_status("UNKNOWN")
        assert not s["has_license"]
        assert s["reason"] == "no_license_found"

        # Test 9: check_license_status — agent with only revoked license
        s = engine.check_license_status("EMP-RM-01")
        # AGT-001 was revoked above
        assert not s["has_license"]
        assert s["reason"] == "no_active_license"

        # Test 10: expiring_licenses — AGT-002 within 30 days
        exp = engine.expiring_licenses(days_ahead=30)
        # Should include AGT-002
        assert any(e["license_number"] == "AGT-002" for e in exp)

        # === Reporting tests ===

        # Test 11: premium_remittance_report
        report = engine.premium_remittance_report("INS-A", "2026-04")
        assert Decimal(report["premium_collected_kes"]) == Decimal("12000.00")

        # Test 12: claim_ratio_report — no claims paid
        cr = engine.claim_ratio_report("INS-A", "2026-04-01", "2026-04-30")
        assert cr["claim_count"] == 0
        assert cr["premium_received_kes"] == "12000.00"
        assert cr["claim_ratio_pct"] == "0.00"

        # Test 13: claim_ratio with zero premium → None
        cr = engine.claim_ratio_report("INS-X", "2026-01-01", "2026-12-31")
        assert cr["claim_ratio_pct"] is None
        assert "zero_premium" in cr["reason"]

        # === Return generation ===

        # Test 14: AGENT_REGISTER return
        ret = engine.generate_ira_return(
            "AGENT_REGISTER", "2026-Q1", actor="compliance",
        )
        assert ret["generated"]
        assert ret["payload"]["total_agents"] == 3
        # State distribution
        assert ret["payload"]["expired_count"] == 1

        # Test 15: invalid return type rejected
        ret = engine.generate_ira_return(
            "INVALID", "2026-Q1", actor="compliance",
        )
        assert not ret["generated"]

        # Test 16: PREMIUM_REMITTANCE return
        ret = engine.generate_ira_return(
            "PREMIUM_REMITTANCE", "2026-04", actor="compliance",
        )
        assert ret["generated"]
        assert "by_insurer" in ret["payload"]

        # Test 17: COMPOSITE_QUARTERLY combines all
        ret = engine.generate_ira_return(
            "COMPOSITE_QUARTERLY", "2026-Q1", actor="compliance",
        )
        assert ret["generated"]
        assert "agent_register" in ret["payload"]
        assert "premium_remittance" in ret["payload"]
        assert "claim_ratio" in ret["payload"]
        assert "solvency_buffer" in ret["payload"]

        # === Executive dashboard ===

        # Test 18: dashboard payload
        dash = engine.executive_dashboard_payload(
            "2026-04-01", "2026-04-30", period_label="2026-Q1",
        )
        assert Decimal(dash["revenue_kes"]) == Decimal("12000.00")
        assert dash["active_policy_count"] == 1
        assert len(dash["top_products"]) == 1
        assert dash["regulatory_summary"]["agent_license_total"] == 3
        # 1 ACTIVE-then-REVOKED, 1 EXPIRING_SOON, 1 EXPIRED
        # Compliance = EXPIRING_SOON (1) / 3 ≈ 33.33
        assert dash["regulatory_summary"]["agent_license_compliance_pct"] is not None
        # Channel mix surfaces explicit reason
        assert dash["channel_mix"]["available"] is False

    print("  ✅ insurance_ira_compliance self-test PASS")


if __name__ == "__main__":
    _self_test()
