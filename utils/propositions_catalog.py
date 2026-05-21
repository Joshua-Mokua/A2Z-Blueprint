"""
================================================================================
A2Z MIS 360 — Standards #349 + #350: Propositions Catalog + Approval Governance
================================================================================

Risk classification: Cat A (CBK Product Governance — multi-level approval
                              + audit trail required by regulator)

Combined module:
    #349: Proposition Design Workbench — tool for product/proposition
          design with features, pricing, eligibility, channels.
          Versioned, approval workflow.
    #350: Proposition Approval & Governance Workflow — multi-level
          approval (product head, risk, compliance, finance, MD) with
          documentation, audit trail, post-launch review.

Standards consolidated because both operate on the SAME proposition
entity through different phases of its lifecycle. Separating them
would create two modules where one owns the data and the other is a
thin facade.

Public API (#349 design):
    register_proposition(proposition_data, actor)
    update_proposition_draft(prop_id, updates, actor, reason)
    create_new_version(prop_id, actor, reason) -> new version
    list_propositions(state=None, owner=None) -> List

Public API (#350 approval):
    submit_for_approval(prop_id, actor, reason)
    record_approval(prop_id, level, decision, actor, reason, notes)
    approval_status(prop_id) -> {level → decision}
    activate_proposition(prop_id, actor, reason) -> LIVE
    retire_proposition(prop_id, actor, reason) -> RETIRED
    post_launch_review(prop_id, review_data, actor)

PROPOSITION_STATES byte-for-byte (Continuation.docx #349 + #350):
    DRAFT          -- initial design, editable
    IN_REVIEW      -- submitted for stakeholder review
    IN_APPROVAL    -- formal multi-level approval underway
    APPROVED       -- all approval levels passed; ready to launch
    LIVE           -- active in market
    PAUSED         -- temporarily withdrawn (resumable)
    RETIRED        -- permanently withdrawn (terminal)
    ARCHIVED       -- archived for historical (terminal)

ALLOWED_PROPOSITION_TRANSITIONS (Rule 4):
    DRAFT       → IN_REVIEW | ARCHIVED
    IN_REVIEW   → DRAFT | IN_APPROVAL | ARCHIVED
    IN_APPROVAL → DRAFT | APPROVED | ARCHIVED  (rejection routes back)
    APPROVED    → LIVE | ARCHIVED
    LIVE        → PAUSED | RETIRED
    PAUSED      → LIVE | RETIRED
    RETIRED     → ARCHIVED
    ARCHIVED    → ()  -- terminal

APPROVAL_LEVELS byte-for-byte (Continuation.docx #350; CBK PG):
    PRODUCT_HEAD       -- product owner sign-off
    RISK_OFFICER       -- risk assessment + mitigation
    COMPLIANCE_OFFICER -- regulatory + AML/KYC review
    FINANCE_OFFICER    -- profitability + capital impact
    MD                 -- final managing director approval

APPROVAL_DECISIONS byte-for-byte:
    APPROVED       -- level approves
    REJECTED       -- level rejects (proposition routes back to DRAFT)
    APPROVED_WITH_CONDITIONS -- conditional approval (notes mandatory)
    PENDING        -- not yet decided (default)

ALL_LEVELS_ORDER required for activation: PRODUCT_HEAD → RISK → COMPLIANCE
                                            → FINANCE → MD (in any order
                                            for parallel approvals, but
                                            ALL must APPROVED for activation)

Honesty rules:
    Rule 4: actor + reason mandatory; no skip transitions
    Rule 6: invalid state / level / decision rejected
    Rule 1: approval_status returns explicit per-level state, never
            assumes silent approvals

CBK Product Governance compliance:
    CBK Prudential Guideline 4 (Product Governance) requires:
    - Documented approval chain (covered: per-level decisions stored)
    - Multi-level review (covered: 5 distinct APPROVAL_LEVELS)
    - Audit trail (covered: transitions list + per-decision records)
    - Post-launch review (covered: post_launch_review API)
    - Formal retirement process (covered: retire_proposition transition)

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROPOSITION_STATES: Tuple[str, ...] = (
    "DRAFT", "IN_REVIEW", "IN_APPROVAL", "APPROVED",
    "LIVE", "PAUSED", "RETIRED", "ARCHIVED",
)

ALLOWED_PROPOSITION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":       ("IN_REVIEW", "ARCHIVED"),
    "IN_REVIEW":   ("DRAFT", "IN_APPROVAL", "ARCHIVED"),
    "IN_APPROVAL": ("DRAFT", "APPROVED", "ARCHIVED"),
    "APPROVED":    ("LIVE", "ARCHIVED"),
    "LIVE":        ("PAUSED", "RETIRED"),
    "PAUSED":      ("LIVE", "RETIRED"),
    "RETIRED":     ("ARCHIVED",),
    "ARCHIVED":    (),
}

APPROVAL_LEVELS: Tuple[str, ...] = (
    "PRODUCT_HEAD", "RISK_OFFICER",
    "COMPLIANCE_OFFICER", "FINANCE_OFFICER", "MD",
)

APPROVAL_DECISIONS: Tuple[str, ...] = (
    "APPROVED", "REJECTED", "APPROVED_WITH_CONDITIONS", "PENDING",
)


class PropositionsCatalogEngine:
    """Proposition entity lifecycle + approval workflow."""

    def __init__(
        self,
        propositions_path: Optional[Path] = None,
        approvals_path: Optional[Path] = None,
        reviews_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.propositions_path = propositions_path or base / "propositions.json"
        self.approvals_path = approvals_path or base / "proposition_approvals.json"
        self.reviews_path = reviews_path or base / "proposition_reviews.json"

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

    # ── #349 Design Workbench ──────────────────────────────────────

    def register_proposition(
        self,
        proposition_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Register new proposition in DRAFT state."""
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("proposition_id", "name", "owner_role"):
            if f not in proposition_data or not proposition_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        records = self._load(self.propositions_path,
                                "propositions", ("proposition_id",))
        if any(r.get("proposition_id") == proposition_data["proposition_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_proposition_id"}

        record = {
            "proposition_id": proposition_data["proposition_id"],
            "name": proposition_data["name"],
            "description": proposition_data.get("description", ""),
            "owner_role": proposition_data["owner_role"],
            "version": 1,
            "state": "DRAFT",
            "features": proposition_data.get("features", []),
            "pricing": proposition_data.get("pricing", {}),
            "eligibility_criteria": proposition_data.get("eligibility_criteria", {}),
            "channels": proposition_data.get("channels", []),
            "target_segments": proposition_data.get("target_segments", []),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": "proposition_registered",
            }],
        }
        records.append(record)
        ok = self._save(self.propositions_path, records,
                          "propositions", "proposition_id")
        return {"registered": ok,
                  "proposition_id": proposition_data["proposition_id"]}

    def update_proposition_draft(
        self,
        prop_id: str,
        updates: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Update DRAFT proposition fields. Only DRAFT/IN_REVIEW editable."""
        if not actor or not reason:
            return {"updated": False, "error": "actor_and_reason_required"}

        records = self._load(self.propositions_path,
                                "propositions", ("proposition_id",))
        for r in records:
            if r.get("proposition_id") == prop_id:
                if r.get("state") not in ("DRAFT", "IN_REVIEW"):
                    return {
                        "updated": False,
                        "error": f"not_editable_in_state:{r['state']}",
                    }
                # Only update editable fields
                editable = ("name", "description", "features", "pricing",
                              "eligibility_criteria", "channels",
                              "target_segments")
                for k, v in updates.items():
                    if k in editable:
                        r[k] = v
                r.setdefault("update_history", []).append({
                    "actor": actor, "reason": reason,
                    "at": datetime.utcnow().isoformat(),
                    "fields": list(k for k in updates.keys() if k in editable),
                })
                ok = self._save(self.propositions_path, records,
                                  "propositions", "proposition_id")
                return {"updated": ok, "version": r.get("version")}
        return {"updated": False, "error": "proposition_not_found"}

    def create_new_version(
        self,
        prop_id: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Create a new draft version of a LIVE/RETIRED proposition."""
        if not actor or not reason:
            return {"created": False, "error": "actor_and_reason_required"}

        records = self._load(self.propositions_path,
                                "propositions", ("proposition_id",))
        # Find current latest version
        existing = [r for r in records if r.get("base_proposition_id") == prop_id
                       or r.get("proposition_id") == prop_id]
        if not existing:
            return {"created": False, "error": "proposition_not_found"}

        latest = max(existing, key=lambda r: r.get("version", 1))
        new_version = latest.get("version", 1) + 1
        new_id = f"{prop_id}-v{new_version}"

        new_record = dict(latest)
        new_record["proposition_id"] = new_id
        new_record["base_proposition_id"] = prop_id
        new_record["version"] = new_version
        new_record["state"] = "DRAFT"
        new_record["registered_by"] = actor
        new_record["registered_at"] = datetime.utcnow().isoformat()
        new_record["transitions"] = [{
            "to": "DRAFT", "actor": actor,
            "at": datetime.utcnow().isoformat(),
            "reason": f"new_version_from_{latest.get('proposition_id')}: {reason}",
        }]
        new_record.pop("update_history", None)
        records.append(new_record)
        ok = self._save(self.propositions_path, records,
                          "propositions", "proposition_id")
        return {"created": ok, "new_proposition_id": new_id,
                  "new_version": new_version}

    def list_propositions(
        self,
        state: Optional[str] = None,
        owner_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.propositions_path,
                                "propositions", ("proposition_id",))
        out = []
        for r in records:
            if state and r.get("state") != state:
                continue
            if owner_role and r.get("owner_role") != owner_role:
                continue
            out.append(r)
        return out

    def get_proposition(self, prop_id: str) -> Optional[Dict[str, Any]]:
        records = self._load(self.propositions_path,
                                "propositions", ("proposition_id",))
        return next((r for r in records
                       if r.get("proposition_id") == prop_id), None)

    # ── #350 Approval Workflow ─────────────────────────────────────

    def _transition(
        self, prop_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if new_state not in PROPOSITION_STATES:
            return {"ok": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.propositions_path,
                                "propositions", ("proposition_id",))
        for r in records:
            if r.get("proposition_id") == prop_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_PROPOSITION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "ok": False,
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
                ok = self._save(self.propositions_path, records,
                                  "propositions", "proposition_id")
                return {"ok": ok, "from": current, "to": new_state}
        return {"ok": False, "error": "proposition_not_found"}

    def submit_for_review(
        self, prop_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"ok": False, "error": "actor_and_reason_required"}
        return self._transition(prop_id, "IN_REVIEW", actor, reason)

    def submit_for_approval(
        self, prop_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"ok": False, "error": "actor_and_reason_required"}
        # Initialize all approval levels to PENDING
        records = self._load(self.approvals_path,
                                "proposition_approvals",
                                ("proposition_id", "level"))
        for level in APPROVAL_LEVELS:
            existing = next((a for a in records
                                if a.get("proposition_id") == prop_id
                                and a.get("level") == level), None)
            if existing is None:
                records.append({
                    "approval_id": f"APR-{prop_id}-{level}",
                    "proposition_id": prop_id,
                    "level": level,
                    "decision": "PENDING",
                    "actor": None,
                    "reason": None,
                    "notes": "",
                    "decided_at": None,
                })
        self._save(self.approvals_path, records,
                     "proposition_approvals", "approval_id")
        return self._transition(prop_id, "IN_APPROVAL", actor, reason)

    def record_approval(
        self,
        prop_id: str,
        level: str,
        decision: str,
        actor: str,
        reason: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"recorded": False, "error": "actor_and_reason_required"}
        if level not in APPROVAL_LEVELS:
            return {
                "recorded": False,
                "error": f"invalid_level:{level}",
                "valid_levels": list(APPROVAL_LEVELS),
            }
        if decision not in APPROVAL_DECISIONS:
            return {
                "recorded": False,
                "error": f"invalid_decision:{decision}",
                "valid_decisions": list(APPROVAL_DECISIONS),
            }
        if decision == "APPROVED_WITH_CONDITIONS" and not notes:
            return {
                "recorded": False,
                "error": "notes_mandatory_for_conditional_approval",
            }

        records = self._load(self.approvals_path,
                                "proposition_approvals",
                                ("proposition_id", "level"))
        for r in records:
            if (r.get("proposition_id") == prop_id
                    and r.get("level") == level):
                if r.get("decision") in ("APPROVED", "REJECTED",
                                              "APPROVED_WITH_CONDITIONS"):
                    return {
                        "recorded": False,
                        "error": f"decision_already_recorded:{r['decision']}",
                    }
                r["decision"] = decision
                r["actor"] = actor
                r["reason"] = reason
                r["notes"] = notes
                r["decided_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.approvals_path, records,
                                  "proposition_approvals", "approval_id")

                # If REJECTED → route proposition back to DRAFT
                if decision == "REJECTED":
                    self._transition(
                        prop_id, "DRAFT", actor,
                        f"rejected_at_{level}: {reason}",
                    )

                # Check if all levels APPROVED → transition to APPROVED state
                self._check_all_approvals_complete(prop_id, actor)

                return {"recorded": ok, "decision": decision}

        return {"recorded": False, "error": "approval_record_not_found"}

    def _check_all_approvals_complete(
        self, prop_id: str, actor: str,
    ) -> None:
        """If all 5 levels are APPROVED or APPROVED_WITH_CONDITIONS,
        transition to APPROVED state."""
        records = self._load(self.approvals_path,
                                "proposition_approvals",
                                ("proposition_id", "level"))
        levels_for_prop = {r["level"]: r["decision"] for r in records
                                if r.get("proposition_id") == prop_id}

        if len(levels_for_prop) < len(APPROVAL_LEVELS):
            return  # Not all levels recorded yet

        all_approved = all(
            levels_for_prop.get(lvl) in ("APPROVED", "APPROVED_WITH_CONDITIONS")
            for lvl in APPROVAL_LEVELS
        )
        if all_approved:
            self._transition(
                prop_id, "APPROVED", actor,
                "all_5_approval_levels_complete",
            )

    def approval_status(self, prop_id: str) -> Dict[str, Any]:
        records = self._load(self.approvals_path,
                                "proposition_approvals",
                                ("proposition_id", "level"))
        for_prop = [r for r in records
                       if r.get("proposition_id") == prop_id]
        if not for_prop:
            return {
                "proposition_id": prop_id,
                "approval_records_count": 0,
                "reason": "no_approval_records",
            }
        per_level = {r["level"]: {
            "decision": r.get("decision", "PENDING"),
            "actor": r.get("actor"),
            "decided_at": r.get("decided_at"),
            "notes": r.get("notes", ""),
        } for r in for_prop}

        all_decided = all(
            per_level.get(lvl, {}).get("decision") in
                ("APPROVED", "REJECTED", "APPROVED_WITH_CONDITIONS")
            for lvl in APPROVAL_LEVELS
        )

        return {
            "proposition_id": prop_id,
            "per_level": per_level,
            "all_levels_decided": all_decided,
            "decision_summary": dict(Counter(
                r.get("decision", "PENDING") for r in for_prop
            )),
        }

    def activate_proposition(
        self, prop_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"ok": False, "error": "actor_and_reason_required"}
        return self._transition(prop_id, "LIVE", actor, reason)

    def pause_proposition(
        self, prop_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"ok": False, "error": "actor_and_reason_required"}
        return self._transition(prop_id, "PAUSED", actor, reason)

    def retire_proposition(
        self, prop_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"ok": False, "error": "actor_and_reason_required"}
        return self._transition(prop_id, "RETIRED", actor, reason)

    def post_launch_review(
        self,
        prop_id: str,
        review_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Record formal post-launch review (CBK PG requirement)."""
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        # Proposition must have been LIVE at some point
        prop = self.get_proposition(prop_id)
        if prop is None:
            return {"recorded": False, "error": "proposition_not_found"}
        was_live = any(t.get("to") == "LIVE"
                          for t in prop.get("transitions", []))
        if not was_live:
            return {
                "recorded": False,
                "error": "post_launch_review_requires_LIVE_history",
            }

        records = self._load(self.reviews_path,
                                "proposition_reviews",
                                ("review_id",))
        review_id = (f"REV-{prop_id}-"
                       f"{int(datetime.utcnow().timestamp())}")
        records.append({
            "review_id": review_id,
            "proposition_id": prop_id,
            "review_period": review_data.get("review_period", ""),
            "take_up_count": review_data.get("take_up_count", 0),
            "revenue_generated": review_data.get("revenue_generated", "0"),
            "issues_identified": review_data.get("issues_identified", []),
            "recommendations": review_data.get("recommendations", []),
            "outcome": review_data.get("outcome", "REVIEWED"),
            "reviewed_by": actor,
            "reviewed_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.reviews_path, records,
                          "proposition_reviews", "review_id")
        return {"recorded": ok, "review_id": review_id}


def _self_test() -> None:
    import tempfile

    assert ALLOWED_PROPOSITION_TRANSITIONS["ARCHIVED"] == ()
    assert "MD" in APPROVAL_LEVELS
    assert "REJECTED" in APPROVAL_DECISIONS

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = PropositionsCatalogEngine(
            propositions_path=Path(tmpdir) / "p.json",
            approvals_path=Path(tmpdir) / "a.json",
            reviews_path=Path(tmpdir) / "r.json",
        )

        # Test 1: register proposition
        r = engine.register_proposition(
            {"proposition_id": "PROP-001",
             "name": "Diaspora Wealth Account",
             "owner_role": "head_of_diaspora_segment",
             "description": "Premium account for diaspora customers",
             "features": ["multi_currency", "preferential_fx"],
             "channels": ["MOBILE_APP", "BRANCH"],
             "target_segments": ["DIASPORA"]},
            actor="product_lead",
        )
        assert r["registered"]

        # Test 2: missing field rejected
        r = engine.register_proposition(
            {"proposition_id": "PROP-X"},
            actor="x",
        )
        assert not r["registered"]

        # Test 3: duplicate id
        r = engine.register_proposition(
            {"proposition_id": "PROP-001", "name": "X",
             "owner_role": "y"},
            actor="x",
        )
        assert not r["registered"]

        # Test 4: update DRAFT
        u = engine.update_proposition_draft(
            "PROP-001",
            {"description": "Updated description",
             "features": ["multi_currency", "preferential_fx", "free_swift"]},
            actor="product_lead", reason="adding swift feature",
        )
        assert u["updated"]

        # Test 5: submit for review (DRAFT → IN_REVIEW)
        r = engine.submit_for_review(
            "PROP-001", actor="product_lead",
            reason="ready for stakeholder review",
        )
        assert r["ok"]
        assert r["to"] == "IN_REVIEW"

        # Test 6: cannot update outside DRAFT/IN_REVIEW (test edge)
        # First push into IN_APPROVAL
        engine.submit_for_approval(
            "PROP-001", actor="product_lead",
            reason="ready for formal approval",
        )
        u = engine.update_proposition_draft(
            "PROP-001", {"description": "X"},
            actor="x", reason="x",
        )
        assert not u["updated"]
        assert "not_editable_in_state" in u["error"]

        # Test 7: record approvals at all 5 levels
        for level in APPROVAL_LEVELS:
            r = engine.record_approval(
                "PROP-001", level, "APPROVED",
                actor=f"{level}_user", reason="reviewed_and_approved",
            )
            assert r["recorded"], (level, r)

        # Test 8: prop should now be in APPROVED state (auto-transition)
        prop = engine.get_proposition("PROP-001")
        assert prop["state"] == "APPROVED"

        # Test 9: invalid level rejected
        engine.register_proposition(
            {"proposition_id": "PROP-002", "name": "Y",
             "owner_role": "head"},
            actor="x",
        )
        engine.submit_for_review("PROP-002", actor="x", reason="r")
        engine.submit_for_approval("PROP-002", actor="x", reason="r")
        r = engine.record_approval(
            "PROP-002", "INVALID_LEVEL", "APPROVED",
            actor="x", reason="r",
        )
        assert not r["recorded"]

        # Test 10: invalid decision rejected
        r = engine.record_approval(
            "PROP-002", "PRODUCT_HEAD", "MAYBE",
            actor="x", reason="r",
        )
        assert not r["recorded"]

        # Test 11: APPROVED_WITH_CONDITIONS requires notes
        r = engine.record_approval(
            "PROP-002", "PRODUCT_HEAD", "APPROVED_WITH_CONDITIONS",
            actor="x", reason="r", notes="",
        )
        assert not r["recorded"]
        assert "notes_mandatory" in r["error"]

        # Test 12: REJECTED routes back to DRAFT
        r = engine.record_approval(
            "PROP-002", "PRODUCT_HEAD", "REJECTED",
            actor="x", reason="needs more work",
        )
        assert r["recorded"]
        prop2 = engine.get_proposition("PROP-002")
        assert prop2["state"] == "DRAFT"

        # Test 13: cannot re-record decision
        r = engine.record_approval(
            "PROP-002", "PRODUCT_HEAD", "APPROVED",
            actor="x", reason="r",
        )
        assert not r["recorded"]
        assert "decision_already_recorded" in r["error"]

        # Test 14: activate APPROVED → LIVE
        r = engine.activate_proposition(
            "PROP-001", actor="md_user", reason="market launch",
        )
        assert r["ok"]
        assert r["to"] == "LIVE"

        # Test 15: skip rejected (LIVE → APPROVED not allowed)
        r = engine._transition(
            "PROP-001", "APPROVED", actor="x", reason="x",
        )
        assert not r["ok"]
        assert "transition_not_allowed" in r["error"]

        # Test 16: pause + resume
        engine.pause_proposition("PROP-001", actor="md", reason="market issue")
        prop = engine.get_proposition("PROP-001")
        assert prop["state"] == "PAUSED"
        engine.activate_proposition("PROP-001", actor="md", reason="resumed")
        prop = engine.get_proposition("PROP-001")
        assert prop["state"] == "LIVE"

        # Test 17: post_launch_review
        r = engine.post_launch_review(
            "PROP-001",
            {"review_period": "2026-Q2",
             "take_up_count": 350, "revenue_generated": "1500000",
             "outcome": "REVIEWED"},
            actor="product_lead",
        )
        assert r["recorded"]

        # Test 18: review without LIVE history
        engine.register_proposition(
            {"proposition_id": "PROP-NEVER-LIVE", "name": "X",
             "owner_role": "head"},
            actor="x",
        )
        r = engine.post_launch_review(
            "PROP-NEVER-LIVE",
            {"review_period": "2026-Q2"},
            actor="x",
        )
        assert not r["recorded"]
        assert "requires_LIVE_history" in r["error"]

        # Test 19: retire
        r = engine.retire_proposition(
            "PROP-001", actor="md", reason="end of lifecycle",
        )
        assert r["ok"]
        assert r["to"] == "RETIRED"

        # Test 20: list_propositions
        live = engine.list_propositions(state="LIVE")
        retired = engine.list_propositions(state="RETIRED")
        assert len(retired) == 1
        assert any(p["proposition_id"] == "PROP-001" for p in retired)

        # Test 21: create_new_version
        r = engine.create_new_version(
            "PROP-001", actor="product_lead",
            reason="2026-Q3 refresh with new features",
        )
        assert r["created"]
        assert r["new_version"] == 2

        # Test 22: approval_status
        st = engine.approval_status("PROP-001")
        assert st["all_levels_decided"]
        assert st["per_level"]["MD"]["decision"] == "APPROVED"

    print("  ✅ propositions_catalog self-test PASS")


if __name__ == "__main__":
    _self_test()
