"""
================================================================================
A2Z MIS 360 — Standard #293: Observability & Monitoring
================================================================================

Risk classification: Cat C (SLI/SLO/error budget telemetry)

Prometheus + Grafana + Loki + Jaeger stack. OpenTelemetry tracing.
SLI/SLO/error budgets. Composes v9.18 monitoring foundation.

Public API:
    register_sli(sli_data, actor, reason)
    register_slo(slo_data, actor, reason)
    record_sli_measurement(sli_id, value, period_start, period_end, actor)
    compute_error_budget(slo_id) -> Dict
    register_alert_rule(rule_data, actor, reason)
    list_violating_slos() -> List

SLI_TYPES byte-for-byte (5):
    AVAILABILITY, LATENCY, ERROR_RATE, THROUGHPUT, SATURATION

SLI_AGGREGATIONS byte-for-byte (4): AVG, P50, P95, P99

SLO_STATES byte-for-byte (4): DRAFT, ACTIVE, BREACHED, ARCHIVED

ALLOWED_SLO_TRANSITIONS (Rule 4):
    DRAFT     → ACTIVE | ARCHIVED
    ACTIVE    → BREACHED | ARCHIVED
    BREACHED  → ACTIVE | ARCHIVED
    ARCHIVED  → ()

ALERT_RULE_SEVERITIES byte-for-byte (4):
    PAGE, TICKET, EMAIL, INFO

DEFAULT_BUDGET_BURN_THRESHOLDS byte-for-byte:
    FAST_BURN_PCT_PER_HOUR=10
    SLOW_BURN_PCT_PER_DAY=10

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SLI_TYPES: Tuple[str, ...] = (
    "AVAILABILITY", "LATENCY", "ERROR_RATE", "THROUGHPUT", "SATURATION",
)

SLI_AGGREGATIONS: Tuple[str, ...] = ("AVG", "P50", "P95", "P99")

SLO_STATES: Tuple[str, ...] = ("DRAFT", "ACTIVE", "BREACHED", "ARCHIVED")

ALLOWED_SLO_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":    ("ACTIVE", "ARCHIVED"),
    "ACTIVE":   ("BREACHED", "ARCHIVED"),
    "BREACHED": ("ACTIVE", "ARCHIVED"),
    "ARCHIVED": (),
}

ALERT_RULE_SEVERITIES: Tuple[str, ...] = ("PAGE", "TICKET", "EMAIL", "INFO")

FAST_BURN_PCT_PER_HOUR = 10
SLOW_BURN_PCT_PER_DAY = 10


class ObservabilityMonitoringEngine:
    """SLI/SLO + error budget + alert rule lifecycle."""

    def __init__(
        self,
        slis_path: Optional[Path] = None,
        slos_path: Optional[Path] = None,
        measurements_path: Optional[Path] = None,
        alert_rules_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.slis_path = slis_path or base / "obs_slis.json"
        self.slos_path = slos_path or base / "obs_slos.json"
        self.measurements_path = measurements_path or base / "obs_measurements.json"
        self.alert_rules_path = alert_rules_path or base / "obs_alert_rules.json"

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

    def register_sli(
        self, sli_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("sli_id", "sli_name", "sli_type", "service_id",
                      "metric_query", "aggregation"):
            if f not in sli_data or not sli_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if sli_data["sli_type"] not in SLI_TYPES:
            return {"registered": False,
                       "error": f"invalid_sli_type:{sli_data['sli_type']}"}
        if sli_data["aggregation"] not in SLI_AGGREGATIONS:
            return {"registered": False,
                       "error": f"invalid_aggregation:{sli_data['aggregation']}"}
        records = self._load(self.slis_path, "obs_slis", ("sli_id",))
        if any(r.get("sli_id") == sli_data["sli_id"] for r in records):
            return {"registered": False, "error": "duplicate_sli_id"}
        record = {
            "sli_id": sli_data["sli_id"],
            "sli_name": sli_data["sli_name"],
            "sli_type": sli_data["sli_type"],
            "service_id": sli_data["service_id"],
            "metric_query": sli_data["metric_query"],
            "aggregation": sli_data["aggregation"],
            "unit": sli_data.get("unit", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.slis_path, records, "obs_slis", "sli_id")
        return {"registered": ok, "sli_id": sli_data["sli_id"]}

    def register_slo(
        self, slo_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("slo_id", "slo_name", "sli_id", "target_pct",
                      "window_days"):
            if f not in slo_data or slo_data[f] is None:
                return {"registered": False, "error": f"missing_field:{f}"}
        # Validate target_pct in (0, 100]
        try:
            target = Decimal(str(slo_data["target_pct"]))
        except Exception:
            return {"registered": False,
                       "error": "target_pct_not_numeric"}
        if target <= 0 or target > 100:
            return {"registered": False,
                       "error": "target_pct_out_of_range"}
        # Verify SLI exists
        slis = self._load(self.slis_path, "obs_slis", ("sli_id",))
        if not any(s.get("sli_id") == slo_data["sli_id"] for s in slis):
            return {"registered": False, "error": "sli_not_found"}
        records = self._load(self.slos_path, "obs_slos", ("slo_id",))
        if any(r.get("slo_id") == slo_data["slo_id"] for r in records):
            return {"registered": False, "error": "duplicate_slo_id"}
        record = {
            "slo_id": slo_data["slo_id"],
            "slo_name": slo_data["slo_name"],
            "sli_id": slo_data["sli_id"],
            "target_pct": str(target),
            "window_days": int(slo_data["window_days"]),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.slos_path, records, "obs_slos", "slo_id")
        return {"registered": ok, "slo_id": slo_data["slo_id"]}

    def transition_slo_state(
        self, slo_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in SLO_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.slos_path, "obs_slos", ("slo_id",))
        for r in records:
            if r.get("slo_id") == slo_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_SLO_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.slos_path, records,
                                  "obs_slos", "slo_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "slo_not_found"}

    def record_sli_measurement(
        self, sli_id: str, value: Any,
        period_start: str, period_end: str, actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if not period_start or not period_end:
            return {"recorded": False, "error": "period_required"}
        # Verify SLI exists
        slis = self._load(self.slis_path, "obs_slis", ("sli_id",))
        if not any(s.get("sli_id") == sli_id for s in slis):
            return {"recorded": False, "error": "sli_not_found"}
        try:
            value_dec = Decimal(str(value))
        except Exception:
            return {"recorded": False, "error": "value_not_numeric"}
        records = self._load(self.measurements_path,
                                "obs_measurements", ("measurement_id",))
        m_id = (f"M-{sli_id}-"
                    f"{int(datetime.utcnow().timestamp() * 1000)}")
        records.append({
            "measurement_id": m_id,
            "sli_id": sli_id,
            "value": str(value_dec),
            "period_start": period_start,
            "period_end": period_end,
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.measurements_path, records,
                          "obs_measurements", "measurement_id")
        return {"recorded": ok, "measurement_id": m_id}

    def compute_error_budget(self, slo_id: str) -> Dict[str, Any]:
        """Compute error budget remaining as pct of allowed bad-events budget."""
        slos = self._load(self.slos_path, "obs_slos", ("slo_id",))
        slo = next((s for s in slos if s.get("slo_id") == slo_id), None)
        if slo is None:
            return {"computed": False, "error": "slo_not_found"}
        # Get measurements for the SLO's SLI
        measurements = [
            m for m in self._load(self.measurements_path,
                                            "obs_measurements",
                                            ("measurement_id",))
            if m.get("sli_id") == slo["sli_id"]
        ]
        if not measurements:
            return {
                "computed": True, "slo_id": slo_id,
                "target_pct": slo["target_pct"],
                "actual_pct": None,
                "budget_remaining_pct": None,
                "measurement_count": 0,
                "fast_burn": False, "slow_burn": False,
            }
        # Average value across measurements
        total = Decimal("0")
        for m in measurements:
            total += Decimal(m["value"])
        actual_pct = total / Decimal(len(measurements))
        target_pct = Decimal(slo["target_pct"])
        # Allowed error budget: 100 - target. Consumed: max(0, target - actual).
        allowed_error = Decimal("100") - target_pct
        consumed_error = max(Decimal("0"), target_pct - actual_pct)
        if allowed_error <= 0:
            budget_remaining_pct = Decimal("100")
        else:
            budget_remaining_pct = max(
                Decimal("0"),
                Decimal("100") * (allowed_error - consumed_error) / allowed_error,
            )
        # Burn rate flags (approximations for static demo)
        burn_rate_pct = Decimal("100") - budget_remaining_pct
        fast_burn = burn_rate_pct > Decimal(FAST_BURN_PCT_PER_HOUR)
        slow_burn = burn_rate_pct > Decimal(SLOW_BURN_PCT_PER_DAY)
        return {
            "computed": True,
            "slo_id": slo_id,
            "target_pct": str(target_pct),
            "actual_pct": str(actual_pct.quantize(Decimal("0.01"))),
            "budget_remaining_pct": str(budget_remaining_pct.quantize(Decimal("0.01"))),
            "measurement_count": len(measurements),
            "fast_burn": fast_burn,
            "slow_burn": slow_burn,
        }

    def register_alert_rule(
        self, rule_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("rule_id", "rule_name", "slo_id", "severity",
                      "condition_expr"):
            if f not in rule_data or not rule_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if rule_data["severity"] not in ALERT_RULE_SEVERITIES:
            return {"registered": False,
                       "error": f"invalid_severity:{rule_data['severity']}"}
        # Verify SLO exists
        slos = self._load(self.slos_path, "obs_slos", ("slo_id",))
        if not any(s.get("slo_id") == rule_data["slo_id"] for s in slos):
            return {"registered": False, "error": "slo_not_found"}
        records = self._load(self.alert_rules_path,
                                "obs_alert_rules", ("rule_id",))
        if any(r.get("rule_id") == rule_data["rule_id"] for r in records):
            return {"registered": False, "error": "duplicate_rule_id"}
        record = {
            "rule_id": rule_data["rule_id"],
            "rule_name": rule_data["rule_name"],
            "slo_id": rule_data["slo_id"],
            "severity": rule_data["severity"],
            "condition_expr": rule_data["condition_expr"],
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.alert_rules_path, records,
                          "obs_alert_rules", "rule_id")
        return {"registered": ok, "rule_id": rule_data["rule_id"]}

    def list_violating_slos(self) -> List[Dict[str, Any]]:
        slos = self._load(self.slos_path, "obs_slos", ("slo_id",))
        violators = []
        for slo in slos:
            if slo.get("state") not in ("ACTIVE", "BREACHED"):
                continue
            budget = self.compute_error_budget(slo["slo_id"])
            if budget.get("budget_remaining_pct") is not None:
                if Decimal(budget["budget_remaining_pct"]) < Decimal("100"):
                    violators.append({
                        "slo_id": slo["slo_id"],
                        "slo_name": slo["slo_name"],
                        "target_pct": slo["target_pct"],
                        "actual_pct": budget["actual_pct"],
                        "budget_remaining_pct": budget["budget_remaining_pct"],
                        "fast_burn": budget["fast_burn"],
                        "slow_burn": budget["slow_burn"],
                    })
        # Sort by least budget remaining first
        violators.sort(
            key=lambda x: Decimal(x.get("budget_remaining_pct", "100")),
        )
        return violators


def _self_test() -> None:
    import tempfile

    assert "AVAILABILITY" in SLI_TYPES
    assert "P95" in SLI_AGGREGATIONS
    assert ALLOWED_SLO_TRANSITIONS["ARCHIVED"] == ()
    assert "PAGE" in ALERT_RULE_SEVERITIES
    assert FAST_BURN_PCT_PER_HOUR == 10
    assert SLOW_BURN_PCT_PER_DAY == 10

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ObservabilityMonitoringEngine(
            slis_path=Path(tmpdir) / "sli.json",
            slos_path=Path(tmpdir) / "slo.json",
            measurements_path=Path(tmpdir) / "m.json",
            alert_rules_path=Path(tmpdir) / "ar.json",
        )
        # Test 1: SLI register
        r = engine.register_sli(
            {"sli_id": "SLI-AUTH-AVAIL",
             "sli_name": "auth-service availability",
             "sli_type": "AVAILABILITY",
             "service_id": "SVC-AUTH",
             "metric_query": "(1 - rate(errors[5m])) * 100",
             "aggregation": "AVG",
             "unit": "pct"},
            actor="sre", reason="auth uptime tracking",
        )
        assert r["registered"]
        # Test 2: invalid SLI type
        r = engine.register_sli(
            {"sli_id": "X", "sli_name": "X", "sli_type": "INVALID",
             "service_id": "X", "metric_query": "x",
             "aggregation": "AVG"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: SLO register
        r = engine.register_slo(
            {"slo_id": "SLO-AUTH-AVAIL-99",
             "slo_name": "auth 99% availability",
             "sli_id": "SLI-AUTH-AVAIL",
             "target_pct": "99",
             "window_days": 30},
            actor="sre", reason="standard auth SLO",
        )
        assert r["registered"]
        # Test 4: invalid target_pct
        r = engine.register_slo(
            {"slo_id": "X", "slo_name": "X",
             "sli_id": "SLI-AUTH-AVAIL", "target_pct": "150",
             "window_days": 30},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 5: SLI not found
        r = engine.register_slo(
            {"slo_id": "X", "slo_name": "X",
             "sli_id": "SLI-NONE", "target_pct": "99",
             "window_days": 30},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 6: SLO state transition
        r = engine.transition_slo_state(
            "SLO-AUTH-AVAIL-99", "ACTIVE",
            actor="sre", reason="approved",
        )
        assert r["transitioned"]
        # Test 7: record measurements
        r = engine.record_sli_measurement(
            "SLI-AUTH-AVAIL", "99.5",
            "2026-05-01T00:00:00", "2026-05-01T01:00:00",
            actor="prom",
        )
        assert r["recorded"]
        engine.record_sli_measurement(
            "SLI-AUTH-AVAIL", "98.7",
            "2026-05-01T01:00:00", "2026-05-01T02:00:00",
            actor="prom",
        )
        # Test 8: error budget
        budget = engine.compute_error_budget("SLO-AUTH-AVAIL-99")
        assert budget["computed"]
        # actual=99.1 < target=99 means budget consumed but not exhausted
        # Wait — actual avg = (99.5 + 98.7)/2 = 99.1, target = 99, so actual >= target
        assert Decimal(budget["actual_pct"]) > Decimal("99")
        # Test 9: SLI not found in measurement
        r = engine.record_sli_measurement(
            "SLI-NONE", "99",
            "2026-05-01", "2026-05-02",
            actor="x",
        )
        assert not r["recorded"]
        # Test 10: alert rule
        r = engine.register_alert_rule(
            {"rule_id": "AR-AUTH-FAST-BURN",
             "rule_name": "auth fast burn",
             "slo_id": "SLO-AUTH-AVAIL-99",
             "severity": "PAGE",
             "condition_expr": "burn_rate > 14.4 for 1h"},
            actor="sre", reason="alert on fast burn",
        )
        assert r["registered"]
        # Test 11: invalid severity
        r = engine.register_alert_rule(
            {"rule_id": "X", "rule_name": "X",
             "slo_id": "SLO-AUTH-AVAIL-99",
             "severity": "URGENT", "condition_expr": "x"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 12: SLO not found in rule
        r = engine.register_alert_rule(
            {"rule_id": "X", "rule_name": "X",
             "slo_id": "SLO-NONE", "severity": "PAGE",
             "condition_expr": "x"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 13: violating SLOs
        # Force a breach by recording bad measurement
        engine.record_sli_measurement(
            "SLI-AUTH-AVAIL", "95",
            "2026-05-02", "2026-05-03",
            actor="prom",
        )
        violators = engine.list_violating_slos()
        # avg = (99.5 + 98.7 + 95) / 3 = 97.7, below target 99 — budget consumed
        assert len(violators) >= 1
        assert violators[0]["slo_id"] == "SLO-AUTH-AVAIL-99"

    print("  ✅ observability_monitoring self-test PASS")


if __name__ == "__main__":
    _self_test()
