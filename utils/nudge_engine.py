"""utils.nudge_engine — Real-time performance nudges (Standard #11, v5.38).

Fires recognition or alert nudges in response to KPI actuals submitted
through `utils.bsc_engine.submit()`. Per the master spec:

    if current > target * 1.10 and trajectory == "accelerating":
        nudge(type="recognition", message="🎉 Exceeding target!")
    elif current < pace_target * 0.80:
        nudge(type="alert", message="⚠️ Behind target", action_items=[...])

This module produces the nudges; persistence + display happen elsewhere.
The engine is INVOKED EXPLICITLY by callers (not fired automatically
inside bsc_engine.submit) to keep the persistence path pure and avoid
synchronous side effects during batch submits.

Entry points
------------
    NudgeEngine().evaluate(staff_code, kpi_id, new_value, period) -> list[Nudge]
        Returns 0, 1, or 2 nudges. The caller persists them via
        `save_pending_nudges()` and surfaces them via the notification
        bell.

    save_pending_nudges(nudges: list[Nudge]) -> int
        Append-write to `data/nudges.json`. Returns the count saved.

    list_active_nudges(staff_code: str) -> list[Nudge]
        Returns un-acknowledged nudges for a given staff member.
        Used by the notification bell.

    acknowledge_nudge(nudge_id: str, actor: str) -> bool
        Marks a nudge as read. Records who and when.

Pace target
-----------
The "pace target" is the target adjusted for time elapsed in the period.
For a monthly target of 100 and we're 50% through the month, pace_target
= 50. The engine fires an alert when actual < 80% of pace_target — i.e.
behind the trajectory needed to hit the full-period target.

Trajectory detection
--------------------
"Accelerating" means the most recent N period values are monotonically
increasing AND the latest delta is larger than the average of prior
deltas. With fewer than 3 historical points we conservatively report
"insufficient_data" (no recognition fired — better to miss a nudge than
fire a wrong one).

Audit + accuracy
----------------
G22 audit gate reads `nudge_accuracy_results.json` (produced by
`tests/test_nudge_accuracy.py` running the labeled fixture set in
`tests/fixtures/nudge_scenarios.json`). Spec target: ≥95% accuracy.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.nudge")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
NUDGES_FILE = DATA_DIR / "nudges.json"

# ── Spec thresholds (Standard #11) ───────────────────────────────────
RECOGNITION_FACTOR = Decimal("1.10")   # current > target * 1.10 → recognition
ALERT_FACTOR       = Decimal("0.80")   # current < pace_target * 0.80 → alert
TRAJECTORY_LOOKBACK_PERIODS = 3        # how many prior periods to look at


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Nudge:
    """A single nudge — recognition or alert.

    Persisted to data/nudges.json. The notification bell reads only
    nudges where acknowledged_at is None.
    """
    id:              str   = field(default_factory=lambda: str(uuid.uuid4()))
    staff_code:      str   = ""
    kpi_id:          str   = ""
    period:          str   = ""
    type:            str   = ""        # "recognition" | "alert"
    message:         str   = ""
    action_items:    List[str] = field(default_factory=list)
    current_value:   Optional[float] = None
    target_value:    Optional[float] = None
    pace_target:     Optional[float] = None
    achievement_pct: Optional[float] = None
    trajectory:      str = ""          # "accelerating" | "flat" | "declining" | "insufficient_data"
    fired_at:        str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# The engine
# ─────────────────────────────────────────────────────────────────────

class PerformanceNudgeEngine:
    """Standard #11 — Real-time performance nudges.

    Stateless evaluator. Each call to evaluate() returns 0-2 Nudges.
    The engine doesn't persist — the caller decides whether to keep
    them (e.g. dedupe against already-fired nudges for the same
    staff/kpi/period).
    """

    def __init__(
        self,
        target_lookup_fn=None,
        history_lookup_fn=None,
        period_progress_fn=None,
        action_items_fn=None,
    ):
        """All collaborators are injectable for testing.

        target_lookup_fn(staff_code, kpi_id, period) -> Optional[Decimal]
            Returns the staff's cascaded target for the KPI in the period.
            Defaults to _default_target_lookup which reads target_cascade.json.

        history_lookup_fn(staff_code, kpi_id, period, n) -> List[Decimal]
            Returns the last n actuals (oldest first) for prior periods.
            Defaults to _default_history_lookup which calls bsc_engine.

        period_progress_fn(period, today) -> float
            Returns 0.0–1.0 for fraction of period elapsed.
            Defaults to _default_period_progress (calendar-month math).

        action_items_fn(staff_code, kpi_id) -> List[str]
            Returns concrete remediation suggestions for an alert.
            Defaults to _default_action_items (KPI-class-specific
            stock advice).
        """
        self._target_lookup    = target_lookup_fn   or _default_target_lookup
        self._history_lookup   = history_lookup_fn  or _default_history_lookup
        self._period_progress  = period_progress_fn or _default_period_progress
        self._action_items     = action_items_fn    or _default_action_items

    def evaluate(
        self,
        staff_code: str,
        kpi_id:     str,
        new_value:  float,
        period:     str,
        today:      Optional[date] = None,
    ) -> List[Nudge]:
        """Evaluate the new value against target + pace + trajectory.
        Returns a list (possibly empty) of fired Nudges."""
        if today is None:
            today = date.today()

        new_value_d = Decimal(str(new_value))

        target = self._target_lookup(staff_code, kpi_id, period)
        if target is None or target == 0:
            # Can't reason about "above/below target" without a target
            return []

        target_d = Decimal(str(target))

        # Compute progress through the period
        progress = self._period_progress(period, today)
        progress = max(0.0, min(1.0, progress))   # clamp [0, 1]
        pace_target = target_d * Decimal(str(progress))

        # Achievement % vs full-period target (informational only)
        achievement_pct = float(new_value_d / target_d * 100) if target_d else 0.0

        # Trajectory based on prior values
        history = self._history_lookup(staff_code, kpi_id, period,
                                       TRAJECTORY_LOOKBACK_PERIODS)
        trajectory = _classify_trajectory(history + [new_value_d])

        nudges: List[Nudge] = []

        # ─── Recognition: above 110% of full-period target AND accelerating ───
        # Note: this fires BEFORE the period ends — "exceeding target" is
        # judged against the full-period target. A staff who hits 110% in
        # week 1 of the month definitely deserves recognition.
        if (
            new_value_d > target_d * RECOGNITION_FACTOR
            and trajectory == "accelerating"
        ):
            nudges.append(Nudge(
                staff_code=      staff_code,
                kpi_id=          kpi_id,
                period=          period,
                type=            "recognition",
                message=         f"🎉 Exceeding target on {kpi_id}!",
                action_items=    [],
                current_value=   float(new_value_d),
                target_value=    float(target_d),
                pace_target=     float(pace_target),
                achievement_pct= achievement_pct,
                trajectory=      trajectory,
            ))

        # ─── Alert: below 80% of pace target ──────────────────────────────────
        # Pace-based, so this fires partway through the period when the
        # trajectory is short of where it needs to be.
        # Two guards prevent over-firing:
        #   pace_target > 0   — won't fire if period barely started
        #   progress >= 0.10  — give staff at least 10% of the period
        #                       to ramp up before nagging them. Without
        #                       this guard, a low value on day 1 of a
        #                       30-day month would alert immediately.
        elif (
            pace_target > 0
            and progress >= 0.10
            and new_value_d < pace_target * ALERT_FACTOR
        ):
            nudges.append(Nudge(
                staff_code=      staff_code,
                kpi_id=          kpi_id,
                period=          period,
                type=            "alert",
                message=         f"⚠️ Behind target on {kpi_id}",
                action_items=    self._action_items(staff_code, kpi_id),
                current_value=   float(new_value_d),
                target_value=    float(target_d),
                pace_target=     float(pace_target),
                achievement_pct= achievement_pct,
                trajectory=      trajectory,
            ))

        return nudges


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _default_target_lookup(staff_code: str, kpi_id: str, period: str) -> Optional[Decimal]:
    """Look up cascaded target from data/target_cascade.json.

    Cascade structure (per v5.x convention):
        {
          "<staff_code>": {
            "<kpi_id>": {"target": 1500000, "weight": 0.15, "period": "..."}
          }
        }

    Falls back to None when no target is found — the engine then skips
    nudge evaluation for this KPI rather than risk false positives.
    """
    try:
        from utils.db import db
        cascade = db.load_json(DATA_DIR / "target_cascade.json", default={})
    except Exception as e:
        logger.warning("nudge_engine: target lookup failed: %s", e)
        return None

    staff_block = cascade.get(staff_code, {}) if isinstance(cascade, dict) else {}
    kpi_block = staff_block.get(kpi_id, {}) if isinstance(staff_block, dict) else {}
    val = kpi_block.get("target") if isinstance(kpi_block, dict) else None
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def _default_history_lookup(
    staff_code: str, kpi_id: str, period: str, n: int
) -> List[Decimal]:
    """Return the last `n` prior-period actuals (oldest first).

    Uses bsc_engine.get_actual and walks back n periods. Returns
    whatever it can find (may be fewer than n if history is short).
    Periods missing actuals are skipped, NOT zero-filled.
    """
    try:
        from utils import bsc_engine
    except Exception as e:
        logger.warning("nudge_engine: history lookup failed (no bsc_engine): %s", e)
        return []

    # Period format expected: "YYYY-MM" (monthly) or "YYYY-Qn"
    prior_periods = _enumerate_prior_periods(period, n)
    out: List[Decimal] = []
    for p in prior_periods:
        try:
            v = bsc_engine.get_actual(staff_code, kpi_id, p)
            if v is not None:
                out.append(v if isinstance(v, Decimal) else Decimal(str(v)))
        except Exception:
            # Missing actuals are not errors — just skip
            continue
    return out


def _default_period_progress(period: str, today: date) -> float:
    """Fraction of `period` elapsed as of `today`. 0.0–1.0.

    Supports "YYYY-MM" (monthly) and "YYYY-Qn" (quarterly). Other
    formats return 0.5 (mid-period guess) rather than 0 — picking 0
    would suppress all alerts forever, picking 1 would over-aggressively
    judge incomplete periods.
    """
    if not period or not isinstance(period, str):
        return 0.5

    try:
        if "-Q" in period:
            year_str, q_str = period.split("-Q", 1)
            year = int(year_str)
            quarter = int(q_str)
            if quarter not in (1, 2, 3, 4):
                return 0.5
            start_month = 3 * (quarter - 1) + 1
            end_month   = start_month + 2
            from calendar import monthrange
            start = date(year, start_month, 1)
            _, last_day = monthrange(year, end_month)
            end = date(year, end_month, last_day)
        elif period.count("-") == 1:
            year_str, month_str = period.split("-", 1)
            year = int(year_str)
            month = int(month_str)
            from calendar import monthrange
            start = date(year, month, 1)
            _, last_day = monthrange(year, month)
            end = date(year, month, last_day)
        else:
            return 0.5
    except (ValueError, IndexError):
        return 0.5

    if today < start:
        return 0.0
    if today > end:
        return 1.0
    total_days = (end - start).days + 1
    elapsed = (today - start).days + 1
    return elapsed / total_days


def _default_action_items(staff_code: str, kpi_id: str) -> List[str]:
    """Stock remediation suggestions per KPI class.

    Real implementation would lookup KPI metadata and tailor by:
      - direction (higher-is-better vs lower-is-better)
      - pillar (Financial / Customer / Operational / People)
      - role
    For v5.38 this is a starting library covering the most common
    KPI shapes. Customisable downstream by injecting action_items_fn.
    """
    kpi_upper = (kpi_id or "").upper()
    # Volume / sales KPIs (DEP_GROWTH, LOAN_GROWTH, DEPOSIT_*, SALES, DEAL_*)
    if any(s in kpi_upper for s in ("DEPOSIT", "DEP_", "LOAN_GROWTH", "DEAL", "SALES")):
        return [
            "Review your top 5 prospects and confirm next-step dates",
            "Schedule 3 client visits this week",
            "Discuss pipeline blockers with your Branch Manager",
        ]
    # NPL / risk KPIs (lower-is-better)
    if any(s in kpi_upper for s in ("NPL", "PAR", "DPD", "DELINQUENCY")):
        return [
            "Review delinquent accounts and call top 10 oldest",
            "Restructure loans where appropriate",
            "Escalate uncooperative cases to recoveries",
        ]
    # AML / case-clearance KPIs
    if any(s in kpi_upper for s in ("AML", "ALERT", "SLA", "TAT")):
        return [
            "Clear the oldest 3 open cases today",
            "Request more info from analyst on stalled cases",
            "Escalate truly blocked cases to compliance lead",
        ]
    # Generic fallback
    return [
        "Review your scorecard and identify the largest gap",
        "Discuss this KPI with your line manager in your next 1:1",
        "Set 2 specific actions for this week to close the gap",
    ]


def _classify_trajectory(values: List[Decimal]) -> str:
    """Classify a value series as accelerating / flat / declining /
    insufficient_data.

    "accelerating" means:
      - All values monotonically non-decreasing (no dips)
      - Prior deltas have non-zero mean (some growth was already happening)
      - Latest delta > mean of prior deltas (positive curvature)
    "declining" means latest value is strictly below mean of prior
    "flat" otherwise
    "insufficient_data" if fewer than 3 values

    The conservative "insufficient_data" return prevents the engine
    from firing recognition nudges based on one or two data points.
    The non-zero-prior-deltas guard prevents flat-then-spike patterns
    (e.g. [110, 110, 110, 115] which is technically "monotonically
    non-decreasing with a final positive delta") from being labeled
    accelerating when they're really just one good period after stasis.
    """
    if len(values) < 3:
        return "insufficient_data"
    deltas = [values[i+1] - values[i] for i in range(len(values) - 1)]
    if all(d >= 0 for d in deltas):
        prior_mean = sum(deltas[:-1]) / len(deltas[:-1])
        # Both conditions: prior growth was non-zero AND latest delta exceeds it
        if prior_mean > 0 and deltas[-1] > prior_mean:
            return "accelerating"
    # Compare latest value to average of prior values
    prior_mean = sum(values[:-1]) / len(values[:-1])
    if values[-1] < prior_mean:
        return "declining"
    return "flat"


def _enumerate_prior_periods(current: str, n: int) -> List[str]:
    """Walk back `n` periods from `current`. Oldest first.

    Supports "YYYY-MM" and "YYYY-Qn"."""
    if not current:
        return []
    out: List[str] = []
    try:
        if "-Q" in current:
            year_str, q_str = current.split("-Q", 1)
            year = int(year_str); q = int(q_str)
            for _ in range(n):
                q -= 1
                if q < 1:
                    q = 4; year -= 1
                out.append(f"{year}-Q{q}")
        elif current.count("-") == 1:
            year_str, month_str = current.split("-", 1)
            year = int(year_str); m = int(month_str)
            for _ in range(n):
                m -= 1
                if m < 1:
                    m = 12; year -= 1
                out.append(f"{year}-{m:02d}")
    except (ValueError, IndexError):
        return []
    return list(reversed(out))   # oldest first


# ─────────────────────────────────────────────────────────────────────
# Persistence (delegated to utils.db so PG migration works seamlessly)
# ─────────────────────────────────────────────────────────────────────

def save_pending_nudges(nudges: List[Nudge]) -> int:
    """Append nudges to data/nudges.json. Returns the count saved.

    Idempotent: if a nudge with the same (staff_code, kpi_id, period,
    type) already exists and is unacknowledged, it's REPLACED rather
    than duplicated. This prevents nudge spam during batch submits
    when the same KPI gets multiple actuals.
    """
    if not nudges:
        return 0
    try:
        from utils.db import db
        existing = db.load_json(NUDGES_FILE, default=[])
    except Exception as e:
        logger.warning("nudge_engine: could not load existing nudges: %s", e)
        existing = []

    # Build dedupe key for unacknowledged nudges
    def _key(n: dict) -> Tuple[str, str, str, str]:
        return (
            str(n.get("staff_code", "")),
            str(n.get("kpi_id", "")),
            str(n.get("period", "")),
            str(n.get("type", "")),
        )

    pending_keys = {
        _key(n) for n in existing
        if isinstance(n, dict) and not n.get("acknowledged_at")
    }

    added = 0
    for n in nudges:
        d = asdict(n)
        if _key(d) in pending_keys:
            # Replace the existing pending nudge (keep id stable
            # would be nicer, but this is a JSON store — we just
            # remove the old and add the new)
            existing = [
                e for e in existing
                if not (isinstance(e, dict)
                        and _key(e) == _key(d)
                        and not e.get("acknowledged_at"))
            ]
        existing.append(d)
        added += 1

    try:
        from utils.db import db
        db.save_json(NUDGES_FILE, existing)
    except Exception as e:
        logger.error("nudge_engine: could not save nudges: %s", e)
        return 0
    return added


def list_active_nudges(staff_code: str) -> List[dict]:
    """Return un-acknowledged nudges for a staff member."""
    try:
        from utils.db import db
        all_nudges = db.load_json(NUDGES_FILE, default=[])
    except Exception:
        return []
    if not isinstance(all_nudges, list):
        return []
    return [
        n for n in all_nudges
        if isinstance(n, dict)
        and n.get("staff_code") == staff_code
        and not n.get("acknowledged_at")
    ]


def acknowledge_nudge(nudge_id: str, actor: str) -> bool:
    """Mark a nudge as acknowledged. Returns True if found + updated."""
    try:
        from utils.db import db
        all_nudges = db.load_json(NUDGES_FILE, default=[])
    except Exception:
        return False
    if not isinstance(all_nudges, list):
        return False

    found = False
    for n in all_nudges:
        if isinstance(n, dict) and n.get("id") == nudge_id and not n.get("acknowledged_at"):
            n["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
            n["acknowledged_by"] = actor
            found = True
            break
    if found:
        try:
            db.save_json(NUDGES_FILE, all_nudges)
        except Exception:
            return False
    return found


# ─────────────────────────────────────────────────────────────────────
# Self-test (mirrors bsc_engine.py pattern: `python -m utils.nudge_engine`)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.nudge_engine self-test")

    # Mock collaborators so the test doesn't depend on real data
    target_table = {("S001", "DEP_GROWTH"): Decimal("100")}
    history_table = {("S001", "DEP_GROWTH"): [Decimal("60"), Decimal("80"), Decimal("90")]}

    def mock_target(s, k, p): return target_table.get((s, k))
    def mock_history(s, k, p, n): return history_table.get((s, k), [])
    def mock_progress(p, t): return 0.5  # half through period
    def mock_action_items(s, k): return ["test action"]

    eng = PerformanceNudgeEngine(
        target_lookup_fn=mock_target,
        history_lookup_fn=mock_history,
        period_progress_fn=mock_progress,
        action_items_fn=mock_action_items,
    )

    # Case 1: above 110% target AND accelerating (60→80→90→115, deltas 20/10/25)
    nudges = eng.evaluate("S001", "DEP_GROWTH", 115, "2026-04")
    assert len(nudges) == 1 and nudges[0].type == "recognition", \
        f"recognition path: got {nudges}"
    print(f"  ✅ recognition fired: {nudges[0].message}")

    # Case 2: below 80% pace target (pace=50, value=39 → 78% of 50 = 39.0 < 40)
    nudges = eng.evaluate("S001", "DEP_GROWTH", 39, "2026-04")
    assert len(nudges) == 1 and nudges[0].type == "alert", \
        f"alert path: got {nudges}"
    assert nudges[0].action_items == ["test action"], \
        f"action items: {nudges[0].action_items}"
    print(f"  ✅ alert fired: {nudges[0].message}, {len(nudges[0].action_items)} actions")

    # Case 3: on pace, no nudge (50 = exactly pace target, not exceeding 110% nor below 80%)
    nudges = eng.evaluate("S001", "DEP_GROWTH", 50, "2026-04")
    assert len(nudges) == 0, f"no-nudge path: got {nudges}"
    print(f"  ✅ on-pace produced no nudge")

    # Case 4: no target → no nudge (engine can't reason without a target)
    nudges = eng.evaluate("S999", "UNKNOWN", 999, "2026-04")
    assert len(nudges) == 0, f"missing-target: {nudges}"
    print(f"  ✅ missing target produced no nudge")

    # Case 5: above 110% but not accelerating (insufficient history)
    eng_no_hist = PerformanceNudgeEngine(
        target_lookup_fn=mock_target,
        history_lookup_fn=lambda s, k, p, n: [],   # no history
        period_progress_fn=mock_progress,
    )
    nudges = eng_no_hist.evaluate("S001", "DEP_GROWTH", 115, "2026-04")
    assert len(nudges) == 0, f"no-history recognition suppressed: {nudges}"
    print(f"  ✅ no-history correctly suppressed recognition")

    # Trajectory classifier
    assert _classify_trajectory([Decimal("10"), Decimal("20"), Decimal("30"), Decimal("50")]) == "accelerating"
    assert _classify_trajectory([Decimal("50"), Decimal("40"), Decimal("30")]) == "declining"
    assert _classify_trajectory([Decimal("10"), Decimal("20")]) == "insufficient_data"
    print(f"  ✅ trajectory classifier")

    # Period progress
    progress = _default_period_progress("2026-04", date(2026, 4, 15))
    assert 0.4 < progress < 0.6, f"period progress mid-month: {progress}"
    progress = _default_period_progress("2026-Q2", date(2026, 5, 15))
    assert 0.4 < progress < 0.6, f"period progress mid-quarter: {progress}"
    progress = _default_period_progress("2026-04", date(2026, 4, 1))
    assert progress < 0.1, f"period progress day 1: {progress}"
    print(f"  ✅ period progress math")

    print("\n  ALL TESTS PASSED")
