"""utils.stage_gate — Stage-Gate Governance
(Standard #50, v5.54). Volume Eight — Execute Enhancement.

Per v6 spec §8:
    StageGateEngine: enforces stage progression criteria for initiatives.

WHAT THIS MODULE SHIPS
----------------------
1. StageGateEngine class with:
   - request_stage_transition(initiative_id, target_stage, requester) — gate check
   - get_gate_criteria(stage) — criteria catalog
   - validate_initiative_at_stage(initiative_id, stage) — full audit

2. STAGES catalog: IDEATION → DESIGN → BUILD → PILOT → ROLLOUT → COMPLETED
3. STAGE_CRITERIA catalog (auditable, byte-for-byte spec literal)

HONESTY DISCIPLINE
------------------
Rule 4 — Default-strict workflow:
  - Stage transitions DEFAULT-DENY when criteria not met
  - NO override mode — criteria are absolute (not "force_advance")
  - All denials produce explicit list of unmet criteria

Rule 6 — No privilege escalation:
  - Unknown stage rejected
  - Non-sequential stage transitions rejected (must move forward through
    the canonical sequence)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.stage_gate")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §8 #50)
# ─────────────────────────────────────────────────────────────────────

# Canonical stage sequence
STAGES: List[str] = [
    "IDEATION", "DESIGN", "BUILD", "PILOT", "ROLLOUT", "COMPLETED",
]

# Criteria for advancement INTO each stage (i.e. STAGE_CRITERIA[X] = what
# must be true to advance into X). IDEATION has no criteria (it's the start).
STAGE_CRITERIA: Dict[str, List[str]] = {
    "IDEATION": [],
    "DESIGN": [
        "business_case_approved",
        "sponsor_assigned",
        "estimated_budget_documented",
    ],
    "BUILD": [
        "design_doc_approved",
        "resource_plan_approved",
        "budget_committed",
    ],
    "PILOT": [
        "build_complete",
        "test_plan_approved",
        "pilot_scope_documented",
    ],
    "ROLLOUT": [
        "pilot_success_criteria_met",
        "rollout_plan_approved",
        "rollback_plan_documented",
        "training_materials_ready",
    ],
    "COMPLETED": [
        "rollout_success_verified",
        "kpi_baseline_captured",
        "lessons_learned_documented",
    ],
}

# Stage transition is forward-only along this sequence
def _stage_index(stage: str) -> int:
    try:
        return STAGES.index(stage)
    except ValueError:
        return -1


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class StageGateEngine:
    """Stage-Gate governance for initiatives."""

    STAGES = STAGES
    STAGE_CRITERIA = STAGE_CRITERIA

    def __init__(
        self,
        initiative_lookup_fn:  Optional[Callable[[str], Optional[dict]]] = None,
        criteria_state_fn:     Optional[Callable[[str], Dict[str, bool]]] = None,
        stage_update_fn:       Optional[Callable[[str, str], bool]]      = None,
        transition_log_fn:     Optional[Callable[[dict], None]]          = None,
    ):
        """All collaborators injectable.

        initiative_lookup_fn(initiative_id) → dict | None
        criteria_state_fn(initiative_id) → dict[criterion_name → bool]
        stage_update_fn(initiative_id, new_stage) → bool (success)
        transition_log_fn(log_entry) → None
        """
        self._init    = initiative_lookup_fn or (lambda i: None)
        self._crit    = criteria_state_fn    or (lambda i: {})
        self._update  = stage_update_fn      or (lambda i, s: False)
        self._log     = transition_log_fn    or (lambda e: None)

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: get_gate_criteria
    # ──────────────────────────────────────────────────────────────────

    def get_gate_criteria(self, stage: str) -> Dict[str, Any]:
        """Return the criteria required to advance INTO a stage."""
        if stage not in STAGES:
            return {
                "stage":      stage,
                "valid":      False,
                "criteria":   [],
                "reason":     f"unknown stage {stage!r}; valid: {STAGES}",
            }
        return {
            "stage":      stage,
            "valid":      True,
            "criteria":   list(STAGE_CRITERIA[stage]),
            "criteria_count": len(STAGE_CRITERIA[stage]),
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: request_stage_transition
    # ──────────────────────────────────────────────────────────────────

    def request_stage_transition(
        self,
        initiative_id: str,
        target_stage: str,
        requester: str,
    ) -> Dict[str, Any]:
        """Request advancement to target_stage; gate-check criteria.

        HONESTY: default-deny. Returns granted=False with explicit unmet
        criteria when any are missing. NO override mode.
        """
        if not initiative_id or not target_stage or not requester:
            return {
                "granted": False,
                "reason":  "initiative_id, target_stage, and requester required",
            }

        if target_stage not in STAGES:
            return {
                "granted": False,
                "reason":  f"invalid target_stage {target_stage!r}; valid: {STAGES}",
            }

        init = self._init(initiative_id)
        if not init:
            return {"granted": False, "reason": "initiative_not_found"}

        current_stage = init.get("stage")
        if current_stage not in STAGES:
            return {
                "granted": False,
                "reason":  f"initiative has invalid current stage {current_stage!r}",
            }

        # Forward-only progression
        cur_idx = _stage_index(current_stage)
        tgt_idx = _stage_index(target_stage)

        if tgt_idx == cur_idx:
            return {
                "granted": False,
                "reason":  f"already at stage {target_stage!r}",
                "current_stage": current_stage,
            }
        if tgt_idx < cur_idx:
            return {
                "granted": False,
                "reason":  f"backward transition not permitted ({current_stage} → {target_stage})",
                "current_stage": current_stage,
            }
        if tgt_idx != cur_idx + 1:
            return {
                "granted": False,
                "reason":  f"non-sequential transition not permitted "
                          f"({current_stage} → {target_stage}; must go through "
                          f"{STAGES[cur_idx + 1]})",
                "current_stage": current_stage,
            }

        # Criteria check
        criteria = STAGE_CRITERIA.get(target_stage, [])
        state = self._crit(initiative_id) or {}
        unmet = [c for c in criteria if not state.get(c)]

        now = datetime.now(timezone.utc).isoformat()

        if unmet:
            self._log({
                "initiative_id": initiative_id,
                "from_stage":    current_stage,
                "target_stage":  target_stage,
                "requester":     requester,
                "outcome":       "denied",
                "unmet_criteria": unmet,
                "logged_at":     now,
            })
            return {
                "granted": False,
                "reason":  "criteria_unmet",
                "current_stage": current_stage,
                "target_stage":  target_stage,
                "unmet_criteria": unmet,
                "criteria_required": criteria,
                "criteria_state": state,
            }

        # All criteria met — apply transition
        ok = self._update(initiative_id, target_stage)
        self._log({
            "initiative_id": initiative_id,
            "from_stage":    current_stage,
            "target_stage":  target_stage,
            "requester":     requester,
            "outcome":       "granted" if ok else "update_failed",
            "logged_at":     now,
        })
        return {
            "granted":       ok,
            "current_stage": target_stage if ok else current_stage,
            "previous_stage": current_stage,
            "criteria_met":  True,
            "transitioned_at": now,
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: validate_initiative_at_stage
    # ──────────────────────────────────────────────────────────────────

    def validate_initiative_at_stage(
        self,
        initiative_id: str,
        stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audit: verify an initiative meets the criteria for its current
        (or specified) stage. Useful for pre-existing data validation.
        """
        if not initiative_id:
            return {}

        init = self._init(initiative_id)
        if not init:
            return {"initiative_id": initiative_id, "valid": False, "reason": "not_found"}

        check_stage = stage or init.get("stage")
        if check_stage not in STAGES:
            return {
                "initiative_id": initiative_id,
                "valid":         False,
                "reason":        f"invalid stage {check_stage!r}",
            }

        criteria = STAGE_CRITERIA.get(check_stage, [])
        state = self._crit(initiative_id) or {}
        unmet = [c for c in criteria if not state.get(c)]

        return {
            "initiative_id":   initiative_id,
            "stage":           check_stage,
            "valid":           len(unmet) == 0,
            "criteria_required": criteria,
            "unmet_criteria":  unmet,
            "criteria_state":  state,
        }


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.stage_gate self-test")

    # ── Spec literals ─────────────────────────────────────────────────
    assert STAGES == ["IDEATION", "DESIGN", "BUILD", "PILOT", "ROLLOUT", "COMPLETED"]
    print(f"  ✅ canonical stages: {STAGES}")

    # Spec criteria byte-for-byte
    assert STAGE_CRITERIA["DESIGN"] == [
        "business_case_approved", "sponsor_assigned", "estimated_budget_documented",
    ]
    assert STAGE_CRITERIA["ROLLOUT"] == [
        "pilot_success_criteria_met", "rollout_plan_approved",
        "rollback_plan_documented", "training_materials_ready",
    ]
    assert STAGE_CRITERIA["COMPLETED"] == [
        "rollout_success_verified", "kpi_baseline_captured", "lessons_learned_documented",
    ]
    print(f"  ✅ stage criteria catalog complete")

    # ── get_gate_criteria ─────────────────────────────────────────────
    eng = StageGateEngine()
    r = eng.get_gate_criteria("DESIGN")
    assert r["valid"] is True
    assert r["criteria_count"] == 3
    print(f"  ✅ get_gate_criteria(DESIGN): {r['criteria_count']} criteria")

    r = eng.get_gate_criteria("UNKNOWN_STAGE")
    assert r["valid"] is False
    print(f"  ✅ unknown stage rejected")

    # ── Setup an initiative ──────────────────────────────────────────
    inits = {
        "INIT_001": {"initiative_id": "INIT_001", "stage": "IDEATION"},
    }
    crit_state = {"INIT_001": {}}    # nothing met yet
    log = []
    updates = []
    eng2 = StageGateEngine(
        initiative_lookup_fn=lambda i: inits.get(i),
        criteria_state_fn=lambda i: crit_state.get(i, {}),
        stage_update_fn=lambda i, s: (
            inits.update({i: {**inits[i], "stage": s}}) or updates.append((i, s)) or True
        ),
        transition_log_fn=lambda e: log.append(e),
    )

    # ── Request DESIGN with no criteria met → denied ─────────────────
    r = eng2.request_stage_transition("INIT_001", "DESIGN", "manager_001")
    assert r["granted"] is False
    assert r["reason"] == "criteria_unmet"
    assert set(r["unmet_criteria"]) == set(STAGE_CRITERIA["DESIGN"])
    assert log[-1]["outcome"] == "denied"
    print(f"  ✅ transition denied: 3 unmet criteria; log entry written")

    # ── Meet partial criteria → still denied ─────────────────────────
    crit_state["INIT_001"] = {"business_case_approved": True, "sponsor_assigned": True}
    r = eng2.request_stage_transition("INIT_001", "DESIGN", "manager_001")
    assert r["granted"] is False
    assert r["unmet_criteria"] == ["estimated_budget_documented"]
    print(f"  ✅ partial criteria: still denied (1 unmet)")

    # ── Meet all criteria → granted ──────────────────────────────────
    crit_state["INIT_001"]["estimated_budget_documented"] = True
    r = eng2.request_stage_transition("INIT_001", "DESIGN", "manager_001")
    assert r["granted"] is True
    assert r["current_stage"] == "DESIGN"
    assert log[-1]["outcome"] == "granted"
    print(f"  ✅ all criteria met: transitioned to DESIGN")

    # ── Skip-stage attempt blocked ───────────────────────────────────
    # Currently at DESIGN; try to skip to PILOT
    r = eng2.request_stage_transition("INIT_001", "PILOT", "manager_001")
    assert r["granted"] is False
    assert "non-sequential" in r["reason"]
    print(f"  ✅ skip-stage attempt blocked: {r['reason'][:50]}")

    # ── Backward transition blocked ──────────────────────────────────
    r = eng2.request_stage_transition("INIT_001", "IDEATION", "manager_001")
    assert r["granted"] is False
    assert "backward" in r["reason"]
    print(f"  ✅ backward transition blocked")

    # ── Same-stage transition blocked ────────────────────────────────
    r = eng2.request_stage_transition("INIT_001", "DESIGN", "manager_001")
    assert r["granted"] is False
    assert "already at" in r["reason"]
    print(f"  ✅ same-stage transition blocked")

    # ── Unknown initiative ───────────────────────────────────────────
    r = eng2.request_stage_transition("INIT_BOGUS", "DESIGN", "x")
    assert r["granted"] is False
    assert r["reason"] == "initiative_not_found"
    print(f"  ✅ unknown initiative rejected")

    # ── Validate at stage ────────────────────────────────────────────
    r = eng2.validate_initiative_at_stage("INIT_001")
    # Currently at DESIGN with all DESIGN criteria met
    assert r["valid"] is True
    print(f"  ✅ validate_at_stage: DESIGN criteria all met")

    r = eng2.validate_initiative_at_stage("INIT_001", "BUILD")
    # BUILD criteria not yet met
    assert r["valid"] is False
    assert "design_doc_approved" in r["unmet_criteria"]
    print(f"  ✅ validate_at_stage(BUILD): {len(r['unmet_criteria'])} unmet")

    # ── Log captured all transitions ─────────────────────────────────
    granted_count = sum(1 for e in log if e.get("outcome") == "granted")
    denied_count = sum(1 for e in log if e.get("outcome") == "denied")
    assert granted_count == 1
    assert denied_count == 2
    print(f"  ✅ transition log: {granted_count} granted, {denied_count} denied")

    # ── No override mode exists ──────────────────────────────────────
    # The engine has no force_advance, no override_criteria, no admin_skip
    # Verify by class introspection
    eng_methods = [m for m in dir(eng2) if not m.startswith("_")]
    forbidden = ["force_advance", "override_criteria", "admin_skip", "bypass_gate"]
    for f in forbidden:
        assert f not in eng_methods, f"forbidden override method present: {f}"
    print(f"  ✅ no override mode exists (Rule 4)")

    print("\n  ALL TESTS PASSED")
