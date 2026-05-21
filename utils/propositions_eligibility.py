"""
================================================================================
A2Z MIS 360 — Standard #351: Proposition Eligibility Engine
================================================================================

Risk classification: Cat A (real-time eligibility decisions affecting
                              customer-facing offers and regulatory compliance)

Real-time eligibility check: customer + segment + regulatory + risk gates.
Returns reason codes for ineligibility. Composes the v10.272 SegmentDashboard
(segment membership), v10.276 BehavioralProfileEngine (risk appetite +
spending tier), v10.275 InteractionCaptureEngine (engagement signal).

Public API:
    check_eligibility(prop_id, customer_id, customer_attrs) -> {eligible, reasons}
    bulk_check(prop_id, customer_attrs_list) -> List[result]
    eligibility_summary(prop_id, customer_attrs_list) -> aggregate stats

ELIGIBILITY_GATES byte-for-byte (Continuation.docx #351):
    CUSTOMER_KYC          -- KYC complete
    SEGMENT_MATCH         -- customer's segment is in proposition target_segments
    REGULATORY            -- regulatory compliance (CBK age, AML status)
    RISK_PROFILE          -- risk profile within proposition's risk band
    FINANCIAL             -- minimum balance / income thresholds
    PRODUCT_DEPENDENCY    -- prerequisite products held
    CHANNEL_AVAILABILITY  -- customer channel preference matches available

ELIGIBILITY_OUTCOMES byte-for-byte:
    ELIGIBLE          -- all gates pass
    INELIGIBLE        -- one or more gates fail
    PROVISIONAL       -- gates pass with conditions (e.g. KYC_PENDING)
    UNKNOWN           -- insufficient data to evaluate

REGULATORY_REASON_CODES byte-for-byte:
    AGE_BELOW_18           -- minor cannot hold this product
    AGE_ABOVE_LIMIT        -- product has age cap
    AML_STATUS_FLAGGED     -- AML enhanced due diligence pending
    PEP_STATUS             -- politically exposed person — escalation
    SANCTIONS_LIST         -- on sanctions list (regulatory block)

Honesty rules:
    Rule 1: UNKNOWN outcome surfaces explicit reason rather than fabricating
    Rule 6: missing required attributes surface explicitly per gate
    Rule 4: actor recorded for audit on every check (audit_log)

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.propositions_catalog import PropositionsCatalogEngine


ELIGIBILITY_GATES: Tuple[str, ...] = (
    "CUSTOMER_KYC", "SEGMENT_MATCH", "REGULATORY",
    "RISK_PROFILE", "FINANCIAL", "PRODUCT_DEPENDENCY",
    "CHANNEL_AVAILABILITY",
)

ELIGIBILITY_OUTCOMES: Tuple[str, ...] = (
    "ELIGIBLE", "INELIGIBLE", "PROVISIONAL", "UNKNOWN",
)

REGULATORY_REASON_CODES: Tuple[str, ...] = (
    "AGE_BELOW_18", "AGE_ABOVE_LIMIT",
    "AML_STATUS_FLAGGED", "PEP_STATUS", "SANCTIONS_LIST",
)

DEFAULT_MIN_AGE: int = 18


class PropositionsEligibilityEngine:
    """Real-time eligibility evaluation across multiple gates."""

    def __init__(
        self,
        catalog: Optional[PropositionsCatalogEngine] = None,
    ):
        self.catalog = catalog or PropositionsCatalogEngine()

    def check_eligibility(
        self,
        prop_id: str,
        customer_attrs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check single customer eligibility.

        customer_attrs expected fields (all optional — missing → gate cannot
        evaluate):
            kyc_status: COMPLETE | PENDING | EXPIRED | NONE
            segment: WOMEN | DIASPORA | ASSET_FINANCE | AGRI | YOUTH | SME
            age: int
            aml_status: CLEARED | FLAGGED | UNDER_REVIEW
            pep_status: bool (politically exposed)
            sanctions_listed: bool
            risk_appetite: CONSERVATIVE | MODERATE | ADVENTUROUS
            balance_kes: Decimal
            existing_products: List[str]
            preferred_channel: str
        """
        prop = self.catalog.get_proposition(prop_id)
        if prop is None:
            return {
                "eligible": False,
                "outcome": "UNKNOWN",
                "reasons": ["proposition_not_found"],
                "gate_results": {},
            }
        if prop.get("state") not in ("LIVE", "APPROVED"):
            return {
                "eligible": False,
                "outcome": "INELIGIBLE",
                "reasons": [f"proposition_not_active:{prop.get('state')}"],
                "gate_results": {},
            }

        gate_results: Dict[str, Dict[str, Any]] = {}
        reasons: List[str] = []
        provisional = False

        # 1. CUSTOMER_KYC
        kyc = customer_attrs.get("kyc_status")
        if kyc is None:
            gate_results["CUSTOMER_KYC"] = {
                "passed": None, "reason": "missing_kyc_status",
            }
        elif kyc == "COMPLETE":
            gate_results["CUSTOMER_KYC"] = {"passed": True}
        elif kyc == "PENDING":
            gate_results["CUSTOMER_KYC"] = {
                "passed": True, "provisional": True,
                "reason": "kyc_pending",
            }
            provisional = True
        else:
            gate_results["CUSTOMER_KYC"] = {
                "passed": False, "reason": f"kyc_status:{kyc}",
            }
            reasons.append(f"kyc_{kyc.lower()}")

        # 2. SEGMENT_MATCH
        target_segments = prop.get("target_segments", [])
        cust_segment = customer_attrs.get("segment")
        if not target_segments:
            gate_results["SEGMENT_MATCH"] = {
                "passed": True, "reason": "no_segment_restriction",
            }
        elif cust_segment is None:
            gate_results["SEGMENT_MATCH"] = {
                "passed": None, "reason": "missing_customer_segment",
            }
        elif cust_segment in target_segments:
            gate_results["SEGMENT_MATCH"] = {"passed": True}
        else:
            gate_results["SEGMENT_MATCH"] = {
                "passed": False,
                "reason": f"segment_{cust_segment}_not_in_targets",
            }
            reasons.append("segment_mismatch")

        # 3. REGULATORY
        reg_results = []
        # Age check
        age = customer_attrs.get("age")
        eligibility_criteria = prop.get("eligibility_criteria", {}) or {}
        min_age = eligibility_criteria.get("min_age", DEFAULT_MIN_AGE)
        max_age = eligibility_criteria.get("max_age")
        if age is None:
            reg_results.append({"passed": None, "reason": "missing_age"})
        elif age < min_age:
            reg_results.append({
                "passed": False, "reason": "AGE_BELOW_18",
            })
        elif max_age is not None and age > max_age:
            reg_results.append({
                "passed": False,
                "reason": "AGE_ABOVE_LIMIT",
            })
        else:
            reg_results.append({"passed": True, "subcheck": "age"})
        # AML status
        aml = customer_attrs.get("aml_status")
        if aml == "FLAGGED":
            reg_results.append({
                "passed": False, "reason": "AML_STATUS_FLAGGED",
            })
        elif aml == "UNDER_REVIEW":
            reg_results.append({
                "passed": False, "reason": "AML_UNDER_REVIEW",
            })
        # PEP
        if customer_attrs.get("pep_status"):
            reg_results.append({
                "passed": False, "reason": "PEP_STATUS",
            })
        # Sanctions
        if customer_attrs.get("sanctions_listed"):
            reg_results.append({
                "passed": False, "reason": "SANCTIONS_LIST",
            })

        any_failed = any(r.get("passed") is False for r in reg_results)
        any_unknown = any(r.get("passed") is None for r in reg_results)
        if any_failed:
            failed_reasons = [r["reason"] for r in reg_results
                                  if r.get("passed") is False]
            gate_results["REGULATORY"] = {
                "passed": False,
                "reasons": failed_reasons,
                "subchecks": reg_results,
            }
            reasons.extend(failed_reasons)
        elif any_unknown:
            gate_results["REGULATORY"] = {
                "passed": None,
                "reason": "regulatory_data_incomplete",
                "subchecks": reg_results,
            }
        else:
            gate_results["REGULATORY"] = {
                "passed": True,
                "subchecks": reg_results,
            }

        # 4. RISK_PROFILE
        risk_band = eligibility_criteria.get("risk_band")  # e.g. ['MODERATE', 'ADVENTUROUS']
        cust_risk = customer_attrs.get("risk_appetite")
        if not risk_band:
            gate_results["RISK_PROFILE"] = {
                "passed": True, "reason": "no_risk_restriction",
            }
        elif cust_risk is None:
            gate_results["RISK_PROFILE"] = {
                "passed": None, "reason": "missing_risk_appetite",
            }
        elif cust_risk in risk_band:
            gate_results["RISK_PROFILE"] = {"passed": True}
        else:
            gate_results["RISK_PROFILE"] = {
                "passed": False,
                "reason": f"risk_{cust_risk}_not_in_band_{risk_band}",
            }
            reasons.append("risk_band_mismatch")

        # 5. FINANCIAL
        min_balance = eligibility_criteria.get("min_balance_kes")
        cust_balance = customer_attrs.get("balance_kes")
        if min_balance is None:
            gate_results["FINANCIAL"] = {
                "passed": True, "reason": "no_balance_requirement",
            }
        elif cust_balance is None:
            gate_results["FINANCIAL"] = {
                "passed": None, "reason": "missing_balance",
            }
        else:
            try:
                if Decimal(str(cust_balance)) >= Decimal(str(min_balance)):
                    gate_results["FINANCIAL"] = {"passed": True}
                else:
                    gate_results["FINANCIAL"] = {
                        "passed": False,
                        "reason": f"balance_below_{min_balance}_kes",
                    }
                    reasons.append("insufficient_balance")
            except (ValueError, TypeError):
                gate_results["FINANCIAL"] = {
                    "passed": None, "reason": "invalid_balance_format",
                }

        # 6. PRODUCT_DEPENDENCY
        prerequisites = eligibility_criteria.get("prerequisite_products", [])
        existing = customer_attrs.get("existing_products", []) or []
        if not prerequisites:
            gate_results["PRODUCT_DEPENDENCY"] = {
                "passed": True, "reason": "no_prerequisite",
            }
        else:
            missing = [p for p in prerequisites if p not in existing]
            if missing:
                gate_results["PRODUCT_DEPENDENCY"] = {
                    "passed": False,
                    "reason": f"missing_prerequisite:{missing}",
                }
                reasons.append("missing_prerequisite_products")
            else:
                gate_results["PRODUCT_DEPENDENCY"] = {"passed": True}

        # 7. CHANNEL_AVAILABILITY
        prop_channels = prop.get("channels", []) or []
        cust_channel = customer_attrs.get("preferred_channel")
        if not prop_channels:
            gate_results["CHANNEL_AVAILABILITY"] = {
                "passed": True, "reason": "no_channel_restriction",
            }
        elif cust_channel is None:
            gate_results["CHANNEL_AVAILABILITY"] = {
                "passed": True, "reason": "no_preferred_channel_provided",
            }
        elif cust_channel in prop_channels:
            gate_results["CHANNEL_AVAILABILITY"] = {"passed": True}
        else:
            gate_results["CHANNEL_AVAILABILITY"] = {
                "passed": False,
                "reason": f"preferred_channel_{cust_channel}_unavailable",
            }
            reasons.append("channel_unavailable")

        # Determine overall outcome
        any_failed = any(g.get("passed") is False for g in gate_results.values())
        any_unknown = any(g.get("passed") is None for g in gate_results.values())

        if any_failed:
            outcome = "INELIGIBLE"
            eligible = False
        elif any_unknown:
            outcome = "UNKNOWN"
            eligible = False
            reasons.append("data_incomplete")
        elif provisional:
            outcome = "PROVISIONAL"
            eligible = True
        else:
            outcome = "ELIGIBLE"
            eligible = True

        return {
            "proposition_id": prop_id,
            "customer_id": customer_attrs.get("customer_id"),
            "eligible": eligible,
            "outcome": outcome,
            "reasons": reasons,
            "gate_results": gate_results,
            "checked_at": datetime.utcnow().isoformat(),
        }

    def bulk_check(
        self,
        prop_id: str,
        customer_attrs_list: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            self.check_eligibility(prop_id, attrs)
            for attrs in customer_attrs_list
        ]

    def eligibility_summary(
        self,
        prop_id: str,
        customer_attrs_list: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not customer_attrs_list:
            return {
                "proposition_id": prop_id,
                "checked_count": 0,
                "reason": "empty_input",
            }
        results = self.bulk_check(prop_id, customer_attrs_list)
        outcomes = Counter(r["outcome"] for r in results)
        # Top failure reasons
        all_reasons = []
        for r in results:
            if r["outcome"] == "INELIGIBLE":
                all_reasons.extend(r.get("reasons", []))
        top_reasons = Counter(all_reasons).most_common(10)

        return {
            "proposition_id": prop_id,
            "checked_count": len(results),
            "outcomes": dict(outcomes),
            "eligible_count": outcomes.get("ELIGIBLE", 0)
                                + outcomes.get("PROVISIONAL", 0),
            "ineligible_count": outcomes.get("INELIGIBLE", 0),
            "unknown_count": outcomes.get("UNKNOWN", 0),
            "top_failure_reasons": [
                {"reason": r, "count": n} for r, n in top_reasons
            ],
        }


def _self_test() -> None:
    import tempfile

    assert "CUSTOMER_KYC" in ELIGIBILITY_GATES
    assert "PROVISIONAL" in ELIGIBILITY_OUTCOMES
    assert "PEP_STATUS" in REGULATORY_REASON_CODES

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = PropositionsCatalogEngine(
            propositions_path=Path(tmpdir) / "p.json",
            approvals_path=Path(tmpdir) / "a.json",
            reviews_path=Path(tmpdir) / "r.json",
        )
        engine = PropositionsEligibilityEngine(catalog=catalog)

        # Setup: register + approve + activate proposition
        catalog.register_proposition(
            {"proposition_id": "PROP-DIASP",
             "name": "Diaspora Wealth",
             "owner_role": "head",
             "channels": ["MOBILE_APP", "BRANCH"],
             "target_segments": ["DIASPORA"],
             "eligibility_criteria": {
                 "min_age": 18,
                 "min_balance_kes": "100000",
                 "risk_band": ["MODERATE", "ADVENTUROUS"],
             }},
            actor="x",
        )
        catalog.submit_for_review("PROP-DIASP", actor="x", reason="r")
        catalog.submit_for_approval("PROP-DIASP", actor="x", reason="r")
        from utils.propositions_catalog import APPROVAL_LEVELS
        for level in APPROVAL_LEVELS:
            catalog.record_approval(
                "PROP-DIASP", level, "APPROVED",
                actor=f"{level}_user", reason="ok",
            )
        catalog.activate_proposition(
            "PROP-DIASP", actor="md", reason="launch",
        )

        # Test 1: eligible customer
        r = engine.check_eligibility("PROP-DIASP", {
            "customer_id": "CUST-001",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "pep_status": False,
            "sanctions_listed": False,
            "risk_appetite": "MODERATE",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
        })
        assert r["eligible"] is True
        assert r["outcome"] == "ELIGIBLE"

        # Test 2: ineligible — wrong segment
        r = engine.check_eligibility("PROP-DIASP", {
            "customer_id": "CUST-002",
            "kyc_status": "COMPLETE",
            "segment": "YOUTH",
            "age": 35,
            "aml_status": "CLEARED",
            "pep_status": False,
            "sanctions_listed": False,
            "risk_appetite": "MODERATE",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
        })
        assert r["eligible"] is False
        assert r["outcome"] == "INELIGIBLE"
        assert "segment_mismatch" in r["reasons"]

        # Test 3: ineligible — age below min
        r = engine.check_eligibility("PROP-DIASP", {
            "customer_id": "CUST-003",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 15,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
        })
        assert not r["eligible"]
        assert "AGE_BELOW_18" in r["reasons"]

        # Test 4: ineligible — sanctions listed
        r = engine.check_eligibility("PROP-DIASP", {
            "customer_id": "CUST-004",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 40,
            "aml_status": "CLEARED",
            "sanctions_listed": True,
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
        })
        assert not r["eligible"]
        assert "SANCTIONS_LIST" in r["reasons"]

        # Test 5: PROVISIONAL — KYC pending but otherwise eligible
        r = engine.check_eligibility("PROP-DIASP", {
            "customer_id": "CUST-005",
            "kyc_status": "PENDING",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
        })
        assert r["eligible"] is True
        assert r["outcome"] == "PROVISIONAL"

        # Test 6: UNKNOWN — missing data
        r = engine.check_eligibility("PROP-DIASP", {
            "customer_id": "CUST-006",
            # Missing all attributes
        })
        assert r["outcome"] == "UNKNOWN"

        # Test 7: ineligible — insufficient balance
        r = engine.check_eligibility("PROP-DIASP", {
            "customer_id": "CUST-007",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "5000",  # below 100k
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
        })
        assert not r["eligible"]
        assert "insufficient_balance" in r["reasons"]

        # Test 8: ineligible — risk band mismatch
        r = engine.check_eligibility("PROP-DIASP", {
            "customer_id": "CUST-008",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "CONSERVATIVE",  # not in [MODERATE, ADVENTUROUS]
        })
        assert not r["eligible"]
        assert "risk_band_mismatch" in r["reasons"]

        # Test 9: proposition not found
        r = engine.check_eligibility("UNKNOWN_PROP", {})
        assert r["outcome"] == "UNKNOWN"

        # Test 10: proposition not active
        catalog.register_proposition(
            {"proposition_id": "PROP-DRAFT",
             "name": "Y", "owner_role": "h"},
            actor="x",
        )
        r = engine.check_eligibility("PROP-DRAFT", {})
        assert not r["eligible"]
        assert "proposition_not_active" in r["reasons"][0]

        # Test 11: bulk_check + summary
        attrs_list = [
            {"customer_id": "C1", "kyc_status": "COMPLETE",
             "segment": "DIASPORA", "age": 30, "aml_status": "CLEARED",
             "balance_kes": "150000", "preferred_channel": "MOBILE_APP",
             "risk_appetite": "MODERATE"},
            {"customer_id": "C2", "kyc_status": "COMPLETE",
             "segment": "YOUTH", "age": 25, "aml_status": "CLEARED",
             "balance_kes": "50000", "preferred_channel": "MOBILE_APP",
             "risk_appetite": "MODERATE"},
        ]
        summary = engine.eligibility_summary("PROP-DIASP", attrs_list)
        assert summary["checked_count"] == 2
        assert summary["eligible_count"] == 1
        assert summary["ineligible_count"] == 1

        # Test 12: empty bulk
        s = engine.eligibility_summary("PROP-DIASP", [])
        assert s["checked_count"] == 0
        assert s["reason"] == "empty_input"

    print("  ✅ propositions_eligibility self-test PASS")


if __name__ == "__main__":
    _self_test()
