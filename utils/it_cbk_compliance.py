"""
================================================================================
A2Z MIS 360 — Standard #300: CBK IT Compliance & Certification
================================================================================

Risk classification: Cat B (regulatory: CBK + ISO + PCI + SOC 2)

CBK Cybersecurity Guidance compliance, ISO 27001 certification, PCI DSS
for card systems, SOC 2 Type II for SaaS components.

Public API:
    register_compliance_program(program_data, actor, reason)
    transition_program_state(program_id, new_state, actor, reason)
    register_control(control_data, actor, reason)
    record_audit_finding(finding_data, actor)
    transition_finding_state(finding_id, new_state, actor, reason)
    register_certification(cert_data, actor, reason)
    transition_certification_state(cert_id, new_state, actor, reason)
    compliance_summary(framework=None) -> Dict
    expiring_certifications(within_days=90) -> List

COMPLIANCE_FRAMEWORKS byte-for-byte (4):
    CBK_CYBERSECURITY, ISO_27001, PCI_DSS, SOC_2_TYPE_II

PROGRAM_STATES byte-for-byte (4): PLANNED, IN_PROGRESS, ACTIVE, RETIRED

ALLOWED_PROGRAM_TRANSITIONS (Rule 4):
    PLANNED     → IN_PROGRESS | RETIRED
    IN_PROGRESS → ACTIVE | RETIRED
    ACTIVE      → IN_PROGRESS | RETIRED
    RETIRED     → ()

CONTROL_CATEGORIES byte-for-byte (6):
    ACCESS_CONTROL, CRYPTOGRAPHY, INCIDENT_RESPONSE,
    BUSINESS_CONTINUITY, VENDOR_MANAGEMENT, AUDIT_LOGGING

FINDING_SEVERITIES byte-for-byte (4): LOW, MEDIUM, HIGH, CRITICAL

FINDING_STATES byte-for-byte (5):
    OPEN, REMEDIATION_IN_PROGRESS, RESOLVED, ACCEPTED_RISK, OVERDUE

ALLOWED_FINDING_TRANSITIONS (Rule 4):
    OPEN                    → REMEDIATION_IN_PROGRESS | ACCEPTED_RISK
    REMEDIATION_IN_PROGRESS → RESOLVED | OVERDUE | ACCEPTED_RISK
    RESOLVED                → ()
    ACCEPTED_RISK           → ()
    OVERDUE                 → REMEDIATION_IN_PROGRESS | RESOLVED | ACCEPTED_RISK

CERTIFICATION_STATES byte-for-byte (5):
    PENDING, ACTIVE, EXPIRING_SOON, EXPIRED, REVOKED

ALLOWED_CERTIFICATION_TRANSITIONS (Rule 4):
    PENDING        → ACTIVE | EXPIRED
    ACTIVE         → EXPIRING_SOON | REVOKED | EXPIRED
    EXPIRING_SOON  → ACTIVE | EXPIRED | REVOKED
    EXPIRED        → ACTIVE
    REVOKED        → ()

CBK_REGULATORY_REFERENCE = "CBK Cybersecurity Guidance"
DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY = {
    "CRITICAL": 7, "HIGH": 30, "MEDIUM": 60, "LOW": 90,
}

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


COMPLIANCE_FRAMEWORKS: Tuple[str, ...] = (
    "CBK_CYBERSECURITY", "ISO_27001", "PCI_DSS", "SOC_2_TYPE_II",
)

PROGRAM_STATES: Tuple[str, ...] = (
    "PLANNED", "IN_PROGRESS", "ACTIVE", "RETIRED",
)

ALLOWED_PROGRAM_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PLANNED":     ("IN_PROGRESS", "RETIRED"),
    "IN_PROGRESS": ("ACTIVE", "RETIRED"),
    "ACTIVE":      ("IN_PROGRESS", "RETIRED"),
    "RETIRED":     (),
}

CONTROL_CATEGORIES: Tuple[str, ...] = (
    "ACCESS_CONTROL", "CRYPTOGRAPHY", "INCIDENT_RESPONSE",
    "BUSINESS_CONTINUITY", "VENDOR_MANAGEMENT", "AUDIT_LOGGING",
)

FINDING_SEVERITIES: Tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

FINDING_STATES: Tuple[str, ...] = (
    "OPEN", "REMEDIATION_IN_PROGRESS", "RESOLVED",
    "ACCEPTED_RISK", "OVERDUE",
)

ALLOWED_FINDING_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "OPEN":                    ("REMEDIATION_IN_PROGRESS", "ACCEPTED_RISK"),
    "REMEDIATION_IN_PROGRESS": ("RESOLVED", "OVERDUE", "ACCEPTED_RISK"),
    "RESOLVED":                (),
    "ACCEPTED_RISK":           (),
    "OVERDUE":                 ("REMEDIATION_IN_PROGRESS", "RESOLVED",
                                  "ACCEPTED_RISK"),
}

CERTIFICATION_STATES: Tuple[str, ...] = (
    "PENDING", "ACTIVE", "EXPIRING_SOON", "EXPIRED", "REVOKED",
)

ALLOWED_CERTIFICATION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PENDING":       ("ACTIVE", "EXPIRED"),
    "ACTIVE":        ("EXPIRING_SOON", "REVOKED", "EXPIRED"),
    "EXPIRING_SOON": ("ACTIVE", "EXPIRED", "REVOKED"),
    "EXPIRED":       ("ACTIVE",),
    "REVOKED":       (),
}

CBK_REGULATORY_REFERENCE = "CBK Cybersecurity Guidance"
DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY = {
    "CRITICAL": 7, "HIGH": 30, "MEDIUM": 60, "LOW": 90,
}


class CBKComplianceEngine:
    """CBK + ISO + PCI + SOC2 compliance program registry."""

    def __init__(
        self,
        programs_path: Optional[Path] = None,
        controls_path: Optional[Path] = None,
        findings_path: Optional[Path] = None,
        certifications_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.programs_path = programs_path or base / "compliance_programs.json"
        self.controls_path = controls_path or base / "compliance_controls.json"
        self.findings_path = findings_path or base / "audit_findings.json"
        self.certifications_path = (
            certifications_path or base / "certifications.json"
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

    def register_compliance_program(
        self, program_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("program_id", "program_name", "framework", "owner_role"):
            if f not in program_data or not program_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if program_data["framework"] not in COMPLIANCE_FRAMEWORKS:
            return {"registered": False,
                       "error": f"invalid_framework:{program_data['framework']}"}
        records = self._load(self.programs_path,
                                "compliance_programs", ("program_id",))
        if any(r.get("program_id") == program_data["program_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_program_id"}
        record = {
            "program_id": program_data["program_id"],
            "program_name": program_data["program_name"],
            "framework": program_data["framework"],
            "owner_role": program_data["owner_role"],
            "scope": program_data.get("scope", ""),
            "regulatory_reference": (
                CBK_REGULATORY_REFERENCE
                if program_data["framework"] == "CBK_CYBERSECURITY"
                else program_data["framework"]
            ),
            "state": "PLANNED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PLANNED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.programs_path, records,
                          "compliance_programs", "program_id")
        return {"registered": ok, "program_id": program_data["program_id"]}

    def transition_program_state(
        self, program_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in PROGRAM_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.programs_path,
                                "compliance_programs", ("program_id",))
        for r in records:
            if r.get("program_id") == program_id:
                current = r.get("state", "PLANNED")
                allowed = ALLOWED_PROGRAM_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.programs_path, records,
                                  "compliance_programs", "program_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "program_not_found"}

    def register_control(
        self, control_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("control_id", "program_id", "control_name", "category"):
            if f not in control_data or not control_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if control_data["category"] not in CONTROL_CATEGORIES:
            return {"registered": False,
                       "error": f"invalid_category:{control_data['category']}"}
        # Verify program
        programs = self._load(self.programs_path,
                                  "compliance_programs", ("program_id",))
        if not any(p.get("program_id") == control_data["program_id"]
                       for p in programs):
            return {"registered": False, "error": "program_not_found"}
        records = self._load(self.controls_path,
                                "compliance_controls", ("control_id",))
        if any(r.get("control_id") == control_data["control_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_control_id"}
        record = {
            "control_id": control_data["control_id"],
            "program_id": control_data["program_id"],
            "control_name": control_data["control_name"],
            "category": control_data["category"],
            "description": control_data.get("description", ""),
            "owner_role": control_data.get("owner_role", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.controls_path, records,
                          "compliance_controls", "control_id")
        return {"registered": ok, "control_id": control_data["control_id"]}

    def record_audit_finding(
        self, finding_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("finding_id", "control_id", "severity", "description"):
            if f not in finding_data or not finding_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if finding_data["severity"] not in FINDING_SEVERITIES:
            return {"recorded": False,
                       "error": f"invalid_severity:{finding_data['severity']}"}
        records = self._load(self.findings_path,
                                "audit_findings", ("finding_id",))
        if any(r.get("finding_id") == finding_data["finding_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_finding_id"}
        sla_days = DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY[
            finding_data["severity"]
        ]
        sla_due = (
            datetime.utcnow() + timedelta(days=sla_days)
        ).isoformat()
        record = {
            "finding_id": finding_data["finding_id"],
            "control_id": finding_data["control_id"],
            "severity": finding_data["severity"],
            "description": finding_data["description"],
            "audit_source": finding_data.get("audit_source", ""),
            "sla_days": sla_days,
            "sla_due_at": sla_due,
            "state": "OPEN",
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "OPEN", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.findings_path, records,
                          "audit_findings", "finding_id")
        return {"recorded": ok, "finding_id": finding_data["finding_id"]}

    def transition_finding_state(
        self, finding_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in FINDING_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.findings_path,
                                "audit_findings", ("finding_id",))
        for r in records:
            if r.get("finding_id") == finding_id:
                current = r.get("state", "OPEN")
                allowed = ALLOWED_FINDING_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                now = datetime.utcnow().isoformat()
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": now, "reason": reason,
                })
                if new_state == "RESOLVED":
                    r["resolved_at"] = now
                ok = self._save(self.findings_path, records,
                                  "audit_findings", "finding_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "finding_not_found"}

    def register_certification(
        self, cert_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("certification_id", "framework", "issued_at",
                      "expires_at", "issuer"):
            if f not in cert_data or not cert_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if cert_data["framework"] not in COMPLIANCE_FRAMEWORKS:
            return {"registered": False,
                       "error": f"invalid_framework:{cert_data['framework']}"}
        records = self._load(self.certifications_path,
                                "certifications", ("certification_id",))
        if any(r.get("certification_id") == cert_data["certification_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_certification_id"}
        record = {
            "certification_id": cert_data["certification_id"],
            "framework": cert_data["framework"],
            "issued_at": cert_data["issued_at"],
            "expires_at": cert_data["expires_at"],
            "issuer": cert_data["issuer"],
            "scope": cert_data.get("scope", ""),
            "evidence_url": cert_data.get("evidence_url", ""),
            "state": "PENDING",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PENDING", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.certifications_path, records,
                          "certifications", "certification_id")
        return {"registered": ok,
                  "certification_id": cert_data["certification_id"]}

    def transition_certification_state(
        self, cert_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in CERTIFICATION_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.certifications_path,
                                "certifications", ("certification_id",))
        for r in records:
            if r.get("certification_id") == cert_id:
                current = r.get("state", "PENDING")
                allowed = ALLOWED_CERTIFICATION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.certifications_path, records,
                                  "certifications", "certification_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "certification_not_found"}

    def compliance_summary(
        self, framework: Optional[str] = None,
    ) -> Dict[str, Any]:
        programs = self._load(self.programs_path,
                                  "compliance_programs", ("program_id",))
        controls = self._load(self.controls_path,
                                  "compliance_controls", ("control_id",))
        findings = self._load(self.findings_path,
                                  "audit_findings", ("finding_id",))
        if framework:
            program_ids = {p["program_id"] for p in programs
                                if p.get("framework") == framework}
            programs = [p for p in programs
                              if p.get("framework") == framework]
            controls = [c for c in controls
                              if c.get("program_id") in program_ids]
            finding_control_ids = {c["control_id"] for c in controls}
            findings = [f for f in findings
                              if f.get("control_id") in finding_control_ids]
        active_programs = [p for p in programs
                                  if p.get("state") == "ACTIVE"]
        open_findings = [f for f in findings
                                if f.get("state") in (
                                    "OPEN", "REMEDIATION_IN_PROGRESS",
                                    "OVERDUE",
                                )]
        critical_open = sum(1 for f in open_findings
                                  if f.get("severity") == "CRITICAL")
        return {
            "framework": framework or "ALL",
            "total_programs": len(programs),
            "active_programs": len(active_programs),
            "total_controls": len(controls),
            "total_findings": len(findings),
            "open_findings": len(open_findings),
            "critical_open": critical_open,
            "regulatory_reference": (
                CBK_REGULATORY_REFERENCE
                if framework == "CBK_CYBERSECURITY"
                else (framework or "")
            ),
        }

    def expiring_certifications(
        self, within_days: int = 90,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.certifications_path,
                                "certifications", ("certification_id",))
        cutoff = (datetime.utcnow() + timedelta(days=within_days)).isoformat()
        active = [r for r in records
                       if r.get("state") in ("ACTIVE", "EXPIRING_SOON")]
        expiring = [r for r in active
                          if r.get("expires_at", "") <= cutoff]
        expiring.sort(key=lambda x: x.get("expires_at", ""))
        return expiring


def _self_test() -> None:
    import tempfile

    assert COMPLIANCE_FRAMEWORKS == (
        "CBK_CYBERSECURITY", "ISO_27001", "PCI_DSS", "SOC_2_TYPE_II",
    )
    assert ALLOWED_PROGRAM_TRANSITIONS["RETIRED"] == ()
    assert "ACCESS_CONTROL" in CONTROL_CATEGORIES
    assert "CRITICAL" in FINDING_SEVERITIES
    assert ALLOWED_FINDING_TRANSITIONS["RESOLVED"] == ()
    assert ALLOWED_CERTIFICATION_TRANSITIONS["REVOKED"] == ()
    assert CBK_REGULATORY_REFERENCE == "CBK Cybersecurity Guidance"
    assert DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY["CRITICAL"] == 7
    assert DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY["HIGH"] == 30

    with tempfile.TemporaryDirectory() as tmpdir:
        e = CBKComplianceEngine(
            programs_path=Path(tmpdir) / "p.json",
            controls_path=Path(tmpdir) / "c.json",
            findings_path=Path(tmpdir) / "f.json",
            certifications_path=Path(tmpdir) / "cert.json",
        )
        # Program
        r = e.register_compliance_program(
            {"program_id": "PROG-CBK",
             "program_name": "CBK Cybersecurity Compliance",
             "framework": "CBK_CYBERSECURITY",
             "owner_role": "CISO",
             "scope": "All banking systems"},
            actor="ciso", reason="annual",
        )
        assert r["registered"]
        # Invalid framework
        r = e.register_compliance_program(
            {"program_id": "X", "program_name": "Y",
             "framework": "WHATEVER", "owner_role": "Z"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Program transitions
        r = e.transition_program_state("PROG-CBK", "IN_PROGRESS",
                                              actor="ciso", reason="kicked off")
        assert r["transitioned"]
        r = e.transition_program_state("PROG-CBK", "ACTIVE",
                                              actor="ciso", reason="signed off")
        assert r["transitioned"]
        # ACTIVE → IN_PROGRESS allowed (re-baseline)
        r = e.transition_program_state("PROG-CBK", "IN_PROGRESS",
                                              actor="ciso",
                                              reason="re-baseline")
        assert r["transitioned"]
        r = e.transition_program_state("PROG-CBK", "ACTIVE",
                                              actor="ciso", reason="closed")
        assert r["transitioned"]
        r = e.transition_program_state("PROG-CBK", "RETIRED",
                                              actor="ciso", reason="superseded")
        assert r["transitioned"]
        # RETIRED is terminal
        r = e.transition_program_state("PROG-CBK", "ACTIVE",
                                              actor="ciso", reason="x")
        assert not r["transitioned"]

        # Control
        r = e.register_control(
            {"control_id": "CTL-AC-01",
             "program_id": "PROG-CBK",
             "control_name": "Privileged access review",
             "category": "ACCESS_CONTROL",
             "owner_role": "Security Manager"},
            actor="ciso", reason="initial",
        )
        assert r["registered"]
        # Invalid category
        r = e.register_control(
            {"control_id": "X", "program_id": "PROG-CBK",
             "control_name": "Y", "category": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Program not found
        r = e.register_control(
            {"control_id": "Y", "program_id": "NOPE",
             "control_name": "Z", "category": "ACCESS_CONTROL"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Audit finding
        r = e.record_audit_finding(
            {"finding_id": "FIND-001",
             "control_id": "CTL-AC-01",
             "severity": "HIGH",
             "description": "Quarterly review overdue",
             "audit_source": "Internal audit Q3 2026"},
            actor="audit-team",
        )
        assert r["recorded"]
        # Invalid severity
        r = e.record_audit_finding(
            {"finding_id": "X", "control_id": "Y",
             "severity": "WHATEVER", "description": "Z"},
            actor="x",
        )
        assert not r["recorded"]
        # Finding state machine
        r = e.transition_finding_state("FIND-001",
                                              "REMEDIATION_IN_PROGRESS",
                                              actor="security-team",
                                              reason="ticket opened")
        assert r["transitioned"]
        r = e.transition_finding_state("FIND-001", "RESOLVED",
                                              actor="security-team",
                                              reason="control restored")
        assert r["transitioned"]
        # RESOLVED is terminal
        r = e.transition_finding_state("FIND-001", "OPEN",
                                              actor="audit-team", reason="x")
        assert not r["transitioned"]

        # Certification
        future = (datetime.utcnow() + timedelta(days=300)).isoformat()
        past = (datetime.utcnow() - timedelta(days=10)).isoformat()
        r = e.register_certification(
            {"certification_id": "CERT-ISO-2026",
             "framework": "ISO_27001",
             "issued_at": past,
             "expires_at": future,
             "issuer": "BSI Group",
             "scope": "Banking platform"},
            actor="ciso", reason="annual cert",
        )
        assert r["registered"]
        # Cert state transitions
        r = e.transition_certification_state("CERT-ISO-2026", "ACTIVE",
                                                      actor="ciso",
                                                      reason="audit passed")
        assert r["transitioned"]
        r = e.transition_certification_state("CERT-ISO-2026",
                                                      "EXPIRING_SOON",
                                                      actor="ciso",
                                                      reason="60-day window")
        assert r["transitioned"]
        # REVOKED is terminal
        r = e.transition_certification_state("CERT-ISO-2026", "REVOKED",
                                                      actor="ciso",
                                                      reason="major finding")
        assert r["transitioned"]
        r = e.transition_certification_state("CERT-ISO-2026", "ACTIVE",
                                                      actor="ciso", reason="x")
        assert not r["transitioned"]

        # Summary
        s = e.compliance_summary()
        assert s["total_programs"] == 1
        assert s["total_controls"] == 1
        assert s["total_findings"] == 1
        assert s["open_findings"] == 0  # finding was resolved

        # Framework filter
        s = e.compliance_summary(framework="CBK_CYBERSECURITY")
        assert s["framework"] == "CBK_CYBERSECURITY"
        assert s["regulatory_reference"] == CBK_REGULATORY_REFERENCE

        # Expiring (REVOKED, so not in active query)
        # Add another active cert
        e.register_certification(
            {"certification_id": "CERT-PCI",
             "framework": "PCI_DSS",
             "issued_at": past,
             "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
             "issuer": "QSA Co",
             "scope": "Card systems"},
            actor="ciso", reason="card cert",
        )
        e.transition_certification_state("CERT-PCI", "ACTIVE",
                                                actor="ciso", reason="passed")
        exp = e.expiring_certifications(within_days=60)
        assert len(exp) == 1
        assert exp[0]["certification_id"] == "CERT-PCI"

    print("  ✅ it_cbk_compliance self-test PASS")


if __name__ == "__main__":
    _self_test()
