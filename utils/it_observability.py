"""
================================================================================
A2Z MIS 360 — Standard #293: Observability & Monitoring
================================================================================

Risk classification: Cat C (SLI/SLO tracking + error budget)

Prometheus + Grafana + Loki + Jaeger stack. OpenTelemetry tracing.
SLI/SLO/error budgets. Composes v9.18 monitoring foundation.

Public API:
    register_sli(sli_data, actor, reason)
    register_slo(slo_data, actor, reason)
    record_sli_measurement(sli_id, value, timestamp, actor)
    error_budget_status(slo_id) -> Dict
    breach_summary(svc_id) -> Dict

SLI_TYPES byte-for-byte (5):
    LATENCY, AVAILABILITY, ERROR_RATE, THROUGHPUT, SATURATION

SLO_TIME_WINDOWS byte-for-byte (3): ROLLING_28_DAYS, CALENDAR_MONTH, QUARTER

SLO_STATES byte-for-byte (4): ACTIVE, PAUSED, MET, BREACHED

ALLOWED_SLO_TRANSITIONS (Rule 4):
    ACTIVE   → PAUSED | MET | BREACHED
    PAUSED   → ACTIVE
    MET      → ACTIVE  (next period)
    BREACHED → ACTIVE  (next period after RCA)

ERROR_BUDGET_POLICIES byte-for-byte (3):
    HALT_RELEASES, INCREASED_OVERSIGHT, ESCALATE_TO_LEADERSHIP

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SLI_TYPES: Tuple[str, ...] = (
    "LATENCY", "AVAILABILITY", "ERROR_RATE", "THROUGHPUT", "SATURATION",
)

SLO_TIME_WINDOWS: Tuple[str, ...] = (
    "ROLLING_28_DAYS", "CALENDAR_MONTH", "QUARTER",
)

SLO_STATES: Tuple[str, ...] = ("ACTIVE", "PAUSED", "MET", "BREACHED")

ALLOWED_SLO_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":   ("PAUSED", "MET", "BREACHED"),
    "PAUSED":   ("ACTIVE",),
    "MET":      ("ACTIVE",),
    "BREACHED": ("ACTIVE",),
}

ERROR_BUDGET_POLICIES: Tuple[str, ...] = (
    "HALT_RELEASES", "INCREASED_OVERSIGHT", "ESCALATE_TO_LEADERSHIP",
)

DEFAULT_BUDGET_BURN_THRESHOLD_PCT = 50  # alert when 50%+ of budget consumed


class ObservabilityEngine:
    """SLI/SLO/error budget tracking — Prometheus/Grafana foundation."""

    def __init__(
        self,
        slis_path: Optional[Path] = None,
        slos_path: Optional[Path] = None,
        measurements_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.slis_path = slis_path or base / "obs_slis.json"
        self.slos_path = slos_path or base / "obs_slos.json"
        self.measurements_path = measurements_path or base / "obs_measurements.json"

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
        for f in ("sli_id", "sli_name", "sli_type", "service_id", "unit"):
            if f not in sli_data or not sli_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if sli_data["sli_type"] not in SLI_TYPES:
            return {"registered": False,
                       "error": f"invalid_sli_type:{sli_data['sli_type']}"}
        records = self._load(self.slis_path, "obs_slis", ("sli_id",))
        if any(r.get("sli_id") == sli_data["sli_id"] for r in records):
            return {"registered": False, "error": "duplicate_sli_id"}
        record = {
            "sli_id": sli_data["sli_id"],
            "sli_name": sli_data["sli_name"],
            "sli_type": sli_data["sli_type"],
            "service_id": sli_data["service_id"],
            "unit": sli_data["unit"],
            "query_template": sli_data.get("query_template", ""),
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
        for f in ("slo_id", "slo_name", "sli_id", "target_pct", "time_window"):
            if f not in slo_data or slo_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if slo_data["time_window"] not in SLO_TIME_WINDOWS:
            return {"registered": False,
                       "error": f"invalid_window:{slo_data['time_window']}"}
        try:
            target = Decimal(str(slo_data["target_pct"]))
        except Exception:
            return {"registered": False, "error": "invalid_target_pct"}
        if target <= Decimal("0") or target > Decimal("100"):
            return {"registered": False, "error": "target_pct_out_of_range"}
        # Verify SLI exists
        slis = self._load(self.slis_path, "obs_slis", ("sli_id",))
        if not any(s.get("sli_id") == slo_data["sli_id"] for s in slis):
            return {"registered": False, "error": "sli_not_found"}
        records = self._load(self.slos_path, "obs_slos", ("slo_id",))
        if any(r.get("slo_id") == slo_data["slo_id"] for r in records):
            return {"registered": False, "error": "duplicate_slo_id"}
        budget_policy = slo_data.get("budget_policy", "INCREASED_OVERSIGHT")
        if budget_policy not in ERROR_BUDGET_POLICIES:
            return {"registered": False,
                       "error": f"invalid_budget_policy:{budget_policy}"}
        record = {
            "slo_id": slo_data["slo_id"],
            "slo_name": slo_data["slo_name"],
            "sli_id": slo_data["sli_id"],
            "target_pct": str(target),
            "time_window": slo_data["time_window"],
            "budget_policy": budget_policy,
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "ACTIVE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.slos_path, records, "obs_slos", "slo_id")
        return {"registered": ok, "slo_id": slo_data["slo_id"]}

    def record_sli_measurement(
        self, sli_id: str, value: Any, timestamp: str, actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if not timestamp:
            return {"recorded": False, "error": "timestamp_required"}
        try:
            v = Decimal(str(value))
        except Exception:
            return {"recorded": False, "error": "invalid_value"}
        # Verify SLI exists
        slis = self._load(self.slis_path, "obs_slis", ("sli_id",))
        if not any(s.get("sli_id") == sli_id for s in slis):
            return {"recorded": False, "error": "sli_not_found"}
        measurements = self._load(self.measurements_path,
                                          "obs_measurements",
                                          ("measurement_id",))
        mid = (f"M-{sli_id}-"
                  f"{int(datetime.utcnow().timestamp() * 1000)}")
        measurements.append({
            "measurement_id": mid,
            "sli_id": sli_id,
            "value": str(v),
            "timestamp": timestamp,
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.measurements_path, measurements,
                          "obs_measurements", "measurement_id")
        return {"recorded": ok, "measurement_id": mid}

    def error_budget_status(self, slo_id: str) -> Dict[str, Any]:
        slos = self._load(self.slos_path, "obs_slos", ("slo_id",))
        slo = next((s for s in slos if s.get("slo_id") == slo_id), None)
        if slo is None:
            return {"found": False, "error": "slo_not_found"}
        target = Decimal(slo["target_pct"])
        # Get measurements for the SLI in the time window
        # Window: 28 days for ROLLING_28_DAYS, etc.
        measurements = self._load(self.measurements_path,
                                          "obs_measurements",
                                          ("measurement_id",))
        sli_meas = [m for m in measurements
                          if m.get("sli_id") == slo["sli_id"]]
        if not sli_meas:
            return {
                "found": True, "slo_id": slo_id,
                "no_data": True, "state": slo["state"],
            }
        values = [Decimal(m["value"]) for m in sli_meas]
        avg = sum(values) / Decimal(len(values))
        # Error budget: 100 - target = max allowed bad %
        # Actual bad % = 100 - avg (assuming SLI is success rate %)
        max_bad_pct = Decimal("100") - target
        actual_bad_pct = max(Decimal("0"), Decimal("100") - avg)
        if max_bad_pct == 0:
            budget_consumed_pct = Decimal("100") if actual_bad_pct > 0 else Decimal("0")
        else:
            budget_consumed_pct = (actual_bad_pct / max_bad_pct) * Decimal("100")
            budget_consumed_pct = min(Decimal("100"), budget_consumed_pct)
        burn_alert = budget_consumed_pct >= Decimal(
            str(DEFAULT_BUDGET_BURN_THRESHOLD_PCT),
        )
        breached = budget_consumed_pct >= Decimal("100")
        return {
            "found": True,
            "slo_id": slo_id,
            "sli_id": slo["sli_id"],
            "target_pct": str(target),
            "average_sli": str(round(avg, 4)),
            "budget_consumed_pct": str(round(budget_consumed_pct, 2)),
            "max_bad_pct": str(max_bad_pct),
            "burn_alert": bool(burn_alert),
            "breached": bool(breached),
            "policy_on_breach": slo["budget_policy"],
            "state": slo["state"],
            "measurement_count": len(sli_meas),
        }

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
                current = r.get("state", "ACTIVE")
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

    def breach_summary(self, service_id: str) -> Dict[str, Any]:
        slis = self._load(self.slis_path, "obs_slis", ("sli_id",))
        svc_slis = [s["sli_id"] for s in slis
                          if s.get("service_id") == service_id]
        slos = self._load(self.slos_path, "obs_slos", ("slo_id",))
        svc_slos = [s for s in slos if s.get("sli_id") in svc_slis]
        breach_count = sum(1 for s in svc_slos if s.get("state") == "BREACHED")
        return {
            "service_id": service_id,
            "sli_count": len(svc_slis),
            "slo_count": len(svc_slos),
            "breach_count": breach_count,
            "breached_slo_ids": [s["slo_id"] for s in svc_slos
                                       if s.get("state") == "BREACHED"],
        }


def _self_test() -> None:
    import tempfile

    assert "LATENCY" in SLI_TYPES
    assert "ROLLING_28_DAYS" in SLO_TIME_WINDOWS
    assert ALLOWED_SLO_TRANSITIONS["BREACHED"] == ("ACTIVE",)
    assert "HALT_RELEASES" in ERROR_BUDGET_POLICIES
    assert DEFAULT_BUDGET_BURN_THRESHOLD_PCT == 50

    with tempfile.TemporaryDirectory() as tmpdir:
        e = ObservabilityEngine(
            slis_path=Path(tmpdir) / "i.json",
            slos_path=Path(tmpdir) / "o.json",
            measurements_path=Path(tmpdir) / "m.json",
        )
        # SLI
        r = e.register_sli(
            {"sli_id": "SLI-AUTH-AVAIL",
             "sli_name": "Auth availability",
             "sli_type": "AVAILABILITY",
             "service_id": "SVC-AUTH",
             "unit": "%"},
            actor="sre", reason="initial",
        )
        assert r["registered"]
        # Invalid type
        r = e.register_sli(
            {"sli_id": "X", "sli_name": "Y", "sli_type": "WHATEVER",
             "service_id": "Z", "unit": "%"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # SLO
        r = e.register_slo(
            {"slo_id": "SLO-AUTH-99-9",
             "slo_name": "Auth 99.9%",
             "sli_id": "SLI-AUTH-AVAIL",
             "target_pct": "99.9",
             "time_window": "ROLLING_28_DAYS",
             "budget_policy": "HALT_RELEASES"},
            actor="sre", reason="critical service",
        )
        assert r["registered"]
        # Invalid target
        r = e.register_slo(
            {"slo_id": "X", "slo_name": "Y",
             "sli_id": "SLI-AUTH-AVAIL", "target_pct": "150",
             "time_window": "ROLLING_28_DAYS"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # SLI not found
        r = e.register_slo(
            {"slo_id": "Y", "slo_name": "Z", "sli_id": "NOPE",
             "target_pct": "99", "time_window": "ROLLING_28_DAYS"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid policy
        r = e.register_slo(
            {"slo_id": "Z", "slo_name": "T",
             "sli_id": "SLI-AUTH-AVAIL", "target_pct": "99",
             "time_window": "ROLLING_28_DAYS",
             "budget_policy": "RANDOM"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Measurements (good — 99.95%)
        for _ in range(10):
            r = e.record_sli_measurement(
                "SLI-AUTH-AVAIL", "99.95",
                datetime.utcnow().isoformat(), actor="prom",
            )
            assert r["recorded"]
        s = e.error_budget_status("SLO-AUTH-99-9")
        assert s["found"]
        assert s["measurement_count"] == 10
        # avg = 99.95, target = 99.9
        # max_bad = 0.1, actual_bad = 0.05, consumed = 50%
        assert "50" in s["budget_consumed_pct"] or s["burn_alert"]
        # Breach test - new SLO with strict target
        e.register_slo(
            {"slo_id": "SLO-STRICT", "slo_name": "Strict 99.99",
             "sli_id": "SLI-AUTH-AVAIL", "target_pct": "99.99",
             "time_window": "ROLLING_28_DAYS"},
            actor="sre", reason="strict",
        )
        s = e.error_budget_status("SLO-STRICT")
        # avg=99.95, target=99.99 → max_bad=0.01, actual_bad=0.05 → consumed=500% (capped 100)
        assert s["breached"]
        # No data SLO
        e.register_sli(
            {"sli_id": "SLI-NODATA", "sli_name": "X",
             "sli_type": "LATENCY", "service_id": "SVC-AUTH",
             "unit": "ms"},
            actor="x", reason="x",
        )
        e.register_slo(
            {"slo_id": "SLO-NODATA", "slo_name": "Y",
             "sli_id": "SLI-NODATA", "target_pct": "95",
             "time_window": "ROLLING_28_DAYS"},
            actor="x", reason="x",
        )
        s = e.error_budget_status("SLO-NODATA")
        assert s.get("no_data")

        # Invalid value
        r = e.record_sli_measurement(
            "SLI-AUTH-AVAIL", "not_a_number",
            datetime.utcnow().isoformat(), actor="prom",
        )
        assert not r["recorded"]

        # SLO state transitions
        r = e.transition_slo_state("SLO-AUTH-99-9", "BREACHED",
                                          actor="sre", reason="incident")
        assert r["transitioned"]
        r = e.transition_slo_state("SLO-AUTH-99-9", "ACTIVE",
                                          actor="sre", reason="next period")
        assert r["transitioned"]
        # Invalid state
        r = e.transition_slo_state("SLO-AUTH-99-9", "WHATEVER",
                                          actor="x", reason="x")
        assert not r["transitioned"]

        # Breach summary
        b = e.breach_summary("SVC-AUTH")
        assert b["sli_count"] == 2
        assert b["slo_count"] == 3

    print("  ✅ it_observability self-test PASS")


if __name__ == "__main__":
    _self_test()
