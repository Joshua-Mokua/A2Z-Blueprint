"""
================================================================================
A2Z MIS 360 — Standard #318: Strategic Initiative Tracking + BSC Linkage
================================================================================

Risk classification: Cat C (initiative milestone tracking + KPI linkage)

Strategic initiative tracking: milestones, owner, RAG status, dependencies,
KPI linkage to BSC. Composes foundation initiative_* engines.

Public API:
    register_initiative(initiative_data, actor, reason)
    add_milestone(initiative_id, milestone_data, actor)
    transition_milestone_state(initiative_id, milestone_id, new_state, actor, reason)
    update_initiative_rag(initiative_id, new_rag, actor, reason)
    link_to_bsc(initiative_id, bsc_perspective, kpi_id, actor, reason)
    register_dependency(initiative_id, depends_on_id, actor, reason)
    initiative_status(initiative_id) -> Dict
    portfolio_summary() -> Dict (RAG distribution + initiatives at risk)

INITIATIVE_RAG_STATES byte-for-byte (3): GREEN, AMBER, RED

INITIATIVE_PHASES byte-for-byte (5):
    PLANNING, IN_PROGRESS, AT_RISK, DELIVERED, CANCELLED

ALLOWED_PHASE_TRANSITIONS (Rule 4):
    PLANNING    → IN_PROGRESS | CANCELLED
    IN_PROGRESS → AT_RISK | DELIVERED | CANCELLED
    AT_RISK     → IN_PROGRESS | DELIVERED | CANCELLED
    DELIVERED   → CANCELLED   (closure only)
    CANCELLED   → ()

MILESTONE_STATES byte-for-byte (4):
    PENDING, IN_PROGRESS, COMPLETED, MISSED

ALLOWED_MILESTONE_TRANSITIONS (Rule 4):
    PENDING     → IN_PROGRESS | MISSED
    IN_PROGRESS → COMPLETED | MISSED
    COMPLETED   → ()
    MISSED      → IN_PROGRESS | COMPLETED

BSC_PERSPECTIVES byte-for-byte (4):
    FINANCIAL, CUSTOMER, INTERNAL_PROCESS, LEARNING_GROWTH

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


INITIATIVE_RAG_STATES: Tuple[str, ...] = ("GREEN", "AMBER", "RED")

INITIATIVE_PHASES: Tuple[str, ...] = (
    "PLANNING", "IN_PROGRESS", "AT_RISK", "DELIVERED", "CANCELLED",
)

ALLOWED_PHASE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PLANNING":    ("IN_PROGRESS", "CANCELLED"),
    "IN_PROGRESS": ("AT_RISK", "DELIVERED", "CANCELLED"),
    "AT_RISK":     ("IN_PROGRESS", "DELIVERED", "CANCELLED"),
    "DELIVERED":   ("CANCELLED",),
    "CANCELLED":   (),
}

MILESTONE_STATES: Tuple[str, ...] = (
    "PENDING", "IN_PROGRESS", "COMPLETED", "MISSED",
)

ALLOWED_MILESTONE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PENDING":     ("IN_PROGRESS", "MISSED"),
    "IN_PROGRESS": ("COMPLETED", "MISSED"),
    "COMPLETED":   (),
    "MISSED":      ("IN_PROGRESS", "COMPLETED"),
}

BSC_PERSPECTIVES: Tuple[str, ...] = (
    "FINANCIAL", "CUSTOMER", "INTERNAL_PROCESS", "LEARNING_GROWTH",
)


class CommandCentreStrategicInitiativesEngine:
    """Strategic initiative portfolio manager with BSC linkage."""

    def __init__(
        self,
        initiatives_path: Optional[Path] = None,
        bsc_links_path: Optional[Path] = None,
        dependencies_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.initiatives_path = initiatives_path or base / "strategic_initiatives.json"
        self.bsc_links_path = bsc_links_path or base / "initiative_bsc_links.json"
        self.dependencies_path = dependencies_path or base / "initiative_dependencies.json"

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

    def register_initiative(
        self, initiative_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("initiative_id", "initiative_name", "owner_role", "target_completion"):
            if f not in initiative_data or not initiative_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.initiatives_path,
                                "strategic_initiatives",
                                ("initiative_id",))
        if any(r.get("initiative_id") == initiative_data["initiative_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_initiative_id"}

        record = {
            "initiative_id": initiative_data["initiative_id"],
            "initiative_name": initiative_data["initiative_name"],
            "description": initiative_data.get("description", ""),
            "owner_role": initiative_data["owner_role"],
            "target_completion": initiative_data["target_completion"],
            "rag_status": initiative_data.get("rag_status", "GREEN"),
            "phase": "PLANNING",
            "milestones": [],
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        if record["rag_status"] not in INITIATIVE_RAG_STATES:
            return {"registered": False,
                       "error": f"invalid_rag:{record['rag_status']}"}
        records.append(record)
        ok = self._save(self.initiatives_path, records,
                          "strategic_initiatives", "initiative_id")
        return {"registered": ok,
                  "initiative_id": initiative_data["initiative_id"]}

    def add_milestone(
        self, initiative_id: str, milestone_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"added": False, "error": "actor_required"}
        for f in ("milestone_id", "milestone_name", "due_date"):
            if f not in milestone_data or not milestone_data[f]:
                return {"added": False, "error": f"missing_field:{f}"}
        records = self._load(self.initiatives_path,
                                "strategic_initiatives", ("initiative_id",))
        for r in records:
            if r.get("initiative_id") == initiative_id:
                # Check for duplicate
                if any(m.get("milestone_id") == milestone_data["milestone_id"]
                         for m in r.get("milestones", [])):
                    return {"added": False, "error": "duplicate_milestone_id"}
                milestone = {
                    "milestone_id": milestone_data["milestone_id"],
                    "milestone_name": milestone_data["milestone_name"],
                    "description": milestone_data.get("description", ""),
                    "due_date": milestone_data["due_date"],
                    "state": "PENDING",
                    "transitions": [{
                        "to": "PENDING", "actor": actor,
                        "at": datetime.utcnow().isoformat(),
                    }],
                    "added_by": actor,
                    "added_at": datetime.utcnow().isoformat(),
                }
                r.setdefault("milestones", []).append(milestone)
                ok = self._save(self.initiatives_path, records,
                                  "strategic_initiatives", "initiative_id")
                return {"added": ok,
                          "milestone_id": milestone_data["milestone_id"]}
        return {"added": False, "error": "initiative_not_found"}

    def transition_milestone_state(
        self, initiative_id: str, milestone_id: str,
        new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in MILESTONE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.initiatives_path,
                                "strategic_initiatives", ("initiative_id",))
        for r in records:
            if r.get("initiative_id") == initiative_id:
                for m in r.get("milestones", []):
                    if m.get("milestone_id") == milestone_id:
                        current = m["state"]
                        allowed = ALLOWED_MILESTONE_TRANSITIONS.get(current, ())
                        if new_state not in allowed:
                            return {
                                "transitioned": False,
                                "error": (
                                    f"transition_not_allowed:"
                                    f"{current}_to_{new_state}"
                                ),
                            }
                        m["state"] = new_state
                        m.setdefault("transitions", []).append({
                            "to": new_state, "actor": actor,
                            "at": datetime.utcnow().isoformat(),
                            "reason": reason,
                        })
                        ok = self._save(self.initiatives_path, records,
                                          "strategic_initiatives",
                                          "initiative_id")
                        return {"transitioned": ok,
                                  "from": current, "to": new_state}
                return {"transitioned": False, "error": "milestone_not_found"}
        return {"transitioned": False, "error": "initiative_not_found"}

    def update_initiative_rag(
        self, initiative_id: str, new_rag: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"updated": False, "error": "actor_and_reason_required"}
        if new_rag not in INITIATIVE_RAG_STATES:
            return {"updated": False, "error": f"invalid_rag:{new_rag}"}
        records = self._load(self.initiatives_path,
                                "strategic_initiatives", ("initiative_id",))
        for r in records:
            if r.get("initiative_id") == initiative_id:
                old_rag = r.get("rag_status", "GREEN")
                r["rag_status"] = new_rag
                r.setdefault("rag_history", []).append({
                    "rag": new_rag, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                # Auto-promote to AT_RISK phase if RAG is RED and IN_PROGRESS
                if new_rag == "RED" and r.get("phase", "") == "IN_PROGRESS":
                    r["phase"] = "AT_RISK"
                    r.setdefault("phase_transitions", []).append({
                        "to": "AT_RISK", "actor": actor,
                        "at": datetime.utcnow().isoformat(),
                        "reason": "auto_promoted_due_to_RED_rag",
                    })
                ok = self._save(self.initiatives_path, records,
                                  "strategic_initiatives", "initiative_id")
                return {"updated": ok, "from": old_rag, "to": new_rag}
        return {"updated": False, "error": "initiative_not_found"}

    def transition_phase(
        self, initiative_id: str, new_phase: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_phase not in INITIATIVE_PHASES:
            return {"transitioned": False, "error": f"invalid_phase:{new_phase}"}
        records = self._load(self.initiatives_path,
                                "strategic_initiatives", ("initiative_id",))
        for r in records:
            if r.get("initiative_id") == initiative_id:
                current = r.get("phase", "PLANNING")
                allowed = ALLOWED_PHASE_TRANSITIONS.get(current, ())
                if new_phase not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_phase}",
                    }
                r["phase"] = new_phase
                r.setdefault("phase_transitions", []).append({
                    "to": new_phase, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.initiatives_path, records,
                                  "strategic_initiatives", "initiative_id")
                return {"transitioned": ok, "from": current, "to": new_phase}
        return {"transitioned": False, "error": "initiative_not_found"}

    def link_to_bsc(
        self, initiative_id: str, bsc_perspective: str, kpi_id: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"linked": False, "error": "actor_and_reason_required"}
        if bsc_perspective not in BSC_PERSPECTIVES:
            return {"linked": False,
                       "error": f"invalid_perspective:{bsc_perspective}"}
        if not kpi_id:
            return {"linked": False, "error": "kpi_id_required"}
        # Verify initiative exists
        initiatives = self._load(self.initiatives_path,
                                       "strategic_initiatives",
                                       ("initiative_id",))
        if not any(r.get("initiative_id") == initiative_id
                       for r in initiatives):
            return {"linked": False, "error": "initiative_not_found"}

        links = self._load(self.bsc_links_path,
                              "initiative_bsc_links", ("link_id",))
        link_id = (f"BSC-{initiative_id}-{bsc_perspective}-{kpi_id}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        # Check for duplicate
        if any(l.get("initiative_id") == initiative_id
                  and l.get("kpi_id") == kpi_id
                  for l in links):
            return {"linked": False, "error": "kpi_already_linked"}
        links.append({
            "link_id": link_id,
            "initiative_id": initiative_id,
            "bsc_perspective": bsc_perspective,
            "kpi_id": kpi_id,
            "linked_by": actor,
            "linked_at": datetime.utcnow().isoformat(),
            "link_reason": reason,
        })
        ok = self._save(self.bsc_links_path, links,
                          "initiative_bsc_links", "link_id")
        return {"linked": ok, "link_id": link_id}

    def register_dependency(
        self, initiative_id: str, depends_on_id: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        if initiative_id == depends_on_id:
            return {"registered": False, "error": "self_dependency_disallowed"}
        # Verify both initiatives exist
        initiatives = self._load(self.initiatives_path,
                                       "strategic_initiatives",
                                       ("initiative_id",))
        ids = {r.get("initiative_id") for r in initiatives}
        if initiative_id not in ids:
            return {"registered": False, "error": "initiative_not_found"}
        if depends_on_id not in ids:
            return {"registered": False, "error": "depends_on_not_found"}

        deps = self._load(self.dependencies_path,
                              "initiative_dependencies", ("dependency_id",))
        # Check for duplicate
        if any(d.get("initiative_id") == initiative_id
                  and d.get("depends_on_id") == depends_on_id
                  for d in deps):
            return {"registered": False, "error": "dependency_exists"}

        dep_id = (f"DEP-{initiative_id}-{depends_on_id}-"
                      f"{int(datetime.utcnow().timestamp() * 1000)}")
        deps.append({
            "dependency_id": dep_id,
            "initiative_id": initiative_id,
            "depends_on_id": depends_on_id,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        })
        ok = self._save(self.dependencies_path, deps,
                          "initiative_dependencies", "dependency_id")
        return {"registered": ok, "dependency_id": dep_id}

    def initiative_status(self, initiative_id: str) -> Dict[str, Any]:
        records = self._load(self.initiatives_path,
                                "strategic_initiatives", ("initiative_id",))
        initiative = next((r for r in records
                                 if r.get("initiative_id") == initiative_id), None)
        if initiative is None:
            return {"found": False, "error": "initiative_not_found"}

        bsc_links = [l for l in self._load(self.bsc_links_path,
                                                  "initiative_bsc_links",
                                                  ("link_id",))
                          if l.get("initiative_id") == initiative_id]
        deps = [d for d in self._load(self.dependencies_path,
                                              "initiative_dependencies",
                                              ("dependency_id",))
                    if d.get("initiative_id") == initiative_id]
        milestones = initiative.get("milestones", [])
        completed = sum(1 for m in milestones if m["state"] == "COMPLETED")
        total = len(milestones)
        completion_pct = (completed / total * 100) if total > 0 else 0
        return {
            "found": True,
            "initiative_id": initiative_id,
            "initiative_name": initiative["initiative_name"],
            "owner_role": initiative["owner_role"],
            "rag_status": initiative["rag_status"],
            "phase": initiative["phase"],
            "target_completion": initiative.get("target_completion"),
            "milestone_count": total,
            "milestones_completed": completed,
            "completion_pct": round(completion_pct, 1),
            "milestones": milestones,
            "bsc_links": bsc_links,
            "dependencies": deps,
        }

    def portfolio_summary(self) -> Dict[str, Any]:
        records = self._load(self.initiatives_path,
                                "strategic_initiatives", ("initiative_id",))
        active = [r for r in records
                     if r.get("phase", "PLANNING") not in ("DELIVERED", "CANCELLED")]
        rag_dist = {rag: 0 for rag in INITIATIVE_RAG_STATES}
        phase_dist = {phase: 0 for phase in INITIATIVE_PHASES}
        for r in records:
            rag_dist[r.get("rag_status", "GREEN")] = (
                rag_dist.get(r.get("rag_status", "GREEN"), 0) + 1
            )
            phase_dist[r.get("phase", "PLANNING")] = (
                phase_dist.get(r.get("phase", "PLANNING"), 0) + 1
            )
        at_risk = [r for r in active
                       if r["rag_status"] in ("AMBER", "RED")
                       or r.get("phase", "") == "AT_RISK"]
        return {
            "total_initiatives": len(records),
            "active_initiatives": len(active),
            "rag_distribution": rag_dist,
            "phase_distribution": phase_dist,
            "at_risk_count": len(at_risk),
            "at_risk_initiatives": [
                {"initiative_id": r["initiative_id"],
                  "initiative_name": r["initiative_name"],
                  "rag_status": r["rag_status"],
                  "phase": r.get("phase", "PLANNING"),
                  "owner_role": r["owner_role"]}
                for r in at_risk
            ],
        }


def _self_test() -> None:
    import tempfile

    assert "GREEN" in INITIATIVE_RAG_STATES
    assert "PLANNING" in INITIATIVE_PHASES
    assert ALLOWED_PHASE_TRANSITIONS["CANCELLED"] == ()
    assert "PENDING" in MILESTONE_STATES
    assert "FINANCIAL" in BSC_PERSPECTIVES

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommandCentreStrategicInitiativesEngine(
            initiatives_path=Path(tmpdir) / "i.json",
            bsc_links_path=Path(tmpdir) / "b.json",
            dependencies_path=Path(tmpdir) / "d.json",
        )
        # Test 1: register
        r = engine.register_initiative(
            {"initiative_id": "INI-DIGITAL",
             "initiative_name": "Digital Banking 2026",
             "owner_role": "COO",
             "target_completion": "2026-12-31"},
            actor="md", reason="board mandate",
        )
        assert r["registered"]
        # Test 2: invalid RAG
        r = engine.register_initiative(
            {"initiative_id": "INI-X", "initiative_name": "X",
             "owner_role": "X", "target_completion": "2026-12-31",
             "rag_status": "PURPLE"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: add milestone
        r = engine.add_milestone(
            "INI-DIGITAL",
            {"milestone_id": "MS-1", "milestone_name": "Mobile redesign",
             "due_date": "2026-06-30"},
            actor="coo",
        )
        assert r["added"]
        # Test 4: duplicate milestone
        r = engine.add_milestone(
            "INI-DIGITAL",
            {"milestone_id": "MS-1", "milestone_name": "Y",
             "due_date": "2026-06-30"},
            actor="coo",
        )
        assert not r["added"]
        # Test 5: milestone transition
        r = engine.transition_milestone_state(
            "INI-DIGITAL", "MS-1", "IN_PROGRESS",
            actor="coo", reason="kicked off",
        )
        assert r["transitioned"]
        # Test 6: invalid transition
        r = engine.transition_milestone_state(
            "INI-DIGITAL", "MS-1", "PENDING",
            actor="coo", reason="x",
        )
        assert not r["transitioned"]
        # Test 7: complete
        r = engine.transition_milestone_state(
            "INI-DIGITAL", "MS-1", "COMPLETED",
            actor="coo", reason="delivered",
        )
        assert r["transitioned"]
        # Test 8: RAG update
        r = engine.update_initiative_rag(
            "INI-DIGITAL", "AMBER", actor="coo", reason="vendor delay",
        )
        assert r["updated"]
        # Test 9: phase transition + auto-promote
        engine.transition_phase("INI-DIGITAL", "IN_PROGRESS",
                                      actor="coo", reason="execution start")
        r = engine.update_initiative_rag(
            "INI-DIGITAL", "RED", actor="coo", reason="vendor cancelled",
        )
        assert r["updated"]
        status = engine.initiative_status("INI-DIGITAL")
        assert status["phase"] == "AT_RISK"  # auto-promoted
        # Test 10: BSC linkage
        r = engine.link_to_bsc(
            "INI-DIGITAL", "CUSTOMER", "KPI-NPS",
            actor="md", reason="aligns with NPS goal",
        )
        assert r["linked"]
        # Test 11: invalid perspective
        r = engine.link_to_bsc(
            "INI-DIGITAL", "INVALID", "KPI-X",
            actor="x", reason="x",
        )
        assert not r["linked"]
        # Test 12: duplicate BSC link
        r = engine.link_to_bsc(
            "INI-DIGITAL", "CUSTOMER", "KPI-NPS",
            actor="md", reason="x",
        )
        assert not r["linked"]
        # Test 13: dependencies
        engine.register_initiative(
            {"initiative_id": "INI-CORE",
             "initiative_name": "Core Banking Upgrade",
             "owner_role": "COO",
             "target_completion": "2026-09-30"},
            actor="md", reason="r",
        )
        r = engine.register_dependency(
            "INI-DIGITAL", "INI-CORE",
            actor="coo", reason="needs core API",
        )
        assert r["registered"]
        # Test 14: self-dependency disallowed
        r = engine.register_dependency(
            "INI-DIGITAL", "INI-DIGITAL",
            actor="coo", reason="x",
        )
        assert not r["registered"]
        # Test 15: depends-on not found
        r = engine.register_dependency(
            "INI-DIGITAL", "INI-NONEXISTENT",
            actor="coo", reason="x",
        )
        assert not r["registered"]
        # Test 16: portfolio
        p = engine.portfolio_summary()
        assert p["total_initiatives"] == 2
        assert p["at_risk_count"] >= 1
        # Test 17: status drill
        status = engine.initiative_status("INI-DIGITAL")
        assert status["completion_pct"] == 100.0
        assert len(status["bsc_links"]) == 1
        assert len(status["dependencies"]) == 1

    print("  ✅ command_centre_strategic_initiatives self-test PASS")


if __name__ == "__main__":
    _self_test()
