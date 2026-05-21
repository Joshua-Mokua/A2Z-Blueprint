"""
================================================================================
A2Z MIS 360 — Standard #200: Compliance Dashboard & KPIs
================================================================================

Risk classification: Cat C (read-side aggregation; KPI registry; never
modifies upstream compliance engines).

Subcategory: compliance

Executive compliance dashboard with key risk indicators. Read-side
composition over the existing CMS suite (#191–#200 active engines:
KYC onboarding, KYB onboarding, PEP/sanctions screening, AML monitoring,
SAR filing, regulatory change management, policy management, training
tracking, risk assessment, examiner portal). The job here is the
bank-wide compliance posture surface — what an MD, CCO, or audit
committee sees in a single glance.

Public API:
    register_kpi_definition(kpi_data, actor, reason)
    transition_kpi_state(kpi_id, new_state, actor, reason)
    record_kpi_observation(observation_data, actor)
    register_executive_view(view_data, actor, reason)
    compliance_summary(framework=None, days=30) -> Dict
    kpi_breach_log(severity=None) -> List

KPI_DOMAINS byte-for-byte (8):
    KYC, AML, SANCTIONS, REGULATORY_REPORTING, POLICY,
    TRAINING, EXAMINER_FINDINGS, RISK_ASSESSMENT

KPI_FREQUENCIES byte-for-byte (5):
    DAILY, WEEKLY, MONTHLY, QUARTERLY, ANNUAL

KPI_STATES byte-for-byte (4):
    ACTIVE, PAUSED, DEPRECATED, ARCHIVED

ALLOWED_KPI_TRANSITIONS (Rule 4):
    ACTIVE     → PAUSED | DEPRECATED | ARCHIVED
    PAUSED     → ACTIVE | DEPRECATED | ARCHIVED
    DEPRECATED → ARCHIVED
    ARCHIVED   → ()

KPI_BREACH_SEVERITIES byte-for-byte (4):
    GREEN, AMBER, RED, CRITICAL

EXECUTIVE_VIEW_TYPES byte-for-byte (5):
    BOARD_PACK, AUDIT_COMMITTEE, CCO_DASHBOARD,
    REGULATOR_BRIEFING, INTERNAL_REVIEW

REGULATORY_FRAMEWORKS byte-for-byte (5):
    CBK_PRUDENTIAL, DPA_KENYA_2019, AML_POCAMLA,
    BASEL_III, ISO_27001

DEFAULT_KPI_REFRESH_HOURS = 24
DEFAULT_BREACH_ESCALATION_HOURS = 4

CBK_PRUDENTIAL_REFERENCE = "CBK Prudential Guidelines"
DPA_KENYA_REFERENCE = "Data Protection Act 2019"
AML_REFERENCE = "POCAMLA Kenya 2009"

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


KPI_DOMAINS: Tuple[str, ...] = (
    "KYC", "AML", "SANCTIONS", "REGULATORY_REPORTING",
    "POLICY", "TRAINING", "EXAMINER_FINDINGS", "RISK_ASSESSMENT",
)

KPI_FREQUENCIES: Tuple[str, ...] = (
    "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "ANNUAL",
)

KPI_STATES: Tuple[str, ...] = (
    "ACTIVE", "PAUSED", "DEPRECATED", "ARCHIVED",
)

ALLOWED_KPI_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":     ("PAUSED", "DEPRECATED", "ARCHIVED"),
    "PAUSED":     ("ACTIVE", "DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

KPI_BREACH_SEVERITIES: Tuple[str, ...] = (
    "GREEN", "AMBER", "RED", "CRITICAL",
)

EXECUTIVE_VIEW_TYPES: Tuple[str, ...] = (
    "BOARD_PACK", "AUDIT_COMMITTEE", "CCO_DASHBOARD",
    "REGULATOR_BRIEFING", "INTERNAL_REVIEW",
)

REGULATORY_FRAMEWORKS: Tuple[str, ...] = (
    "CBK_PRUDENTIAL", "DPA_KENYA_2019", "AML_POCAMLA",
    "BASEL_III", "ISO_27001",
)

DEFAULT_KPI_REFRESH_HOURS = 24
DEFAULT_BREACH_ESCALATION_HOURS = 4

CBK_PRUDENTIAL_REFERENCE = "CBK Prudential Guidelines"
DPA_KENYA_REFERENCE = "Data Protection Act 2019"
AML_REFERENCE = "POCAMLA Kenya 2009"


class ComplianceDashboardEngine:
    """Compliance KPI registry + observation log + executive view registry."""

    def __init__(
        self,
        kpis_path: Optional[Path] = None,
        observations_path: Optional[Path] = None,
        views_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.kpis_path = kpis_path or base / "compliance_kpis.json"
        self.observations_path = (
            observations_path or base / "compliance_kpi_observations.json"
        )
        self.views_path = views_path or base / "compliance_executive_views.json"

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

    def register_kpi_definition(
        self, kpi_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("kpi_id", "name", "domain", "frequency",
                      "framework"):
            if f not in kpi_data or not kpi_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if kpi_data["domain"] not in KPI_DOMAINS:
            return {"registered": False,
                       "error": f"invalid_domain:{kpi_data['domain']}"}
        if kpi_data["frequency"] not in KPI_FREQUENCIES:
            return {"registered": False,
                       "error": f"invalid_frequency:{kpi_data['frequency']}"}
        if kpi_data["framework"] not in REGULATORY_FRAMEWORKS:
            return {"registered": False,
                       "error": f"invalid_framework:{kpi_data['framework']}"}
        records = self._load(self.kpis_path,
                                "compliance_kpis", ("kpi_id",))
        if any(r.get("kpi_id") == kpi_data["kpi_id"] for r in records):
            return {"registered": False, "error": "duplicate_kpi_id"}
        record = {
            "kpi_id": kpi_data["kpi_id"],
            "name": kpi_data["name"],
            "domain": kpi_data["domain"],
            "frequency": kpi_data["frequency"],
            "framework": kpi_data["framework"],
            "amber_threshold": kpi_data.get("amber_threshold"),
            "red_threshold": kpi_data.get("red_threshold"),
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
        ok = self._save(self.kpis_path, records,
                          "compliance_kpis", "kpi_id")
        return {"registered": ok, "kpi_id": kpi_data["kpi_id"]}

    def transition_kpi_state(
        self, kpi_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in KPI_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.kpis_path,
                                "compliance_kpis", ("kpi_id",))
        for r in records:
            if r.get("kpi_id") == kpi_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_KPI_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.kpis_path, records,
                                  "compliance_kpis", "kpi_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "kpi_not_found"}

    def record_kpi_observation(
        self, observation_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("observation_id", "kpi_id",
                      "observed_value", "severity"):
            if f not in observation_data or observation_data[f] in (None, ""):
                return {"recorded": False, "error": f"missing_field:{f}"}
        if observation_data["severity"] not in KPI_BREACH_SEVERITIES:
            return {"recorded": False,
                       "error": f"invalid_severity:{observation_data['severity']}"}
        records = self._load(self.observations_path,
                                "compliance_kpi_observations",
                                ("observation_id",))
        if any(r.get("observation_id") == observation_data["observation_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_observation_id"}
        record = {
            "observation_id": observation_data["observation_id"],
            "kpi_id": observation_data["kpi_id"],
            "observed_value": str(observation_data["observed_value"]),
            "severity": observation_data["severity"],
            "narrative": observation_data.get("narrative", ""),
            "observed_at": datetime.utcnow().isoformat(),
            "observed_by": actor,
        }
        records.append(record)
        ok = self._save(self.observations_path, records,
                          "compliance_kpi_observations", "observation_id")
        return {"recorded": ok,
                  "observation_id": observation_data["observation_id"]}

    def register_executive_view(
        self, view_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("view_id", "view_type", "title"):
            if f not in view_data or not view_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if view_data["view_type"] not in EXECUTIVE_VIEW_TYPES:
            return {"registered": False,
                       "error": f"invalid_view_type:{view_data['view_type']}"}
        records = self._load(self.views_path,
                                "compliance_executive_views", ("view_id",))
        if any(r.get("view_id") == view_data["view_id"] for r in records):
            return {"registered": False, "error": "duplicate_view_id"}
        record = {
            "view_id": view_data["view_id"],
            "view_type": view_data["view_type"],
            "title": view_data["title"],
            "kpi_ids": list(view_data.get("kpi_ids", [])),
            "audience": view_data.get("audience", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.views_path, records,
                          "compliance_executive_views", "view_id")
        return {"registered": ok, "view_id": view_data["view_id"]}

    def compliance_summary(
        self, framework: Optional[str] = None, days: int = 30,
    ) -> Dict[str, Any]:
        if framework is not None and framework not in REGULATORY_FRAMEWORKS:
            return {"error": f"invalid_framework:{framework}"}
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        kpis = self._load(self.kpis_path,
                              "compliance_kpis", ("kpi_id",))
        if framework:
            kpis = [k for k in kpis if k.get("framework") == framework]
        active = [k for k in kpis if k.get("state") == "ACTIVE"]
        observations = self._load(self.observations_path,
                                              "compliance_kpi_observations",
                                              ("observation_id",))
        active_ids = {k.get("kpi_id") for k in active}
        recent = [
            o for o in observations
            if o.get("observed_at", "") >= cutoff
                  and o.get("kpi_id") in active_ids
        ]
        per_severity: Dict[str, int] = {}
        per_domain: Dict[str, int] = {}
        latest_per_kpi: Dict[str, Dict[str, Any]] = {}
        for o in recent:
            sev = o.get("severity", "")
            per_severity[sev] = per_severity.get(sev, 0) + 1
        kpi_to_domain = {k.get("kpi_id"): k.get("domain") for k in active}
        for o in recent:
            dom = kpi_to_domain.get(o.get("kpi_id"), "")
            per_domain[dom] = per_domain.get(dom, 0) + 1
            kid = o.get("kpi_id")
            if (kid not in latest_per_kpi
                    or o.get("observed_at", "") >
                          latest_per_kpi[kid].get("observed_at", "")):
                latest_per_kpi[kid] = o
        red_count = (per_severity.get("RED", 0)
                          + per_severity.get("CRITICAL", 0))
        return {
            "framework": framework or "ALL",
            "window_days": days,
            "active_kpi_count": len(active),
            "observations_in_window": len(recent),
            "per_severity": per_severity,
            "per_domain": per_domain,
            "red_or_critical_count": red_count,
            "latest_per_kpi_count": len(latest_per_kpi),
        }

    def kpi_breach_log(
        self, severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if severity is not None and severity not in KPI_BREACH_SEVERITIES:
            return []
        observations = self._load(self.observations_path,
                                              "compliance_kpi_observations",
                                              ("observation_id",))
        if severity:
            return [o for o in observations
                          if o.get("severity") == severity]
        return [o for o in observations
                       if o.get("severity") in ("RED", "CRITICAL")]


def _self_test() -> None:
    import tempfile

    assert KPI_DOMAINS == (
        "KYC", "AML", "SANCTIONS", "REGULATORY_REPORTING",
        "POLICY", "TRAINING", "EXAMINER_FINDINGS", "RISK_ASSESSMENT",
    )
    assert KPI_FREQUENCIES == (
        "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "ANNUAL",
    )
    assert KPI_STATES == ("ACTIVE", "PAUSED", "DEPRECATED", "ARCHIVED")
    assert ALLOWED_KPI_TRANSITIONS["ARCHIVED"] == ()
    assert KPI_BREACH_SEVERITIES == ("GREEN", "AMBER", "RED", "CRITICAL")
    assert EXECUTIVE_VIEW_TYPES == (
        "BOARD_PACK", "AUDIT_COMMITTEE", "CCO_DASHBOARD",
        "REGULATOR_BRIEFING", "INTERNAL_REVIEW",
    )
    assert REGULATORY_FRAMEWORKS == (
        "CBK_PRUDENTIAL", "DPA_KENYA_2019", "AML_POCAMLA",
        "BASEL_III", "ISO_27001",
    )
    assert DEFAULT_KPI_REFRESH_HOURS == 24
    assert DEFAULT_BREACH_ESCALATION_HOURS == 4
    assert CBK_PRUDENTIAL_REFERENCE == "CBK Prudential Guidelines"
    assert DPA_KENYA_REFERENCE == "Data Protection Act 2019"
    assert AML_REFERENCE == "POCAMLA Kenya 2009"

    with tempfile.TemporaryDirectory() as tmpdir:
        e = ComplianceDashboardEngine(
            kpis_path=Path(tmpdir) / "k.json",
            observations_path=Path(tmpdir) / "o.json",
            views_path=Path(tmpdir) / "v.json",
        )
        # KPI
        r = e.register_kpi_definition(
            {"kpi_id": "KYC-COMPLETION-RATE",
             "name": "KYC Completion Rate",
             "domain": "KYC", "frequency": "DAILY",
             "framework": "CBK_PRUDENTIAL",
             "amber_threshold": "95",
             "red_threshold": "90"},
            actor="cco", reason="CBK requirement",
        )
        assert r["registered"]
        # Invalid domain
        r = e.register_kpi_definition(
            {"kpi_id": "X", "name": "Y", "domain": "WHATEVER",
             "frequency": "DAILY", "framework": "CBK_PRUDENTIAL"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid framework
        r = e.register_kpi_definition(
            {"kpi_id": "Z", "name": "Y", "domain": "KYC",
             "frequency": "DAILY", "framework": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # State machine
        r = e.transition_kpi_state(
            "KYC-COMPLETION-RATE", "PAUSED",
            actor="cco", reason="rule rewrite",
        )
        assert r["transitioned"]
        r = e.transition_kpi_state(
            "KYC-COMPLETION-RATE", "DEPRECATED",
            actor="cco", reason="superseded",
        )
        assert r["transitioned"]
        # DEPRECATED only goes to ARCHIVED
        r = e.transition_kpi_state(
            "KYC-COMPLETION-RATE", "ACTIVE",
            actor="x", reason="x",
        )
        assert not r["transitioned"]
        r = e.transition_kpi_state(
            "KYC-COMPLETION-RATE", "ARCHIVED",
            actor="cco", reason="closed",
        )
        assert r["transitioned"]
        # ARCHIVED is terminal
        r = e.transition_kpi_state(
            "KYC-COMPLETION-RATE", "ACTIVE",
            actor="x", reason="x",
        )
        assert not r["transitioned"]

        # New active KPI for observations
        e.register_kpi_definition(
            {"kpi_id": "AML-ALERT-RATE",
             "name": "AML Alert False Positive Rate",
             "domain": "AML", "frequency": "WEEKLY",
             "framework": "AML_POCAMLA",
             "amber_threshold": "85",
             "red_threshold": "70"},
            actor="cco", reason="AML KPI",
        )

        # Observations
        r = e.record_kpi_observation(
            {"observation_id": "OBS-AML-001",
             "kpi_id": "AML-ALERT-RATE",
             "observed_value": "65",
             "severity": "RED",
             "narrative": "Below red threshold; ML retrain pending"},
            actor="aml-team",
        )
        assert r["recorded"]
        # Invalid severity
        r = e.record_kpi_observation(
            {"observation_id": "OBS-X",
             "kpi_id": "AML-ALERT-RATE",
             "observed_value": "70",
             "severity": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Executive view
        r = e.register_executive_view(
            {"view_id": "VIEW-BOARD",
             "view_type": "BOARD_PACK",
             "title": "Q2 Compliance Board Pack",
             "kpi_ids": ["AML-ALERT-RATE"],
             "audience": "Board of Directors"},
            actor="cco", reason="Q2 board meeting",
        )
        assert r["registered"]
        # Invalid view_type
        r = e.register_executive_view(
            {"view_id": "X", "view_type": "WHATEVER", "title": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Summary
        s = e.compliance_summary(framework="AML_POCAMLA", days=30)
        assert s["active_kpi_count"] >= 1
        assert s["observations_in_window"] == 1
        assert s["per_severity"]["RED"] == 1
        assert s["red_or_critical_count"] == 1
        # All-framework summary
        s2 = e.compliance_summary(days=30)
        assert s2["framework"] == "ALL"

        # Breach log
        breaches = e.kpi_breach_log()
        assert len(breaches) == 1
        red_only = e.kpi_breach_log(severity="RED")
        assert len(red_only) == 1

    print("  ✅ compliance_dashboard self-test PASS")


if __name__ == "__main__":
    _self_test()
