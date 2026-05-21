"""
================================================================================
A2Z MIS 360 — Standard #303: Insurance Partner Integration Hub
================================================================================

Risk classification: Cat C (third-party integration; standard data schema)

Multi-insurer API integration hub. Standard data schema for quotes,
applications, claims across insurers. Real-time quote engine that
aggregates from registered insurers via their adapter interfaces.

This module is the integration CONTRACT — actual HTTP calls to
insurer APIs are downstream adapter concerns. The hub defines the
unified schema and orchestrates fan-out.

Public API:
    register_insurer(insurer_data, actor, reason)
    update_insurer_status(insurer_id, new_status, actor, reason)
    get_quotes(product_type, customer_attrs) -> aggregated quotes
    submit_application(quote_id, application_data, actor)
    list_active_insurers() -> [insurers with INTEGRATED status]

INSURER_STATES byte-for-byte:
    DISCOVERY        -- evaluation phase
    NEGOTIATING      -- terms negotiation
    INTEGRATING      -- API integration in progress
    INTEGRATED       -- live; can quote/issue
    SUSPENDED        -- temporary suspension
    OFF_BOARDING     -- being phased out
    OFF_BOARDED      -- terminal

ALLOWED_INSURER_TRANSITIONS (Rule 4):
    DISCOVERY     → NEGOTIATING | OFF_BOARDED
    NEGOTIATING   → INTEGRATING | DISCOVERY | OFF_BOARDED
    INTEGRATING   → INTEGRATED | NEGOTIATING | OFF_BOARDED
    INTEGRATED    → SUSPENDED | OFF_BOARDING
    SUSPENDED     → INTEGRATED | OFF_BOARDING
    OFF_BOARDING  → OFF_BOARDED
    OFF_BOARDED   → ()  -- terminal

QUOTE_STATES byte-for-byte:
    REQUESTED        -- quote requested; awaiting insurer response
    QUOTED           -- quote received from insurer
    EXPIRED          -- past quote validity window (terminal)
    CONVERTED        -- quote converted to application (terminal)
    CANCELLED        -- customer cancelled (terminal)

DEFAULT_QUOTE_VALIDITY_DAYS = 30

Honesty rules:
    Rule 4: actor + reason mandatory; no skip transitions
    Rule 6: invalid product_type / state rejected
    Rule 1: get_quotes returns empty list with reason when no insurers
            offer that product type

================================================================================
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.insurance_catalog import INSURANCE_PRODUCT_TYPES

getcontext().prec = 28


INSURER_STATES: Tuple[str, ...] = (
    "DISCOVERY", "NEGOTIATING", "INTEGRATING", "INTEGRATED",
    "SUSPENDED", "OFF_BOARDING", "OFF_BOARDED",
)

ALLOWED_INSURER_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DISCOVERY":    ("NEGOTIATING", "OFF_BOARDED"),
    "NEGOTIATING":  ("INTEGRATING", "DISCOVERY", "OFF_BOARDED"),
    "INTEGRATING":  ("INTEGRATED", "NEGOTIATING", "OFF_BOARDED"),
    "INTEGRATED":   ("SUSPENDED", "OFF_BOARDING"),
    "SUSPENDED":    ("INTEGRATED", "OFF_BOARDING"),
    "OFF_BOARDING": ("OFF_BOARDED",),
    "OFF_BOARDED":  (),
}

QUOTE_STATES: Tuple[str, ...] = (
    "REQUESTED", "QUOTED", "EXPIRED", "CONVERTED", "CANCELLED",
)

DEFAULT_QUOTE_VALIDITY_DAYS: int = 30


class InsurancePartnerHub:
    """Multi-insurer integration hub + standard quote schema."""

    def __init__(
        self,
        insurers_path: Optional[Path] = None,
        quotes_path: Optional[Path] = None,
        adapter_registry: Optional[Dict[str, Callable[..., Dict[str, Any]]]] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.insurers_path = insurers_path or base / "insurance_insurers.json"
        self.quotes_path = quotes_path or base / "insurance_quotes.json"
        # adapter_registry maps insurer_id → callable for live quotes
        # When None or empty, get_quotes returns no_adapter_registered reason
        self.adapter_registry = adapter_registry or {}

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

    def register_insurer(
        self,
        insurer_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Register insurer in DISCOVERY state."""
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}

        for f in ("insurer_id", "insurer_name", "supported_product_types"):
            if f not in insurer_data or not insurer_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        # Validate supported_product_types
        supported = insurer_data["supported_product_types"]
        if not isinstance(supported, (list, tuple)):
            return {"registered": False, "error": "supported_product_types_not_list"}
        invalid = [t for t in supported if t not in INSURANCE_PRODUCT_TYPES]
        if invalid:
            return {
                "registered": False,
                "error": f"invalid_product_types:{invalid}",
            }

        records = self._load(self.insurers_path, "insurance_insurers",
                                ("insurer_id",))
        if any(r.get("insurer_id") == insurer_data["insurer_id"] for r in records):
            return {"registered": False, "error": "duplicate_insurer_id"}

        record = {
            "insurer_id": insurer_data["insurer_id"],
            "insurer_name": insurer_data["insurer_name"],
            "supported_product_types": list(supported),
            "state": "DISCOVERY",
            "api_endpoint": insurer_data.get("api_endpoint", ""),
            "schema_version": insurer_data.get("schema_version", "v1"),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "DISCOVERY", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(self.insurers_path, records,
                          "insurance_insurers", "insurer_id")
        return {"registered": ok, "insurer_id": insurer_data["insurer_id"]}

    def update_insurer_status(
        self,
        insurer_id: str,
        new_status: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Transition insurer state (Rule 4 no-skip)."""
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_status not in INSURER_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_status}"}

        records = self._load(self.insurers_path, "insurance_insurers",
                                ("insurer_id",))
        for r in records:
            if r.get("insurer_id") == insurer_id:
                current = r.get("state", "DISCOVERY")
                allowed = ALLOWED_INSURER_TRANSITIONS.get(current, ())
                if new_status not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_status}",
                        "current_state": current,
                        "allowed": list(allowed),
                    }
                r["state"] = new_status
                r.setdefault("transitions", []).append({
                    "to": new_status, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.insurers_path, records,
                                  "insurance_insurers", "insurer_id")
                return {"transitioned": ok, "from": current, "to": new_status}

        return {"transitioned": False, "error": "insurer_not_found"}

    def list_active_insurers(
        self,
        product_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List INTEGRATED insurers, optionally filtered by product type."""
        records = self._load(self.insurers_path, "insurance_insurers",
                                ("insurer_id",))
        out = []
        for r in records:
            if r.get("state") != "INTEGRATED":
                continue
            if product_type:
                supported = r.get("supported_product_types", [])
                if product_type not in supported:
                    continue
            out.append(r)
        return out

    def get_quotes(
        self,
        product_type: str,
        customer_attrs: Dict[str, Any],
        actor: str = "system",
    ) -> Dict[str, Any]:
        """Aggregate quotes from active insurers supporting product_type."""
        if product_type not in INSURANCE_PRODUCT_TYPES:
            return {
                "quotes": [],
                "reason": f"invalid_product_type:{product_type}",
            }

        active = self.list_active_insurers(product_type=product_type)
        if not active:
            return {
                "quotes": [],
                "product_type": product_type,
                "reason": "no_active_insurers_for_product_type",
            }

        quote_id_base = f"Q-{product_type}-{int(datetime.utcnow().timestamp())}"
        records = self._load(self.quotes_path, "insurance_quotes",
                                ("quote_id",))
        quotes = []

        for ins in active:
            ins_id = ins["insurer_id"]
            quote_id = f"{quote_id_base}-{ins_id}"
            adapter = self.adapter_registry.get(ins_id)

            if adapter is None:
                quote_record = {
                    "quote_id": quote_id,
                    "insurer_id": ins_id,
                    "product_type": product_type,
                    "state": "REQUESTED",
                    "premium_kes": None,
                    "sum_assured_kes": None,
                    "validity_days": DEFAULT_QUOTE_VALIDITY_DAYS,
                    "reason": "no_adapter_registered",
                    "requested_at": datetime.utcnow().isoformat(),
                    "requested_by": actor,
                }
            else:
                try:
                    adapter_response = adapter(product_type, customer_attrs)
                    quote_record = {
                        "quote_id": quote_id,
                        "insurer_id": ins_id,
                        "product_type": product_type,
                        "state": "QUOTED",
                        "premium_kes": str(adapter_response.get("premium_kes")),
                        "sum_assured_kes": str(adapter_response.get("sum_assured_kes")),
                        "validity_days": int(adapter_response.get(
                            "validity_days", DEFAULT_QUOTE_VALIDITY_DAYS)),
                        "expires_on": (date.today() + timedelta(
                            days=int(adapter_response.get(
                                "validity_days", DEFAULT_QUOTE_VALIDITY_DAYS))
                        )).isoformat(),
                        "raw_response": adapter_response,
                        "requested_at": datetime.utcnow().isoformat(),
                        "requested_by": actor,
                    }
                except Exception as e:
                    quote_record = {
                        "quote_id": quote_id,
                        "insurer_id": ins_id,
                        "product_type": product_type,
                        "state": "REQUESTED",
                        "premium_kes": None,
                        "sum_assured_kes": None,
                        "validity_days": DEFAULT_QUOTE_VALIDITY_DAYS,
                        "reason": f"adapter_error:{type(e).__name__}",
                        "requested_at": datetime.utcnow().isoformat(),
                        "requested_by": actor,
                    }

            records.append(quote_record)
            quotes.append(quote_record)

        self._save(self.quotes_path, records,
                     "insurance_quotes", "quote_id")
        return {
            "product_type": product_type,
            "quote_count": len(quotes),
            "quotes": quotes,
            "active_insurers": len(active),
        }

    def submit_application(
        self,
        quote_id: str,
        application_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Convert quote to application (CONVERTED state)."""
        if not actor:
            return {"submitted": False, "error": "actor_required"}

        records = self._load(self.quotes_path, "insurance_quotes",
                                ("quote_id",))
        for r in records:
            if r.get("quote_id") == quote_id:
                if r.get("state") != "QUOTED":
                    return {
                        "submitted": False,
                        "error": f"quote_not_in_QUOTED_state:{r['state']}",
                    }
                r["state"] = "CONVERTED"
                r["application_data"] = application_data
                r["converted_by"] = actor
                r["converted_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.quotes_path, records,
                                  "insurance_quotes", "quote_id")
                return {"submitted": ok, "quote_id": quote_id}

        return {"submitted": False, "error": "quote_not_found"}


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        hub = InsurancePartnerHub(
            insurers_path=Path(tmpdir) / "ins.json",
            quotes_path=Path(tmpdir) / "q.json",
        )

        # Test 1: register insurer
        r = hub.register_insurer(
            {"insurer_id": "INS-A",
             "insurer_name": "Insurer A",
             "supported_product_types": ["LIFE", "HEALTH"]},
            actor="bd", reason="initial reg",
        )
        assert r["registered"], r

        # Test 2: invalid product type rejected
        r = hub.register_insurer(
            {"insurer_id": "INS-B", "insurer_name": "Insurer B",
             "supported_product_types": ["LIFE", "INVALID"]},
            actor="bd", reason="bad",
        )
        assert not r["registered"]
        assert "invalid_product_types" in r["error"]

        # Test 3: state lifecycle
        for new_state, reason in [
            ("NEGOTIATING", "terms agreed"),
            ("INTEGRATING", "API work in progress"),
            ("INTEGRATED", "live"),
        ]:
            t = hub.update_insurer_status(
                "INS-A", new_state, actor="bd", reason=reason
            )
            assert t["transitioned"]

        # Test 4: skip rejected
        hub.register_insurer(
            {"insurer_id": "INS-B", "insurer_name": "B",
             "supported_product_types": ["LIFE"]},
            actor="bd", reason="reg",
        )
        t = hub.update_insurer_status(
            "INS-B", "INTEGRATED", actor="bd", reason="skip"
        )
        assert not t["transitioned"]
        assert "transition_not_allowed" in t["error"]

        # Test 5: list_active_insurers
        active = hub.list_active_insurers()
        assert len(active) == 1
        assert active[0]["insurer_id"] == "INS-A"

        # Test 6: list_active_insurers filtered by product type
        active_life = hub.list_active_insurers(product_type="LIFE")
        assert len(active_life) == 1
        active_motor = hub.list_active_insurers(product_type="MOTOR")
        assert len(active_motor) == 0

        # Test 7: get_quotes — no adapters → REQUESTED with reason
        quotes = hub.get_quotes("LIFE", {"age": 35, "sum_assured_kes": "1000000"})
        assert quotes["quote_count"] == 1
        assert quotes["quotes"][0]["state"] == "REQUESTED"
        assert quotes["quotes"][0]["reason"] == "no_adapter_registered"

        # Test 8: get_quotes with adapter
        def fake_adapter(product_type, attrs):
            return {
                "premium_kes": "12000",
                "sum_assured_kes": attrs.get("sum_assured_kes"),
                "validity_days": 30,
            }
        hub_with_adapter = InsurancePartnerHub(
            insurers_path=Path(tmpdir) / "ins.json",
            quotes_path=Path(tmpdir) / "q2.json",
            adapter_registry={"INS-A": fake_adapter},
        )
        quotes = hub_with_adapter.get_quotes(
            "LIFE", {"age": 35, "sum_assured_kes": "1000000"}
        )
        assert quotes["quotes"][0]["state"] == "QUOTED"
        assert quotes["quotes"][0]["premium_kes"] == "12000"

        # Test 9: adapter error gracefully captured
        def broken_adapter(pt, attrs):
            raise RuntimeError("API down")
        hub_broken = InsurancePartnerHub(
            insurers_path=Path(tmpdir) / "ins.json",
            quotes_path=Path(tmpdir) / "q3.json",
            adapter_registry={"INS-A": broken_adapter},
        )
        quotes = hub_broken.get_quotes("LIFE", {})
        assert quotes["quotes"][0]["state"] == "REQUESTED"
        assert "adapter_error" in quotes["quotes"][0]["reason"]

        # Test 10: get_quotes with no active insurers for product type
        quotes = hub.get_quotes("MARINE", {})
        assert quotes["quotes"] == []
        assert quotes["reason"] == "no_active_insurers_for_product_type"

        # Test 11: submit_application
        quote_id = hub_with_adapter.get_quotes(
            "LIFE", {"age": 35}
        )["quotes"][0]["quote_id"]
        r = hub_with_adapter.submit_application(
            quote_id,
            {"customer_id": "CUST-001", "applicant_name": "John Doe"},
            actor="rm",
        )
        assert r["submitted"]

        # Test 12: cannot resubmit
        r = hub_with_adapter.submit_application(
            quote_id, {}, actor="rm",
        )
        assert not r["submitted"]
        assert "quote_not_in_QUOTED_state" in r["error"]

    print("  ✅ insurance_partner_hub self-test PASS")


if __name__ == "__main__":
    _self_test()
