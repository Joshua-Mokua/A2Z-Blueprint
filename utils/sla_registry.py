"""
================================================================================
A2Z MIS 360 — Standard #379: SLA Registry & Definition Engine
================================================================================

Risk classification: Cat B (deterministic SLA registry + definition validation)

Central registry for all SLA definitions across the bank:
    - register_sla(...)               -- create new SLA definition
    - get_sla(...)                    -- retrieve SLA by id
    - list_slas(...)                  -- enumerate SLAs by type/owner
    - validate_sla_definition(...)    -- structural + semantic validation
    - sla_summary()                   -- counts by type/priority/status

SLA_TYPES byte-for-byte (Continuation.docx + CBK PG/09):
    CUSTOMER     -- customer-facing service (transaction processing,
                    complaint resolution, account opening)
    INTERNAL     -- internal process SLA (interdepartmental handoffs,
                    approval cycles, credit decision turnaround)
    VENDOR       -- third-party vendor commitments (uptime, response,
                    delivery; auto-credit calculations on breach)
    REGULATORY   -- regulator-mandated SLAs (CBK 30-day complaint
                    resolution, CRB 14-day dispute resolution, FATCA
                    reporting deadlines)

SLA_PRIORITY_LEVELS byte-for-byte:
    P1_CRITICAL  -- mission-critical; near-real-time monitoring; auto-
                    escalate to executive on breach
    P2_HIGH      -- material to operations; daily monitoring;
                    escalate to manco on sustained breach
    P3_MEDIUM    -- standard operational; weekly monitoring
    P4_LOW       -- informational; monthly review

SLA_METRIC_TYPES byte-for-byte:
    RESPONSE_TIME    -- duration target (e.g. 30 days for CBK complaint)
    UPTIME           -- percentage target (e.g. 99.5% for ATM)
    THROUGHPUT       -- volume per period
    QUALITY          -- defect rate / accuracy target
    AVAILABILITY     -- service hours target

Honesty rules applied:
    Rule 1: returns None when target_value missing or zero
    Rule 6: invalid sla_type / metric_type rejected (fail closed)

================================================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Decimal precision for SLA calculations
getcontext().prec = 28

# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte from Continuation.docx Standard #379
# ────────────────────────────────────────────────────────────────────

SLA_TYPES: Tuple[str, ...] = (
    "CUSTOMER",
    "INTERNAL",
    "VENDOR",
    "REGULATORY",
)

SLA_PRIORITY_LEVELS: Tuple[str, ...] = (
    "P1_CRITICAL",
    "P2_HIGH",
    "P3_MEDIUM",
    "P4_LOW",
)

SLA_METRIC_TYPES: Tuple[str, ...] = (
    "RESPONSE_TIME",
    "UPTIME",
    "THROUGHPUT",
    "QUALITY",
    "AVAILABILITY",
)

SLA_STATUSES: Tuple[str, ...] = (
    "DRAFT",
    "ACTIVE",
    "SUSPENDED",
    "RETIRED",
)

# Default monitoring frequency by priority (per Continuation.docx)
DEFAULT_MONITORING_FREQ: Dict[str, str] = {
    "P1_CRITICAL": "REAL_TIME",
    "P2_HIGH": "DAILY",
    "P3_MEDIUM": "WEEKLY",
    "P4_LOW": "MONTHLY",
}


# ────────────────────────────────────────────────────────────────────
# Data classes
# ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SlaDefinition:
    """Frozen SLA definition record."""
    sla_id: str
    name: str
    sla_type: str           # one of SLA_TYPES
    priority: str           # one of SLA_PRIORITY_LEVELS
    metric_type: str        # one of SLA_METRIC_TYPES
    target_value: Decimal   # e.g. 30 (days), 99.5 (pct), 1000 (txns/day)
    target_unit: str        # "days", "percent", "txns/day"
    direction: str          # "min" (e.g. uptime) or "max" (e.g. response time)
    owner_department: str
    counterparty: Optional[str] = None  # for vendor/customer SLAs
    regulatory_ref: Optional[str] = None  # e.g. "CBK PG/09"
    monitoring_freq: str = "DAILY"
    status: str = "ACTIVE"
    description: str = ""
    created_at: str = ""
    last_updated: str = ""


# ────────────────────────────────────────────────────────────────────
# SlaRegistryEngine
# ────────────────────────────────────────────────────────────────────

class SlaRegistryEngine:
    """
    Central registry for SLA definitions.

    Persists to data/sla_registry.json. Atomic writes via standard
    JSON serialization.
    """

    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = (
            registry_path
            if registry_path is not None
            else Path(__file__).parent.parent / "data" / "sla_registry.json"
        )

    def _load_registry(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db   # singleton Database instance
            data = _db.dual_load(
                self.registry_path,
                table="sla_registry",
                index_cols=("sla_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_registry(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.registry_path,
                data=records,
                table="sla_registry",
                pk_col="sla_id")
            return True
        except Exception:
            return False

    def validate_sla_definition(
        self, sla: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate SLA definition structurally + semantically.

        Returns: {valid: bool, errors: [str]}
        """
        errors: List[str] = []

        # Required fields
        for required in ("sla_id", "name", "sla_type", "priority",
                          "metric_type", "target_value", "target_unit",
                          "direction", "owner_department"):
            if required not in sla or sla[required] in (None, ""):
                errors.append(f"missing_required_field:{required}")

        # Catalog validation
        if sla.get("sla_type") not in SLA_TYPES:
            errors.append(f"invalid_sla_type:{sla.get('sla_type')}")
        if sla.get("priority") not in SLA_PRIORITY_LEVELS:
            errors.append(f"invalid_priority:{sla.get('priority')}")
        if sla.get("metric_type") not in SLA_METRIC_TYPES:
            errors.append(f"invalid_metric_type:{sla.get('metric_type')}")
        if sla.get("status") and sla["status"] not in SLA_STATUSES:
            errors.append(f"invalid_status:{sla.get('status')}")
        if sla.get("direction") not in ("min", "max"):
            errors.append(f"invalid_direction:{sla.get('direction')}")

        # Target value must be positive (Rule 1: zero/negative reject)
        try:
            tv = Decimal(str(sla.get("target_value", 0)))
            if tv <= 0:
                errors.append(f"target_value_not_positive:{tv}")
        except (ValueError, TypeError):
            errors.append("target_value_not_decimal")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def register_sla(self, sla: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register new SLA definition. Returns {registered, sla_id, errors}.

        Rule 6: invalid definitions rejected (fail closed).
        """
        validation = self.validate_sla_definition(sla)
        if not validation["valid"]:
            return {
                "registered": False,
                "sla_id": sla.get("sla_id"),
                "errors": validation["errors"],
            }

        # Check duplicate
        records = self._load_registry()
        existing_ids = {r.get("sla_id") for r in records}
        if sla["sla_id"] in existing_ids:
            return {
                "registered": False,
                "sla_id": sla["sla_id"],
                "errors": ["duplicate_sla_id"],
            }

        # Normalize: stringify Decimal for JSON, set defaults
        normalized = dict(sla)
        normalized["target_value"] = str(normalized["target_value"])
        normalized.setdefault("monitoring_freq",
                                DEFAULT_MONITORING_FREQ.get(sla["priority"], "DAILY"))
        normalized.setdefault("status", "ACTIVE")
        normalized.setdefault("description", "")

        records.append(normalized)
        ok = self._save_registry(records)
        return {
            "registered": ok,
            "sla_id": sla["sla_id"],
            "errors": [] if ok else ["save_failed"],
        }

    def get_sla(self, sla_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve SLA by id. Returns None if not found."""
        records = self._load_registry()
        for r in records:
            if r.get("sla_id") == sla_id:
                return r
        return None

    def list_slas(
        self,
        sla_type: Optional[str] = None,
        priority: Optional[str] = None,
        owner_department: Optional[str] = None,
        status: Optional[str] = "ACTIVE",
    ) -> List[Dict[str, Any]]:
        """Enumerate SLAs by filter."""
        records = self._load_registry()
        out = []
        for r in records:
            if sla_type and r.get("sla_type") != sla_type:
                continue
            if priority and r.get("priority") != priority:
                continue
            if owner_department and r.get("owner_department") != owner_department:
                continue
            if status and r.get("status") != status:
                continue
            out.append(r)
        return out

    def sla_summary(self) -> Dict[str, Any]:
        """Aggregated counts by type / priority / status."""
        records = self._load_registry()

        by_type: Dict[str, int] = {t: 0 for t in SLA_TYPES}
        by_priority: Dict[str, int] = {p: 0 for p in SLA_PRIORITY_LEVELS}
        by_status: Dict[str, int] = {s: 0 for s in SLA_STATUSES}

        for r in records:
            t = r.get("sla_type")
            p = r.get("priority")
            s = r.get("status", "ACTIVE")
            if t in by_type:
                by_type[t] += 1
            if p in by_priority:
                by_priority[p] += 1
            if s in by_status:
                by_status[s] += 1

        return {
            "total": len(records),
            "by_type": by_type,
            "by_priority": by_priority,
            "by_status": by_status,
        }


# ────────────────────────────────────────────────────────────────────
# Self-test
# ────────────────────────────────────────────────────────────────────

def _self_test() -> None:
    """Smoke test for v10.271 SLA Registry."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "sla_registry.json"
        engine = SlaRegistryEngine(registry_path=registry_path)

        # Test 1: validate good definition
        good_sla = {
            "sla_id": "SLA-CUST-001",
            "name": "CBK Complaint Resolution",
            "sla_type": "REGULATORY",
            "priority": "P1_CRITICAL",
            "metric_type": "RESPONSE_TIME",
            "target_value": Decimal("30"),
            "target_unit": "days",
            "direction": "max",
            "owner_department": "Compliance",
            "regulatory_ref": "CBK PG/09",
        }
        v = engine.validate_sla_definition(good_sla)
        assert v["valid"], f"Good SLA failed validation: {v['errors']}"

        # Test 2: register valid SLA
        result = engine.register_sla(good_sla)
        assert result["registered"], f"Register failed: {result['errors']}"

        # Test 3: duplicate detection
        result2 = engine.register_sla(good_sla)
        assert not result2["registered"]
        assert "duplicate_sla_id" in result2["errors"]

        # Test 4: invalid sla_type rejected
        bad = dict(good_sla)
        bad["sla_id"] = "SLA-BAD-001"
        bad["sla_type"] = "INVALID_TYPE"
        v = engine.validate_sla_definition(bad)
        assert not v["valid"]
        assert any("invalid_sla_type" in e for e in v["errors"])

        # Test 5: zero target_value rejected
        bad2 = dict(good_sla)
        bad2["sla_id"] = "SLA-BAD-002"
        bad2["target_value"] = Decimal("0")
        v = engine.validate_sla_definition(bad2)
        assert not v["valid"]
        assert any("target_value_not_positive" in e for e in v["errors"])

        # Test 6: list and summary
        listed = engine.list_slas(sla_type="REGULATORY")
        assert len(listed) == 1
        summary = engine.sla_summary()
        assert summary["total"] == 1
        assert summary["by_type"]["REGULATORY"] == 1
        assert summary["by_priority"]["P1_CRITICAL"] == 1

    print("  ✅ sla_registry self-test PASS")


if __name__ == "__main__":
    _self_test()
