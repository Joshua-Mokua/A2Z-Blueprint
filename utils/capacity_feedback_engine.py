"""Capacity Feedback Engine — v10.412 (E6 QA-Standards enhancement).

Per Joshua's QA standards Enhancement #6:
  Problem: Top-down targets ignore local capacity constraints.
  Solution: Capacity feedback from staff before targets are finalized.

This is the bottom-up channel: staff (Branch Managers, RMs, etc.) flag
local constraints (team size, market conditions, system gaps) BEFORE
their manager finalizes the cascade. Manager sees these constraints
inline when allocating in Set team targets.

API-first design per v10.412 React-readiness pattern:
  - Pure Python, zero Streamlit deps
  - Dataclass returns → JSON-serializable via dataclasses.asdict()
  - Functions take primitive types
  - Module-level cache for performance
  - Suitable for both Streamlit page and FastAPI endpoint consumption

Public API:
  submit_feedback(...)        → CapacityFeedback
  list_feedback(period, ...)  → list[CapacityFeedback]
  feedback_for_kpi(...)       → list (used by Set team targets)
  update_status(...)          → CapacityFeedback
  delete_feedback(id, by)     → bool

Per Rule 7, this is a COMPUTATION + MUTATION module. The mutation is
isolated to data/capacity_feedback.json with stamped audit fields.

Shipped: v10.412.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
FEEDBACK_FILE = DATA_DIR / "capacity_feedback.json"


# ════════════════════════════════════════════════════════════════════
# Constraint type taxonomy (validates submissions)
# ════════════════════════════════════════════════════════════════════

CONSTRAINT_TYPES = (
    "team_size",          # not enough headcount for the target
    "market_conditions",  # external (competitor, regulation, macro)
    "system_gap",         # missing process/tool/data
    "skills_gap",         # team needs training
    "data_quality",       # actuals/baseline unreliable
    "deadline",           # target asks for impossible timeline
    "dependency",         # blocked by another team
    "other",              # catch-all with rationale
)

FEEDBACK_STATUSES = (
    "Open",               # raised by staff, awaiting manager review
    "Acknowledged",       # manager has seen and is considering
    "Accepted",           # manager accepted; will adjust target
    "Rejected",           # manager rejected; target stands as-is
    "Resolved",           # constraint resolved (e.g., new hire approved)
)


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class CapacityFeedback:
    """One piece of capacity feedback from staff to manager."""
    id: str
    staff_code: str
    staff_name: str
    manager_code: str             # the recipient — staff's line manager
    manager_name: str
    period: str
    kpi: str
    constraint_type: str          # one of CONSTRAINT_TYPES
    constraint_value: str         # free-text description
    suggested_target_max: Optional[float]  # what staff thinks is realistic
    rationale: str                # WHY this constraint exists
    status: str                   # one of FEEDBACK_STATUSES
    raised_at: str                # ISO datetime
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    response: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        """JSON-serializable dict (API response shape)."""
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Storage
# ════════════════════════════════════════════════════════════════════

def _load() -> Dict[str, Any]:
    """Load capacity_feedback.json with safe defaults."""
    if not FEEDBACK_FILE.exists():
        return {"_version": "v10.412", "feedback": []}
    try:
        raw = json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"_version": "v10.412", "feedback": []}
    if not isinstance(raw, dict) or "feedback" not in raw:
        return {"_version": "v10.412", "feedback": []}
    return raw


def _save(data: Dict[str, Any]) -> None:
    FEEDBACK_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _next_id() -> str:
    data = _load()
    n = len(data.get("feedback", []))
    return f"CF{n+1:04d}"


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _staff_lookup(code: str) -> Dict[str, str]:
    """Resolve staff code → name + manager."""
    users_path = DATA_DIR / "users.json"
    if not users_path.exists():
        return {"name": "?", "manager_code": "", "manager_name": ""}
    try:
        users = json.loads(users_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"name": "?", "manager_code": "", "manager_name": ""}

    # Find the staff record
    staff_rec = None
    for u in users.values():
        if isinstance(u, dict) and str(u.get("staff_code", "")) == str(code):
            staff_rec = u
            break
    if not staff_rec:
        return {"name": "?", "manager_code": "", "manager_name": ""}

    name = str(staff_rec.get("full_name") or staff_rec.get("name", ""))
    manager_code = str(staff_rec.get("manager_code", ""))

    # Try canonical fallback if no manager_code
    if not manager_code:
        try:
            from utils.cascade_regenerator import (
                build_reporting_tree, _strip_meta, DEFAULT_BRANCH_TIER_THRESHOLD,
            )
            ohc_path = DATA_DIR / "org_hierarchy_config.json"
            if ohc_path.exists():
                ohc = json.loads(ohc_path.read_text(encoding="utf-8"))
                rmw = _strip_meta(ohc.get("role_manager_whitelist", {}))
                rmw = {k: v for k, v in rmw.items() if isinstance(v, list)}
                tiers = _strip_meta(ohc.get("role_tiers", {}))
                tiers = {k: int(v) for k, v in tiers.items()
                         if isinstance(v, (int, float))}
                threshold = int(ohc.get(
                    "branch_tier_threshold", DEFAULT_BRANCH_TIER_THRESHOLD))
                _tree, _orphans, _reports_of = build_reporting_tree(
                    users, rmw, tiers, threshold
                )
                # Find who has `code` as a direct report
                for mgr_code, reports in _tree.items():
                    if str(code) in reports:
                        manager_code = str(mgr_code)
                        break
        except Exception:  # noqa: BLE001
            pass

    # Resolve manager name
    manager_name = ""
    if manager_code:
        for u in users.values():
            if isinstance(u, dict) and str(u.get("staff_code", "")) == manager_code:
                manager_name = str(u.get("full_name") or u.get("name", ""))
                break

    return {"name": name, "manager_code": manager_code, "manager_name": manager_name}


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def submit_feedback(
    staff_code: str,
    period: str,
    kpi: str,
    constraint_type: str,
    constraint_value: str,
    rationale: str,
    suggested_target_max: Optional[float] = None,
) -> CapacityFeedback:
    """Staff raises a new capacity feedback.

    Args:
      staff_code: who is raising
      period: e.g. "2026"
      kpi: KPI id (e.g. "PBT", "K001")
      constraint_type: one of CONSTRAINT_TYPES
      constraint_value: short description of the constraint
      rationale: WHY (longer explanation)
      suggested_target_max: optional realistic ceiling

    Returns: created CapacityFeedback (also persisted).
    """
    if constraint_type not in CONSTRAINT_TYPES:
        raise ValueError(
            f"constraint_type must be one of {CONSTRAINT_TYPES}; got {constraint_type!r}"
        )
    info = _staff_lookup(staff_code)
    feedback = CapacityFeedback(
        id=_next_id(),
        staff_code=str(staff_code),
        staff_name=info["name"],
        manager_code=info["manager_code"],
        manager_name=info["manager_name"],
        period=period,
        kpi=kpi,
        constraint_type=constraint_type,
        constraint_value=constraint_value,
        suggested_target_max=(
            float(suggested_target_max) if suggested_target_max is not None else None
        ),
        rationale=rationale,
        status="Open",
        raised_at=datetime.now().isoformat(),
        history=[{
            "at": datetime.now().isoformat(),
            "by": str(staff_code),
            "action": "submitted",
        }],
    )
    data = _load()
    data["feedback"].append(asdict(feedback))
    _save(data)
    return feedback


def list_feedback(
    period: Optional[str] = None,
    manager_code: Optional[str] = None,
    staff_code: Optional[str] = None,
    kpi: Optional[str] = None,
    status: Optional[str] = None,
) -> List[CapacityFeedback]:
    """List feedback with optional filters.

    Used by:
      - Staff "My feedback" view → filter by staff_code
      - Manager "Team feedback" view → filter by manager_code
      - Set team targets KPI inline → filter by manager_code + kpi + status=Open
    """
    data = _load()
    out: List[CapacityFeedback] = []
    for entry in data.get("feedback", []):
        if not isinstance(entry, dict):
            continue
        if period and entry.get("period") != period:
            continue
        if manager_code and str(entry.get("manager_code", "")) != str(manager_code):
            continue
        if staff_code and str(entry.get("staff_code", "")) != str(staff_code):
            continue
        if kpi and entry.get("kpi") != kpi:
            continue
        if status and entry.get("status") != status:
            continue
        # Coerce back into dataclass
        try:
            out.append(CapacityFeedback(**entry))
        except TypeError:
            continue
    return out


def feedback_for_kpi(
    manager_code: str,
    kpi: str,
    period: str,
    open_only: bool = True,
) -> List[CapacityFeedback]:
    """Feedback for one (manager, kpi, period) — used by Set team targets.

    Inline warning surface: when manager allocates KPI X, show any open
    feedback raised by their team members about KPI X.
    """
    status_filter = "Open" if open_only else None
    return list_feedback(
        period=period, manager_code=manager_code, kpi=kpi, status=status_filter
    )


def update_status(
    feedback_id: str,
    status: str,
    response: str,
    resolved_by: str,
) -> Optional[CapacityFeedback]:
    """Manager updates the status of a feedback.

    Statuses: Open / Acknowledged / Accepted / Rejected / Resolved.
    Stamps resolved_at, resolved_by, response + appends history entry.
    """
    if status not in FEEDBACK_STATUSES:
        raise ValueError(
            f"status must be one of {FEEDBACK_STATUSES}; got {status!r}"
        )
    data = _load()
    found = None
    for entry in data.get("feedback", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("id") == feedback_id:
            entry["status"] = status
            entry["response"] = response
            entry["resolved_by"] = resolved_by
            entry["resolved_at"] = datetime.now().isoformat()
            entry.setdefault("history", []).append({
                "at": datetime.now().isoformat(),
                "by": resolved_by,
                "action": status,
                "response": response,
            })
            found = entry
            break
    if not found:
        return None
    _save(data)
    try:
        return CapacityFeedback(**found)
    except TypeError:
        return None


def delete_feedback(feedback_id: str, by: str) -> bool:
    """Hard-delete feedback (staff can withdraw their own)."""
    data = _load()
    before = len(data.get("feedback", []))
    data["feedback"] = [
        e for e in data.get("feedback", [])
        if not (isinstance(e, dict) and e.get("id") == feedback_id)
    ]
    if len(data["feedback"]) == before:
        return False
    _save(data)
    return True


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ capacity_feedback_engine self-test ─")
    # Empty initial state
    assert list_feedback() == []

    # Submit
    fb = submit_feedback(
        staff_code="300050",
        period="2026",
        kpi="PBT",
        constraint_type="team_size",
        constraint_value="Only 3 RMs vs target assumes 6",
        rationale="Industrial Area branch lost 3 RMs to attrition Q4 2025; replacements not yet hired.",
        suggested_target_max=8000000000.0,
    )
    print(f"  Submitted: {fb.id} — status={fb.status}")
    assert fb.id.startswith("CF")
    assert fb.status == "Open"
    assert fb.suggested_target_max == 8000000000.0

    # List
    all_fb = list_feedback()
    assert len(all_fb) == 1

    # Filter
    by_period = list_feedback(period="2026")
    assert len(by_period) == 1
    by_other_period = list_feedback(period="2027")
    assert len(by_other_period) == 0

    # Manager-scoped query
    if fb.manager_code:
        mgr_fb = feedback_for_kpi(fb.manager_code, "PBT", "2026")
        print(f"  Manager view ({fb.manager_code}): {len(mgr_fb)} feedback")

    # Update status
    updated = update_status(fb.id, "Acknowledged",
                            "Will discuss in 1:1", "MANAGER001")
    print(f"  Updated: {updated.id} — status={updated.status}")
    assert updated.status == "Acknowledged"

    # Cleanup
    delete_feedback(fb.id, "test")
    assert len(list_feedback()) == 0

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
