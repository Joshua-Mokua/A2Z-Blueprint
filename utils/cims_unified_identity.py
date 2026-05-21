"""
================================================================================
A2Z MIS 360 — Standard #173: Unified Customer Identity (Contact as Consumer)
================================================================================

Risk classification: Cat C (read-side identity resolution; never auto-merges
records — merge proposals require human approval).

Subcategory: cims (Customer Instructions Management System)

ServiceNow FSO-inspired unified identity model. The bank holds many
representations of the same customer across systems — core banking
customer ID, mobile app user ID, biometric ID, contact-centre lookup ID,
sanctions-screening ID, etc. This engine catalogues those identifiers
as IdentityLink records pointing to a single canonical UnifiedIdentity,
and tracks proposed merges through an explicit approval workflow.

Public API:
    register_unified_identity(identity_data, actor, reason)
    register_identity_link(link_data, actor, reason)
    transition_identity_state(identity_id, new_state, actor, reason)
    propose_merge(merge_data, actor, reason)
    approve_merge(merge_id, actor, reason)
    reject_merge(merge_id, actor, reason)
    identity_summary(identity_id) -> Dict
    pending_merges() -> List

IDENTITY_LINK_TYPES byte-for-byte (8):
    CORE_BANKING_CUST_ID, MOBILE_APP_USER_ID, BIOMETRIC_ID,
    CONTACT_CENTRE_ID, SANCTIONS_SCREENING_ID, NATIONAL_ID,
    PASSPORT_NUMBER, CRM_LEAD_ID

IDENTITY_STATES byte-for-byte (5):
    PROVISIONAL, VERIFIED, MERGED, ARCHIVED, FLAGGED

ALLOWED_IDENTITY_TRANSITIONS (Rule 4):
    PROVISIONAL → VERIFIED | FLAGGED | ARCHIVED
    VERIFIED    → MERGED | FLAGGED | ARCHIVED
    MERGED      → ()
    FLAGGED     → VERIFIED | ARCHIVED
    ARCHIVED    → ()

MERGE_OUTCOMES byte-for-byte (4):
    PROPOSED, APPROVED, REJECTED, REVERSED

ALLOWED_MERGE_TRANSITIONS (Rule 4):
    PROPOSED → APPROVED | REJECTED
    APPROVED → REVERSED
    REJECTED → ()
    REVERSED → ()

DEFAULT_MERGE_REVIEW_HOURS = 24
DEFAULT_FLAGGED_REVIEW_HOURS = 4

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


IDENTITY_LINK_TYPES: Tuple[str, ...] = (
    "CORE_BANKING_CUST_ID", "MOBILE_APP_USER_ID", "BIOMETRIC_ID",
    "CONTACT_CENTRE_ID", "SANCTIONS_SCREENING_ID", "NATIONAL_ID",
    "PASSPORT_NUMBER", "CRM_LEAD_ID",
)

IDENTITY_STATES: Tuple[str, ...] = (
    "PROVISIONAL", "VERIFIED", "MERGED", "ARCHIVED", "FLAGGED",
)

ALLOWED_IDENTITY_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PROVISIONAL": ("VERIFIED", "FLAGGED", "ARCHIVED"),
    "VERIFIED":    ("MERGED", "FLAGGED", "ARCHIVED"),
    "MERGED":      (),
    "FLAGGED":     ("VERIFIED", "ARCHIVED"),
    "ARCHIVED":    (),
}

MERGE_OUTCOMES: Tuple[str, ...] = (
    "PROPOSED", "APPROVED", "REJECTED", "REVERSED",
)

ALLOWED_MERGE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PROPOSED": ("APPROVED", "REJECTED"),
    "APPROVED": ("REVERSED",),
    "REJECTED": (),
    "REVERSED": (),
}

DEFAULT_MERGE_REVIEW_HOURS = 24
DEFAULT_FLAGGED_REVIEW_HOURS = 4


class UnifiedIdentityEngine:
    """Unified identity registry — never auto-merges; explicit approval."""

    def __init__(
        self,
        identities_path: Optional[Path] = None,
        links_path: Optional[Path] = None,
        merges_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.identities_path = (
            identities_path or base / "cims_unified_identities.json"
        )
        self.links_path = (
            links_path or base / "cims_identity_links.json"
        )
        self.merges_path = (
            merges_path or base / "cims_identity_merges.json"
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

    def register_unified_identity(
        self, identity_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("identity_id", "display_name"):
            if f not in identity_data or not identity_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.identities_path,
                                "cims_unified_identities", ("identity_id",))
        if any(r.get("identity_id") == identity_data["identity_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_identity_id"}
        record = {
            "identity_id": identity_data["identity_id"],
            "display_name": identity_data["display_name"],
            "primary_email": identity_data.get("primary_email", ""),
            "primary_phone": identity_data.get("primary_phone", ""),
            "state": "PROVISIONAL",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PROVISIONAL", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.identities_path, records,
                          "cims_unified_identities", "identity_id")
        return {"registered": ok,
                  "identity_id": identity_data["identity_id"]}

    def register_identity_link(
        self, link_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("link_id", "identity_id", "link_type", "external_id"):
            if f not in link_data or not link_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if link_data["link_type"] not in IDENTITY_LINK_TYPES:
            return {"registered": False,
                       "error": f"invalid_link_type:{link_data['link_type']}"}
        # Verify identity exists
        identities = self._load(self.identities_path,
                                            "cims_unified_identities",
                                            ("identity_id",))
        if not any(i.get("identity_id") == link_data["identity_id"]
                       for i in identities):
            return {"registered": False, "error": "identity_not_found"}
        records = self._load(self.links_path,
                                "cims_identity_links", ("link_id",))
        if any(r.get("link_id") == link_data["link_id"] for r in records):
            return {"registered": False, "error": "duplicate_link_id"}
        record = {
            "link_id": link_data["link_id"],
            "identity_id": link_data["identity_id"],
            "link_type": link_data["link_type"],
            "external_id": link_data["external_id"],
            "verified": bool(link_data.get("verified", False)),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.links_path, records,
                          "cims_identity_links", "link_id")
        return {"registered": ok, "link_id": link_data["link_id"]}

    def transition_identity_state(
        self, identity_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in IDENTITY_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.identities_path,
                                "cims_unified_identities", ("identity_id",))
        for r in records:
            if r.get("identity_id") == identity_id:
                current = r.get("state", "PROVISIONAL")
                allowed = ALLOWED_IDENTITY_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.identities_path, records,
                                  "cims_unified_identities", "identity_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "identity_not_found"}

    def propose_merge(
        self, merge_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"proposed": False, "error": "actor_and_reason_required"}
        for f in ("merge_id", "primary_identity_id",
                      "secondary_identity_id"):
            if f not in merge_data or not merge_data[f]:
                return {"proposed": False, "error": f"missing_field:{f}"}
        if (merge_data["primary_identity_id"]
                == merge_data["secondary_identity_id"]):
            return {"proposed": False,
                       "error": "primary_and_secondary_must_differ"}
        # Verify both identities exist
        identities = self._load(self.identities_path,
                                            "cims_unified_identities",
                                            ("identity_id",))
        existing_ids = {i.get("identity_id") for i in identities}
        if merge_data["primary_identity_id"] not in existing_ids:
            return {"proposed": False, "error": "primary_identity_not_found"}
        if merge_data["secondary_identity_id"] not in existing_ids:
            return {"proposed": False,
                       "error": "secondary_identity_not_found"}
        records = self._load(self.merges_path,
                                "cims_identity_merges", ("merge_id",))
        if any(r.get("merge_id") == merge_data["merge_id"]
                 for r in records):
            return {"proposed": False, "error": "duplicate_merge_id"}
        record = {
            "merge_id": merge_data["merge_id"],
            "primary_identity_id": merge_data["primary_identity_id"],
            "secondary_identity_id": merge_data["secondary_identity_id"],
            "match_score": merge_data.get("match_score"),
            "match_evidence": list(
                merge_data.get("match_evidence", []),
            ),
            "outcome": "PROPOSED",
            "proposed_by": actor,
            "proposed_at": datetime.utcnow().isoformat(),
            "proposal_reason": reason,
            "transitions": [{
                "to": "PROPOSED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.merges_path, records,
                          "cims_identity_merges", "merge_id")
        return {"proposed": ok, "merge_id": merge_data["merge_id"]}

    def _transition_merge(
        self, merge_id: str, new_outcome: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        records = self._load(self.merges_path,
                                "cims_identity_merges", ("merge_id",))
        for r in records:
            if r.get("merge_id") == merge_id:
                current = r.get("outcome", "PROPOSED")
                allowed = ALLOWED_MERGE_TRANSITIONS.get(current, ())
                if new_outcome not in allowed:
                    return {"ok": False,
                               "error": f"transition_not_allowed:{current}_to_{new_outcome}"}
                r["outcome"] = new_outcome
                r.setdefault("transitions", []).append({
                    "to": new_outcome, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                if new_outcome == "APPROVED":
                    r["approved_by"] = actor
                    r["approved_at"] = datetime.utcnow().isoformat()
                elif new_outcome == "REJECTED":
                    r["rejected_by"] = actor
                    r["rejected_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.merges_path, records,
                                  "cims_identity_merges", "merge_id")
                return {"ok": ok, "from": current, "to": new_outcome}
        return {"ok": False, "error": "merge_not_found"}

    def approve_merge(
        self, merge_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"approved": False, "error": "actor_and_reason_required"}
        result = self._transition_merge(
            merge_id, "APPROVED", actor=actor, reason=reason,
        )
        return {"approved": result.get("ok", False),
                  "from": result.get("from"),
                  "to": result.get("to"),
                  **({"error": result["error"]}
                          if "error" in result else {})}

    def reject_merge(
        self, merge_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"rejected": False, "error": "actor_and_reason_required"}
        result = self._transition_merge(
            merge_id, "REJECTED", actor=actor, reason=reason,
        )
        return {"rejected": result.get("ok", False),
                  "from": result.get("from"),
                  "to": result.get("to"),
                  **({"error": result["error"]}
                          if "error" in result else {})}

    def identity_summary(self, identity_id: str) -> Dict[str, Any]:
        identities = self._load(self.identities_path,
                                            "cims_unified_identities",
                                            ("identity_id",))
        identity = next((i for i in identities
                                  if i.get("identity_id") == identity_id),
                                 None)
        if identity is None:
            return {"found": False, "error": "identity_not_found"}
        links = [l for l in self._load(self.links_path,
                                                  "cims_identity_links",
                                                  ("link_id",))
                       if l.get("identity_id") == identity_id]
        link_types = sorted({l.get("link_type") for l in links})
        merges = [
            m for m in self._load(self.merges_path,
                                              "cims_identity_merges",
                                              ("merge_id",))
            if (m.get("primary_identity_id") == identity_id
                    or m.get("secondary_identity_id") == identity_id)
        ]
        return {
            "found": True,
            "identity_id": identity_id,
            "state": identity.get("state"),
            "display_name": identity.get("display_name"),
            "link_count": len(links),
            "link_types": link_types,
            "merge_history_count": len(merges),
            "verified_links": sum(
                1 for l in links if l.get("verified")
            ),
        }

    def pending_merges(self) -> List[Dict[str, Any]]:
        records = self._load(self.merges_path,
                                "cims_identity_merges", ("merge_id",))
        return [r for r in records if r.get("outcome") == "PROPOSED"]


def _self_test() -> None:
    import tempfile

    assert IDENTITY_LINK_TYPES == (
        "CORE_BANKING_CUST_ID", "MOBILE_APP_USER_ID", "BIOMETRIC_ID",
        "CONTACT_CENTRE_ID", "SANCTIONS_SCREENING_ID", "NATIONAL_ID",
        "PASSPORT_NUMBER", "CRM_LEAD_ID",
    )
    assert IDENTITY_STATES == (
        "PROVISIONAL", "VERIFIED", "MERGED", "ARCHIVED", "FLAGGED",
    )
    assert ALLOWED_IDENTITY_TRANSITIONS["MERGED"] == ()
    assert ALLOWED_IDENTITY_TRANSITIONS["ARCHIVED"] == ()
    assert MERGE_OUTCOMES == (
        "PROPOSED", "APPROVED", "REJECTED", "REVERSED",
    )
    assert ALLOWED_MERGE_TRANSITIONS["REJECTED"] == ()
    assert ALLOWED_MERGE_TRANSITIONS["REVERSED"] == ()
    assert DEFAULT_MERGE_REVIEW_HOURS == 24
    assert DEFAULT_FLAGGED_REVIEW_HOURS == 4

    with tempfile.TemporaryDirectory() as tmpdir:
        e = UnifiedIdentityEngine(
            identities_path=Path(tmpdir) / "i.json",
            links_path=Path(tmpdir) / "l.json",
            merges_path=Path(tmpdir) / "m.json",
        )
        # Identity
        r = e.register_unified_identity(
            {"identity_id": "ID-001",
             "display_name": "Jane Wanjiru",
             "primary_email": "jane@example.com",
             "primary_phone": "+254700000001"},
            actor="onboarding", reason="new customer",
        )
        assert r["registered"]

        # Link
        r = e.register_identity_link(
            {"link_id": "LINK-001",
             "identity_id": "ID-001",
             "link_type": "CORE_BANKING_CUST_ID",
             "external_id": "CB-1234567",
             "verified": True},
            actor="kyc", reason="onboarded",
        )
        assert r["registered"]
        # Bad link type
        r = e.register_identity_link(
            {"link_id": "X", "identity_id": "ID-001",
             "link_type": "WHATEVER", "external_id": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Identity not found
        r = e.register_identity_link(
            {"link_id": "Y", "identity_id": "GHOST",
             "link_type": "CORE_BANKING_CUST_ID",
             "external_id": "Z"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Add another link
        e.register_identity_link(
            {"link_id": "LINK-002",
             "identity_id": "ID-001",
             "link_type": "MOBILE_APP_USER_ID",
             "external_id": "MOB-9999",
             "verified": True},
            actor="mobile-svc", reason="mobile registration",
        )

        # Lifecycle
        r = e.transition_identity_state(
            "ID-001", "VERIFIED",
            actor="kyc", reason="documents verified",
        )
        assert r["transitioned"]

        # Second identity for merge test
        e.register_unified_identity(
            {"identity_id": "ID-002",
             "display_name": "Jane W.",
             "primary_phone": "+254700000001"},
            actor="contact-centre", reason="duplicate suspected",
        )

        # Propose merge
        r = e.propose_merge(
            {"merge_id": "MERGE-001",
             "primary_identity_id": "ID-001",
             "secondary_identity_id": "ID-002",
             "match_score": 0.94,
             "match_evidence": ["matching_phone", "similar_name"]},
            actor="dedup-svc", reason="suspected duplicate",
        )
        assert r["proposed"]
        # Self-merge rejected
        r = e.propose_merge(
            {"merge_id": "X", "primary_identity_id": "ID-001",
             "secondary_identity_id": "ID-001"},
            actor="x", reason="x",
        )
        assert not r["proposed"]
        # Ghost identity
        r = e.propose_merge(
            {"merge_id": "Y", "primary_identity_id": "GHOST",
             "secondary_identity_id": "ID-001"},
            actor="x", reason="x",
        )
        assert not r["proposed"]

        pending = e.pending_merges()
        assert len(pending) == 1

        # Approve
        r = e.approve_merge(
            "MERGE-001", actor="data-steward",
            reason="evidence supports duplicate",
        )
        assert r["approved"]
        # Approving again — must fail (APPROVED can only go REVERSED)
        r = e.approve_merge(
            "MERGE-001", actor="x", reason="x",
        )
        assert not r["approved"]

        # Summary
        s = e.identity_summary("ID-001")
        assert s["found"]
        assert s["link_count"] == 2
        assert "CORE_BANKING_CUST_ID" in s["link_types"]
        assert "MOBILE_APP_USER_ID" in s["link_types"]
        assert s["verified_links"] == 2
        assert s["merge_history_count"] == 1

        # Reject path
        e.register_unified_identity(
            {"identity_id": "ID-003",
             "display_name": "Bob"},
            actor="onboarding", reason="new",
        )
        e.propose_merge(
            {"merge_id": "MERGE-002",
             "primary_identity_id": "ID-001",
             "secondary_identity_id": "ID-003",
             "match_score": 0.31},
            actor="dedup-svc", reason="weak match",
        )
        r = e.reject_merge(
            "MERGE-002", actor="data-steward",
            reason="match score too low",
        )
        assert r["rejected"]
        # REJECTED is terminal
        r = e.approve_merge(
            "MERGE-002", actor="x", reason="x",
        )
        assert not r["approved"]

    print("  ✅ cims_unified_identity self-test PASS")


if __name__ == "__main__":
    _self_test()
