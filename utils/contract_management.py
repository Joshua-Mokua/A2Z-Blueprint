"""
================================================================================
A2Z MIS 360 — Standard #370: MOU & Contract Management
================================================================================

Risk classification: Cat B + Cat C (deterministic versioning + state machine
                                       + key-date tracking)

Centralized MOU/contract repository with versioning, key-dates
(renewal, termination), obligations + milestones tracking. Composes
the existing legal_repository for storage; this module adds the
partner-specific contract surface.

Public API:
    register_contract(partner_id, contract_data, actor, reason)
    create_version(contract_id, version_data, actor, reason)
    track_milestone(contract_id, milestone_id, status, actor)
    expiring_soon(days_ahead=90) -> contracts approaching renewal
    list_obligations(contract_id, state=None) -> [obligations]
    transition_contract_state(contract_id, new_state, actor, reason)

CONTRACT_TYPES byte-for-byte:
    MOU             -- non-binding memorandum of understanding
    SLA             -- service-level agreement
    REFERRAL        -- referral commission agreement
    DISTRIBUTION    -- distribution agreement
    INTEGRATION     -- technical integration / API
    NDA             -- non-disclosure agreement

CONTRACT_STATES byte-for-byte:
    DRAFT           -- being prepared
    UNDER_REVIEW    -- in legal/compliance review
    SIGNED          -- executed; binding
    AMENDED         -- being amended (parent → AMENDED while child active)
    RENEWED         -- replaced by renewal contract (terminal)
    EXPIRED         -- past expiry without renewal (terminal)
    TERMINATED      -- early termination (terminal)

ALLOWED_CONTRACT_TRANSITIONS (Rule 4):
    DRAFT          → UNDER_REVIEW | TERMINATED
    UNDER_REVIEW   → DRAFT | SIGNED | TERMINATED
    SIGNED         → AMENDED | RENEWED | EXPIRED | TERMINATED
    AMENDED        → SIGNED | TERMINATED
    RENEWED        → ()
    EXPIRED        → ()
    TERMINATED     → ()

OBLIGATION_STATES byte-for-byte:
    PENDING        -- not yet due
    IN_PROGRESS    -- being delivered
    COMPLETE       -- delivered
    OVERDUE        -- past due, not delivered
    WAIVED         -- formally waived

DEFAULT_RENEWAL_NOTICE_DAYS = 90  -- alerting window per Continuation.docx

Honesty rules:
    Rule 4: actor + reason mandatory; state machine no-skip
    Rule 6: invalid type/state/obligation rejected
    Rule 1: expiring_soon returns [] when no contracts (not None)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CONTRACT_TYPES: Tuple[str, ...] = (
    "MOU", "SLA", "REFERRAL", "DISTRIBUTION", "INTEGRATION", "NDA",
)

CONTRACT_STATES: Tuple[str, ...] = (
    "DRAFT", "UNDER_REVIEW", "SIGNED",
    "AMENDED", "RENEWED", "EXPIRED", "TERMINATED",
)

ALLOWED_CONTRACT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":         ("UNDER_REVIEW", "TERMINATED"),
    "UNDER_REVIEW":  ("DRAFT", "SIGNED", "TERMINATED"),
    "SIGNED":        ("AMENDED", "RENEWED", "EXPIRED", "TERMINATED"),
    "AMENDED":       ("SIGNED", "TERMINATED"),
    "RENEWED":       (),
    "EXPIRED":       (),
    "TERMINATED":    (),
}

OBLIGATION_STATES: Tuple[str, ...] = (
    "PENDING", "IN_PROGRESS", "COMPLETE", "OVERDUE", "WAIVED",
)

DEFAULT_RENEWAL_NOTICE_DAYS: int = 90


class ContractManagementEngine:
    """MOU/contract repository with versioning + obligations tracking."""

    def __init__(self, contracts_path: Optional[Path] = None):
        self.contracts_path = (
            contracts_path
            if contracts_path is not None
            else Path(__file__).parent.parent / "data" / "partner_contracts.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.contracts_path,
                table="partner_contracts",
                index_cols=("contract_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.contracts_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.contracts_path,
                data=records,
                table="partner_contracts",
                pk_col="contract_id")
            return True
        except Exception:
            return False

    def register_contract(
        self,
        partner_id: str,
        contract_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Register new contract in DRAFT state."""
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}

        for f in ("contract_id", "contract_type", "effective_date", "expiry_date"):
            if f not in contract_data or not contract_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        if contract_data["contract_type"] not in CONTRACT_TYPES:
            return {
                "registered": False,
                "error": f"invalid_contract_type:{contract_data['contract_type']}",
            }

        # Validate dates
        try:
            eff = date.fromisoformat(contract_data["effective_date"])
            exp = date.fromisoformat(contract_data["expiry_date"])
        except (ValueError, TypeError):
            return {"registered": False, "error": "invalid_date_format"}
        if exp < eff:
            return {"registered": False, "error": "expiry_before_effective"}

        records = self._load()
        if any(r.get("contract_id") == contract_data["contract_id"] for r in records):
            return {"registered": False, "error": "duplicate_contract_id"}

        record = {
            "contract_id": contract_data["contract_id"],
            "partner_id": partner_id,
            "contract_type": contract_data["contract_type"],
            "title": contract_data.get("title", ""),
            "state": "DRAFT",
            "version": "1.0",
            "effective_date": contract_data["effective_date"],
            "expiry_date": contract_data["expiry_date"],
            "renewal_notice_days": int(contract_data.get(
                "renewal_notice_days", DEFAULT_RENEWAL_NOTICE_DAYS)),
            "obligations": list(contract_data.get("obligations", [])),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
            "versions": [{
                "version": "1.0", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(records)
        return {"registered": ok, "contract_id": contract_data["contract_id"]}

    def create_version(
        self,
        contract_id: str,
        version: str,
        actor: str,
        reason: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Create new contract version."""
        if not actor or not reason or not version:
            return {"created": False, "error": "actor_reason_version_required"}

        records = self._load()
        for r in records:
            if r.get("contract_id") == contract_id:
                if r.get("state") in ("RENEWED", "EXPIRED", "TERMINATED"):
                    return {
                        "created": False,
                        "error": f"contract_in_terminal_state:{r['state']}",
                    }
                # Reject duplicate version number
                existing = {v["version"] for v in r.get("versions", [])}
                if version in existing:
                    return {
                        "created": False,
                        "error": f"duplicate_version:{version}",
                    }
                r["version"] = version
                r.setdefault("versions", []).append({
                    "version": version, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason, "notes": notes,
                })
                ok = self._save(records)
                return {"created": ok, "contract_id": contract_id,
                         "version": version}

        return {"created": False, "error": "contract_not_found"}

    def transition_contract_state(
        self,
        contract_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Transition contract state (Rule 4 no-skip)."""
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in CONTRACT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        records = self._load()
        for r in records:
            if r.get("contract_id") == contract_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_CONTRACT_TRANSITIONS.get(current, ())
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

        return {"transitioned": False, "error": "contract_not_found"}

    def track_milestone(
        self,
        contract_id: str,
        obligation_id: str,
        new_status: str,
        actor: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Update obligation/milestone status."""
        if not actor:
            return {"tracked": False, "error": "actor_required"}
        if new_status not in OBLIGATION_STATES:
            return {
                "tracked": False,
                "error": f"invalid_obligation_state:{new_status}",
                "valid_states": list(OBLIGATION_STATES),
            }

        records = self._load()
        for r in records:
            if r.get("contract_id") == contract_id:
                obs = r.get("obligations", [])
                for o in obs:
                    if o.get("obligation_id") == obligation_id:
                        o["status"] = new_status
                        o.setdefault("status_history", []).append({
                            "to": new_status, "actor": actor,
                            "at": datetime.utcnow().isoformat(),
                            "notes": notes,
                        })
                        ok = self._save(records)
                        return {
                            "tracked": ok,
                            "obligation_id": obligation_id,
                            "status": new_status,
                        }
                return {"tracked": False, "error": "obligation_not_found"}

        return {"tracked": False, "error": "contract_not_found"}

    def expiring_soon(
        self,
        days_ahead: int = DEFAULT_RENEWAL_NOTICE_DAYS,
        as_of: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Return contracts in SIGNED state with expiry within window."""
        as_of = as_of or date.today()
        cutoff = as_of + timedelta(days=days_ahead)
        out = []
        for r in self._load():
            if r.get("state") != "SIGNED":
                continue
            try:
                exp = date.fromisoformat(r.get("expiry_date", ""))
            except (ValueError, TypeError):
                continue
            if as_of <= exp <= cutoff:
                out.append({
                    "contract_id": r["contract_id"],
                    "partner_id": r.get("partner_id"),
                    "expiry_date": r["expiry_date"],
                    "days_until_expiry": (exp - as_of).days,
                    "contract_type": r.get("contract_type"),
                })
        out.sort(key=lambda x: x["days_until_expiry"])
        return out

    def list_obligations(
        self,
        contract_id: str,
        state: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List obligations for a contract, optionally filtered by state."""
        for r in self._load():
            if r.get("contract_id") == contract_id:
                obs = r.get("obligations", [])
                if state:
                    return [o for o in obs if o.get("status") == state]
                return list(obs)
        return []


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ContractManagementEngine(
            contracts_path=Path(tmpdir) / "c.json"
        )

        # Test 1: register contract
        r = engine.register_contract(
            "P-001",
            {"contract_id": "C-001", "contract_type": "REFERRAL",
             "title": "ACME referral agreement",
             "effective_date": "2026-01-01", "expiry_date": "2026-12-31",
             "obligations": [
                 {"obligation_id": "O-001", "description": "Provide leads weekly",
                  "due_date": "2026-12-31", "status": "PENDING"},
             ]},
            actor="legal", reason="initial registration",
        )
        assert r["registered"]

        # Test 2: invalid type rejected
        r = engine.register_contract(
            "P-001",
            {"contract_id": "C-002", "contract_type": "INVALID",
             "effective_date": "2026-01-01", "expiry_date": "2026-12-31"},
            actor="legal", reason="bad",
        )
        assert not r["registered"]

        # Test 3: expiry before effective rejected
        r = engine.register_contract(
            "P-001",
            {"contract_id": "C-003", "contract_type": "MOU",
             "effective_date": "2026-12-01", "expiry_date": "2026-01-01"},
            actor="legal", reason="bad date",
        )
        assert not r["registered"]
        assert r["error"] == "expiry_before_effective"

        # Test 4: state transition DRAFT → UNDER_REVIEW → SIGNED
        t = engine.transition_contract_state("C-001", "UNDER_REVIEW",
                                              "legal", "out for review")
        assert t["transitioned"]
        t = engine.transition_contract_state("C-001", "SIGNED",
                                              "legal", "executed")
        assert t["transitioned"]

        # Test 5: skip rejected DRAFT → SIGNED
        engine.register_contract(
            "P-002",
            {"contract_id": "C-004", "contract_type": "DISTRIBUTION",
             "effective_date": "2026-02-01", "expiry_date": "2027-01-31"},
            actor="legal", reason="reg",
        )
        t = engine.transition_contract_state("C-004", "SIGNED",
                                              "legal", "trying to skip")
        assert not t["transitioned"]
        assert "transition_not_allowed" in t["error"]

        # Test 6: create_version
        v = engine.create_version("C-001", "1.1", actor="legal",
                                    reason="amendment", notes="annex A")
        assert v["created"]

        # Test 7: duplicate version rejected
        v = engine.create_version("C-001", "1.0", actor="legal",
                                    reason="dup test")
        assert not v["created"]
        assert "duplicate_version" in v["error"]

        # Test 8: track_milestone
        m = engine.track_milestone("C-001", "O-001", "IN_PROGRESS",
                                     "ops", "leads flowing")
        assert m["tracked"]

        # Test 9: invalid obligation state rejected
        m = engine.track_milestone("C-001", "O-001", "INVALID",
                                     "ops", "")
        assert not m["tracked"]
        assert "invalid_obligation_state" in m["error"]

        # Test 10: expiring_soon — C-001 expires 2026-12-31
        # Set as_of to 2026-10-01 → 91 days → just outside default 90 window
        # Set as_of to 2026-10-15 → 77 days → inside window
        soon = engine.expiring_soon(
            days_ahead=90, as_of=date(2026, 10, 15)
        )
        assert len(soon) == 1
        assert soon[0]["contract_id"] == "C-001"

        # Test 11: terminal state — RENEWED can't transition out
        engine.transition_contract_state(
            "C-001", "RENEWED", actor="legal", reason="renewal"
        )
        t = engine.transition_contract_state(
            "C-001", "SIGNED", actor="legal", reason="trying to revive"
        )
        assert not t["transitioned"]

        # Test 12: list_obligations filtered
        in_progress = engine.list_obligations("C-001", state="IN_PROGRESS")
        assert len(in_progress) == 1
        assert in_progress[0]["obligation_id"] == "O-001"

    print("  ✅ contract_management self-test PASS")


if __name__ == "__main__":
    _self_test()
