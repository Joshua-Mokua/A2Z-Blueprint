"""
================================================================================
A2Z MIS 360 — Standard #289: Anomaly Detection & Alerting
================================================================================

Risk classification: Cat C (read-side detection; never auto-acts on signal —
emits alerts that route through #287 ScheduledReportsEngine for delivery).

Subcategory: analytics_hub

Detection rule registry + anomaly observation + classification + status
lifecycle. Composes (not replaces) the existing risk and revenue assurance
anomaly engines (#241–#248). The job here is the ANALYTICS HUB-FACING
anomaly surface — what an MIS analyst sees about deviations across any
metric the platform tracks.

Public API:
    register_detection_rule(rule_data, actor, reason)
    transition_rule_state(rule_id, new_state, actor, reason)
    record_anomaly_observation(observation_data, actor)
    classify_anomaly(observation_id, classification, actor, reason)
    transition_observation_state(observation_id, new_state, actor, reason)
    anomaly_metrics(days=30) -> Dict
    high_severity_open() -> List

DETECTION_METHODS byte-for-byte (5):
    THRESHOLD, Z_SCORE, MOVING_AVERAGE, ISOLATION_FOREST, MANUAL

RULE_STATES byte-for-byte (4):
    ACTIVE, PAUSED, DEPRECATED, ARCHIVED

ALLOWED_RULE_TRANSITIONS (Rule 4):
    ACTIVE     → PAUSED | DEPRECATED | ARCHIVED
    PAUSED     → ACTIVE | DEPRECATED | ARCHIVED
    DEPRECATED → ARCHIVED
    ARCHIVED   → ()

ANOMALY_SEVERITIES byte-for-byte (4):
    LOW, MEDIUM, HIGH, CRITICAL

ANOMALY_STATES byte-for-byte (5):
    OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE, SUPPRESSED

ALLOWED_ANOMALY_TRANSITIONS (Rule 4):
    OPEN           → INVESTIGATING | RESOLVED | FALSE_POSITIVE | SUPPRESSED
    INVESTIGATING  → RESOLVED | FALSE_POSITIVE | SUPPRESSED
    RESOLVED       → ()
    FALSE_POSITIVE → ()
    SUPPRESSED     → ()

ANOMALY_CLASSIFICATIONS byte-for-byte (5):
    DATA_QUALITY, SEASONALITY, GENUINE_ANOMALY, POLICY_BREACH, UNCLASSIFIED

DEFAULT_DETECTION_INTERVAL_MINUTES = 15
DEFAULT_SEVERITY_ESCALATION_HOURS = 4

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DETECTION_METHODS: Tuple[str, ...] = (
    "THRESHOLD", "Z_SCORE", "MOVING_AVERAGE",
    "ISOLATION_FOREST", "MANUAL",
)

RULE_STATES: Tuple[str, ...] = (
    "ACTIVE", "PAUSED", "DEPRECATED", "ARCHIVED",
)

ALLOWED_RULE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":     ("PAUSED", "DEPRECATED", "ARCHIVED"),
    "PAUSED":     ("ACTIVE", "DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

ANOMALY_SEVERITIES: Tuple[str, ...] = (
    "LOW", "MEDIUM", "HIGH", "CRITICAL",
)

ANOMALY_STATES: Tuple[str, ...] = (
    "OPEN", "INVESTIGATING", "RESOLVED",
    "FALSE_POSITIVE", "SUPPRESSED",
)

ALLOWED_ANOMALY_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "OPEN":           ("INVESTIGATING", "RESOLVED",
                            "FALSE_POSITIVE", "SUPPRESSED"),
    "INVESTIGATING":  ("RESOLVED", "FALSE_POSITIVE", "SUPPRESSED"),
    "RESOLVED":       (),
    "FALSE_POSITIVE": (),
    "SUPPRESSED":     (),
}

ANOMALY_CLASSIFICATIONS: Tuple[str, ...] = (
    "DATA_QUALITY", "SEASONALITY", "GENUINE_ANOMALY",
    "POLICY_BREACH", "UNCLASSIFIED",
)

DEFAULT_DETECTION_INTERVAL_MINUTES = 15
DEFAULT_SEVERITY_ESCALATION_HOURS = 4


class AnomalyDetectionEngine:
    """Anomaly rule + observation + classification registry."""

    def __init__(
        self,
        rules_path: Optional[Path] = None,
        observations_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.rules_path = rules_path or base / "anomaly_rules.json"
        self.observations_path = (
            observations_path or base / "anomaly_observations.json"
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

    def register_detection_rule(
        self, rule_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("rule_id", "metric_id", "method"):
            if f not in rule_data or not rule_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if rule_data["method"] not in DETECTION_METHODS:
            return {"registered": False,
                       "error": f"invalid_method:{rule_data['method']}"}
        records = self._load(self.rules_path,
                                "anomaly_rules", ("rule_id",))
        if any(r.get("rule_id") == rule_data["rule_id"] for r in records):
            return {"registered": False, "error": "duplicate_rule_id"}
        record = {
            "rule_id": rule_data["rule_id"],
            "metric_id": rule_data["metric_id"],
            "method": rule_data["method"],
            "threshold_value": rule_data.get("threshold_value"),
            "severity": rule_data.get("severity", "MEDIUM"),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "ACTIVE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        if record["severity"] not in ANOMALY_SEVERITIES:
            return {"registered": False,
                       "error": f"invalid_severity:{record['severity']}"}
        records.append(record)
        ok = self._save(self.rules_path, records,
                          "anomaly_rules", "rule_id")
        return {"registered": ok, "rule_id": rule_data["rule_id"]}

    def transition_rule_state(
        self, rule_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in RULE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.rules_path,
                                "anomaly_rules", ("rule_id",))
        for r in records:
            if r.get("rule_id") == rule_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_RULE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.rules_path, records,
                                  "anomaly_rules", "rule_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "rule_not_found"}

    def record_anomaly_observation(
        self, observation_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("observation_id", "rule_id", "metric_id",
                      "observed_value", "severity"):
            if f not in observation_data or observation_data[f] in (None, ""):
                return {"recorded": False, "error": f"missing_field:{f}"}
        if observation_data["severity"] not in ANOMALY_SEVERITIES:
            return {"recorded": False,
                       "error": f"invalid_severity:{observation_data['severity']}"}
        records = self._load(self.observations_path,
                                "anomaly_observations", ("observation_id",))
        if any(r.get("observation_id") == observation_data["observation_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_observation_id"}
        record = {
            "observation_id": observation_data["observation_id"],
            "rule_id": observation_data["rule_id"],
            "metric_id": observation_data["metric_id"],
            "observed_value": str(observation_data["observed_value"]),
            "expected_value": str(observation_data.get("expected_value", "")),
            "severity": observation_data["severity"],
            "classification": "UNCLASSIFIED",
            "state": "OPEN",
            "detected_at": datetime.utcnow().isoformat(),
            "detected_by": actor,
            "transitions": [{
                "to": "OPEN", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.observations_path, records,
                          "anomaly_observations", "observation_id")
        return {"recorded": ok,
                  "observation_id": observation_data["observation_id"]}

    def classify_anomaly(
        self, observation_id: str, classification: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"classified": False,
                       "error": "actor_and_reason_required"}
        if classification not in ANOMALY_CLASSIFICATIONS:
            return {"classified": False,
                       "error": f"invalid_classification:{classification}"}
        records = self._load(self.observations_path,
                                "anomaly_observations", ("observation_id",))
        for r in records:
            if r.get("observation_id") == observation_id:
                r["classification"] = classification
                r["classified_at"] = datetime.utcnow().isoformat()
                r["classified_by"] = actor
                r["classification_reason"] = reason
                ok = self._save(self.observations_path, records,
                                  "anomaly_observations", "observation_id")
                return {"classified": ok, "classification": classification}
        return {"classified": False, "error": "observation_not_found"}

    def transition_observation_state(
        self, observation_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in ANOMALY_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.observations_path,
                                "anomaly_observations", ("observation_id",))
        for r in records:
            if r.get("observation_id") == observation_id:
                current = r.get("state", "OPEN")
                allowed = ALLOWED_ANOMALY_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.observations_path, records,
                                  "anomaly_observations",
                                  "observation_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "observation_not_found"}

    def anomaly_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        observations = self._load(self.observations_path,
                                              "anomaly_observations",
                                              ("observation_id",))
        recent = [o for o in observations
                       if o.get("detected_at", "") >= cutoff]
        per_severity: Dict[str, int] = {}
        per_classification: Dict[str, int] = {}
        per_state: Dict[str, int] = {}
        for o in recent:
            per_severity[o.get("severity", "")] = (
                per_severity.get(o.get("severity", ""), 0) + 1
            )
            per_classification[o.get("classification", "")] = (
                per_classification.get(o.get("classification", ""), 0) + 1
            )
            per_state[o.get("state", "")] = (
                per_state.get(o.get("state", ""), 0) + 1
            )
        false_positive_rate = round(
            (per_classification.get("DATA_QUALITY", 0) /
             len(recent) * 100) if recent else 0, 1,
        )
        return {
            "window_days": days,
            "total_observations": len(recent),
            "per_severity": per_severity,
            "per_classification": per_classification,
            "per_state": per_state,
            "data_quality_rate_pct": false_positive_rate,
        }

    def high_severity_open(self) -> List[Dict[str, Any]]:
        records = self._load(self.observations_path,
                                "anomaly_observations", ("observation_id",))
        return [
            r for r in records
            if r.get("severity") in ("HIGH", "CRITICAL")
                  and r.get("state") in ("OPEN", "INVESTIGATING")
        ]


def _self_test() -> None:
    import tempfile

    assert DETECTION_METHODS == (
        "THRESHOLD", "Z_SCORE", "MOVING_AVERAGE",
        "ISOLATION_FOREST", "MANUAL",
    )
    assert ALLOWED_RULE_TRANSITIONS["ARCHIVED"] == ()
    assert ANOMALY_SEVERITIES == ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert ANOMALY_STATES == (
        "OPEN", "INVESTIGATING", "RESOLVED",
        "FALSE_POSITIVE", "SUPPRESSED",
    )
    assert ALLOWED_ANOMALY_TRANSITIONS["RESOLVED"] == ()
    assert ALLOWED_ANOMALY_TRANSITIONS["FALSE_POSITIVE"] == ()
    assert ALLOWED_ANOMALY_TRANSITIONS["SUPPRESSED"] == ()
    assert ANOMALY_CLASSIFICATIONS == (
        "DATA_QUALITY", "SEASONALITY", "GENUINE_ANOMALY",
        "POLICY_BREACH", "UNCLASSIFIED",
    )
    assert DEFAULT_DETECTION_INTERVAL_MINUTES == 15
    assert DEFAULT_SEVERITY_ESCALATION_HOURS == 4

    with tempfile.TemporaryDirectory() as tmpdir:
        e = AnomalyDetectionEngine(
            rules_path=Path(tmpdir) / "r.json",
            observations_path=Path(tmpdir) / "o.json",
        )
        # Rule
        r = e.register_detection_rule(
            {"rule_id": "RULE-CAR",
             "metric_id": "CAR",
             "method": "THRESHOLD",
             "threshold_value": "14.5",
             "severity": "HIGH"},
            actor="cro", reason="CBK floor",
        )
        assert r["registered"]
        # Invalid method
        r = e.register_detection_rule(
            {"rule_id": "X", "metric_id": "Y", "method": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid severity
        r = e.register_detection_rule(
            {"rule_id": "Z", "metric_id": "Y",
             "method": "THRESHOLD", "severity": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # State
        r = e.transition_rule_state(
            "RULE-CAR", "PAUSED", actor="cro", reason="audit freeze",
        )
        assert r["transitioned"]
        r = e.transition_rule_state(
            "RULE-CAR", "ACTIVE", actor="cro", reason="resume",
        )
        assert r["transitioned"]
        r = e.transition_rule_state(
            "RULE-CAR", "DEPRECATED", actor="cro", reason="rule rewrite",
        )
        assert r["transitioned"]
        # Deprecated only goes to archived
        r = e.transition_rule_state(
            "RULE-CAR", "ACTIVE", actor="x", reason="x",
        )
        assert not r["transitioned"]
        r = e.transition_rule_state(
            "RULE-CAR", "ARCHIVED", actor="cro", reason="closed",
        )
        assert r["transitioned"]
        # ARCHIVED is terminal
        r = e.transition_rule_state(
            "RULE-CAR", "ACTIVE", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Observation
        r = e.record_anomaly_observation(
            {"observation_id": "OBS-001",
             "rule_id": "RULE-CAR",
             "metric_id": "CAR",
             "observed_value": "13.2",
             "expected_value": "15.0",
             "severity": "CRITICAL"},
            actor="auto-detector",
        )
        assert r["recorded"]
        # Classify
        r = e.classify_anomaly(
            "OBS-001", "GENUINE_ANOMALY",
            actor="cro", reason="CAR breach",
        )
        assert r["classified"]
        # Bad classification
        r = e.classify_anomaly(
            "OBS-001", "WHATEVER",
            actor="x", reason="x",
        )
        assert not r["classified"]
        # Transition
        r = e.transition_observation_state(
            "OBS-001", "INVESTIGATING",
            actor="cro", reason="taking lead",
        )
        assert r["transitioned"]
        r = e.transition_observation_state(
            "OBS-001", "RESOLVED",
            actor="cro", reason="capital injection completed",
        )
        assert r["transitioned"]

        # Metrics
        m = e.anomaly_metrics(days=30)
        assert m["total_observations"] == 1
        assert m["per_severity"]["CRITICAL"] == 1
        assert m["per_classification"]["GENUINE_ANOMALY"] == 1
        assert m["per_state"]["RESOLVED"] == 1

        # high_severity_open should be empty (we resolved it)
        hsos = e.high_severity_open()
        assert len(hsos) == 0

    print("  ✅ analytics_anomaly_detection self-test PASS")


if __name__ == "__main__":
    _self_test()
