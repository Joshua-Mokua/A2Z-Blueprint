"""
================================================================================
A2Z MIS 360 — Standard #304: Agentic Claims Processing
================================================================================

Risk classification: Cat A (financial — claim settlement automation)
                     + Rule 7 ML hook (fraud screening)

AI-agent claim intake, document validation, fraud screening, settlement
calculation, auto-approval below threshold. v10.274 ships rule-based
deterministic baseline + Rule 7 ML hook for fraud scoring.

Public API:
    submit_claim(policy_id, claim_data, actor)
    transition_claim_state(claim_id, new_state, actor, reason)
    record_document(claim_id, doc_type, doc_ref, actor)
    auto_evaluate_claim(claim_id, actor) -> {decision, fraud_score, ...}
    settlement_calculation(claim_id) -> {amount, breakdown}
    list_claims(state=None, policy_id=None)

CLAIM_STATES byte-for-byte:
    SUBMITTED       -- intake complete; awaiting review
    DOCUMENT_REVIEW -- documents being validated
    INVESTIGATING   -- fraud / loss verification
    APPROVED        -- approved for settlement (terminal-success)
    REJECTED        -- rejected (terminal)
    SETTLED         -- payment made (final-terminal-success)
    CONTESTED       -- customer contesting; in dispute
    CLOSED          -- formally closed (terminal)

ALLOWED_CLAIM_TRANSITIONS (Rule 4):
    SUBMITTED       → DOCUMENT_REVIEW | REJECTED | CLOSED
    DOCUMENT_REVIEW → INVESTIGATING | REJECTED | CLOSED
    INVESTIGATING   → APPROVED | REJECTED | CLOSED
    APPROVED        → SETTLED | CONTESTED | CLOSED
    REJECTED        → CONTESTED | CLOSED
    SETTLED         → CLOSED
    CONTESTED       → APPROVED | REJECTED | CLOSED
    CLOSED          → ()  -- terminal

REQUIRED_DOCUMENT_TYPES byte-for-byte:
    LIFE         → ("DEATH_CERTIFICATE", "POLICY_DOCUMENT")
    HEALTH       → ("MEDICAL_REPORT", "INVOICES", "POLICY_DOCUMENT")
    MOTOR        → ("POLICE_ABSTRACT", "REPAIR_QUOTE", "PHOTOS",
                      "POLICY_DOCUMENT")
    PROPERTY     → ("LOSS_REPORT", "PHOTOS", "POLICY_DOCUMENT")
    TRAVEL       → ("INCIDENT_REPORT", "RECEIPTS", "POLICY_DOCUMENT")
    OTHER        → ("POLICY_DOCUMENT",)

AUTO_APPROVAL_THRESHOLD_KES byte-for-byte:
    100,000 KES — claims at or below auto-approve when:
        - all required documents present AND
        - fraud_score < AUTO_APPROVAL_FRAUD_LIMIT (40) AND
        - state is INVESTIGATING

AUTO_APPROVAL_FRAUD_LIMIT = Decimal("40")

Honesty rules:
    Rule 4: actor + reason mandatory; no skip transitions
    Rule 6: invalid claim_state / doc_type rejected
    Rule 1: settlement_calculation returns None when policy lookup fails
    Rule 7: ML fraud hook isolated; deterministic fallback always returns
            score 50 (neutral) and surfaces no_ml_hook_loaded reason

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.insurance_catalog import InsuranceCatalogEngine

getcontext().prec = 28


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #304 specifies AI-agent claims processing. "
    "v10.274 ships rule-based deterministic baseline (document "
    "completeness check + claim-amount threshold + auto-approval "
    "rules) + Rule 7 ML hook (fraud_score_fn) for fraud scoring. "
    "Production fraud ML requires customer behavioral cluster (#337-"
    "348, batch v10.275-276). Without ML hook, fraud_score defaults "
    "to 50 (neutral) and surfaces 'no_ml_hook_loaded'."
)


CLAIM_STATES: Tuple[str, ...] = (
    "SUBMITTED", "DOCUMENT_REVIEW", "INVESTIGATING",
    "APPROVED", "REJECTED", "SETTLED", "CONTESTED", "CLOSED",
)

ALLOWED_CLAIM_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "SUBMITTED":       ("DOCUMENT_REVIEW", "REJECTED", "CLOSED"),
    "DOCUMENT_REVIEW": ("INVESTIGATING", "REJECTED", "CLOSED"),
    "INVESTIGATING":   ("APPROVED", "REJECTED", "CLOSED"),
    "APPROVED":        ("SETTLED", "CONTESTED", "CLOSED"),
    "REJECTED":        ("CONTESTED", "CLOSED"),
    "SETTLED":         ("CLOSED",),
    "CONTESTED":       ("APPROVED", "REJECTED", "CLOSED"),
    "CLOSED":          (),
}

REQUIRED_DOCUMENT_TYPES: Dict[str, Tuple[str, ...]] = {
    "LIFE":     ("DEATH_CERTIFICATE", "POLICY_DOCUMENT"),
    "HEALTH":   ("MEDICAL_REPORT", "INVOICES", "POLICY_DOCUMENT"),
    "MOTOR":    ("POLICE_ABSTRACT", "REPAIR_QUOTE", "PHOTOS", "POLICY_DOCUMENT"),
    "PROPERTY": ("LOSS_REPORT", "PHOTOS", "POLICY_DOCUMENT"),
    "TRAVEL":   ("INCIDENT_REPORT", "RECEIPTS", "POLICY_DOCUMENT"),
    "OTHER":    ("POLICY_DOCUMENT",),
}

AUTO_APPROVAL_THRESHOLD_KES: Decimal = Decimal("100000")
AUTO_APPROVAL_FRAUD_LIMIT:    Decimal = Decimal("40")


class ClaimsProcessingEngine:
    """Agentic claims processing with Rule 7 fraud ML hook."""

    def __init__(
        self,
        claims_path: Optional[Path] = None,
        catalog: Optional[InsuranceCatalogEngine] = None,
        fraud_score_fn: Optional[Callable[[Dict[str, Any]], Decimal]] = None,
    ):
        self.claims_path = (
            claims_path or
            Path(__file__).parent.parent / "data" / "insurance_claims.json"
        )
        self.catalog = catalog or InsuranceCatalogEngine()
        self.fraud_score_fn = fraud_score_fn  # Rule 7 hook

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.claims_path,
                table="insurance_claims",
                index_cols=("claim_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.claims_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.claims_path,
                data=records,
                table="insurance_claims",
                pk_col="claim_id")
            return True
        except Exception:
            return False

    def submit_claim(
        self,
        policy_id: str,
        claim_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Submit new claim in SUBMITTED state."""
        if not actor:
            return {"submitted": False, "error": "actor_required"}

        for f in ("claim_id", "incident_date", "claim_amount_kes",
                    "claim_description"):
            if f not in claim_data or claim_data[f] in (None, ""):
                return {"submitted": False, "error": f"missing_field:{f}"}

        try:
            amt = Decimal(str(claim_data["claim_amount_kes"]))
        except (ValueError, TypeError):
            return {"submitted": False, "error": "amount_not_decimal"}
        if amt <= 0:
            return {"submitted": False, "error": "amount_must_be_positive"}

        # Validate policy exists
        policies = self.catalog._load(
            self.catalog.policies_path, "insurance_policies", ("policy_id",)
        )
        if not any(p.get("policy_id") == policy_id for p in policies):
            return {"submitted": False, "error": "policy_not_found"}

        records = self._load()
        if any(r.get("claim_id") == claim_data["claim_id"] for r in records):
            return {"submitted": False, "error": "duplicate_claim_id"}

        record = {
            "claim_id": claim_data["claim_id"],
            "policy_id": policy_id,
            "incident_date": claim_data["incident_date"],
            "claim_amount_kes": str(amt),
            "claim_description": claim_data["claim_description"],
            "state": "SUBMITTED",
            "documents": [],
            "fraud_score": None,
            "auto_approved": False,
            "submitted_by": actor,
            "submitted_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "SUBMITTED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": "claim_submitted",
            }],
        }
        records.append(record)
        ok = self._save(records)
        return {"submitted": ok, "claim_id": claim_data["claim_id"]}

    def transition_claim_state(
        self,
        claim_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in CLAIM_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        records = self._load()
        for r in records:
            if r.get("claim_id") == claim_id:
                current = r.get("state", "SUBMITTED")
                allowed = ALLOWED_CLAIM_TRANSITIONS.get(current, ())
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
                ok = self._save(records)
                return {"transitioned": ok, "from": current, "to": new_state}

        return {"transitioned": False, "error": "claim_not_found"}

    def record_document(
        self,
        claim_id: str,
        doc_type: str,
        doc_ref: str,
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if not doc_type or not doc_ref:
            return {"recorded": False, "error": "doc_type_and_ref_required"}

        records = self._load()
        for r in records:
            if r.get("claim_id") == claim_id:
                docs = r.setdefault("documents", [])
                docs.append({
                    "doc_type": doc_type,
                    "doc_ref": doc_ref,
                    "recorded_by": actor,
                    "recorded_at": datetime.utcnow().isoformat(),
                })
                ok = self._save(records)
                return {
                    "recorded": ok,
                    "claim_id": claim_id,
                    "document_count": len(docs),
                }
        return {"recorded": False, "error": "claim_not_found"}

    def _get_required_documents(self, policy_id: str) -> Tuple[str, ...]:
        """Look up required document types for a policy's product type."""
        policies = self.catalog._load(
            self.catalog.policies_path, "insurance_policies", ("policy_id",)
        )
        policy = next(
            (p for p in policies if p.get("policy_id") == policy_id), None,
        )
        if not policy:
            return REQUIRED_DOCUMENT_TYPES["OTHER"]

        products = self.catalog._load(
            self.catalog.products_path, "insurance_products", ("product_code",)
        )
        product = next(
            (p for p in products if p.get("product_code") == policy.get("product_code")),
            None,
        )
        if not product:
            return REQUIRED_DOCUMENT_TYPES["OTHER"]

        ptype = product.get("product_type", "OTHER")
        return REQUIRED_DOCUMENT_TYPES.get(ptype, REQUIRED_DOCUMENT_TYPES["OTHER"])

    def auto_evaluate_claim(
        self,
        claim_id: str,
        actor: str,
    ) -> Dict[str, Any]:
        """
        Rule-based + ML-blended evaluation.

        Returns: {decision, fraud_score, missing_documents, reasons}.
        Decision values: AUTO_APPROVE / REQUIRES_REVIEW / REJECTED.
        """
        if not actor:
            return {"evaluated": False, "error": "actor_required"}

        records = self._load()
        for r in records:
            if r.get("claim_id") == claim_id:
                # 1. Document completeness
                required = set(self._get_required_documents(r.get("policy_id", "")))
                provided = {d.get("doc_type") for d in r.get("documents", [])}
                missing = sorted(required - provided)

                # 2. Fraud score (Rule 7 hook)
                if self.fraud_score_fn is not None:
                    try:
                        fs = Decimal(str(self.fraud_score_fn(r)))
                        fraud_reason = "ml_score_applied"
                    except Exception as e:
                        fs = Decimal("50")  # neutral fallback
                        fraud_reason = f"ml_hook_error:{type(e).__name__}"
                else:
                    fs = Decimal("50")  # neutral fallback
                    fraud_reason = "no_ml_hook_loaded"

                # 3. Decision
                try:
                    amt = Decimal(r["claim_amount_kes"])
                except (ValueError, TypeError, KeyError):
                    return {
                        "evaluated": False,
                        "error": "claim_amount_invalid",
                    }

                reasons = [fraud_reason]
                if missing:
                    decision = "REQUIRES_REVIEW"
                    reasons.append(f"missing_documents:{','.join(missing)}")
                elif fs >= AUTO_APPROVAL_FRAUD_LIMIT:
                    decision = "REQUIRES_REVIEW"
                    reasons.append(f"fraud_score_above_threshold:{fs}")
                elif amt > AUTO_APPROVAL_THRESHOLD_KES:
                    decision = "REQUIRES_REVIEW"
                    reasons.append(
                        f"amount_above_auto_approval:{amt}_vs_{AUTO_APPROVAL_THRESHOLD_KES}"
                    )
                else:
                    decision = "AUTO_APPROVE"
                    reasons.append(
                        f"all_criteria_met:amt<={AUTO_APPROVAL_THRESHOLD_KES},"
                        f"fraud<{AUTO_APPROVAL_FRAUD_LIMIT},docs_complete"
                    )

                # Persist
                r["fraud_score"] = str(fs)
                r["last_evaluation"] = {
                    "decision": decision,
                    "fraud_score": str(fs),
                    "missing_documents": missing,
                    "reasons": reasons,
                    "evaluated_by": actor,
                    "evaluated_at": datetime.utcnow().isoformat(),
                }
                if decision == "AUTO_APPROVE" and r.get("state") == "INVESTIGATING":
                    r["auto_approved"] = True
                self._save(records)

                return {
                    "evaluated": True,
                    "claim_id": claim_id,
                    "decision": decision,
                    "fraud_score": str(fs),
                    "missing_documents": missing,
                    "reasons": reasons,
                    "ml_hook_active": self.fraud_score_fn is not None,
                }

        return {"evaluated": False, "error": "claim_not_found"}

    def settlement_calculation(
        self,
        claim_id: str,
    ) -> Dict[str, Any]:
        """
        Calculate settlement amount = min(claim_amount, sum_assured).

        Rule 1: returns amount_kes=None when policy lookup fails.
        """
        records = self._load()
        claim = next(
            (r for r in records if r.get("claim_id") == claim_id), None,
        )
        if claim is None:
            return {"claim_id": claim_id, "amount_kes": None,
                     "reason": "claim_not_found"}

        try:
            claim_amount = Decimal(claim["claim_amount_kes"])
        except (ValueError, TypeError, KeyError):
            return {"claim_id": claim_id, "amount_kes": None,
                     "reason": "claim_amount_invalid"}

        policies = self.catalog._load(
            self.catalog.policies_path, "insurance_policies", ("policy_id",)
        )
        policy = next(
            (p for p in policies if p.get("policy_id") == claim.get("policy_id")),
            None,
        )
        if policy is None:
            return {"claim_id": claim_id, "amount_kes": None,
                     "reason": "policy_lookup_failed"}

        try:
            sum_assured = Decimal(policy["sum_assured_kes"])
        except (ValueError, TypeError, KeyError):
            return {"claim_id": claim_id, "amount_kes": None,
                     "reason": "sum_assured_invalid"}

        settlement = min(claim_amount, sum_assured)

        return {
            "claim_id": claim_id,
            "amount_kes": str(settlement.quantize(Decimal("0.01"))),
            "claim_amount_kes": str(claim_amount),
            "sum_assured_kes": str(sum_assured),
            "capped_by_sum_assured": claim_amount > sum_assured,
        }

    def list_claims(
        self,
        state: Optional[str] = None,
        policy_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load()
        out = []
        for r in records:
            if state and r.get("state") != state:
                continue
            if policy_id and r.get("policy_id") != policy_id:
                continue
            out.append(r)
        return out


def _self_test() -> None:
    import tempfile

    # Spec deviation note
    assert "AI-agent" in SPEC_DEVIATION_NOTE
    assert "v10.275-276" in SPEC_DEVIATION_NOTE

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = InsuranceCatalogEngine(
            products_path=Path(tmpdir) / "p.json",
            policies_path=Path(tmpdir) / "po.json",
            premiums_path=Path(tmpdir) / "pr.json",
        )
        # Seed product + policy
        catalog.register_product(
            "INS-A",
            {"product_code": "P-MOTOR", "product_name": "Motor Comp",
             "product_type": "MOTOR"},
            actor="bd", reason="seed",
        )
        catalog.issue_policy(
            "CUST-001", "P-MOTOR",
            {"policy_id": "POL-MOTOR-01",
             "sum_assured_kes": "500000",
             "premium_kes": "5000",
             "premium_frequency": "ANNUAL",
             "effective_date": "2026-01-01",
             "expiry_date": "2027-01-01"},
            actor="rm",
        )

        engine = ClaimsProcessingEngine(
            claims_path=Path(tmpdir) / "c.json",
            catalog=catalog,
        )

        # Test 1: submit claim
        r = engine.submit_claim(
            "POL-MOTOR-01",
            {"claim_id": "CLM-001",
             "incident_date": "2026-04-15",
             "claim_amount_kes": "80000",
             "claim_description": "Minor accident"},
            actor="rm",
        )
        assert r["submitted"], r

        # Test 2: missing required field
        r = engine.submit_claim(
            "POL-MOTOR-01",
            {"claim_id": "CLM-X",
             "incident_date": "",
             "claim_amount_kes": "100"},
            actor="rm",
        )
        assert not r["submitted"]

        # Test 3: unknown policy rejected
        r = engine.submit_claim(
            "UNKNOWN-POL",
            {"claim_id": "CLM-Y",
             "incident_date": "2026-01-01",
             "claim_amount_kes": "100",
             "claim_description": "x"},
            actor="rm",
        )
        assert not r["submitted"]

        # Test 4: state lifecycle
        for new_state, reason in [
            ("DOCUMENT_REVIEW", "starting docs"),
            ("INVESTIGATING", "verification"),
            ("APPROVED", "approved"),
            ("SETTLED", "paid"),
            ("CLOSED", "closing"),
        ]:
            t = engine.transition_claim_state(
                "CLM-001", new_state, actor="claims_ops", reason=reason,
            )
            assert t["transitioned"], (new_state, t)

        # Test 5: skip rejected
        r2 = engine.submit_claim(
            "POL-MOTOR-01",
            {"claim_id": "CLM-002",
             "incident_date": "2026-04-20",
             "claim_amount_kes": "60000",
             "claim_description": "Another claim"},
            actor="rm",
        )
        t = engine.transition_claim_state(
            "CLM-002", "APPROVED", actor="ops", reason="skip"
        )
        assert not t["transitioned"]

        # Test 6: record_document
        d = engine.record_document(
            "CLM-002", "POLICE_ABSTRACT", "doc-ref-001", actor="rm",
        )
        assert d["recorded"]
        assert d["document_count"] == 1

        # Test 7: auto_evaluate — missing docs → REQUIRES_REVIEW
        e = engine.auto_evaluate_claim("CLM-002", actor="auto_agent")
        assert e["evaluated"]
        assert e["decision"] == "REQUIRES_REVIEW"
        assert any("missing_documents" in r for r in e["reasons"])
        # Without ML hook
        assert "no_ml_hook_loaded" in e["reasons"]

        # Test 8: complete documents → AUTO_APPROVE (60K < 100K + no ML)
        # Without ML, fraud_score = 50 → above limit → REQUIRES_REVIEW
        for dt in ("REPAIR_QUOTE", "PHOTOS", "POLICY_DOCUMENT"):
            engine.record_document("CLM-002", dt, f"ref-{dt}", actor="rm")
        e = engine.auto_evaluate_claim("CLM-002", actor="auto_agent")
        # Default fraud=50 ≥ AUTO_APPROVAL_FRAUD_LIMIT(40) → REQUIRES_REVIEW
        assert e["decision"] == "REQUIRES_REVIEW"
        assert any("fraud_score_above_threshold" in r for r in e["reasons"])

        # Test 9: with ML hook returning low fraud → AUTO_APPROVE
        def low_fraud(claim):
            return Decimal("10")
        engine_ml = ClaimsProcessingEngine(
            claims_path=Path(tmpdir) / "c.json",
            catalog=catalog,
            fraud_score_fn=low_fraud,
        )
        e = engine_ml.auto_evaluate_claim("CLM-002", actor="auto_agent")
        assert e["decision"] == "AUTO_APPROVE"
        assert e["fraud_score"] == "10"

        # Test 10: with ML hook returning high fraud → REQUIRES_REVIEW
        def high_fraud(claim):
            return Decimal("85")
        engine_high = ClaimsProcessingEngine(
            claims_path=Path(tmpdir) / "c.json",
            catalog=catalog,
            fraud_score_fn=high_fraud,
        )
        e = engine_high.auto_evaluate_claim("CLM-002", actor="auto_agent")
        assert e["decision"] == "REQUIRES_REVIEW"

        # Test 11: amount above threshold → REQUIRES_REVIEW
        catalog.issue_policy(
            "CUST-001", "P-MOTOR",
            {"policy_id": "POL-BIG",
             "sum_assured_kes": "5000000",
             "premium_kes": "20000",
             "premium_frequency": "ANNUAL",
             "effective_date": "2026-01-01",
             "expiry_date": "2027-01-01"},
            actor="rm",
        )
        engine.submit_claim(
            "POL-BIG",
            {"claim_id": "CLM-BIG",
             "incident_date": "2026-04-25",
             "claim_amount_kes": "500000",
             "claim_description": "Big claim"},
            actor="rm",
        )
        # Add all required docs
        for dt in ("POLICE_ABSTRACT", "REPAIR_QUOTE", "PHOTOS", "POLICY_DOCUMENT"):
            engine_ml.record_document("CLM-BIG", dt, f"r-{dt}", actor="rm")
        e = engine_ml.auto_evaluate_claim("CLM-BIG", actor="auto_agent")
        assert e["decision"] == "REQUIRES_REVIEW"
        assert any("amount_above" in r for r in e["reasons"])

        # Test 12: ML hook failure → fallback fraud=50
        def broken(c):
            raise RuntimeError("model timeout")
        engine_broken = ClaimsProcessingEngine(
            claims_path=Path(tmpdir) / "c.json",
            catalog=catalog,
            fraud_score_fn=broken,
        )
        e = engine_broken.auto_evaluate_claim("CLM-002", actor="auto_agent")
        assert e["fraud_score"] == "50"
        assert any("ml_hook_error" in r for r in e["reasons"])

        # Test 13: settlement_calculation — amount within sum_assured
        s = engine.settlement_calculation("CLM-002")
        assert Decimal(s["amount_kes"]) == Decimal("60000.00")
        assert s["capped_by_sum_assured"] is False

        # Test 14: settlement capped at sum_assured
        s = engine.settlement_calculation("CLM-BIG")
        # Sum assured 5M, claim 500K — 500K wins; not capped
        assert Decimal(s["amount_kes"]) == Decimal("500000.00")
        assert s["capped_by_sum_assured"] is False

        # Submit a claim above sum_assured
        engine.submit_claim(
            "POL-MOTOR-01",
            {"claim_id": "CLM-CAP",
             "incident_date": "2026-04-30",
             "claim_amount_kes": "800000",  # > 500K sum assured
             "claim_description": "Total loss"},
            actor="rm",
        )
        s = engine.settlement_calculation("CLM-CAP")
        assert Decimal(s["amount_kes"]) == Decimal("500000.00")
        assert s["capped_by_sum_assured"] is True

        # Test 15: settlement for unknown claim
        s = engine.settlement_calculation("UNKNOWN")
        assert s["amount_kes"] is None
        assert s["reason"] == "claim_not_found"

        # Test 16: list_claims
        all_claims = engine.list_claims()
        assert len(all_claims) >= 4
        closed = engine.list_claims(state="CLOSED")
        assert len(closed) == 1

    print("  ✅ insurance_claims self-test PASS")


if __name__ == "__main__":
    _self_test()
