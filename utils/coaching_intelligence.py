"""utils.coaching_intelligence — Manager Coaching Intelligence
(Standard #15, v5.42).

Per the master spec:

    class CoachingIntelligence:
        def generate_coaching_script(self, manager_code, staff_code):
            return {
                "meeting_agenda":      ["Review wins", "Discuss challenge",
                                        "Action plan"],
                "talking_points":      ["I noticed you're exceeding on
                                        deposits. What's working?"],
                "recommended_actions": ["Shadow top performer",
                                        "Review 3 deals together"],
            }

Verification:
  - "Managers use scripts in 80% of reviews" ← deployed-runtime
                                                behavioral metric
                                                (whether managers
                                                actually open the
                                                script). OUT OF SCOPE.

The verifiable structural claim G26 enforces: given (manager, staff)
pairs in a labeled fixture set, the engine produces well-formed
scripts for ≥90% of valid pairs.

Architectural payoff: composing the V2 engines
-----------------------------------------------
Standard #15 is where #11, #12, #13, #14 finally compose into
something a manager can USE. The coaching script reads (not imports)
the persisted outputs of:

  - #11 (nudges)       → data/nudges.json       — pending alerts/recs
  - #12 (growth paths) → data/growth_plans.json — skill_gaps, readiness
  - #13 (microtasks)   → data/microtasks.json   — outstanding tasks
  - #14 (peer cards)   → data/learning_cards.json — relevant peers

Plus its own data:
  - users.json         — full names, roles, units
  - target_cascade.json — manager-report relationship + targets
  - bsc_engine actuals — current performance

Engines stay decoupled at runtime: this module imports NONE of the
others' classes; it consumes their published data files. Each engine
can fail/be missing independently — coaching script gracefully omits
the section.

Honesty rules (same as #14)
---------------------------
The engine produces ONLY observable signals. NEVER fabricates:
  - emotions ("I noticed you've been frustrated...")
  - attitudes ("Your team morale seems low...")
  - intent ("You don't seem motivated...")

Every talking point references an attributable, falsifiable signal:
  - KPI achievement_pct
  - Skill gap (skill name + current level + required level)
  - Active alert/recognition (kpi_id + period)
  - Outstanding micro-task (kpi_id + for_date)
  - Promotion readiness score
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.coaching")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
SCRIPTS_FILE = DATA_DIR / "coaching_scripts.json"

# ── Spec-aligned defaults ────────────────────────────────────────────
DEFAULT_AGENDA_MIN = 3       # spec example has 3 items
DEFAULT_AGENDA_MAX = 5       # 30-45 min 1:1 ceiling
DEFAULT_TALKING_POINTS_MIN = 1
DEFAULT_TALKING_POINTS_MAX = 8
DEFAULT_ACTIONS_MIN = 1
DEFAULT_ACTIONS_MAX = 5


# ─────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CoachingScript:
    """A complete coaching script. The dict shape returned by
    generate_coaching_script() flattens this for spec compliance,
    plus a `meta` block for traceability."""
    manager_code:         str = ""
    staff_code:           str = ""
    generated_for_date:   str = ""
    meeting_agenda:       List[str] = field(default_factory=list)
    talking_points:       List[str] = field(default_factory=list)
    recommended_actions:  List[str] = field(default_factory=list)
    signals_used:         Dict[str, int] = field(default_factory=dict)
    generated_at:         str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class CoachingIntelligence:
    """Standard #15 — Manager Coaching Intelligence.

    Stateless: each call returns a fresh script dict. Persistence is
    the caller's responsibility (use save_script).
    """

    def __init__(
        self,
        is_direct_report_fn: Optional[Callable[[str, str], bool]] = None,
        staff_lookup_fn:     Optional[Callable[[str], Optional[dict]]] = None,
        kpi_status_fn:       Optional[Callable[[str], List[dict]]] = None,
        nudges_fn:           Optional[Callable[[str], List[dict]]] = None,
        growth_plan_fn:      Optional[Callable[[str], dict]] = None,
        microtasks_fn:       Optional[Callable[[str], List[dict]]] = None,
        learning_cards_fn:   Optional[Callable[[str], List[dict]]] = None,
    ):
        """All collaborators injectable for testability.

        is_direct_report_fn(manager_code, staff_code) -> bool
            Returns True if staff is in manager's cascade-derived
            report chain. Default reads target_cascade.json.

        staff_lookup_fn(staff_code) -> dict | None
            Returns staff record (full_name, role, unit, etc.).

        kpi_status_fn(staff_code) -> [{kpi_id, current, target,
                                        achievement_pct, status}]
            Returns current KPI status for the staff. Default
            reads target_cascade + bsc_engine actuals.

        nudges_fn(staff_code) -> list[dict]
            Returns active nudges for the staff. Default reads
            data/nudges.json.

        growth_plan_fn(staff_code) -> dict
            Returns the growth plan dict (skill_gaps,
            promotion_readiness). Default reads
            data/growth_plans.json.

        microtasks_fn(staff_code) -> list[dict]
            Returns outstanding micro-tasks. Default reads
            data/microtasks.json filtered to incomplete.

        learning_cards_fn(staff_code) -> list[dict]
            Returns learning cards relevant to the staff. Default
            reads data/learning_cards.json.
        """
        self._is_direct_report = is_direct_report_fn or _default_is_direct_report
        self._staff_lookup     = staff_lookup_fn     or _default_staff_lookup
        self._kpi_status       = kpi_status_fn       or _default_kpi_status
        self._nudges           = nudges_fn           or _default_active_nudges
        self._growth_plan      = growth_plan_fn      or _default_growth_plan
        self._microtasks       = microtasks_fn       or _default_active_microtasks
        self._learning_cards   = learning_cards_fn   or _default_learning_cards

    # ──────────────────────────────────────────────────────────────────
    # Public API — spec entry
    # ──────────────────────────────────────────────────────────────────

    def generate_coaching_script(
        self,
        manager_code: str,
        staff_code:   str,
        today: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Return the spec-shaped coaching script.

        Returns {} when:
          - staff isn't a direct report of manager
          - staff_code is unknown
          - manager_code is unknown

        Defensive contract: never raises. Caller treats {} as "no
        script available."
        """
        if today is None:
            today = date.today()

        # Validate identities
        manager = self._staff_lookup(manager_code)
        staff   = self._staff_lookup(staff_code)
        if not manager or not staff:
            return {}
        if manager_code == staff_code:
            return {}   # can't coach yourself

        # Validate relationship
        if not self._is_direct_report(manager_code, staff_code):
            return {}

        # ── Gather signals (each is independently optional) ───────────
        kpi_status     = self._kpi_status(staff_code) or []
        nudges         = self._nudges(staff_code) or []
        plan           = self._growth_plan(staff_code) or {}
        microtasks     = self._microtasks(staff_code) or []
        learning_cards = self._learning_cards(staff_code) or []

        signals_used = {
            "kpi_status_rows":     len(kpi_status),
            "active_nudges":       len(nudges),
            "growth_plan_present": 1 if plan else 0,
            "active_microtasks":   len(microtasks),
            "learning_cards":      len(learning_cards),
        }

        # ── Build the three spec-required sections ────────────────────
        agenda = self._build_meeting_agenda(
            kpi_status, nudges, plan, microtasks,
        )
        talking_points = self._build_talking_points(
            staff, kpi_status, nudges, plan, microtasks,
        )
        recommended_actions = self._build_recommended_actions(
            kpi_status, plan, microtasks, learning_cards,
        )

        # Caps for sanity
        agenda = agenda[:DEFAULT_AGENDA_MAX]
        talking_points = talking_points[:DEFAULT_TALKING_POINTS_MAX]
        recommended_actions = recommended_actions[:DEFAULT_ACTIONS_MAX]

        return {
            "meeting_agenda":      agenda,
            "talking_points":      talking_points,
            "recommended_actions": recommended_actions,
            "meta": {
                "manager_code":  manager_code,
                "staff_code":    staff_code,
                "staff_name":    staff.get("full_name") or staff.get("name", ""),
                "staff_role":    staff.get("role", ""),
                "staff_unit":    staff.get("unit") or staff.get("department", ""),
                "for_date":      today.isoformat(),
                "signals_used":  signals_used,
                "generated_at":  datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Section builders
    # ──────────────────────────────────────────────────────────────────

    def _build_meeting_agenda(
        self,
        kpi_status: List[dict],
        nudges:     List[dict],
        plan:       dict,
        microtasks: List[dict],
    ) -> List[str]:
        """Spec example: ['Review wins', 'Discuss challenge',
        'Action plan']. Adapt to what data shows."""
        agenda: List[str] = []

        wins = [
            r for r in kpi_status
            if (r.get("achievement_pct") or 0) >= 100
        ]
        challenges = [
            r for r in kpi_status
            if (r.get("achievement_pct") or 0) < 80
        ]

        # Always lead with wins if any exist (positive opening = better
        # coaching). Always cover challenges if any exist. Always close
        # with action plan.
        if wins:
            agenda.append("Review wins and recognise strong KPI performance")
        if challenges:
            agenda.append("Discuss KPIs behind pace and root causes")
        else:
            agenda.append("Check in on overall KPI progress")
        if plan and plan.get("skill_gaps"):
            agenda.append("Review development priorities and skill gaps")
        if microtasks:
            agenda.append("Confirm outstanding micro-tasks")
        agenda.append("Agree on action plan for next 1-2 weeks")
        # Ensure at least the minimum (the spec example shows 3)
        if len(agenda) < DEFAULT_AGENDA_MIN:
            agenda.extend([
                "Discuss any blockers or support needed",
                "Confirm priorities for the coming period",
            ])
        return agenda

    def _build_talking_points(
        self,
        staff:      dict,
        kpi_status: List[dict],
        nudges:     List[dict],
        plan:       dict,
        microtasks: List[dict],
    ) -> List[str]:
        """Specific, conversation-ready phrases. Every point must
        reference an OBSERVABLE signal — never fabricate emotions."""
        points: List[str] = []
        name = staff.get("full_name") or staff.get("name") or "the team member"
        first_name = name.split()[0] if name else "the team member"

        # Wins (recognition opportunities)
        wins = sorted(
            [r for r in kpi_status if (r.get("achievement_pct") or 0) >= 110],
            key=lambda r: r.get("achievement_pct", 0),
            reverse=True,
        )[:2]
        for w in wins:
            kpi = w.get("kpi_id", "")
            ach = w.get("achievement_pct", 0)
            points.append(
                f"\"I noticed you're exceeding on {kpi} at "
                f"{ach:.0f}% of target. What's working?\""
            )

        # Active recognition nudges (independent corroboration)
        recog_nudges = [n for n in nudges if n.get("type") == "recognition"]
        for rn in recog_nudges[:1]:
            kpi = rn.get("kpi_id", "")
            if not any(kpi in p for p in points):
                points.append(
                    f"\"Strong recognition signal on {kpi} this period — "
                    f"keep up the momentum.\""
                )

        # Challenges (opening discussion, not lecture)
        behind = sorted(
            [r for r in kpi_status if 0 < (r.get("achievement_pct") or 0) < 80],
            key=lambda r: r.get("achievement_pct", 0),
        )[:2]
        for c in behind:
            kpi = c.get("kpi_id", "")
            ach = c.get("achievement_pct", 0)
            points.append(
                f"\"On {kpi} you're at {ach:.0f}% of target — "
                f"what are the biggest blockers right now?\""
            )

        # Behind-pace alerts (add only if not already covered above)
        alert_nudges = [n for n in nudges if n.get("type") == "alert"]
        already_covered_kpis = {
            n.get("kpi_id") for n in nudges if n.get("type") == "recognition"
        } | {w.get("kpi_id") for w in wins} | {c.get("kpi_id") for c in behind}
        for a in alert_nudges[:2]:
            kpi = a.get("kpi_id", "")
            if kpi and kpi not in already_covered_kpis:
                points.append(
                    f"\"Pace alert on {kpi} — what support would help "
                    f"you close the gap?\""
                )

        # Skill gaps (development talk)
        skill_gaps = (plan.get("skill_gaps") or [])[:2] if isinstance(plan, dict) else []
        for sg in skill_gaps:
            skill = sg.get("skill", "")
            cur = sg.get("current", 0)
            req = sg.get("required", 0)
            if skill:
                points.append(
                    f"\"On {skill}, you're at {cur} versus required "
                    f"{req}. What development support would you "
                    f"prioritise?\""
                )

        # Outstanding micro-tasks
        if microtasks:
            high = [t for t in microtasks if t.get("priority") == "High"]
            if high:
                points.append(
                    f"\"You have {len(high)} high-priority micro-tasks "
                    f"outstanding. Let's go through them together.\""
                )
            elif len(microtasks) > 0:
                points.append(
                    f"\"You have {len(microtasks)} micro-tasks pending — "
                    f"any blockers?\""
                )

        # Fallback when there's no signal at all (new joiner, no data)
        if not points:
            points.append(
                f"\"How's the work going overall? Anything I should know?\""
            )
            points.append(
                f"\"What's one thing I could do as your manager to make "
                f"your role easier?\""
            )

        return points

    def _build_recommended_actions(
        self,
        kpi_status:     List[dict],
        plan:           dict,
        microtasks:     List[dict],
        learning_cards: List[dict],
    ) -> List[str]:
        """2-3 concrete next steps the manager can assign or follow up on."""
        actions: List[str] = []

        # If learning cards exist for behind-pace KPIs → suggest peer learning
        behind_kpis = {
            r.get("kpi_id") for r in kpi_status
            if 0 < (r.get("achievement_pct") or 0) < 80
        }
        relevant_cards = [
            c for c in learning_cards
            if c.get("card_type") == "kpi" and c.get("kpi_id") in behind_kpis
        ]
        if relevant_cards:
            top = relevant_cards[0]
            performer = top.get("performer_staff_code", "a top performer")
            kpi = top.get("kpi_id", "")
            actions.append(
                f"Connect {performer} with the team member to share "
                f"approach on {kpi}"
            )

        # Skill gap → recommended development action
        skill_gaps = (plan.get("skill_gaps") or [])[:1] if isinstance(plan, dict) else []
        if skill_gaps and isinstance(plan, dict):
            recommended = plan.get("recommended_actions") or []
            if recommended:
                actions.append(f"Action: {recommended[0]}")

        # Outstanding high-priority micro-tasks → review together
        high_tasks = [t for t in microtasks if t.get("priority") == "High"]
        if len(high_tasks) >= 3:
            actions.append(
                f"Review the top 3 high-priority micro-tasks together"
            )
        elif high_tasks:
            actions.append(
                f"Review the {len(high_tasks)} high-priority micro-task(s) "
                f"together"
            )

        # Behind-pace KPIs without learning cards → manager-driven coaching
        for kpi_id in list(behind_kpis)[:2]:
            if not any(kpi_id in a for a in actions):
                actions.append(
                    f"Schedule a focused working session on {kpi_id}"
                )

        # Always close with a follow-up commitment
        actions.append("Confirm the date and outcome of the next 1:1")

        # Ensure minimum
        if len(actions) < DEFAULT_ACTIONS_MIN:
            actions.append("Document outcomes and next steps in the 1:1 log")

        return actions


# ─────────────────────────────────────────────────────────────────────
# Default collaborators (read persisted data; degrade gracefully)
# ─────────────────────────────────────────────────────────────────────

def _safe_load(path: Path, default):
    try:
        from utils.db import db
        d = db.load_json(path, default=default)
        return d
    except Exception as e:
        logger.warning("coaching: could not load %s: %s", path, e)
        return default


def _default_staff_lookup(staff_code: str) -> Optional[dict]:
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return None
    for username, info in users.items():
        if isinstance(info, dict) and str(info.get("staff_code", "")) == str(staff_code):
            return {**info, "username": username}
    return None


def _default_is_direct_report(manager_code: str, staff_code: str) -> bool:
    """Use target_cascade allocations as the manager-report relationship.

    A is B's manager iff there exists any cascade entry where
    from_code=A and one of the allocations.to_code=B.
    """
    cascade = _safe_load(DATA_DIR / "target_cascade.json", {})
    if not isinstance(cascade, dict):
        return False
    for _, block in cascade.items():
        if not isinstance(block, dict):
            continue
        if str(block.get("from_code", "")) != str(manager_code):
            continue
        for alloc in block.get("allocations", []) or []:
            if isinstance(alloc, dict) and str(alloc.get("to_code", "")) == str(staff_code):
                return True
    return False


def _default_kpi_status(staff_code: str) -> List[dict]:
    """Return current-period KPI status for a staff member.

    Combines target_cascade + bsc_engine actuals."""
    cascade = _safe_load(DATA_DIR / "target_cascade.json", {})
    if not isinstance(cascade, dict):
        return []
    try:
        from utils import bsc_engine
    except Exception:
        bsc_engine = None

    today = date.today()
    period = f"{today.year:04d}-{today.month:02d}"

    rows: List[dict] = []
    seen_kpis = set()
    for _, block in cascade.items():
        if not isinstance(block, dict):
            continue
        kpi_id = block.get("kpi", "")
        if not kpi_id:
            continue
        for alloc in block.get("allocations", []) or []:
            if not isinstance(alloc, dict):
                continue
            if str(alloc.get("to_code", "")) != str(staff_code):
                continue
            if (kpi_id, str(alloc.get("to_code"))) in seen_kpis:
                continue
            seen_kpis.add((kpi_id, str(alloc.get("to_code"))))
            target = alloc.get("amount")
            if target is None or float(target) <= 0:
                continue
            actual = None
            if bsc_engine is not None:
                try:
                    actual = bsc_engine.get_actual(staff_code, kpi_id, period)
                except Exception:
                    actual = None
            actual_f = float(actual) if actual is not None else 0.0
            ach = (actual_f / float(target) * 100) if target else 0.0
            rows.append({
                "kpi_id":          kpi_id,
                "current":         actual_f,
                "target":          float(target),
                "achievement_pct": ach,
                "status": (
                    "exceeding" if ach >= 110 else
                    "on_pace"   if ach >= 90  else
                    "behind"    if ach > 0    else
                    "no_data"
                ),
            })
    return rows


def _default_active_nudges(staff_code: str) -> List[dict]:
    nudges = _safe_load(DATA_DIR / "nudges.json", [])
    if not isinstance(nudges, list):
        return []
    return [
        n for n in nudges
        if isinstance(n, dict)
        and str(n.get("staff_code", "")) == str(staff_code)
        and not n.get("acknowledged_at")
    ]


def _default_growth_plan(staff_code: str) -> dict:
    plans = _safe_load(DATA_DIR / "growth_plans.json", {})
    if not isinstance(plans, dict):
        return {}
    plan = plans.get(str(staff_code))
    return plan if isinstance(plan, dict) else {}


def _default_active_microtasks(staff_code: str) -> List[dict]:
    tasks = _safe_load(DATA_DIR / "microtasks.json", [])
    if not isinstance(tasks, list):
        return []
    return [
        t for t in tasks
        if isinstance(t, dict)
        and str(t.get("staff_code", "")) == str(staff_code)
        and not t.get("completed_at")
    ]


def _default_learning_cards(staff_code: str) -> List[dict]:
    cards = _safe_load(DATA_DIR / "learning_cards.json", [])
    if not isinstance(cards, list):
        return []
    return [
        c for c in cards
        if isinstance(c, dict)
        and str(c.get("requesting_staff", "")) == str(staff_code)
    ]


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_script(manager_code: str, staff_code: str, script: dict) -> bool:
    """Persist a generated script. Idempotent on (manager, staff,
    for_date) — re-running for the same day overwrites."""
    if not script:
        return False
    try:
        from utils.db import db
        existing = db.load_json(SCRIPTS_FILE, default=[])
    except Exception:
        existing = []
    if not isinstance(existing, list):
        existing = []

    for_date = (script.get("meta") or {}).get("for_date", "")
    key = (str(manager_code), str(staff_code), for_date)
    kept = [
        s for s in existing
        if isinstance(s, dict)
        and (
            str(s.get("manager_code", "")) != key[0]
            or str(s.get("staff_code", ""))   != key[1]
            or str((s.get("meta") or {}).get("for_date", "")) != key[2]
        )
    ]
    record = {
        "manager_code": manager_code,
        "staff_code":   staff_code,
        **script,
    }
    kept.append(record)
    try:
        from utils.db import db
        db.save_json(SCRIPTS_FILE, kept)
        return True
    except Exception as e:
        logger.error("coaching: could not save script: %s", e)
        return False


def list_scripts_for_manager(manager_code: str, limit: int = 20) -> List[dict]:
    try:
        from utils.db import db
        all_scripts = db.load_json(SCRIPTS_FILE, default=[])
    except Exception:
        return []
    if not isinstance(all_scripts, list):
        return []
    relevant = [
        s for s in all_scripts
        if isinstance(s, dict) and str(s.get("manager_code", "")) == str(manager_code)
    ]
    relevant.sort(
        key=lambda s: (s.get("meta") or {}).get("generated_at", ""), reverse=True,
    )
    return relevant[:limit]


# ─────────────────────────────────────────────────────────────────────
# Self-test (`python -m utils.coaching_intelligence`)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.coaching_intelligence self-test")

    # Mock data
    staff_table = {
        "MGR1":  {"full_name": "Manager One",   "role": "Branch Manager",
                  "unit": "Mombasa"},
        "S100":  {"full_name": "Staff Strong",  "role": "Personal Banker",
                  "unit": "Mombasa"},
        "S200":  {"full_name": "Staff Behind",  "role": "Personal Banker",
                  "unit": "Mombasa"},
        "S300":  {"full_name": "Staff Mixed",   "role": "Personal Banker",
                  "unit": "Mombasa"},
        "S999":  {"full_name": "Other Branch",  "role": "Personal Banker",
                  "unit": "Nairobi"},
    }
    reports = {("MGR1", "S100"), ("MGR1", "S200"), ("MGR1", "S300")}
    # S999 reports to a different manager

    kpi_data = {
        "S100": [
            {"kpi_id": "DEP_GROWTH", "current": 130, "target": 100, "achievement_pct": 130, "status": "exceeding"},
        ],
        "S200": [
            {"kpi_id": "DEP_GROWTH", "current": 50, "target": 100, "achievement_pct": 50, "status": "behind"},
            {"kpi_id": "NPL_PCT",    "current": 30, "target": 100, "achievement_pct": 30, "status": "behind"},
        ],
        "S300": [
            {"kpi_id": "DEP_GROWTH", "current": 95, "target": 100, "achievement_pct": 95, "status": "on_pace"},
            {"kpi_id": "NPL_PCT",    "current": 40, "target": 100, "achievement_pct": 40, "status": "behind"},
        ],
    }
    nudges_data = {
        "S200": [{"staff_code": "S200", "kpi_id": "DEP_GROWTH",
                  "type": "alert", "period": "2026-04"}],
    }
    plans_data = {
        "S300": {
            "promotion_readiness": 0.45,
            "skill_gaps": [{"skill": "Risk Management", "current": 2.5, "required": 4.0}],
            "recommended_actions": ["Complete CISI Risk Management Level 1"],
        },
    }
    microtasks_data = {
        "S200": [
            {"staff_code": "S200", "kpi_id": "DEP_GROWTH", "priority": "High",
             "for_date": "2026-04-29", "task": "Make 5 outbound prospect calls"},
        ],
    }
    cards_data = {
        "S200": [
            {"card_type": "kpi", "kpi_id": "DEP_GROWTH",
             "performer_staff_code": "300100", "achievement_pct": 152,
             "requesting_staff": "S200"},
        ],
    }

    eng = CoachingIntelligence(
        is_direct_report_fn=lambda m, s: (m, s) in reports,
        staff_lookup_fn=    lambda sc: staff_table.get(sc),
        kpi_status_fn=      lambda sc: kpi_data.get(sc, []),
        nudges_fn=          lambda sc: nudges_data.get(sc, []),
        growth_plan_fn=     lambda sc: plans_data.get(sc, {}),
        microtasks_fn=      lambda sc: microtasks_data.get(sc, []),
        learning_cards_fn=  lambda sc: cards_data.get(sc, []),
    )

    # Case 1: Strong performer
    s = eng.generate_coaching_script("MGR1", "S100", today=date(2026, 4, 29))
    assert s, "expected non-empty script for valid pair"
    assert "meeting_agenda" in s and len(s["meeting_agenda"]) >= 3
    assert "talking_points" in s and len(s["talking_points"]) >= 1
    assert "recommended_actions" in s and len(s["recommended_actions"]) >= 1
    # Wins should be referenced for strong performer
    joined = " ".join(s["talking_points"])
    assert "DEP_GROWTH" in joined and "exceeding" in joined.lower()
    print(f"  ✅ strong performer: {len(s['talking_points'])} talking points, "
          f"signals={s['meta']['signals_used']}")

    # Case 2: Struggling staff
    s2 = eng.generate_coaching_script("MGR1", "S200", today=date(2026, 4, 29))
    assert s2
    joined2 = " ".join(s2["talking_points"])
    # Should reference the behind KPIs
    assert "DEP_GROWTH" in joined2 or "NPL_PCT" in joined2
    # Should reference the high-priority micro-task
    assert "high-priority" in joined2.lower() or "micro-task" in joined2.lower()
    # Recommended actions should include the peer learning suggestion
    actions_joined = " ".join(s2["recommended_actions"])
    assert "300100" in actions_joined or "peer" in actions_joined.lower() \
        or "DEP_GROWTH" in actions_joined
    print(f"  ✅ struggling staff: {len(s2['talking_points'])} talking points, "
          f"{len(s2['recommended_actions'])} actions")

    # Case 3: Mixed (some on pace, some behind, with growth plan)
    s3 = eng.generate_coaching_script("MGR1", "S300", today=date(2026, 4, 29))
    assert s3
    joined3 = " ".join(s3["talking_points"])
    # Should reference NPL behind pace
    assert "NPL_PCT" in joined3
    # Should reference the skill gap
    assert "Risk Management" in joined3
    print(f"  ✅ mixed: {len(s3['talking_points'])} talking points "
          f"(includes skill gap + behind KPI)")

    # Case 4: Cross-branch (S999 doesn't report to MGR1)
    s4 = eng.generate_coaching_script("MGR1", "S999")
    assert s4 == {}, f"expected empty for non-report pair, got {s4}"
    print(f"  ✅ cross-team pair returns {{}}")

    # Case 5: Self-coaching (manager == staff)
    s5 = eng.generate_coaching_script("MGR1", "MGR1")
    assert s5 == {}
    print(f"  ✅ self-coaching returns {{}}")

    # Case 6: Unknown manager
    s6 = eng.generate_coaching_script("UNKNOWN", "S100")
    assert s6 == {}
    print(f"  ✅ unknown manager returns {{}}")

    # Case 7: Unknown staff
    s7 = eng.generate_coaching_script("MGR1", "UNKNOWN")
    assert s7 == {}
    print(f"  ✅ unknown staff returns {{}}")

    # Case 8: No data at all (new joiner with valid relationship)
    eng_empty = CoachingIntelligence(
        is_direct_report_fn=lambda m, s: True,
        staff_lookup_fn=    lambda sc: {"full_name": "New Joiner", "role": "Trainee"},
        kpi_status_fn=      lambda sc: [],
        nudges_fn=          lambda sc: [],
        growth_plan_fn=     lambda sc: {},
        microtasks_fn=      lambda sc: [],
        learning_cards_fn=  lambda sc: [],
    )
    s8 = eng_empty.generate_coaching_script("M1", "S1")
    assert s8, "engine should produce a script even with no signal data"
    assert s8["talking_points"], "fallback talking points required"
    print(f"  ✅ no-signal staff: fallback script "
          f"({len(s8['talking_points'])} talking points)")

    # Case 9: Persistence
    print(f"  ✅ all 8 self-test cases passed")
    print("\n  ALL TESTS PASSED")
