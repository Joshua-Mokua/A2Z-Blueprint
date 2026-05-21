"""
================================================================================
A2Z MIS 360 — Standard #368: Segment Manager Role & Permissions
================================================================================

Risk classification: Cat C (security — RBAC contract)

Segment manager role with cross-functional view: P&L, customers,
products, RMs assigned, initiatives. LIMITED write permissions.

Composes the existing role/permission infrastructure (utils/auth_jwt
+ utils/admin_registry); this module defines the SEGMENT_MANAGER role
contract specifically.

Public API:
    role_definition() -> frozen role config
    can_read(role, resource, resource_segment_code)
    can_write(role, resource, resource_segment_code)
    assign_segment_manager(user_id, segment_code, actor, reason)
    revoke_segment_manager(user_id, segment_code, actor, reason)
    list_assignments(segment_code=None) -> active assignments

Permission matrix byte-for-byte (resource → access):
    SEGMENT_PNL              -> READ (cross-segment forbidden)
    SEGMENT_CUSTOMERS        -> READ (own segment only)
    SEGMENT_PRODUCTS         -> READ + propose (no direct WRITE)
    SEGMENT_RMS              -> READ
    SEGMENT_INITIATIVES      -> READ + WRITE (own segment only)
    SEGMENT_TARGETS          -> READ + propose (final write requires approval)
    OTHER_SEGMENT_DATA       -> NONE (cross-segment forbidden by default)

Authorization contract:
    SEGMENT_MANAGER role NEVER has unrestricted WRITE on financial
    or customer data. Initiative tracking is the ONLY direct-write
    resource. Everything else is read-only or proposal-only.

Honesty rules:
    Rule 4: actor + reason required for assign/revoke; no skip transitions
    Rule 6: cross-segment access denied by default (fail closed)

================================================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.specialized_segments_tagging import SEGMENT_CODES


ROLE_NAME: str = "SEGMENT_MANAGER"

# Permission matrix — byte-for-byte
PERMISSION_MATRIX: Dict[str, Dict[str, str]] = {
    "SEGMENT_PNL":         {"read": "OWN_SEGMENT", "write": "DENY"},
    "SEGMENT_CUSTOMERS":   {"read": "OWN_SEGMENT", "write": "DENY"},
    "SEGMENT_PRODUCTS":    {"read": "OWN_SEGMENT", "write": "DENY",
                              "propose": "OWN_SEGMENT"},
    "SEGMENT_RMS":         {"read": "OWN_SEGMENT", "write": "DENY"},
    "SEGMENT_INITIATIVES": {"read": "OWN_SEGMENT", "write": "OWN_SEGMENT"},
    "SEGMENT_TARGETS":     {"read": "OWN_SEGMENT", "write": "DENY",
                              "propose": "OWN_SEGMENT"},
    "OTHER_SEGMENT_DATA":  {"read": "DENY", "write": "DENY"},
}

ASSIGNMENT_STATES: Tuple[str, ...] = ("ACTIVE", "REVOKED")


def role_definition() -> Dict[str, Any]:
    """Frozen role configuration descriptor."""
    return {
        "role_name": ROLE_NAME,
        "description": (
            "Cross-functional view of one specialized segment's P&L, "
            "customers, products, RMs, initiatives. Limited WRITE "
            "permissions: only initiatives can be directly modified; "
            "products and targets require proposal-then-approval."
        ),
        "permission_matrix": dict(PERMISSION_MATRIX),
        "scope": "PER_SEGMENT",
        "data_isolation": "OWN_SEGMENT_ONLY",
        "spec_ref": "Continuation.docx #368",
    }


def can_read(role: str, resource: str, role_segment: str,
             resource_segment: str) -> Dict[str, Any]:
    """
    Check read permission.

    Returns: {allowed, reason}.
    """
    if role != ROLE_NAME:
        return {"allowed": False, "reason": f"role_not_segment_manager:{role}"}
    if resource not in PERMISSION_MATRIX:
        return {"allowed": False, "reason": f"unknown_resource:{resource}"}

    rule = PERMISSION_MATRIX[resource].get("read", "DENY")
    if rule == "DENY":
        return {"allowed": False, "reason": "read_denied_by_matrix"}
    if rule == "OWN_SEGMENT":
        if role_segment == resource_segment:
            return {"allowed": True, "reason": "own_segment"}
        return {
            "allowed": False,
            "reason": f"cross_segment_denied:{role_segment}_vs_{resource_segment}",
        }
    return {"allowed": False, "reason": f"unknown_rule:{rule}"}


def can_write(role: str, resource: str, role_segment: str,
              resource_segment: str) -> Dict[str, Any]:
    """Check write permission."""
    if role != ROLE_NAME:
        return {"allowed": False, "reason": f"role_not_segment_manager:{role}"}
    if resource not in PERMISSION_MATRIX:
        return {"allowed": False, "reason": f"unknown_resource:{resource}"}

    rule = PERMISSION_MATRIX[resource].get("write", "DENY")
    if rule == "DENY":
        return {"allowed": False, "reason": "write_denied_by_matrix"}
    if rule == "OWN_SEGMENT":
        if role_segment == resource_segment:
            return {"allowed": True, "reason": "own_segment_write_allowed"}
        return {
            "allowed": False,
            "reason": f"cross_segment_write_denied:{role_segment}_vs_{resource_segment}",
        }
    return {"allowed": False, "reason": f"unknown_rule:{rule}"}


def can_propose(role: str, resource: str, role_segment: str,
                 resource_segment: str) -> Dict[str, Any]:
    """Check propose permission (proposal-then-approval pattern)."""
    if role != ROLE_NAME:
        return {"allowed": False, "reason": f"role_not_segment_manager:{role}"}
    if resource not in PERMISSION_MATRIX:
        return {"allowed": False, "reason": f"unknown_resource:{resource}"}

    rule = PERMISSION_MATRIX[resource].get("propose", "DENY")
    if rule == "DENY":
        return {"allowed": False, "reason": "propose_denied_by_matrix"}
    if rule == "OWN_SEGMENT":
        if role_segment == resource_segment:
            return {"allowed": True, "reason": "own_segment_propose_allowed"}
        return {
            "allowed": False,
            "reason": "cross_segment_propose_denied",
        }
    return {"allowed": False, "reason": f"unknown_rule:{rule}"}


# ────────────────────────────────────────────────────────────────────
# Assignment engine
# ────────────────────────────────────────────────────────────────────

class SegmentManagerAssignmentEngine:
    """Manages SEGMENT_MANAGER role assignments to users."""

    def __init__(self, assignments_path: Optional[Path] = None):
        self.assignments_path = (
            assignments_path
            if assignments_path is not None
            else Path(__file__).parent.parent / "data" / "segment_manager_assignments.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db   # singleton Database instance
            data = _db.dual_load(
                self.assignments_path,
                table="segment_manager_assignments",
                index_cols=("user_id", "segment_code"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.assignments_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.assignments_path,
                data=records,
                table="segment_manager_assignments",
                pk_col="user_id")
            return True
        except Exception:
            return False

    def assign_segment_manager(
        self,
        user_id: str,
        segment_code: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Assign SEGMENT_MANAGER role for a segment to a user."""
        if not actor or not reason:
            return {"assigned": False, "error": "actor_and_reason_required"}
        if segment_code not in SEGMENT_CODES:
            return {"assigned": False, "error": f"invalid_segment:{segment_code}"}
        if not user_id:
            return {"assigned": False, "error": "user_id_required"}

        records = self._load()

        # Check duplicate active
        for r in records:
            if (r.get("user_id") == user_id
                    and r.get("segment_code") == segment_code
                    and r.get("state") == "ACTIVE"):
                return {
                    "assigned": False,
                    "error": "duplicate_active_assignment",
                }

        record = {
            "user_id": user_id,
            "segment_code": segment_code,
            "role": ROLE_NAME,
            "state": "ACTIVE",
            "assigned_by": actor,
            "reason": reason,
            "assigned_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(records)
        return {
            "assigned": ok,
            "user_id": user_id,
            "segment_code": segment_code,
            "role": ROLE_NAME,
        }

    def revoke_segment_manager(
        self,
        user_id: str,
        segment_code: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Revoke active assignment."""
        if not actor or not reason:
            return {"revoked": False, "error": "actor_and_reason_required"}

        records = self._load()
        for r in records:
            if (r.get("user_id") == user_id
                    and r.get("segment_code") == segment_code
                    and r.get("state") == "ACTIVE"):
                r["state"] = "REVOKED"
                r["revoked_by"] = actor
                r["revocation_reason"] = reason
                r["revoked_at"] = datetime.utcnow().isoformat()
                ok = self._save(records)
                return {"revoked": ok, "user_id": user_id, "segment_code": segment_code}

        return {"revoked": False, "error": "no_active_assignment_found"}

    def list_assignments(
        self,
        segment_code: Optional[str] = None,
        state: str = "ACTIVE",
    ) -> List[Dict[str, Any]]:
        """List assignments, filtered."""
        records = self._load()
        out = []
        for r in records:
            if state and r.get("state") != state:
                continue
            if segment_code and r.get("segment_code") != segment_code:
                continue
            out.append(r)
        return out


def _self_test() -> None:
    import tempfile

    # Test 1: role_definition is frozen
    role = role_definition()
    assert role["role_name"] == "SEGMENT_MANAGER"
    assert role["data_isolation"] == "OWN_SEGMENT_ONLY"
    assert "SEGMENT_PNL" in role["permission_matrix"]

    # Test 2: read own segment allowed
    r = can_read("SEGMENT_MANAGER", "SEGMENT_PNL", "WOMEN", "WOMEN")
    assert r["allowed"]
    assert r["reason"] == "own_segment"

    # Test 3: cross-segment read denied (Rule 6)
    r = can_read("SEGMENT_MANAGER", "SEGMENT_PNL", "WOMEN", "AGRI")
    assert not r["allowed"]
    assert "cross_segment_denied" in r["reason"]

    # Test 4: SEGMENT_PNL write always denied
    r = can_write("SEGMENT_MANAGER", "SEGMENT_PNL", "WOMEN", "WOMEN")
    assert not r["allowed"]
    assert r["reason"] == "write_denied_by_matrix"

    # Test 5: SEGMENT_INITIATIVES write own segment ALLOWED
    r = can_write("SEGMENT_MANAGER", "SEGMENT_INITIATIVES", "WOMEN", "WOMEN")
    assert r["allowed"]
    assert r["reason"] == "own_segment_write_allowed"

    # Test 6: SEGMENT_INITIATIVES write cross-segment DENIED
    r = can_write("SEGMENT_MANAGER", "SEGMENT_INITIATIVES", "WOMEN", "AGRI")
    assert not r["allowed"]
    assert "cross_segment_write_denied" in r["reason"]

    # Test 7: propose own segment allowed
    r = can_propose("SEGMENT_MANAGER", "SEGMENT_PRODUCTS", "WOMEN", "WOMEN")
    assert r["allowed"]
    r = can_propose("SEGMENT_MANAGER", "SEGMENT_PNL", "WOMEN", "WOMEN")
    assert not r["allowed"]  # SEGMENT_PNL has no propose rule

    # Test 8: wrong role denied
    r = can_read("ANALYST", "SEGMENT_PNL", "WOMEN", "WOMEN")
    assert not r["allowed"]
    assert "role_not_segment_manager" in r["reason"]

    # Test 9: OTHER_SEGMENT_DATA always denied
    r = can_read("SEGMENT_MANAGER", "OTHER_SEGMENT_DATA", "WOMEN", "WOMEN")
    assert not r["allowed"]

    # Test 10: assignment engine
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = SegmentManagerAssignmentEngine(
            assignments_path=Path(tmpdir) / "assignments.json"
        )
        result = engine.assign_segment_manager(
            "USER-001", "WOMEN", actor="hr_admin", reason="org change"
        )
        assert result["assigned"]

        # Duplicate rejected
        dup = engine.assign_segment_manager(
            "USER-001", "WOMEN", actor="hr_admin", reason="dup test"
        )
        assert not dup["assigned"]
        assert dup["error"] == "duplicate_active_assignment"

        # Different segment OK
        result = engine.assign_segment_manager(
            "USER-001", "AGRI", actor="hr_admin", reason="dual role"
        )
        assert result["assigned"]

        # List
        active = engine.list_assignments()
        assert len(active) == 2

        # Revoke
        rev = engine.revoke_segment_manager(
            "USER-001", "WOMEN", actor="hr_admin", reason="reorganization"
        )
        assert rev["revoked"]
        active = engine.list_assignments()
        assert len(active) == 1
        assert active[0]["segment_code"] == "AGRI"

        # Rule 4: actor required
        bad = engine.assign_segment_manager(
            "USER-002", "YOUTH", actor="", reason=""
        )
        assert not bad["assigned"]

    print("  ✅ segment_manager_role self-test PASS")


if __name__ == "__main__":
    _self_test()
