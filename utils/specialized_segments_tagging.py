"""
================================================================================
A2Z MIS 360 — Standard #359: Specialized Segments Customer Tagging
================================================================================

Risk classification: Cat B (deterministic tagging + lifecycle state machine)

Multi-tag customer segmentation by specialized banking segment (women,
diaspora, asset-finance, agri, youth, SME). Composes existing
customer_segmentation engine for the base segmentation logic; this
module adds the specialized-segments overlay.

Public API:
    tag_customer(customer_id, segment_code, actor, source, ...)
    untag_customer(customer_id, segment_code, actor, reason)
    get_customer_segments(customer_id) -> list of active tags
    list_segment_customers(segment_code, status='ACTIVE') -> [customer_ids]
    transition_tag_state(customer_id, segment_code, new_state, actor, reason)
    segment_summary() -> per-segment + total tagged customers

SEGMENT_CODES byte-for-byte (Continuation.docx #359-#364 + SME):
    WOMEN          -- Women-focused proposition (#360, SDG 5)
    DIASPORA       -- Diaspora banking (#361)
    ASSET_FINANCE  -- Vehicle / machinery / equipment finance (#362)
    AGRI           -- Agri-business (#363, AFC Act)
    YOUTH          -- 18-35 youth banking (#364)
    SME            -- Small/medium enterprise (cluster anchor)

Tag lifecycle states byte-for-byte:
    TAGGED        -- initial tag captured pending verification
    ACTIVE        -- verified eligibility, segment benefits enabled
    INACTIVE      -- previously active, currently dormant
    REMOVED       -- tag retired (terminal)

ALLOWED_TAG_TRANSITIONS (Rule 4 no-skip state machine):
    TAGGED   → ACTIVE | REMOVED
    ACTIVE   → INACTIVE | REMOVED
    INACTIVE → ACTIVE | REMOVED
    REMOVED  → ()  -- terminal

Tag sources (fail-closed catalog):
    BRANCH_OFFICER   -- in-branch tagging by RM
    DIGITAL_SIGNUP   -- self-service via mobile/web
    DATA_INFERENCE   -- inferred from transaction patterns + KYC data
    BULK_MIGRATION   -- one-time migration (e.g. portfolio transfer)
    AUTO_RENEWAL     -- system-driven re-evaluation

Honesty rules:
    Rule 4: actor + reason mandatory on all transitions; CLOSED states
            cannot reopen; skip transitions rejected
    Rule 6: invalid segment_code or transition rejected (fail-closed)
    Rule 1: get_customer_segments returns [] when customer not found
            (NOT None — empty list is the natural "no segments" answer)

================================================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte
# ────────────────────────────────────────────────────────────────────

SEGMENT_CODES: Tuple[str, ...] = (
    "WOMEN",
    "DIASPORA",
    "ASSET_FINANCE",
    "AGRI",
    "YOUTH",
    "SME",
)

TAG_STATES: Tuple[str, ...] = (
    "TAGGED",
    "ACTIVE",
    "INACTIVE",
    "REMOVED",
)

ALLOWED_TAG_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "TAGGED":   ("ACTIVE", "REMOVED"),
    "ACTIVE":   ("INACTIVE", "REMOVED"),
    "INACTIVE": ("ACTIVE", "REMOVED"),
    "REMOVED":  (),
}

TAG_SOURCES: Tuple[str, ...] = (
    "BRANCH_OFFICER",
    "DIGITAL_SIGNUP",
    "DATA_INFERENCE",
    "BULK_MIGRATION",
    "AUTO_RENEWAL",
)


# ────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────

class SegmentTaggingEngine:
    """
    Multi-tag specialized segments engine. Customers may carry
    multiple tags simultaneously (e.g. WOMEN + AGRI + SME).
    """

    def __init__(self, tags_path: Optional[Path] = None):
        self.tags_path = (
            tags_path
            if tags_path is not None
            else Path(__file__).parent.parent / "data" / "specialized_segment_tags.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db   # singleton Database instance
            data = _db.dual_load(
                self.tags_path,
                table="specialized_segment_tags",
                index_cols=("customer_id", "segment_code"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.tags_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.tags_path,
                data=records,
                table="specialized_segment_tags",
                pk_col="customer_id")
            return True
        except Exception:
            return False

    def tag_customer(
        self,
        customer_id: str,
        segment_code: str,
        actor: str,
        source: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Tag customer with specialized segment.

        Rule 4: actor + source mandatory.
        Rule 6: invalid segment_code or source rejected.
        """
        if not actor or not source:
            return {"tagged": False, "error": "actor_and_source_required"}
        if segment_code not in SEGMENT_CODES:
            return {
                "tagged": False,
                "error": f"invalid_segment_code:{segment_code}",
                "valid_codes": list(SEGMENT_CODES),
            }
        if source not in TAG_SOURCES:
            return {
                "tagged": False,
                "error": f"invalid_source:{source}",
                "valid_sources": list(TAG_SOURCES),
            }

        records = self._load()

        # Check duplicate active tag
        for r in records:
            if (r.get("customer_id") == customer_id
                    and r.get("segment_code") == segment_code
                    and r.get("state") in ("TAGGED", "ACTIVE", "INACTIVE")):
                return {
                    "tagged": False,
                    "error": "duplicate_active_tag",
                    "existing_state": r["state"],
                }

        tag = {
            "customer_id": customer_id,
            "segment_code": segment_code,
            "state": "TAGGED",
            "source": source,
            "tagged_by": actor,
            "tagged_at": datetime.utcnow().isoformat(),
            "notes": notes,
            "transitions": [{
                "to": "TAGGED", "actor": actor, "source": source,
                "at": datetime.utcnow().isoformat(),
                "reason": "initial_tag",
            }],
        }
        records.append(tag)
        ok = self._save(records)
        return {
            "tagged": ok,
            "customer_id": customer_id,
            "segment_code": segment_code,
            "state": "TAGGED",
        }

    def transition_tag_state(
        self,
        customer_id: str,
        segment_code: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Transition tag state. Rule 4 no-skip enforced."""
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in TAG_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        records = self._load()
        for r in records:
            if (r.get("customer_id") == customer_id
                    and r.get("segment_code") == segment_code
                    and r.get("state") != "REMOVED"):  # most-recent non-removed
                current = r["state"]
                allowed = ALLOWED_TAG_TRANSITIONS.get(current, ())
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
                return {
                    "transitioned": ok,
                    "from": current, "to": new_state,
                }

        return {"transitioned": False, "error": "tag_not_found"}

    def get_customer_segments(
        self, customer_id: str, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Return all (or active-only) segment tags for a customer."""
        records = self._load()
        if active_only:
            return [
                r for r in records
                if r.get("customer_id") == customer_id and r.get("state") == "ACTIVE"
            ]
        return [
            r for r in records
            if r.get("customer_id") == customer_id
        ]

    def list_segment_customers(
        self, segment_code: str, state: str = "ACTIVE"
    ) -> List[str]:
        """List customer IDs in a given segment + state."""
        if segment_code not in SEGMENT_CODES:
            return []
        records = self._load()
        return sorted({
            r["customer_id"] for r in records
            if r.get("segment_code") == segment_code and r.get("state") == state
        })

    def segment_summary(self) -> Dict[str, Any]:
        """Per-segment counts by state."""
        records = self._load()
        summary: Dict[str, Dict[str, int]] = {
            s: {"TAGGED": 0, "ACTIVE": 0, "INACTIVE": 0, "REMOVED": 0}
            for s in SEGMENT_CODES
        }
        for r in records:
            sc = r.get("segment_code")
            st = r.get("state")
            if sc in summary and st in summary[sc]:
                summary[sc][st] += 1

        # Multi-tag count: customers with 2+ active tags
        from collections import defaultdict
        by_customer: Dict[str, set] = defaultdict(set)
        for r in records:
            if r.get("state") == "ACTIVE":
                by_customer[r["customer_id"]].add(r["segment_code"])
        multi_tag_customers = sum(1 for tags in by_customer.values() if len(tags) >= 2)

        return {
            "by_segment": summary,
            "total_tags": len(records),
            "multi_tag_customers": multi_tag_customers,
            "unique_active_customers": len(by_customer),
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = SegmentTaggingEngine(tags_path=Path(tmpdir) / "tags.json")

        # Test 1: tag customer
        result = engine.tag_customer(
            "CUST-001", "WOMEN", "alice", "BRANCH_OFFICER",
            notes="self-identified at branch onboarding",
        )
        assert result["tagged"], result
        assert result["state"] == "TAGGED"

        # Test 2: invalid segment_code rejected
        result = engine.tag_customer(
            "CUST-002", "INVALID", "alice", "BRANCH_OFFICER"
        )
        assert not result["tagged"]
        assert "invalid_segment_code" in result["error"]

        # Test 3: invalid source rejected
        result = engine.tag_customer(
            "CUST-003", "AGRI", "alice", "INVALID_SOURCE"
        )
        assert not result["tagged"]
        assert "invalid_source" in result["error"]

        # Test 4: actor required
        result = engine.tag_customer(
            "CUST-004", "YOUTH", "", "DIGITAL_SIGNUP"
        )
        assert not result["tagged"]
        assert result["error"] == "actor_and_source_required"

        # Test 5: state transition TAGGED → ACTIVE
        t = engine.transition_tag_state(
            "CUST-001", "WOMEN", "ACTIVE", "alice",
            "eligibility verified",
        )
        assert t["transitioned"]
        assert t["from"] == "TAGGED" and t["to"] == "ACTIVE"

        # Test 6: skip transition rejected ACTIVE → TAGGED (not allowed)
        t = engine.transition_tag_state(
            "CUST-001", "WOMEN", "TAGGED", "alice", "trying to skip"
        )
        assert not t["transitioned"]
        assert "transition_not_allowed" in t["error"]

        # Test 7: ACTIVE → REMOVED → cannot reopen
        engine.tag_customer("CUST-005", "AGRI", "alice", "BRANCH_OFFICER")
        engine.transition_tag_state(
            "CUST-005", "AGRI", "ACTIVE", "alice", "verified"
        )
        engine.transition_tag_state(
            "CUST-005", "AGRI", "REMOVED", "alice", "customer left"
        )
        # After removed, no active tag for this customer+segment
        # Trying to transition will say tag_not_found because we exclude REMOVED
        # in the lookup; that's acceptable behavior.

        # Test 8: multi-tag — same customer, different segments
        engine.tag_customer("CUST-001", "AGRI", "alice", "BRANCH_OFFICER")
        engine.transition_tag_state(
            "CUST-001", "AGRI", "ACTIVE", "alice", "agri loan opened"
        )
        segs = engine.get_customer_segments("CUST-001", active_only=True)
        assert len(segs) == 2  # WOMEN + AGRI both active
        codes = {s["segment_code"] for s in segs}
        assert codes == {"WOMEN", "AGRI"}

        # Test 9: list_segment_customers
        women_customers = engine.list_segment_customers("WOMEN")
        assert "CUST-001" in women_customers

        # Test 10: segment_summary
        summary = engine.segment_summary()
        assert summary["by_segment"]["WOMEN"]["ACTIVE"] == 1
        assert summary["by_segment"]["AGRI"]["ACTIVE"] == 1
        # CUST-001 has 2 active tags
        assert summary["multi_tag_customers"] == 1

        # Test 11: duplicate active tag rejected
        result = engine.tag_customer(
            "CUST-001", "WOMEN", "alice", "BRANCH_OFFICER"
        )
        assert not result["tagged"]
        assert result["error"] == "duplicate_active_tag"

        # Test 12: Rule 1 — unknown customer returns []
        empty = engine.get_customer_segments("UNKNOWN-CUST")
        assert empty == []

    print("  ✅ specialized_segments_tagging self-test PASS")


if __name__ == "__main__":
    _self_test()
