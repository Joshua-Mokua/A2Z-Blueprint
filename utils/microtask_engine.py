"""utils.microtask_engine — Daily micro-task generation (Standard #13, v5.40).

Per the master spec:

    class MicroTaskEngine:
        def generate_daily_tasks(self, staff_code):
            tasks = []
            for kpi in self.get_active_kpis(staff_code):
                daily_req = kpi.target / working_days_remaining
                if current_pace < daily_req * 0.9:
                    tasks.append({
                        "task":     self.get_recommended_task(kpi.id),
                        "priority": "High",
                    })
            return tasks

Verification:
  - 90% task conversion rate ← deployed-runtime metric
                                 (% of recommended tasks staff actually
                                 complete). OUT OF SCOPE for this
                                 session.

The verifiable claim we DO measure is trigger reliability: given a
labeled fixture set of behind-pace inputs, the engine produces tasks
for ≥90% of them. Audit gate G24 enforces this.

Relationship to other engines
-----------------------------
- Nudge engine (Std #11)   — fires on actual-submit events;
                             "you're {recognized | behind} right now"
- Micro-task engine (#13)  — fires on a daily schedule;
                             "today's most leveraged actions"
- Growth path engine (#12) — fires on weekly/monthly review;
                             "long-arc development plan"

The three are deliberately decoupled: each runs on its own cadence,
none depend on the others. They surface in their own UI panels.

Design notes — deviations from the literal spec
------------------------------------------------
The spec snippet shows `daily_req = kpi.target / working_days_remaining`.
A literal read says "if you've achieved 80% with 2 days left, you
still need 100/2 = 50/day" — which is wrong arithmetic. We compute
the more honest version:

    remaining_target = max(target - current_actual, 0)
    daily_req        = remaining_target / working_days_remaining

This matches what a manager would actually tell a banker. The deviation
is documented in `details.daily_req_method` so callers can see how
the number was produced.

"current_pace" interpretation: actuals-to-date divided by days-elapsed.
This mirrors the nudge engine's pace_target math for symmetry — both
engines tell the same pace story.
"""
from __future__ import annotations

import json
import logging
from calendar import monthrange
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.microtask")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
TASKS_FILE = DATA_DIR / "microtasks.json"

# ── Spec-aligned thresholds ──────────────────────────────────────────
PACE_THRESHOLD     = Decimal("0.90")   # current_pace < daily_req * 0.9 → task
HIGH_PRIORITY_GAP  = Decimal("0.50")   # gap_pct < 50% of daily_req → High
MEDIUM_PRIORITY_GAP = Decimal("0.80")  # gap_pct < 80% → Medium; else no task
DEFAULT_MAX_TASKS_PER_STAFF = 5        # don't overwhelm; show top 5 by priority


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class MicroTask:
    """A single daily micro-task. Persisted to data/microtasks.json.
    The notification bell or Today's Tasks panel reads only tasks
    where completed_at is None and the date is today."""
    id:                   str   = ""
    staff_code:           str   = ""
    kpi_id:               str   = ""
    period:               str   = ""
    for_date:             str   = ""        # YYYY-MM-DD this task applies to
    task:                 str   = ""
    priority:             str   = ""        # "High" | "Medium"
    current_value:        Optional[float] = None
    target_value:         Optional[float] = None
    daily_req:            Optional[float] = None
    current_pace:         Optional[float] = None
    days_remaining:       Optional[int]  = None
    gap_pct:              Optional[float] = None
    generated_at:         str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at:         Optional[str]  = None
    completed_by:         Optional[str]  = None


# ─────────────────────────────────────────────────────────────────────
# The engine
# ─────────────────────────────────────────────────────────────────────

class MicroTaskEngine:
    """Standard #13 — Daily Micro-Task Engine.

    Pure-function evaluator. Construct once, call generate_daily_tasks
    for each staff. The engine doesn't persist — `save_pending_tasks`
    handles that.
    """

    def __init__(
        self,
        active_kpis_fn:        Optional[Callable[[str], List[dict]]] = None,
        target_lookup_fn:      Optional[Callable[[str, str, str], Optional[Decimal]]] = None,
        actual_lookup_fn:      Optional[Callable[[str, str, str], Optional[Decimal]]] = None,
        recommended_task_fn:   Optional[Callable[[str], str]] = None,
        working_days_fn:       Optional[Callable[[str, date], int]] = None,
        period_fn:             Optional[Callable[[date], str]] = None,
        max_tasks_per_staff:   int = DEFAULT_MAX_TASKS_PER_STAFF,
    ):
        """All collaborators are functions for testability.

        active_kpis_fn(staff_code) -> list[{"id", "name"?, "kpi_class"?}]
            Returns the KPIs in scope for this staff in the current
            period. Default reads target_cascade.json.

        target_lookup_fn(staff_code, kpi_id, period) -> Decimal | None
            Same interface as nudge_engine's target lookup.

        actual_lookup_fn(staff_code, kpi_id, period) -> Decimal | None
            Returns the current period actual.

        recommended_task_fn(kpi_id) -> str
            Returns ONE specific action for today (not a multi-day
            strategy list). Default is KPI-class routing.

        working_days_fn(period, today) -> int
            Returns Mon-Fri days remaining in the period (today
            counts; weekends excluded). Default uses calendar math.

        period_fn(today) -> str
            Returns the period string ("YYYY-MM" or "YYYY-Qn") for the
            given date. Default returns the calendar month.

        max_tasks_per_staff
            Don't overwhelm: cap output at this many tasks (highest
            priority first).
        """
        self._active_kpis      = active_kpis_fn        or _default_active_kpis
        self._target_lookup    = target_lookup_fn      or _default_target_lookup
        self._actual_lookup    = actual_lookup_fn      or _default_actual_lookup
        self._recommended_task = recommended_task_fn   or _default_recommended_task
        self._working_days     = working_days_fn       or _default_working_days_remaining
        self._period           = period_fn             or _default_period
        self._max_tasks        = max_tasks_per_staff

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def generate_daily_tasks(
        self,
        staff_code: str,
        today: Optional[date] = None,
    ) -> List[MicroTask]:
        """Return today's micro-tasks for the staff member.

        Returns [] when:
          - staff has no active KPIs
          - all KPIs are on/ahead of pace
          - the period has 0 working days remaining (period closed)
        Never raises for missing staff/KPI — defensive contract.
        """
        if today is None:
            today = date.today()
        period = self._period(today)
        days_remaining = self._working_days(period, today)
        if days_remaining <= 0:
            return []

        kpis = self._active_kpis(staff_code) or []

        candidates: List[Tuple[Decimal, MicroTask]] = []
        for kpi in kpis:
            kpi_id = kpi.get("id") if isinstance(kpi, dict) else None
            if not kpi_id:
                continue

            target = self._target_lookup(staff_code, kpi_id, period)
            actual = self._actual_lookup(staff_code, kpi_id, period)
            if target is None or target <= 0:
                # Can't reason without a target
                continue

            current = actual if actual is not None else Decimal(0)
            target_d = target if isinstance(target, Decimal) else Decimal(str(target))
            current_d = current if isinstance(current, Decimal) else Decimal(str(current))

            remaining_target = max(target_d - current_d, Decimal(0))
            if remaining_target == 0:
                # Already met — no task needed
                continue

            daily_req = remaining_target / Decimal(days_remaining)

            # current_pace: how much per day are they currently producing?
            # = current_actual / days_elapsed_in_period
            days_elapsed = self._compute_days_elapsed(period, today)
            if days_elapsed <= 0:
                # First working day of period; can't compute pace
                # → use current_actual as pace (very small, almost certainly
                # below daily_req which fires the task — that's correct)
                current_pace = current_d
            else:
                current_pace = current_d / Decimal(days_elapsed)

            # Spec: if current_pace < daily_req * 0.9 → task
            if current_pace >= daily_req * PACE_THRESHOLD:
                continue

            # Compute gap_pct = current_pace / daily_req in [0, 1]
            gap_ratio = (
                current_pace / daily_req if daily_req > 0 else Decimal(0)
            )

            # Priority bands
            if gap_ratio < HIGH_PRIORITY_GAP:
                priority = "High"
            elif gap_ratio < MEDIUM_PRIORITY_GAP:
                priority = "Medium"
            else:
                # Within [0.8, 0.9) — borderline; spec gates at 0.9 so still
                # emit, but lowest priority
                priority = "Medium"

            task_text = self._recommended_task(kpi_id) or _generic_task(kpi_id)

            mt = MicroTask(
                id=               f"{staff_code}:{kpi_id}:{period}:{today.isoformat()}",
                staff_code=       staff_code,
                kpi_id=           kpi_id,
                period=           period,
                for_date=         today.isoformat(),
                task=             task_text,
                priority=         priority,
                current_value=    float(current_d),
                target_value=     float(target_d),
                daily_req=        float(daily_req),
                current_pace=     float(current_pace),
                days_remaining=   days_remaining,
                gap_pct=          float(round(gap_ratio * 100, 1)),
            )
            # Sort key: smaller gap_ratio = more urgent = higher priority
            candidates.append((gap_ratio, mt))

        # Sort ascending by gap_ratio (most urgent first), cap
        candidates.sort(key=lambda kv: kv[0])
        return [mt for _, mt in candidates[: self._max_tasks]]

    @staticmethod
    def _compute_days_elapsed(period: str, today: date) -> int:
        """Working days (Mon–Fri) elapsed in the period up to and
        including today. Used to compute current_pace.

        Returns 0 if today is before the period starts.
        """
        bounds = _period_bounds(period)
        if not bounds:
            return 0
        start, end = bounds
        if today < start:
            return 0
        eff_today = min(today, end)
        return _count_weekdays_inclusive(start, eff_today)


# ─────────────────────────────────────────────────────────────────────
# Helpers — date/period math
# ─────────────────────────────────────────────────────────────────────

def _period_bounds(period: str) -> Optional[Tuple[date, date]]:
    """Return (start, end) for a YYYY-MM or YYYY-Qn period."""
    if not period or not isinstance(period, str):
        return None
    try:
        if "-Q" in period:
            year_str, q_str = period.split("-Q", 1)
            year = int(year_str); q = int(q_str)
            if q not in (1, 2, 3, 4):
                return None
            start_month = 3 * (q - 1) + 1
            end_month   = start_month + 2
            start = date(year, start_month, 1)
            _, last = monthrange(year, end_month)
            end = date(year, end_month, last)
            return start, end
        if period.count("-") == 1:
            year_str, m_str = period.split("-", 1)
            year = int(year_str); m = int(m_str)
            start = date(year, m, 1)
            _, last = monthrange(year, m)
            end = date(year, m, last)
            return start, end
    except (ValueError, IndexError):
        return None
    return None


def _count_weekdays_inclusive(start: date, end: date) -> int:
    """Count Mon–Fri days from `start` to `end` inclusive.

    Returns 0 if start > end. Holidays are NOT excluded (the engine
    has no holiday calendar — that's a future enhancement)."""
    if start > end:
        return 0
    weekdays = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:   # 0=Mon … 4=Fri
            weekdays += 1
        cur = date.fromordinal(cur.toordinal() + 1)
    return weekdays


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _default_period(today: date) -> str:
    """Default: monthly. 'YYYY-MM' format."""
    return f"{today.year:04d}-{today.month:02d}"


def _default_working_days_remaining(period: str, today: date) -> int:
    """Mon–Fri days from today through end of period inclusive.

    today counts (so the engine is "what to do today including today")."""
    bounds = _period_bounds(period)
    if not bounds:
        return 0
    start, end = bounds
    if today > end:
        return 0
    eff_start = max(today, start)
    return _count_weekdays_inclusive(eff_start, end)


def _safe_load_dict(path: Path) -> dict:
    try:
        from utils.db import db
        d = db.load_json(path, default={})
        return d if isinstance(d, dict) else {}
    except Exception as e:
        logger.warning("microtask: could not load %s: %s", path, e)
        return {}


def _default_active_kpis(staff_code: str) -> List[dict]:
    """Read the target cascade and return KPIs assigned to this staff.

    Cascade shape:
      {staff_code: {kpi_id: {target, weight, period?}}}
    """
    cascade = _safe_load_dict(DATA_DIR / "target_cascade.json")
    block = cascade.get(staff_code, {}) if isinstance(cascade, dict) else {}
    if not isinstance(block, dict):
        return []
    return [
        {"id": kpi_id, "weight": (info or {}).get("weight", 0)}
        for kpi_id, info in block.items()
        if isinstance(info, dict)
    ]


def _default_target_lookup(staff_code: str, kpi_id: str, period: str) -> Optional[Decimal]:
    """Look up cascaded target. Same shape as nudge_engine's helper."""
    cascade = _safe_load_dict(DATA_DIR / "target_cascade.json")
    block = cascade.get(staff_code, {}) if isinstance(cascade, dict) else {}
    kpi_block = block.get(kpi_id, {}) if isinstance(block, dict) else {}
    val = kpi_block.get("target") if isinstance(kpi_block, dict) else None
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def _default_actual_lookup(staff_code: str, kpi_id: str, period: str) -> Optional[Decimal]:
    """Read the current actual via bsc_engine.get_actual."""
    try:
        from utils import bsc_engine
        return bsc_engine.get_actual(staff_code, kpi_id, period)
    except Exception:
        return None


def _default_recommended_task(kpi_id: str) -> str:
    """Single concrete action FOR TODAY based on KPI class.

    Distinct from nudge_engine's action_items (which are multi-day
    strategies) — this is one specific thing the staff member can
    do in the next 8 hours."""
    kpi_upper = (kpi_id or "").upper()
    # Sales / volume
    if any(s in kpi_upper for s in ("DEPOSIT", "DEP_", "LOAN_GROWTH", "DEAL", "SALES")):
        return "Make 5 outbound prospect calls today"
    # NPL / risk
    if any(s in kpi_upper for s in ("NPL", "PAR", "DPD", "DELINQUENC")):
        return "Call the 3 oldest delinquent accounts today"
    # AML / case clearance
    if any(s in kpi_upper for s in ("AML", "ALERT", "SLA", "TAT")):
        return "Clear at least 2 AML alerts today"
    # Customer service / NPS
    if any(s in kpi_upper for s in ("NPS", "COMPLAINT", "CSAT", "CUSTOMER")):
        return "Resolve any open customer complaints in your queue today"
    # Approvals / TAT
    if any(s in kpi_upper for s in ("APPROVAL", "DECISION")):
        return "Process 3 pending approvals before noon"
    # Generic
    return "Identify one specific action for this KPI today and execute it"


def _generic_task(kpi_id: str) -> str:
    return f"Take one specific action toward {kpi_id} today"


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_pending_tasks(tasks: List[MicroTask]) -> int:
    """Persist tasks. Idempotent on (staff, kpi, for_date) — re-running
    the morning generator doesn't multiply yesterday's already-saved
    tasks; it replaces tasks for the same date."""
    if not tasks:
        return 0
    try:
        from utils.db import db
        existing = db.load_json(TASKS_FILE, default=[])
    except Exception as e:
        logger.warning("microtask: could not load existing tasks: %s", e)
        existing = []
    if not isinstance(existing, list):
        existing = []

    def _key(t: dict) -> Tuple[str, str, str]:
        return (
            str(t.get("staff_code", "")),
            str(t.get("kpi_id", "")),
            str(t.get("for_date", "")),
        )

    incoming_keys = {_key(asdict(t)) for t in tasks}
    # Keep tasks with different keys; replace tasks with the same keys
    kept = [
        t for t in existing
        if isinstance(t, dict) and _key(t) not in incoming_keys
    ]
    for t in tasks:
        kept.append(asdict(t))

    try:
        from utils.db import db
        db.save_json(TASKS_FILE, kept)
    except Exception as e:
        logger.error("microtask: could not save tasks: %s", e)
        return 0
    return len(tasks)


def list_active_tasks(staff_code: str, for_date: Optional[date] = None) -> List[dict]:
    """Return today's incomplete tasks for a staff member."""
    try:
        from utils.db import db
        all_tasks = db.load_json(TASKS_FILE, default=[])
    except Exception:
        return []
    if not isinstance(all_tasks, list):
        return []
    target_date = (for_date or date.today()).isoformat()
    return [
        t for t in all_tasks
        if isinstance(t, dict)
        and t.get("staff_code") == staff_code
        and t.get("for_date") == target_date
        and not t.get("completed_at")
    ]


def complete_task(task_id: str, actor: str) -> bool:
    """Mark a task as completed."""
    try:
        from utils.db import db
        all_tasks = db.load_json(TASKS_FILE, default=[])
    except Exception:
        return False
    if not isinstance(all_tasks, list):
        return False
    found = False
    for t in all_tasks:
        if isinstance(t, dict) and t.get("id") == task_id and not t.get("completed_at"):
            t["completed_at"] = datetime.now(timezone.utc).isoformat()
            t["completed_by"] = actor
            found = True
            break
    if found:
        try:
            db.save_json(TASKS_FILE, all_tasks)
        except Exception:
            return False
    return found


# ─────────────────────────────────────────────────────────────────────
# Self-test (`python -m utils.microtask_engine`)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.microtask_engine self-test")

    # Mock fixtures: April 15 2026 (Wed), monthly period
    today = date(2026, 4, 15)
    # April 2026: 1=Wed; weekdays in month = 22 total
    # From Apr 15 to Apr 30: 12 weekdays remaining (incl today)

    kpis_table = {
        "S001": [
            {"id": "DEP_GROWTH"},     # behind pace
            {"id": "NPL_PCT"},        # on pace
            {"id": "AML_SLA"},        # also behind
        ],
    }
    targets = {
        ("S001", "DEP_GROWTH", "2026-04"): Decimal("100"),  # 100 by month-end
        ("S001", "NPL_PCT",    "2026-04"): Decimal("100"),
        ("S001", "AML_SLA",    "2026-04"): Decimal("100"),
    }
    actuals = {
        # Days elapsed Apr 1..15 weekdays = 11; pace = actual/11
        # daily_req on day 15 (12 days remaining): (target - actual) / 12
        # DEP_GROWTH: actual=20, target=100 → remaining=80, daily_req≈6.67
        #             pace=20/11≈1.82, threshold=daily_req*0.9=6.0
        #             1.82 < 6.0 → fires task. gap_ratio = 1.82/6.67 = 0.27 → High
        ("S001", "DEP_GROWTH", "2026-04"): Decimal("20"),
        # NPL_PCT: actual=80 (above pace), target=100 → remaining=20, daily_req≈1.67
        #          pace=80/11≈7.27, threshold≈1.5 → 7.27 >= 1.5 → no task
        ("S001", "NPL_PCT", "2026-04"): Decimal("80"),
        # AML_SLA: actual=15 → remaining=85, daily_req≈7.08, threshold≈6.38
        #          pace=15/11≈1.36 < 6.38 → fires task, gap_ratio=1.36/7.08≈0.19 → High
        ("S001", "AML_SLA", "2026-04"): Decimal("15"),
    }

    eng = MicroTaskEngine(
        active_kpis_fn=lambda sc: kpis_table.get(sc, []),
        target_lookup_fn=lambda sc, k, p: targets.get((sc, k, p)),
        actual_lookup_fn=lambda sc, k, p: actuals.get((sc, k, p)),
    )
    tasks = eng.generate_daily_tasks("S001", today=today)
    assert len(tasks) == 2, f"expected 2 behind-pace tasks, got {len(tasks)}"
    kpi_ids = {t.kpi_id for t in tasks}
    assert kpi_ids == {"DEP_GROWTH", "AML_SLA"}, f"unexpected kpis: {kpi_ids}"
    for t in tasks:
        assert t.priority in ("High", "Medium")
        assert t.task and isinstance(t.task, str)
    print(f"  ✅ behind-pace KPIs produced {len(tasks)} tasks: "
          f"{[(t.kpi_id, t.priority) for t in tasks]}")

    # Case 2: unknown staff → no tasks (engine doesn't crash)
    tasks2 = eng.generate_daily_tasks("UNKNOWN", today=today)
    assert tasks2 == []
    print(f"  ✅ unknown staff returned []")

    # Case 3: end-of-period, no working days remaining → no tasks
    eng_eom = MicroTaskEngine(
        active_kpis_fn=lambda sc: kpis_table.get(sc, []),
        target_lookup_fn=lambda sc, k, p: targets.get((sc, k, p)),
        actual_lookup_fn=lambda sc, k, p: actuals.get((sc, k, p)),
        working_days_fn=lambda p, t: 0,
    )
    tasks3 = eng_eom.generate_daily_tasks("S001", today=today)
    assert tasks3 == [], f"end-of-period should produce no tasks, got {tasks3}"
    print(f"  ✅ end-of-period correctly empty")

    # Case 4: target met (actual >= target) → no task for that KPI
    actuals_met = {**actuals, ("S001", "DEP_GROWTH", "2026-04"): Decimal("110")}
    eng_met = MicroTaskEngine(
        active_kpis_fn=lambda sc: [{"id": "DEP_GROWTH"}],
        target_lookup_fn=lambda sc, k, p: targets.get((sc, k, p)),
        actual_lookup_fn=lambda sc, k, p: actuals_met.get((sc, k, p)),
    )
    tasks4 = eng_met.generate_daily_tasks("S001", today=today)
    assert tasks4 == [], f"target met should produce no task: {tasks4}"
    print(f"  ✅ target-met KPI produces no task")

    # Case 5: weekday counting
    assert _count_weekdays_inclusive(date(2026, 4, 1), date(2026, 4, 30)) == 22
    assert _count_weekdays_inclusive(date(2026, 4, 6), date(2026, 4, 10)) == 5  # Mon-Fri
    assert _count_weekdays_inclusive(date(2026, 4, 11), date(2026, 4, 12)) == 0  # Sat-Sun
    print(f"  ✅ weekday counting")

    # Case 6: priority bands
    # Force High: gap_ratio < 0.5
    actuals_v_low = {("S001", "DEP_GROWTH", "2026-04"): Decimal("5")}
    eng_lo = MicroTaskEngine(
        active_kpis_fn=lambda sc: [{"id": "DEP_GROWTH"}],
        target_lookup_fn=lambda sc, k, p: targets.get((sc, k, p)),
        actual_lookup_fn=lambda sc, k, p: actuals_v_low.get((sc, k, p)),
    )
    tasks_hi = eng_lo.generate_daily_tasks("S001", today=today)
    assert tasks_hi and tasks_hi[0].priority == "High", tasks_hi
    print(f"  ✅ very-behind KPI gets High priority")

    print("\n  ALL TESTS PASSED")
