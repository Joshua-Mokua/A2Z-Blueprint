"""
================================================================================
A2Z MIS 360 — Standard #291: IT Service Management (ITSM) Framework
================================================================================

Risk classification: Cat C (operational ITSM lifecycle tracking)

ITIL-aligned ITSM: incident, problem, change, release, asset, knowledge
management. ServiceNow / Jira Service Management integration patterns.

Public API:
    register_incident(incident_data, actor)
    transition_incident_state(incident_id, new_state, actor, reason)
    register_problem(problem_data, actor)
    link_incident_to_problem(incident_id, problem_id, actor, reason)
    register_change(change_data, actor)
    record_change_approval(change_id, approver_role, decision, actor)
    transition_change_state(change_id, new_state, actor, reason)
    register_release(release_data, actor)
    register_asset(asset_data, actor)
    transition_asset_state(asset_id, new_state, actor, reason)
    register_kb_article(article_data, actor)
    itsm_dashboard() -> Dict (open incidents/changes by priority + SLA breach)

ITIL_INCIDENT_PRIORITIES byte-for-byte (4): P1, P2, P3, P4

INCIDENT_STATES byte-for-byte (6):
    NEW, ASSIGNED, IN_PROGRESS, RESOLVED, CLOSED, CANCELLED

ALLOWED_INCIDENT_TRANSITIONS (Rule 4):
    NEW         → ASSIGNED | CANCELLED
    ASSIGNED    → IN_PROGRESS | CANCELLED
    IN_PROGRESS → RESOLVED | ASSIGNED | CANCELLED
    RESOLVED    → CLOSED | IN_PROGRESS
    CLOSED      → ()
    CANCELLED   → ()

PROBLEM_STATES byte-for-byte (5):
    NEW, INVESTIGATING, KNOWN_ERROR, RESOLVED, CLOSED

ALLOWED_PROBLEM_TRANSITIONS (Rule 4):
    NEW           → INVESTIGATING
    INVESTIGATING → KNOWN_ERROR | RESOLVED
    KNOWN_ERROR   → RESOLVED
    RESOLVED      → CLOSED
    CLOSED        → ()

CHANGE_TYPES byte-for-byte (3): STANDARD, NORMAL, EMERGENCY

CHANGE_STATES byte-for-byte (7):
    DRAFT, SUBMITTED, IN_APPROVAL, APPROVED, IN_IMPLEMENTATION,
    COMPLETED, REJECTED

ALLOWED_CHANGE_TRANSITIONS (Rule 4):
    DRAFT              → SUBMITTED
    SUBMITTED          → IN_APPROVAL | REJECTED
    IN_APPROVAL        → APPROVED | REJECTED
    APPROVED           → IN_IMPLEMENTATION
    IN_IMPLEMENTATION  → COMPLETED
    COMPLETED          → ()
    REJECTED           → ()

CAB_APPROVERS byte-for-byte (4): IT_HEAD, SECURITY, OPS_HEAD, BUSINESS_OWNER
CAB_DECISIONS byte-for-byte (3): APPROVE, REJECT, REQUEST_INFO

ASSET_STATES byte-for-byte (5):
    IN_STOCK, IN_USE, IN_MAINTENANCE, RETIRED, DISPOSED

ALLOWED_ASSET_TRANSITIONS (Rule 4):
    IN_STOCK        → IN_USE | DISPOSED
    IN_USE          → IN_MAINTENANCE | RETIRED
    IN_MAINTENANCE  → IN_USE | RETIRED
    RETIRED         → DISPOSED
    DISPOSED        → ()

ASSET_CATEGORIES byte-for-byte (6):
    SERVER, NETWORK, ENDPOINT, DATABASE, APPLICATION, SECURITY

SLA_TARGETS_HOURS byte-for-byte (P1=1, P2=4, P3=24, P4=72)

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ITIL_INCIDENT_PRIORITIES: Tuple[str, ...] = ("P1", "P2", "P3", "P4")

INCIDENT_STATES: Tuple[str, ...] = (
    "NEW", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "CANCELLED",
)

ALLOWED_INCIDENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "NEW":         ("ASSIGNED", "CANCELLED"),
    "ASSIGNED":    ("IN_PROGRESS", "CANCELLED"),
    "IN_PROGRESS": ("RESOLVED", "ASSIGNED", "CANCELLED"),
    "RESOLVED":    ("CLOSED", "IN_PROGRESS"),
    "CLOSED":      (),
    "CANCELLED":   (),
}

PROBLEM_STATES: Tuple[str, ...] = (
    "NEW", "INVESTIGATING", "KNOWN_ERROR", "RESOLVED", "CLOSED",
)

ALLOWED_PROBLEM_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "NEW":           ("INVESTIGATING",),
    "INVESTIGATING": ("KNOWN_ERROR", "RESOLVED"),
    "KNOWN_ERROR":   ("RESOLVED",),
    "RESOLVED":      ("CLOSED",),
    "CLOSED":        (),
}

CHANGE_TYPES: Tuple[str, ...] = ("STANDARD", "NORMAL", "EMERGENCY")

CHANGE_STATES: Tuple[str, ...] = (
    "DRAFT", "SUBMITTED", "IN_APPROVAL", "APPROVED",
    "IN_IMPLEMENTATION", "COMPLETED", "REJECTED",
)

ALLOWED_CHANGE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":              ("SUBMITTED",),
    "SUBMITTED":          ("IN_APPROVAL", "REJECTED"),
    "IN_APPROVAL":        ("APPROVED", "REJECTED"),
    "APPROVED":           ("IN_IMPLEMENTATION",),
    "IN_IMPLEMENTATION":  ("COMPLETED",),
    "COMPLETED":          (),
    "REJECTED":           (),
}

CAB_APPROVERS: Tuple[str, ...] = (
    "IT_HEAD", "SECURITY", "OPS_HEAD", "BUSINESS_OWNER",
)

CAB_DECISIONS: Tuple[str, ...] = ("APPROVE", "REJECT", "REQUEST_INFO")

ASSET_STATES: Tuple[str, ...] = (
    "IN_STOCK", "IN_USE", "IN_MAINTENANCE", "RETIRED", "DISPOSED",
)

ALLOWED_ASSET_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "IN_STOCK":       ("IN_USE", "DISPOSED"),
    "IN_USE":         ("IN_MAINTENANCE", "RETIRED"),
    "IN_MAINTENANCE": ("IN_USE", "RETIRED"),
    "RETIRED":        ("DISPOSED",),
    "DISPOSED":       (),
}

ASSET_CATEGORIES: Tuple[str, ...] = (
    "SERVER", "NETWORK", "ENDPOINT", "DATABASE", "APPLICATION", "SECURITY",
)

SLA_TARGETS_HOURS: Dict[str, int] = {"P1": 1, "P2": 4, "P3": 24, "P4": 72}


class ITSMFrameworkEngine:
    """ITIL-aligned ITSM lifecycle: incident/problem/change/release/asset/KB."""

    def __init__(
        self,
        incidents_path: Optional[Path] = None,
        problems_path: Optional[Path] = None,
        changes_path: Optional[Path] = None,
        cab_approvals_path: Optional[Path] = None,
        releases_path: Optional[Path] = None,
        assets_path: Optional[Path] = None,
        kb_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.incidents_path = incidents_path or base / "itsm_incidents.json"
        self.problems_path = problems_path or base / "itsm_problems.json"
        self.changes_path = changes_path or base / "itsm_changes.json"
        self.cab_approvals_path = cab_approvals_path or base / "itsm_cab_approvals.json"
        self.releases_path = releases_path or base / "itsm_releases.json"
        self.assets_path = assets_path or base / "itsm_assets.json"
        self.kb_path = kb_path or base / "itsm_kb_articles.json"

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

    # ---- Incidents ----
    def register_incident(
        self, incident_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("incident_id", "title", "priority", "category"):
            if f not in incident_data or not incident_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if incident_data["priority"] not in ITIL_INCIDENT_PRIORITIES:
            return {"registered": False,
                       "error": f"invalid_priority:{incident_data['priority']}"}
        records = self._load(self.incidents_path,
                                "itsm_incidents", ("incident_id",))
        if any(r.get("incident_id") == incident_data["incident_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_incident_id"}
        sla_due_hours = SLA_TARGETS_HOURS[incident_data["priority"]]
        record = {
            "incident_id": incident_data["incident_id"],
            "title": incident_data["title"],
            "description": incident_data.get("description", ""),
            "priority": incident_data["priority"],
            "category": incident_data["category"],
            "affected_service": incident_data.get("affected_service", ""),
            "reported_by": incident_data.get("reported_by", actor),
            "assignee": incident_data.get("assignee", ""),
            "state": "NEW",
            "linked_problem_id": None,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "sla_due_hours": sla_due_hours,
            "transitions": [{
                "to": "NEW", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.incidents_path, records,
                          "itsm_incidents", "incident_id")
        return {"registered": ok,
                  "incident_id": incident_data["incident_id"],
                  "sla_due_hours": sla_due_hours}

    def transition_incident_state(
        self, incident_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in INCIDENT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.incidents_path,
                                "itsm_incidents", ("incident_id",))
        for r in records:
            if r.get("incident_id") == incident_id:
                current = r.get("state", "NEW")
                allowed = ALLOWED_INCIDENT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.incidents_path, records,
                                  "itsm_incidents", "incident_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "incident_not_found"}

    # ---- Problems ----
    def register_problem(
        self, problem_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("problem_id", "title", "category"):
            if f not in problem_data or not problem_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.problems_path,
                                "itsm_problems", ("problem_id",))
        if any(r.get("problem_id") == problem_data["problem_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_problem_id"}
        record = {
            "problem_id": problem_data["problem_id"],
            "title": problem_data["title"],
            "category": problem_data["category"],
            "description": problem_data.get("description", ""),
            "linked_incidents": [],
            "root_cause": "",
            "workaround": "",
            "state": "NEW",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "NEW", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.problems_path, records,
                          "itsm_problems", "problem_id")
        return {"registered": ok,
                  "problem_id": problem_data["problem_id"]}

    def link_incident_to_problem(
        self, incident_id: str, problem_id: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"linked": False, "error": "actor_and_reason_required"}
        # Verify both exist
        incidents = self._load(self.incidents_path,
                                     "itsm_incidents", ("incident_id",))
        problems = self._load(self.problems_path,
                                    "itsm_problems", ("problem_id",))
        if not any(i.get("incident_id") == incident_id for i in incidents):
            return {"linked": False, "error": "incident_not_found"}
        if not any(p.get("problem_id") == problem_id for p in problems):
            return {"linked": False, "error": "problem_not_found"}
        for i in incidents:
            if i["incident_id"] == incident_id:
                i["linked_problem_id"] = problem_id
                break
        for p in problems:
            if p["problem_id"] == problem_id:
                if incident_id not in p.get("linked_incidents", []):
                    p.setdefault("linked_incidents", []).append(incident_id)
                break
        self._save(self.incidents_path, incidents,
                     "itsm_incidents", "incident_id")
        ok = self._save(self.problems_path, problems,
                          "itsm_problems", "problem_id")
        return {"linked": ok}

    # ---- Changes ----
    def register_change(
        self, change_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("change_id", "title", "change_type", "scheduled_for"):
            if f not in change_data or not change_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if change_data["change_type"] not in CHANGE_TYPES:
            return {"registered": False,
                       "error": f"invalid_change_type:{change_data['change_type']}"}
        records = self._load(self.changes_path,
                                "itsm_changes", ("change_id",))
        if any(r.get("change_id") == change_data["change_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_change_id"}
        record = {
            "change_id": change_data["change_id"],
            "title": change_data["title"],
            "description": change_data.get("description", ""),
            "change_type": change_data["change_type"],
            "scheduled_for": change_data["scheduled_for"],
            "implementer": change_data.get("implementer", actor),
            "rollback_plan": change_data.get("rollback_plan", ""),
            "state": "DRAFT",
            "approvals": [],
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.changes_path, records,
                          "itsm_changes", "change_id")
        return {"registered": ok,
                  "change_id": change_data["change_id"]}

    def record_change_approval(
        self, change_id: str, approver_role: str,
        decision: str, actor: str, reason: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if approver_role not in CAB_APPROVERS:
            return {"recorded": False,
                       "error": f"invalid_approver_role:{approver_role}"}
        if decision not in CAB_DECISIONS:
            return {"recorded": False,
                       "error": f"invalid_decision:{decision}"}
        # Verify change is in IN_APPROVAL state
        changes = self._load(self.changes_path,
                                "itsm_changes", ("change_id",))
        change = next((c for c in changes
                            if c.get("change_id") == change_id), None)
        if change is None:
            return {"recorded": False, "error": "change_not_found"}
        if change["state"] != "IN_APPROVAL":
            return {"recorded": False,
                       "error": f"change_not_in_approval:{change['state']}"}
        # Add approval (one per role; reject duplicate)
        if any(a.get("approver_role") == approver_role
                  for a in change.get("approvals", [])):
            return {"recorded": False,
                       "error": f"role_already_approved:{approver_role}"}
        change.setdefault("approvals", []).append({
            "approver_role": approver_role,
            "decision": decision,
            "actor": actor,
            "at": datetime.utcnow().isoformat(),
            "reason": reason,
        })
        ok = self._save(self.changes_path, changes,
                          "itsm_changes", "change_id")
        return {"recorded": ok,
                  "approver_role": approver_role,
                  "decision": decision}

    def transition_change_state(
        self, change_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in CHANGE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.changes_path,
                                "itsm_changes", ("change_id",))
        for r in records:
            if r.get("change_id") == change_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_CHANGE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                # Approvals required for APPROVED state (NORMAL/EMERGENCY)
                if new_state == "APPROVED" and r["change_type"] != "STANDARD":
                    approvals = [a for a in r.get("approvals", [])
                                       if a["decision"] == "APPROVE"]
                    if len(approvals) < 2:
                        return {"transitioned": False,
                                   "error": "insufficient_cab_approvals"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.changes_path, records,
                                  "itsm_changes", "change_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "change_not_found"}

    # ---- Releases ----
    def register_release(
        self, release_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("release_id", "release_name", "version", "scheduled_for"):
            if f not in release_data or not release_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.releases_path,
                                "itsm_releases", ("release_id",))
        if any(r.get("release_id") == release_data["release_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_release_id"}
        record = {
            "release_id": release_data["release_id"],
            "release_name": release_data["release_name"],
            "version": release_data["version"],
            "scheduled_for": release_data["scheduled_for"],
            "linked_changes": release_data.get("linked_changes", []),
            "release_notes": release_data.get("release_notes", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.releases_path, records,
                          "itsm_releases", "release_id")
        return {"registered": ok,
                  "release_id": release_data["release_id"]}

    # ---- Assets (CMDB) ----
    def register_asset(
        self, asset_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("asset_id", "asset_name", "category"):
            if f not in asset_data or not asset_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if asset_data["category"] not in ASSET_CATEGORIES:
            return {"registered": False,
                       "error": f"invalid_category:{asset_data['category']}"}
        records = self._load(self.assets_path,
                                "itsm_assets", ("asset_id",))
        if any(r.get("asset_id") == asset_data["asset_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_asset_id"}
        record = {
            "asset_id": asset_data["asset_id"],
            "asset_name": asset_data["asset_name"],
            "category": asset_data["category"],
            "description": asset_data.get("description", ""),
            "owner_role": asset_data.get("owner_role", ""),
            "location": asset_data.get("location", ""),
            "state": "IN_STOCK",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "IN_STOCK", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.assets_path, records,
                          "itsm_assets", "asset_id")
        return {"registered": ok, "asset_id": asset_data["asset_id"]}

    def transition_asset_state(
        self, asset_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in ASSET_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.assets_path,
                                "itsm_assets", ("asset_id",))
        for r in records:
            if r.get("asset_id") == asset_id:
                current = r.get("state", "IN_STOCK")
                allowed = ALLOWED_ASSET_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.assets_path, records,
                                  "itsm_assets", "asset_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "asset_not_found"}

    # ---- Knowledge Base ----
    def register_kb_article(
        self, article_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("article_id", "title", "body"):
            if f not in article_data or not article_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.kb_path,
                                "itsm_kb_articles", ("article_id",))
        if any(r.get("article_id") == article_data["article_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_article_id"}
        record = {
            "article_id": article_data["article_id"],
            "title": article_data["title"],
            "body": article_data["body"],
            "category": article_data.get("category", "general"),
            "linked_problem_id": article_data.get("linked_problem_id"),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.kb_path, records,
                          "itsm_kb_articles", "article_id")
        return {"registered": ok,
                  "article_id": article_data["article_id"]}

    # ---- Dashboard ----
    def itsm_dashboard(self) -> Dict[str, Any]:
        incidents = self._load(self.incidents_path,
                                     "itsm_incidents", ("incident_id",))
        changes = self._load(self.changes_path,
                                   "itsm_changes", ("change_id",))
        problems = self._load(self.problems_path,
                                    "itsm_problems", ("problem_id",))
        assets = self._load(self.assets_path,
                                  "itsm_assets", ("asset_id",))
        open_incidents = [i for i in incidents
                                if i["state"] not in ("CLOSED", "CANCELLED")]
        priority_dist = {p: 0 for p in ITIL_INCIDENT_PRIORITIES}
        for i in open_incidents:
            priority_dist[i.get("priority", "P4")] += 1
        # SLA breach computation: now > registered_at + sla_due_hours
        sla_breaches = 0
        now = datetime.utcnow()
        for i in open_incidents:
            try:
                reg = datetime.fromisoformat(i["registered_at"])
                due = reg + timedelta(hours=i.get("sla_due_hours", 24))
                if now > due:
                    sla_breaches += 1
            except Exception:
                pass
        open_changes = [c for c in changes
                              if c["state"] not in ("COMPLETED", "REJECTED")]
        in_use_assets = [a for a in assets if a["state"] == "IN_USE"]
        return {
            "open_incidents": len(open_incidents),
            "incident_priority_distribution": priority_dist,
            "sla_breaches": sla_breaches,
            "open_problems": len([p for p in problems
                                          if p["state"] != "CLOSED"]),
            "open_changes": len(open_changes),
            "in_use_assets": len(in_use_assets),
            "total_assets": len(assets),
        }


def _self_test() -> None:
    import tempfile

    assert ITIL_INCIDENT_PRIORITIES == ("P1", "P2", "P3", "P4")
    assert SLA_TARGETS_HOURS == {"P1": 1, "P2": 4, "P3": 24, "P4": 72}
    assert ALLOWED_INCIDENT_TRANSITIONS["CLOSED"] == ()
    assert ALLOWED_CHANGE_TRANSITIONS["COMPLETED"] == ()
    assert ALLOWED_ASSET_TRANSITIONS["DISPOSED"] == ()
    assert "EMERGENCY" in CHANGE_TYPES

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ITSMFrameworkEngine(
            incidents_path=Path(tmpdir) / "i.json",
            problems_path=Path(tmpdir) / "p.json",
            changes_path=Path(tmpdir) / "c.json",
            cab_approvals_path=Path(tmpdir) / "ca.json",
            releases_path=Path(tmpdir) / "r.json",
            assets_path=Path(tmpdir) / "a.json",
            kb_path=Path(tmpdir) / "kb.json",
        )
        # Test 1: incident
        r = engine.register_incident(
            {"incident_id": "INC-1", "title": "DB down",
             "priority": "P1", "category": "DATABASE"},
            actor="ops",
        )
        assert r["registered"]
        assert r["sla_due_hours"] == 1
        # Test 2: invalid priority
        r = engine.register_incident(
            {"incident_id": "INC-X", "title": "X",
             "priority": "P5", "category": "X"},
            actor="x",
        )
        assert not r["registered"]
        # Test 3: incident transition
        r = engine.transition_incident_state(
            "INC-1", "ASSIGNED", actor="ops", reason="assigned to dba",
        )
        assert r["transitioned"]
        # Test 4: invalid transition
        r = engine.transition_incident_state(
            "INC-1", "CLOSED", actor="ops", reason="x",
        )
        assert not r["transitioned"]
        # Test 5: problem + link
        r = engine.register_problem(
            {"problem_id": "PRB-1", "title": "DB connection pool exhaustion",
             "category": "DATABASE"},
            actor="ops",
        )
        assert r["registered"]
        r = engine.link_incident_to_problem(
            "INC-1", "PRB-1", actor="ops",
            reason="root cause traced to pool exhaustion",
        )
        assert r["linked"]
        # Test 6: link missing → fail
        r = engine.link_incident_to_problem(
            "INC-Z", "PRB-1", actor="ops", reason="x",
        )
        assert not r["linked"]
        # Test 7: change
        r = engine.register_change(
            {"change_id": "CHG-1", "title": "Increase pool size",
             "change_type": "NORMAL",
             "scheduled_for": "2026-05-15T20:00:00"},
            actor="ops",
        )
        assert r["registered"]
        # Test 8: invalid change type
        r = engine.register_change(
            {"change_id": "X", "title": "X", "change_type": "URGENT",
             "scheduled_for": "2026"},
            actor="x",
        )
        assert not r["registered"]
        # Test 9: change → submitted → in_approval
        engine.transition_change_state(
            "CHG-1", "SUBMITTED", actor="ops", reason="ready for review",
        )
        engine.transition_change_state(
            "CHG-1", "IN_APPROVAL", actor="cab", reason="cab review",
        )
        # Test 10: cannot promote to APPROVED with insufficient approvals
        r = engine.transition_change_state(
            "CHG-1", "APPROVED", actor="cab", reason="x",
        )
        assert not r["transitioned"]
        # Test 11: record approvals
        r = engine.record_change_approval(
            "CHG-1", "IT_HEAD", "APPROVE", actor="it_head",
        )
        assert r["recorded"]
        # Test 12: duplicate approval rejected
        r = engine.record_change_approval(
            "CHG-1", "IT_HEAD", "APPROVE", actor="it_head",
        )
        assert not r["recorded"]
        # Test 13: invalid approver
        r = engine.record_change_approval(
            "CHG-1", "RANDOM_ROLE", "APPROVE", actor="x",
        )
        assert not r["recorded"]
        # Test 14: 2nd approval + APPROVED transition
        engine.record_change_approval(
            "CHG-1", "OPS_HEAD", "APPROVE", actor="ops_head",
        )
        r = engine.transition_change_state(
            "CHG-1", "APPROVED", actor="cab", reason="2 approvals received",
        )
        assert r["transitioned"]
        # Test 15: STANDARD changes don't need 2 approvals
        engine.register_change(
            {"change_id": "CHG-STD", "title": "Standard restart",
             "change_type": "STANDARD",
             "scheduled_for": "2026-05-12T01:00:00"},
            actor="ops",
        )
        engine.transition_change_state(
            "CHG-STD", "SUBMITTED", actor="ops", reason="r",
        )
        engine.transition_change_state(
            "CHG-STD", "IN_APPROVAL", actor="cab", reason="r",
        )
        r = engine.transition_change_state(
            "CHG-STD", "APPROVED", actor="cab", reason="standard",
        )
        assert r["transitioned"]
        # Test 16: assets
        r = engine.register_asset(
            {"asset_id": "AST-DB1", "asset_name": "PG primary",
             "category": "DATABASE"},
            actor="ops",
        )
        assert r["registered"]
        # Test 17: invalid category
        r = engine.register_asset(
            {"asset_id": "X", "asset_name": "X", "category": "INVALID"},
            actor="x",
        )
        assert not r["registered"]
        # Test 18: asset transitions
        r = engine.transition_asset_state(
            "AST-DB1", "IN_USE", actor="ops", reason="deployed",
        )
        assert r["transitioned"]
        # Test 19: KB
        r = engine.register_kb_article(
            {"article_id": "KB-1", "title": "DB pool exhaustion runbook",
             "body": "Step 1: ...", "linked_problem_id": "PRB-1"},
            actor="ops",
        )
        assert r["registered"]
        # Test 20: dashboard
        d = engine.itsm_dashboard()
        assert d["open_incidents"] >= 1
        assert d["incident_priority_distribution"]["P1"] >= 1
        assert d["in_use_assets"] >= 1

    print("  ✅ itsm_framework self-test PASS")


if __name__ == "__main__":
    _self_test()
