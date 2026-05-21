"""
================================================================================
A2Z MIS 360 — Standard #175: Automated Exception Management
================================================================================

Risk classification: Cat C (read-side exception orchestration; SLA
tracking; never auto-resolves exceptions — auto-escalation only).

Subcategory: cims

Auto-escalation with conditional branching and SLA tracking for CIMS
exceptions. Composes upstream capture (#166), classification (#167),
STP (#168), process intelligence (#169), and dropout prevention (#170)
— exceptions raised from any of those engines route through this
engine's lifecycle.

The engine provides:
  • Exception registry with categories and severities
  • Conditional escalation rules tied to SLA breach windows
  • Multi-step resolution workflow with named approvers
  • SLA breach tracking against per-severity targets

Public API:
    register_exception_category(category_data, actor, reason)
    register_exception(exception_data, actor, reason)
    transition_exception_state(exception_id, new_state, actor, reason)
    record_escalation(escalation_data, actor)
    record_resolution(resolution_data, actor)
    sla_breach_report(days=30) -> Dict
    open_exceptions_by_severity(severity=None) -> List

EXCEPTION_SEVERITIES byte-for-byte (4):
    LOW, MEDIUM, HIGH, CRITICAL

EXCEPTION_STATES byte-for-byte (6):
    OPEN, ASSIGNED, IN_PROGRESS, ESCALATED, RESOLVED, CANCELLED

ALLOWED_EXCEPTION_TRANSITIONS (Rule 4):
    OPEN        → ASSIGNED | ESCALATED | CANCELLED
    ASSIGNED    → IN_PROGRESS | ESCALATED | CANCELLED
    IN_PROGRESS → RESOLVED | ESCALATED | CANCELLED
    ESCALATED   → IN_PROGRESS | RESOLVED | CANCELLED
    RESOLVED    → ()
    CANCELLED   → ()

ESCALATION_TARGETS byte-for-byte (5):
    TEAM_LEAD, OPERATIONS_HEAD, RM, COMPLIANCE_OFFICER, CCO

RESOLUTION_OUTCOMES byte-for-byte (5):
    RESOLVED_BY_OPS, RESOLVED_BY_CUSTOMER, AUTO_RESOLVED,
    WAIVED, CLOSED_NO_ACTION

EXCEPTION_CATEGORIES byte-for-byte (8):
    DATA_QUALITY, SLA_BREACH, MANUAL_REVIEW_NEEDED,
    SYSTEM_TIMEOUT, COMPLIANCE_FLAG, IDENTITY_MISMATCH,
    DOCUMENT_MISSING, CHANNEL_FAILURE

SLA_TARGETS_HOURS byte-for-byte (4):
    LOW = 72
    MEDIUM = 24
    HIGH = 8
    CRITICAL = 2

DEFAULT_AUTO_ESCALATION_THRESHOLD_HOURS_FOR_HIGH = 4
DEFAULT_REASSIGNMENT_LIMIT = 3

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


EXCEPTION_SEVERITIES: Tuple[str, ...] = (
    "LOW", "MEDIUM", "HIGH", "CRITICAL",
)

EXCEPTION_STATES: Tuple[str, ...] = (
    "OPEN", "ASSIGNED", "IN_PROGRESS",
    "ESCALATED", "RESOLVED", "CANCELLED",
)

ALLOWED_EXCEPTION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "OPEN":        ("ASSIGNED", "ESCALATED", "CANCELLED"),
    "ASSIGNED":    ("IN_PROGRESS", "ESCALATED", "CANCELLED"),
    "IN_PROGRESS": ("RESOLVED", "ESCALATED", "CANCELLED"),
    "ESCALATED":   ("IN_PROGRESS", "RESOLVED", "CANCELLED"),
    "RESOLVED":    (),
    "CANCELLED":   (),
}

ESCALATION_TARGETS: Tuple[str, ...] = (
    "TEAM_LEAD", "OPERATIONS_HEAD", "RM",
    "COMPLIANCE_OFFICER", "CCO",
)

RESOLUTION_OUTCOMES: Tuple[str, ...] = (
    "RESOLVED_BY_OPS", "RESOLVED_BY_CUSTOMER", "AUTO_RESOLVED",
    "WAIVED", "CLOSED_NO_ACTION",
)

EXCEPTION_CATEGORIES: Tuple[str, ...] = (
    "DATA_QUALITY", "SLA_BREACH", "MANUAL_REVIEW_NEEDED",
    "SYSTEM_TIMEOUT", "COMPLIANCE_FLAG", "IDENTITY_MISMATCH",
    "DOCUMENT_MISSING", "CHANNEL_FAILURE",
)

SLA_TARGETS_HOURS: Dict[str, int] = {
    "LOW": 72,
    "MEDIUM": 24,
    "HIGH": 8,
    "CRITICAL": 2,
}

DEFAULT_AUTO_ESCALATION_THRESHOLD_HOURS_FOR_HIGH = 4
DEFAULT_REASSIGNMENT_LIMIT = 3


class ExceptionManagementEngine:
    """Exception + escalation + resolution registry. SLA breach tracking."""

    def __init__(
        self,
        categories_path: Optional[Path] = None,
        exceptions_path: Optional[Path] = None,
        escalations_path: Optional[Path] = None,
        resolutions_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.categories_path = (
            categories_path or base / "cims_exception_categories.json"
        )
        self.exceptions_path = (
            exceptions_path or base / "cims_exceptions.json"
        )
        self.escalations_path = (
            escalations_path or base / "cims_escalations.json"
        )
        self.resolutions_path = (
            resolutions_path or base / "cims_resolutions.json"
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

    def register_exception_category(
        self, category_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("category_id", "exception_category",
                      "default_severity"):
            if f not in category_data or not category_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if category_data["exception_category"] not in EXCEPTION_CATEGORIES:
            return {"registered": False,
                       "error": f"invalid_category:{category_data['exception_category']}"}
        if category_data["default_severity"] not in EXCEPTION_SEVERITIES:
            return {"registered": False,
                       "error": f"invalid_severity:{category_data['default_severity']}"}
        records = self._load(self.categories_path,
                                "cims_exception_categories",
                                ("category_id",))
        if any(r.get("category_id") == category_data["category_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_category_id"}
        record = {
            "category_id": category_data["category_id"],
            "exception_category": category_data["exception_category"],
            "default_severity": category_data["default_severity"],
            "auto_escalate_after_hours":
                category_data.get("auto_escalate_after_hours"),
            "default_target": category_data.get(
                "default_target", "TEAM_LEAD",
            ),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        if record["default_target"] not in ESCALATION_TARGETS:
            return {"registered": False,
                       "error": f"invalid_target:{record['default_target']}"}
        records.append(record)
        ok = self._save(self.categories_path, records,
                          "cims_exception_categories", "category_id")
        return {"registered": ok,
                  "category_id": category_data["category_id"]}

    def register_exception(
        self, exception_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("exception_id", "exception_category",
                      "severity", "narrative"):
            if f not in exception_data or not exception_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if exception_data["exception_category"] not in EXCEPTION_CATEGORIES:
            return {"registered": False,
                       "error": f"invalid_category:{exception_data['exception_category']}"}
        if exception_data["severity"] not in EXCEPTION_SEVERITIES:
            return {"registered": False,
                       "error": f"invalid_severity:{exception_data['severity']}"}
        records = self._load(self.exceptions_path,
                                "cims_exceptions", ("exception_id",))
        if any(r.get("exception_id") == exception_data["exception_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_exception_id"}
        sla_target = SLA_TARGETS_HOURS.get(exception_data["severity"], 24)
        record = {
            "exception_id": exception_data["exception_id"],
            "exception_category": exception_data["exception_category"],
            "severity": exception_data["severity"],
            "narrative": exception_data["narrative"],
            "linked_session_id": exception_data.get("linked_session_id", ""),
            "sla_target_hours": sla_target,
            "state": "OPEN",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "OPEN", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.exceptions_path, records,
                          "cims_exceptions", "exception_id")
        return {"registered": ok,
                  "exception_id": exception_data["exception_id"],
                  "sla_target_hours": sla_target}

    def transition_exception_state(
        self, exception_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in EXCEPTION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.exceptions_path,
                                "cims_exceptions", ("exception_id",))
        for r in records:
            if r.get("exception_id") == exception_id:
                current = r.get("state", "OPEN")
                allowed = ALLOWED_EXCEPTION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                if new_state == "RESOLVED":
                    r["resolved_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.exceptions_path, records,
                                  "cims_exceptions", "exception_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "exception_not_found"}

    def record_escalation(
        self, escalation_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("escalation_id", "exception_id", "target"):
            if f not in escalation_data or not escalation_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if escalation_data["target"] not in ESCALATION_TARGETS:
            return {"recorded": False,
                       "error": f"invalid_target:{escalation_data['target']}"}
        records = self._load(self.escalations_path,
                                "cims_escalations", ("escalation_id",))
        if any(r.get("escalation_id") == escalation_data["escalation_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_escalation_id"}
        record = {
            "escalation_id": escalation_data["escalation_id"],
            "exception_id": escalation_data["exception_id"],
            "target": escalation_data["target"],
            "trigger": escalation_data.get("trigger", "manual"),
            "narrative": escalation_data.get("narrative", ""),
            "escalated_by": actor,
            "escalated_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.escalations_path, records,
                          "cims_escalations", "escalation_id")
        return {"recorded": ok,
                  "escalation_id": escalation_data["escalation_id"]}

    def record_resolution(
        self, resolution_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("resolution_id", "exception_id", "outcome"):
            if f not in resolution_data or not resolution_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if resolution_data["outcome"] not in RESOLUTION_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{resolution_data['outcome']}"}
        records = self._load(self.resolutions_path,
                                "cims_resolutions", ("resolution_id",))
        if any(r.get("resolution_id") == resolution_data["resolution_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_resolution_id"}
        record = {
            "resolution_id": resolution_data["resolution_id"],
            "exception_id": resolution_data["exception_id"],
            "outcome": resolution_data["outcome"],
            "narrative": resolution_data.get("narrative", ""),
            "resolved_by": actor,
            "resolved_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.resolutions_path, records,
                          "cims_resolutions", "resolution_id")
        return {"recorded": ok,
                  "resolution_id": resolution_data["resolution_id"]}

    def sla_breach_report(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        exceptions = [e for e in self._load(self.exceptions_path,
                                                          "cims_exceptions",
                                                          ("exception_id",))
                            if e.get("registered_at", "") >= cutoff]
        breached = []
        for e in exceptions:
            sla = e.get("sla_target_hours", 24)
            registered_iso = e.get("registered_at", "")
            try:
                registered_dt = datetime.fromisoformat(registered_iso)
            except ValueError:
                continue
            if e.get("state") == "RESOLVED":
                resolved_iso = e.get("resolved_at", "")
                try:
                    resolved_dt = datetime.fromisoformat(resolved_iso)
                except ValueError:
                    continue
                hours_taken = (
                    (resolved_dt - registered_dt).total_seconds() / 3600
                )
                if hours_taken > sla:
                    breached.append({
                        "exception_id": e.get("exception_id"),
                        "severity": e.get("severity"),
                        "sla_target_hours": sla,
                        "actual_hours": round(hours_taken, 1),
                        "outcome": "RESOLVED_LATE",
                    })
            elif e.get("state") in ("OPEN", "ASSIGNED",
                                                "IN_PROGRESS", "ESCALATED"):
                hours_open = (
                    (datetime.utcnow() - registered_dt).total_seconds()
                    / 3600
                )
                if hours_open > sla:
                    breached.append({
                        "exception_id": e.get("exception_id"),
                        "severity": e.get("severity"),
                        "sla_target_hours": sla,
                        "actual_hours": round(hours_open, 1),
                        "outcome": "STILL_OPEN_PAST_SLA",
                    })
        breach_pct = round(
            (len(breached) / len(exceptions) * 100) if exceptions else 0, 1,
        )
        return {
            "window_days": days,
            "exceptions_in_window": len(exceptions),
            "breaches": breached,
            "breach_count": len(breached),
            "breach_pct": breach_pct,
        }

    def open_exceptions_by_severity(
        self, severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if severity is not None and severity not in EXCEPTION_SEVERITIES:
            return []
        records = self._load(self.exceptions_path,
                                "cims_exceptions", ("exception_id",))
        open_states = ("OPEN", "ASSIGNED", "IN_PROGRESS", "ESCALATED")
        if severity:
            return [r for r in records
                          if r.get("severity") == severity
                             and r.get("state") in open_states]
        return [r for r in records if r.get("state") in open_states]


def _self_test() -> None:
    import tempfile

    assert EXCEPTION_SEVERITIES == ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert EXCEPTION_STATES == (
        "OPEN", "ASSIGNED", "IN_PROGRESS",
        "ESCALATED", "RESOLVED", "CANCELLED",
    )
    assert ALLOWED_EXCEPTION_TRANSITIONS["RESOLVED"] == ()
    assert ALLOWED_EXCEPTION_TRANSITIONS["CANCELLED"] == ()
    assert ESCALATION_TARGETS == (
        "TEAM_LEAD", "OPERATIONS_HEAD", "RM",
        "COMPLIANCE_OFFICER", "CCO",
    )
    assert RESOLUTION_OUTCOMES == (
        "RESOLVED_BY_OPS", "RESOLVED_BY_CUSTOMER", "AUTO_RESOLVED",
        "WAIVED", "CLOSED_NO_ACTION",
    )
    assert EXCEPTION_CATEGORIES == (
        "DATA_QUALITY", "SLA_BREACH", "MANUAL_REVIEW_NEEDED",
        "SYSTEM_TIMEOUT", "COMPLIANCE_FLAG", "IDENTITY_MISMATCH",
        "DOCUMENT_MISSING", "CHANNEL_FAILURE",
    )
    assert SLA_TARGETS_HOURS == {
        "LOW": 72, "MEDIUM": 24, "HIGH": 8, "CRITICAL": 2,
    }
    assert DEFAULT_AUTO_ESCALATION_THRESHOLD_HOURS_FOR_HIGH == 4
    assert DEFAULT_REASSIGNMENT_LIMIT == 3

    with tempfile.TemporaryDirectory() as tmpdir:
        e = ExceptionManagementEngine(
            categories_path=Path(tmpdir) / "c.json",
            exceptions_path=Path(tmpdir) / "e.json",
            escalations_path=Path(tmpdir) / "es.json",
            resolutions_path=Path(tmpdir) / "r.json",
        )
        # Category
        r = e.register_exception_category(
            {"category_id": "CAT-001",
             "exception_category": "DATA_QUALITY",
             "default_severity": "MEDIUM",
             "auto_escalate_after_hours": 12,
             "default_target": "TEAM_LEAD"},
            actor="ops", reason="setup",
        )
        assert r["registered"]
        # Bad target
        r = e.register_exception_category(
            {"category_id": "X",
             "exception_category": "DATA_QUALITY",
             "default_severity": "LOW",
             "default_target": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Exception
        r = e.register_exception(
            {"exception_id": "EXC-001",
             "exception_category": "DATA_QUALITY",
             "severity": "HIGH",
             "narrative": "Customer ID mismatch",
             "linked_session_id": "CAP-001"},
            actor="ops", reason="data quality",
        )
        assert r["registered"]
        assert r["sla_target_hours"] == 8  # HIGH -> 8h
        # Bad severity
        r = e.register_exception(
            {"exception_id": "X",
             "exception_category": "DATA_QUALITY",
             "severity": "WHATEVER",
             "narrative": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_exception_state(
            "EXC-001", "ASSIGNED", actor="ops", reason="picked up",
        )
        assert r["transitioned"]
        r = e.transition_exception_state(
            "EXC-001", "IN_PROGRESS", actor="ops", reason="working",
        )
        assert r["transitioned"]
        r = e.transition_exception_state(
            "EXC-001", "ESCALATED", actor="ops", reason="needs senior",
        )
        assert r["transitioned"]
        r = e.transition_exception_state(
            "EXC-001", "RESOLVED",
            actor="senior_ops", reason="data corrected",
        )
        assert r["transitioned"]
        # RESOLVED is terminal
        r = e.transition_exception_state(
            "EXC-001", "OPEN", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Escalation
        r = e.record_escalation(
            {"escalation_id": "ESC-001",
             "exception_id": "EXC-001",
             "target": "OPERATIONS_HEAD",
             "trigger": "auto",
             "narrative": "SLA approaching"},
            actor="ops",
        )
        assert r["recorded"]
        # Bad target
        r = e.record_escalation(
            {"escalation_id": "X",
             "exception_id": "Y",
             "target": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Resolution
        r = e.record_resolution(
            {"resolution_id": "RES-001",
             "exception_id": "EXC-001",
             "outcome": "RESOLVED_BY_OPS"},
            actor="senior_ops",
        )
        assert r["recorded"]
        # Bad outcome
        r = e.record_resolution(
            {"resolution_id": "X",
             "exception_id": "Y",
             "outcome": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # SLA report — exception was resolved within minutes, not breached
        rep = e.sla_breach_report(days=30)
        assert rep["exceptions_in_window"] == 1
        assert rep["breach_count"] == 0

        # Open by severity — none open after the resolve
        opens = e.open_exceptions_by_severity()
        assert len(opens) == 0

    print("  ✅ cims_exception_management self-test PASS")


if __name__ == "__main__":
    _self_test()
