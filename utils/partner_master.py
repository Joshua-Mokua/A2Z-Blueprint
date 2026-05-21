"""
================================================================================
A2Z MIS 360 — Standard #369: Partner Master Data & Lifecycle Management
================================================================================

Risk classification: Cat B + Cat C (deterministic master record + state machine)

Partner master record management with lifecycle state machine.
Partners include referral partners, integration partners, distribution
partners, and ecosystem partners.

Public API:
    register_partner(partner_data, actor, reason)
    get_partner(partner_id)
    list_partners(partner_type=None, state='ACTIVE')
    transition_state(partner_id, new_state, actor, reason)
    update_partner_data(partner_id, updates, actor, reason)
    partner_summary() -> counts by type + state

PARTNER_TYPES byte-for-byte (Continuation.docx #369):
    REFERRAL       -- introduces customers; commission-based
    INTEGRATION    -- technical integration (API/data exchange)
    DISTRIBUTION   -- sells bank products through their channels
    ECOSYSTEM      -- joint products / co-branded offerings
    SERVICE        -- third-party service provider

PARTNER_STATES byte-for-byte (lifecycle):
    PROSPECT       -- initial discovery, not yet engaged
    ONBOARDING     -- contract + due diligence in progress
    ACTIVE         -- live; revenue-generating
    SUSPENDED      -- temporary suspension (compliance/perf issue)
    OFF_BOARDING   -- termination in progress
    OFF_BOARDED    -- terminal; relationship ended

ALLOWED_PARTNER_TRANSITIONS (Rule 4):
    PROSPECT       → ONBOARDING | OFF_BOARDED
    ONBOARDING     → ACTIVE | OFF_BOARDING | OFF_BOARDED
    ACTIVE         → SUSPENDED | OFF_BOARDING
    SUSPENDED      → ACTIVE | OFF_BOARDING
    OFF_BOARDING   → OFF_BOARDED
    OFF_BOARDED    → ()  -- terminal

RISK_TIERS byte-for-byte:
    LOW            -- minimal exposure
    MEDIUM         -- moderate; quarterly review
    HIGH           -- significant; monthly review
    CRITICAL       -- existential; weekly + executive oversight

Honesty rules:
    Rule 4: actor + reason mandatory on all transitions; no skip
    Rule 6: invalid type / state / risk_tier rejected (fail-closed)
    Rule 1: get_partner returns None when not found

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte
# ────────────────────────────────────────────────────────────────────

PARTNER_TYPES: Tuple[str, ...] = (
    "REFERRAL",
    "INTEGRATION",
    "DISTRIBUTION",
    "ECOSYSTEM",
    "SERVICE",
)

PARTNER_STATES: Tuple[str, ...] = (
    "PROSPECT",
    "ONBOARDING",
    "ACTIVE",
    "SUSPENDED",
    "OFF_BOARDING",
    "OFF_BOARDED",
)

ALLOWED_PARTNER_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PROSPECT":     ("ONBOARDING", "OFF_BOARDED"),
    "ONBOARDING":   ("ACTIVE", "OFF_BOARDING", "OFF_BOARDED"),
    "ACTIVE":       ("SUSPENDED", "OFF_BOARDING"),
    "SUSPENDED":    ("ACTIVE", "OFF_BOARDING"),
    "OFF_BOARDING": ("OFF_BOARDED",),
    "OFF_BOARDED":  (),  # terminal
}

RISK_TIERS: Tuple[str, ...] = (
    "LOW", "MEDIUM", "HIGH", "CRITICAL",
)


class PartnerMasterEngine:
    """Partner master data + lifecycle state machine."""

    def __init__(self, partners_path: Optional[Path] = None):
        self.partners_path = (
            partners_path
            if partners_path is not None
            else Path(__file__).parent.parent / "data" / "partners.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.partners_path,
                table="partners",
                index_cols=("partner_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.partners_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.partners_path,
                data=records,
                table="partners",
                pk_col="partner_id")
            return True
        except Exception:
            return False

    def register_partner(
        self,
        partner_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Register new partner in PROSPECT state."""
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}

        # Required fields
        for f in ("partner_id", "partner_name", "partner_type"):
            if f not in partner_data or not partner_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        if partner_data["partner_type"] not in PARTNER_TYPES:
            return {
                "registered": False,
                "error": f"invalid_partner_type:{partner_data['partner_type']}",
                "valid_types": list(PARTNER_TYPES),
            }

        risk_tier = partner_data.get("risk_tier", "MEDIUM")
        if risk_tier not in RISK_TIERS:
            return {
                "registered": False,
                "error": f"invalid_risk_tier:{risk_tier}",
                "valid_tiers": list(RISK_TIERS),
            }

        records = self._load()
        if any(r.get("partner_id") == partner_data["partner_id"] for r in records):
            return {"registered": False, "error": "duplicate_partner_id"}

        record = {
            "partner_id": partner_data["partner_id"],
            "partner_name": partner_data["partner_name"],
            "partner_type": partner_data["partner_type"],
            "state": "PROSPECT",
            "risk_tier": risk_tier,
            "primary_contact": partner_data.get("primary_contact", ""),
            "contact_email": partner_data.get("contact_email", ""),
            "contact_phone": partner_data.get("contact_phone", ""),
            "country": partner_data.get("country", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PROSPECT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
            "data_updates": [],
        }
        records.append(record)
        ok = self._save(records)
        return {
            "registered": ok,
            "partner_id": partner_data["partner_id"],
            "state": "PROSPECT",
        }

    def get_partner(self, partner_id: str) -> Optional[Dict[str, Any]]:
        for r in self._load():
            if r.get("partner_id") == partner_id:
                return r
        return None

    def list_partners(
        self,
        partner_type: Optional[str] = None,
        state: Optional[str] = "ACTIVE",
        risk_tier: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        out = []
        for r in self._load():
            if partner_type and r.get("partner_type") != partner_type:
                continue
            if state and r.get("state") != state:
                continue
            if risk_tier and r.get("risk_tier") != risk_tier:
                continue
            out.append(r)
        return out

    def transition_state(
        self,
        partner_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Transition partner state. Rule 4 no-skip enforced."""
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in PARTNER_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        records = self._load()
        for r in records:
            if r.get("partner_id") == partner_id:
                current = r.get("state", "PROSPECT")
                allowed = ALLOWED_PARTNER_TRANSITIONS.get(current, ())
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

        return {"transitioned": False, "error": "partner_not_found"}

    def update_partner_data(
        self,
        partner_id: str,
        updates: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Update partner master data (NOT state — use transition_state)."""
        if not actor or not reason:
            return {"updated": False, "error": "actor_and_reason_required"}

        # Forbidden update fields (Rule 4: state must go through transition)
        FORBIDDEN = ("partner_id", "state", "transitions", "registered_by",
                       "registered_at", "data_updates")
        bad = [k for k in updates.keys() if k in FORBIDDEN]
        if bad:
            return {
                "updated": False,
                "error": f"forbidden_update_fields:{','.join(bad)}",
            }

        # Validate risk_tier if updating
        if "risk_tier" in updates and updates["risk_tier"] not in RISK_TIERS:
            return {
                "updated": False,
                "error": f"invalid_risk_tier:{updates['risk_tier']}",
            }
        if "partner_type" in updates and updates["partner_type"] not in PARTNER_TYPES:
            return {
                "updated": False,
                "error": f"invalid_partner_type:{updates['partner_type']}",
            }

        records = self._load()
        for r in records:
            if r.get("partner_id") == partner_id:
                # Capture before/after for each field
                changes = {}
                for k, v in updates.items():
                    changes[k] = {"from": r.get(k), "to": v}
                    r[k] = v
                r.setdefault("data_updates", []).append({
                    "actor": actor, "reason": reason,
                    "at": datetime.utcnow().isoformat(),
                    "changes": changes,
                })
                ok = self._save(records)
                return {"updated": ok, "partner_id": partner_id, "changes": changes}

        return {"updated": False, "error": "partner_not_found"}

    def partner_summary(self) -> Dict[str, Any]:
        records = self._load()
        by_type = {t: 0 for t in PARTNER_TYPES}
        by_state = {s: 0 for s in PARTNER_STATES}
        by_risk = {r: 0 for r in RISK_TIERS}
        for r in records:
            t = r.get("partner_type")
            s = r.get("state")
            rt = r.get("risk_tier")
            if t in by_type:
                by_type[t] += 1
            if s in by_state:
                by_state[s] += 1
            if rt in by_risk:
                by_risk[rt] += 1
        return {
            "total": len(records),
            "by_type": by_type,
            "by_state": by_state,
            "by_risk_tier": by_risk,
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = PartnerMasterEngine(partners_path=Path(tmpdir) / "p.json")

        # Test 1: register valid partner
        r = engine.register_partner(
            {"partner_id": "P-001", "partner_name": "ACME Referrals",
             "partner_type": "REFERRAL", "risk_tier": "LOW",
             "primary_contact": "Jane Doe"},
            actor="bd_lead", reason="initial pipeline registration",
        )
        assert r["registered"], r
        assert r["state"] == "PROSPECT"

        # Test 2: duplicate rejected
        r = engine.register_partner(
            {"partner_id": "P-001", "partner_name": "Dup",
             "partner_type": "REFERRAL"},
            actor="bd_lead", reason="dup test",
        )
        assert not r["registered"]
        assert r["error"] == "duplicate_partner_id"

        # Test 3: invalid type rejected
        r = engine.register_partner(
            {"partner_id": "P-002", "partner_name": "X",
             "partner_type": "INVALID"},
            actor="bd_lead", reason="test",
        )
        assert not r["registered"]
        assert "invalid_partner_type" in r["error"]

        # Test 4: state transition PROSPECT → ONBOARDING
        t = engine.transition_state(
            "P-001", "ONBOARDING", actor="bd_lead",
            reason="contract draft initiated",
        )
        assert t["transitioned"], t

        # Test 5: skip rejected — ONBOARDING → SUSPENDED (not allowed)
        t = engine.transition_state(
            "P-001", "SUSPENDED", actor="bd_lead", reason="trying to skip",
        )
        assert not t["transitioned"]
        assert "transition_not_allowed" in t["error"]

        # Test 6: ONBOARDING → ACTIVE
        t = engine.transition_state(
            "P-001", "ACTIVE", actor="bd_lead", reason="contract signed",
        )
        assert t["transitioned"]

        # Test 7: ACTIVE → SUSPENDED → ACTIVE → OFF_BOARDING → OFF_BOARDED
        t = engine.transition_state("P-001", "SUSPENDED", "compliance",
                                       "compliance review")
        assert t["transitioned"]
        t = engine.transition_state("P-001", "ACTIVE", "compliance",
                                       "review cleared")
        assert t["transitioned"]
        t = engine.transition_state("P-001", "OFF_BOARDING", "bd_lead",
                                       "contract not renewed")
        assert t["transitioned"]
        t = engine.transition_state("P-001", "OFF_BOARDED", "bd_lead",
                                       "off-boarding complete")
        assert t["transitioned"]
        # Terminal — cannot transition out
        t = engine.transition_state("P-001", "ACTIVE", "bd_lead",
                                       "trying to reactivate")
        assert not t["transitioned"]

        # Test 8: update_partner_data
        engine.register_partner(
            {"partner_id": "P-002", "partner_name": "Beta",
             "partner_type": "DISTRIBUTION"},
            actor="bd_lead", reason="reg",
        )
        u = engine.update_partner_data(
            "P-002",
            {"primary_contact": "John Doe", "risk_tier": "HIGH"},
            actor="bd_lead", reason="contact update",
        )
        assert u["updated"]
        assert u["changes"]["risk_tier"]["to"] == "HIGH"

        # Test 9: forbidden update field rejected
        u = engine.update_partner_data(
            "P-002", {"state": "ACTIVE"}, actor="bd_lead", reason="hack",
        )
        assert not u["updated"]
        assert "forbidden_update_fields" in u["error"]

        # Test 10: invalid risk_tier rejected
        u = engine.update_partner_data(
            "P-002", {"risk_tier": "EXTREME"},
            actor="bd_lead", reason="bad",
        )
        assert not u["updated"]

        # Test 11: list filtering
        actives = engine.list_partners(state="ACTIVE")
        assert len(actives) == 0  # P-001 is OFF_BOARDED, P-002 still PROSPECT
        prospects = engine.list_partners(state="PROSPECT")
        assert len(prospects) == 1
        high_risk = engine.list_partners(state=None, risk_tier="HIGH")
        assert len(high_risk) == 1

        # Test 12: summary
        summary = engine.partner_summary()
        assert summary["total"] == 2
        assert summary["by_type"]["REFERRAL"] == 1
        assert summary["by_type"]["DISTRIBUTION"] == 1
        assert summary["by_state"]["OFF_BOARDED"] == 1

        # Test 13: get_partner unknown
        assert engine.get_partner("UNKNOWN") is None

    print("  ✅ partner_master self-test PASS")


if __name__ == "__main__":
    _self_test()
