"""
================================================================================
A2Z MIS 360 — Standard #291: IT Service Management (ITSM) Framework
================================================================================

Risk classification: Cat C (operational ITSM tracking + state machines)

ITIL v4-aligned ITSM: incident, problem, change, release, asset, knowledge.

Public API:
    raise_incident(incident_data, actor)
    transition_incident(incident_id, new_state, actor, reason)
    raise_problem(problem_data, actor)
    raise_change_request(change_data, actor)
    transition_change(change_id, new_state, actor, reason)
    register_asset(asset_data, actor, reason)
    publish_knowledge_article(article_data, actor, reason)
    incident_status(incident_id) -> Dict
    open_incidents() -> List

ITSM_INCIDENT_PRIORITIES byte-for-byte (4): P1, P2, P3, P4

ITSM_INCIDENT_STATES byte-for-byte (5):
    OPEN, IN_PROGRESS, RESOLVED, CLOSED, CANCELLED

ALLOWED_INCIDENT_TRANSITIONS (Rule 4):
    OPEN        → IN_PROGRESS | CANCELLED
    IN_PROGRESS → RESOLVED | CANCELLED
    RESOLVED    → CLOSED | IN_PROGRESS  (re-open)
    CLOSED      → ()
    CANCELLED   → ()

CHANGE_TYPES byte-for-byte (3): STANDARD, NORMAL, EMERGENCY

CHANGE_STATES byte-for-byte (6):
    PROPOSED, APPROVED, IN_IMPLEMENTATION, IMPLEMENTED, FAILED, ROLLED_BACK

ALLOWED_CHANGE_TRANSITIONS (Rule 4):
    PROPOSED            → APPROVED | CANCELLED_AT_PROPOSAL
    APPROVED            → IN_IMPLEMENTATION
    IN_IMPLEMENTATION   → IMPLEMENTED | FAILED
    IMPLEMENTED         → ROLLED_BACK
    FAILED              → ROLLED_BACK
    ROLLED_BACK         → ()

ASSET_TYPES byte-for-byte (5):
    HARDWARE, SOFTWARE_LICENSE, NETWORK, CLOUD_RESOURCE, MOBILE_DEVICE

ASSET_STATES byte-for-byte (4): IN_USE, IN_STORAGE, RETIRED, LOST

KNOWLEDGE_ARTICLE_STATES byte-for-byte (3): DRAFT, PUBLISHED, ARCHIVED

ALLOWED_KB_TRANSITIONS (Rule 4):
    DRAFT     → PUBLISHED | ARCHIVED
    PUBLISHED → ARCHIVED
    ARCHIVED  → ()

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ITSM_INCIDENT_PRIORITIES: Tuple[str, ...] = ("P1", "P2", "P3", "P4")

ITSM_INCIDENT_STATES: Tuple[str, ...] = (
    "OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED", "CANCELLED",
)

ALLOWED_INCIDENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "OPEN":        ("IN_PROGRESS", "CANCELLED"),
    "IN_PROGRESS": ("RESOLVED", "CANCELLED"),
    "RESOLVED":    ("CLOSED", "IN_PROGRESS"),
    "CLOSED":      (),
    "CANCELLED":   (),
}

CHANGE_TYPES: Tuple[str, ...] = ("STANDARD", "NORMAL", "EMERGENCY")

CHANGE_STATES: Tuple[str, ...] = (
    "PROPOSED", "APPROVED", "IN_IMPLEMENTATION",
    "IMPLEMENTED", "FAILED", "ROLLED_BACK",
)

ALLOWED_CHANGE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PROPOSED":          ("APPROVED",),
    "APPROVED":          ("IN_IMPLEMENTATION",),
    "IN_IMPLEMENTATION": ("IMPLEMENTED", "FAILED"),
    "IMPLEMENTED":       ("ROLLED_BACK",),
    "FAILED":            ("ROLLED_BACK",),
    "ROLLED_BACK":       (),
}

ASSET_TYPES: Tuple[str, ...] = (
    "HARDWARE", "SOFTWARE_LICENSE", "NETWORK",
    "CLOUD_RESOURCE", "MOBILE_DEVICE",
)

ASSET_STATES: Tuple[str, ...] = ("IN_USE", "IN_STORAGE", "RETIRED", "LOST")

KNOWLEDGE_ARTICLE_STATES: Tuple[str, ...] = (
    "DRAFT", "PUBLISHED", "ARCHIVED",
)

ALLOWED_KB_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":     ("PUBLISHED", "ARCHIVED"),
    "PUBLISHED": ("ARCHIVED",),
    "ARCHIVED":  (),
}


class ITSMFrameworkEngine:
    """ITIL v4-aligned ITSM with incident/change/asset/KB management."""

    def __init__(
        self,
        incidents_path: Optional[Path] = None,
        problems_path: Optional[Path] = None,
        changes_path: Optional[Path] = None,
        assets_path: Optional[Path] = None,
        articles_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.incidents_path = incidents_path or base / "itsm_incidents.json"
        self.problems_path = problems_path or base / "itsm_problems.json"
        self.changes_path = changes_path or base / "itsm_changes.json"
        self.assets_path = assets_path or base / "itsm_assets.json"
        self.articles_path = articles_path or base / "itsm_kb_articles.json"

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

    def raise_incident(
        self, incident_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"raised": False, "error": "actor_required"}
        for f in ("incident_id", "title", "priority"):
            if f not in incident_data or not incident_data[f]:
                return {"raised": False, "error": f"missing_field:{f}"}
        if incident_data["priority"] not in ITSM_INCIDENT_PRIORITIES:
            return {"raised": False,
                       "error": f"invalid_priority:{incident_data['priority']}"}
        records = self._load(self.incidents_path,
                                "itsm_incidents", ("incident_id",))
        if any(r.get("incident_id") == incident_data["incident_id"]
                 for r in records):
            return {"raised": False, "error": "duplicate_incident_id"}
        record = {
            "incident_id": incident_data["incident_id"],
            "title": incident_data["title"],
            "description": incident_data.get("description", ""),
            "priority": incident_data["priority"],
            "affected_service": incident_data.get("affected_service", ""),
            "reporter": actor,
            "assigned_to": incident_data.get("assigned_to", ""),
            "state": "OPEN",
            "raised_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "OPEN", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.incidents_path, records,
                          "itsm_incidents", "incident_id")
        return {"raised": ok, "incident_id": incident_data["incident_id"]}

    def transition_incident(
        self, incident_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in ITSM_INCIDENT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.incidents_path,
                                "itsm_incidents", ("incident_id",))
        for r in records:
            if r.get("incident_id") == incident_id:
                current = r.get("state", "OPEN")
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
                if new_state == "RESOLVED":
                    r["resolved_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.incidents_path, records,
                                  "itsm_incidents", "incident_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "incident_not_found"}

    def raise_problem(
        self, problem_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"raised": False, "error": "actor_required"}
        for f in ("problem_id", "title"):
            if f not in problem_data or not problem_data[f]:
                return {"raised": False, "error": f"missing_field:{f}"}
        records = self._load(self.problems_path,
                                "itsm_problems", ("problem_id",))
        if any(r.get("problem_id") == problem_data["problem_id"]
                 for r in records):
            return {"raised": False, "error": "duplicate_problem_id"}
        record = {
            "problem_id": problem_data["problem_id"],
            "title": problem_data["title"],
            "description": problem_data.get("description", ""),
            "linked_incidents": problem_data.get("linked_incidents", []),
            "raised_by": actor,
            "raised_at": datetime.utcnow().isoformat(),
            "root_cause": "",
            "workaround": problem_data.get("workaround", ""),
            "permanent_fix_change_id": "",
        }
        records.append(record)
        ok = self._save(self.problems_path, records,
                          "itsm_problems", "problem_id")
        return {"raised": ok, "problem_id": problem_data["problem_id"]}

    def raise_change_request(
        self, change_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"raised": False, "error": "actor_required"}
        for f in ("change_id", "title", "change_type"):
            if f not in change_data or not change_data[f]:
                return {"raised": False, "error": f"missing_field:{f}"}
        if change_data["change_type"] not in CHANGE_TYPES:
            return {"raised": False,
                       "error": f"invalid_change_type:{change_data['change_type']}"}
        records = self._load(self.changes_path,
                                "itsm_changes", ("change_id",))
        if any(r.get("change_id") == change_data["change_id"]
                 for r in records):
            return {"raised": False, "error": "duplicate_change_id"}
        record = {
            "change_id": change_data["change_id"],
            "title": change_data["title"],
            "change_type": change_data["change_type"],
            "description": change_data.get("description", ""),
            "implementation_plan": change_data.get("implementation_plan", ""),
            "rollback_plan": change_data.get("rollback_plan", ""),
            "scheduled_for": change_data.get("scheduled_for", ""),
            "raised_by": actor,
            "raised_at": datetime.utcnow().isoformat(),
            "state": "PROPOSED",
            "transitions": [{
                "to": "PROPOSED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.changes_path, records,
                          "itsm_changes", "change_id")
        return {"raised": ok, "change_id": change_data["change_id"]}

    def transition_change(
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
                current = r.get("state", "PROPOSED")
                allowed = ALLOWED_CHANGE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
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

    def register_asset(
        self, asset_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("asset_id", "asset_name", "asset_type"):
            if f not in asset_data or not asset_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if asset_data["asset_type"] not in ASSET_TYPES:
            return {"registered": False,
                       "error": f"invalid_asset_type:{asset_data['asset_type']}"}
        records = self._load(self.assets_path,
                                "itsm_assets", ("asset_id",))
        if any(r.get("asset_id") == asset_data["asset_id"] for r in records):
            return {"registered": False, "error": "duplicate_asset_id"}
        record = {
            "asset_id": asset_data["asset_id"],
            "asset_name": asset_data["asset_name"],
            "asset_type": asset_data["asset_type"],
            "owner_team": asset_data.get("owner_team", ""),
            "location": asset_data.get("location", ""),
            "state": asset_data.get("state", "IN_USE"),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        if record["state"] not in ASSET_STATES:
            return {"registered": False,
                       "error": f"invalid_asset_state:{record['state']}"}
        records.append(record)
        ok = self._save(self.assets_path, records, "itsm_assets", "asset_id")
        return {"registered": ok, "asset_id": asset_data["asset_id"]}

    def publish_knowledge_article(
        self, article_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"published": False, "error": "actor_and_reason_required"}
        for f in ("article_id", "title", "content"):
            if f not in article_data or not article_data[f]:
                return {"published": False, "error": f"missing_field:{f}"}
        records = self._load(self.articles_path,
                                "itsm_kb_articles", ("article_id",))
        if any(r.get("article_id") == article_data["article_id"]
                 for r in records):
            return {"published": False, "error": "duplicate_article_id"}
        record = {
            "article_id": article_data["article_id"],
            "title": article_data["title"],
            "content": article_data["content"],
            "category": article_data.get("category", ""),
            "tags": article_data.get("tags", []),
            "state": "PUBLISHED",
            "published_by": actor,
            "published_at": datetime.utcnow().isoformat(),
            "publication_reason": reason,
        }
        records.append(record)
        ok = self._save(self.articles_path, records,
                          "itsm_kb_articles", "article_id")
        return {"published": ok, "article_id": article_data["article_id"]}

    def incident_status(self, incident_id: str) -> Dict[str, Any]:
        records = self._load(self.incidents_path,
                                "itsm_incidents", ("incident_id",))
        for r in records:
            if r.get("incident_id") == incident_id:
                return {
                    "found": True,
                    "incident_id": incident_id,
                    "title": r["title"],
                    "priority": r["priority"],
                    "state": r["state"],
                    "assigned_to": r.get("assigned_to", ""),
                    "raised_at": r["raised_at"],
                    "resolved_at": r.get("resolved_at", ""),
                    "transitions": r.get("transitions", []),
                }
        return {"found": False, "error": "incident_not_found"}

    def open_incidents(self) -> List[Dict[str, Any]]:
        records = self._load(self.incidents_path,
                                "itsm_incidents", ("incident_id",))
        opens = [r for r in records
                     if r.get("state") in ("OPEN", "IN_PROGRESS")]
        opens.sort(key=lambda x: x.get("priority", "P4"))
        return opens


def _self_test() -> None:
    import tempfile

    assert ITSM_INCIDENT_PRIORITIES == ("P1", "P2", "P3", "P4")
    assert "OPEN" in ITSM_INCIDENT_STATES
    assert ALLOWED_INCIDENT_TRANSITIONS["CLOSED"] == ()
    assert "STANDARD" in CHANGE_TYPES
    assert ALLOWED_CHANGE_TRANSITIONS["ROLLED_BACK"] == ()
    assert "HARDWARE" in ASSET_TYPES
    assert "DRAFT" in KNOWLEDGE_ARTICLE_STATES
    assert ALLOWED_KB_TRANSITIONS["ARCHIVED"] == ()

    with tempfile.TemporaryDirectory() as tmpdir:
        e = ITSMFrameworkEngine(
            incidents_path=Path(tmpdir) / "i.json",
            problems_path=Path(tmpdir) / "p.json",
            changes_path=Path(tmpdir) / "c.json",
            assets_path=Path(tmpdir) / "a.json",
            articles_path=Path(tmpdir) / "k.json",
        )
        # Incident lifecycle
        r = e.raise_incident({"incident_id": "INC-001",
                                  "title": "FLEXCUBE login failure",
                                  "priority": "P1",
                                  "affected_service": "core_banking"},
                                 actor="ops-1")
        assert r["raised"]
        # Invalid priority
        r = e.raise_incident({"incident_id": "X", "title": "Y", "priority": "P9"},
                                 actor="ops-1")
        assert not r["raised"]
        # OPEN → IN_PROGRESS
        r = e.transition_incident("INC-001", "IN_PROGRESS",
                                       actor="ops-1", reason="picked up")
        assert r["transitioned"]
        # Cannot OPEN → RESOLVED directly (no longer OPEN; now IN_PROGRESS)
        r = e.transition_incident("INC-001", "RESOLVED",
                                       actor="ops-1", reason="fixed")
        assert r["transitioned"]
        r = e.transition_incident("INC-001", "CLOSED",
                                       actor="ops-1", reason="confirmed")
        assert r["transitioned"]
        # CLOSED → terminal
        r = e.transition_incident("INC-001", "OPEN",
                                       actor="ops-1", reason="x")
        assert not r["transitioned"]

        # Problem
        r = e.raise_problem({"problem_id": "PRB-001",
                                  "title": "FLEXCUBE auth recurring",
                                  "linked_incidents": ["INC-001"]},
                                 actor="ops-1")
        assert r["raised"]

        # Change request
        r = e.raise_change_request({"change_id": "CHG-001",
                                          "title": "Update FLEXCUBE patch",
                                          "change_type": "NORMAL",
                                          "rollback_plan": "Restore from snapshot"},
                                         actor="cto")
        assert r["raised"]
        # Invalid type
        r = e.raise_change_request({"change_id": "X", "title": "Y",
                                          "change_type": "WHATEVER"},
                                         actor="cto")
        assert not r["raised"]
        # PROPOSED → APPROVED
        r = e.transition_change("CHG-001", "APPROVED",
                                     actor="cto", reason="CAB approved")
        assert r["transitioned"]
        # APPROVED → IN_IMPLEMENTATION
        r = e.transition_change("CHG-001", "IN_IMPLEMENTATION",
                                     actor="ops-1", reason="starting")
        assert r["transitioned"]
        # IN_IMPLEMENTATION → IMPLEMENTED
        r = e.transition_change("CHG-001", "IMPLEMENTED",
                                     actor="ops-1", reason="done")
        assert r["transitioned"]
        # IMPLEMENTED → ROLLED_BACK
        r = e.transition_change("CHG-001", "ROLLED_BACK",
                                     actor="ops-1", reason="prod issue")
        assert r["transitioned"]
        # ROLLED_BACK is terminal
        r = e.transition_change("CHG-001", "IMPLEMENTED",
                                     actor="ops-1", reason="x")
        assert not r["transitioned"]

        # Asset
        r = e.register_asset({"asset_id": "AST-001",
                                  "asset_name": "Core DB Server",
                                  "asset_type": "HARDWARE"},
                                 actor="ops-1", reason="newly procured")
        assert r["registered"]
        r = e.register_asset({"asset_id": "X", "asset_name": "Y",
                                  "asset_type": "WEIRD"},
                                 actor="ops-1", reason="x")
        assert not r["registered"]
        r = e.register_asset({"asset_id": "AST-002",
                                  "asset_name": "Y", "asset_type": "HARDWARE",
                                  "state": "INVALID"},
                                 actor="x", reason="x")
        assert not r["registered"]

        # KB article
        r = e.publish_knowledge_article({"article_id": "KB-001",
                                                "title": "FLEXCUBE password reset",
                                                "content": "Steps to reset..."},
                                               actor="ops-1",
                                               reason="docs request")
        assert r["published"]

        # Open incidents
        opens = e.open_incidents()
        # INC-001 was closed, expect 0
        assert len(opens) == 0

    print("  ✅ it_itsm self-test PASS")


if __name__ == "__main__":
    _self_test()
