"""utils.wellness — Wellness & Burnout Risk (Standard #19, v5.44).

Per the master spec:

    class WellnessEngine:
        def assess_burnout_risk(self, staff_code):
            signals = {
                "overtime_frequency": self.get_overtime_rate(staff_code),
                "kpi_stress":         self.get_stress_score(staff_code),
            }
            if risk_score > 0.7:
                self.alert_manager({
                    "staff": staff_code,
                    "risk_level": "High",
                    "recommendations": ["Reduce target by 15%"],
                })

Verification:
  - 100% high-risk cases escalated  ← VERIFIABLE: every staff above
                                        threshold gets a manager alert.
                                        Audit gate G30 enforces.

CRITICAL HONESTY REQUIREMENTS
=============================
This is the most sensitive engine in the platform. Burnout signals
are about people's wellbeing — fabricating distress signals or
making medical/psychological claims is an unacceptable harm. Strict
rules:

1. The engine ONLY uses observable workplace signals — never
   fabricates emotional, medical, or psychological claims.

2. The engine NEVER labels anyone as "burnt out" or "depressed" —
   it produces a risk SCORE based on observable patterns, with
   recommendations to engage with the staff and (if appropriate)
   review their workload.

3. Recommendations are CONSERVATIVE — "have a 1:1 conversation,"
   "review workload," NOT clinical interventions.

4. The engine respects an OPT-OUT signal in users.json
   (`wellness_monitoring_disabled = true`). When set, the engine
   returns an empty result and writes no alerts.

5. Alerts go to the line manager only — NOT to HR, NOT to senior
   leadership unless explicitly configured. Managers receive the
   risk level and a short, non-medical recommendation.

6. The engine NEVER persists the underlying signal values to a
   permanent record without consent. The risk_score is computed
   per-call; the alert record contains only what the manager needs
   to take action.

Observable signals used
-----------------------
  - sustained_pace_deficit: how many of the last N periods the staff
    finished below 80% achievement (workload-vs-target mismatch)
  - alert_frequency: count of #11 alerts in last 30 days (consistent
    behind-pace signals)
  - microtask_overflow: open #13 micro-tasks > 7 days old (work
    accumulating that isn't getting done)
  - declining_trajectory: 3+ consecutive periods of decreasing
    achievement (negative trend)

These are LEADING INDICATORS of unsustainable workload, not labels
of mental state. A high score means "this staff's WORKLOAD pattern
suggests their manager should check in" — nothing about the person.

Risk scoring
------------
Each signal contributes 0..1 to a weighted sum. The default weights:
  sustained_pace_deficit  : 0.30
  alert_frequency         : 0.25
  microtask_overflow      : 0.20
  declining_trajectory    : 0.25

Risk levels:
  < 0.4   : Low      — no alert
  0.4-0.7 : Moderate — coaching prompt (not an alert)
  > 0.7   : High     — manager alert per spec
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.wellness")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
ALERTS_FILE = DATA_DIR / "wellness_alerts.json"

# ── Spec-aligned thresholds ──────────────────────────────────────────
RISK_LOW_CEILING       = 0.4
RISK_MODERATE_CEILING  = 0.7
RISK_HIGH_FLOOR        = 0.7   # spec: > 0.7 → manager alert

# ── Default signal weights (sum to 1.0) ──────────────────────────────
DEFAULT_WEIGHTS = {
    "sustained_pace_deficit": 0.30,
    "alert_frequency":        0.25,
    "microtask_overflow":     0.20,
    "declining_trajectory":   0.25,
}

# ── Signal computation thresholds ─────────────────────────────────────
PACE_DEFICIT_THRESHOLD_PCT  = 80.0   # below this counts as "deficit"
PACE_DEFICIT_LOOKBACK       = 4
ALERT_LOOKBACK_DAYS         = 30
ALERT_FREQUENCY_SATURATION  = 8       # ≥8 alerts in 30 days = max signal
MICROTASK_OVERFLOW_DAYS     = 7
MICROTASK_OVERFLOW_SATURATION = 5     # ≥5 stale tasks = max signal
TRAJECTORY_LOOKBACK         = 3


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class WellnessAlert:
    id:               str = ""
    staff_code:       str = ""
    manager_code:     str = ""
    assessed_at:      str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    risk_score:       float = 0.0
    risk_level:       str = ""    # Low | Moderate | High
    signals:          Dict[str, float] = field(default_factory=dict)
    recommendations:  List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class WellnessEngine:
    """Standard #19 — Wellness & Burnout Risk.

    Strict honesty rules apply (see module docstring).
    """

    def __init__(
        self,
        staff_lookup_fn:   Optional[Callable[[str], Optional[dict]]] = None,
        bsc_history_fn:    Optional[Callable[[str, int], List[Tuple[str, float]]]] = None,
        alerts_in_window_fn: Optional[Callable[[str, int], int]] = None,
        stale_microtasks_fn: Optional[Callable[[str, int], int]] = None,
        manager_lookup_fn: Optional[Callable[[str], Optional[str]]] = None,
        weights:           Optional[Dict[str, float]] = None,
    ):
        """All collaborators injectable.

        staff_lookup_fn(staff_code) → dict | None
            Standard staff record. Engine reads
            wellness_monitoring_disabled (default False).

        bsc_history_fn(staff_code, n) → [(period, achievement_pct), ...]
            Last n periods, most-recent first. Used for pace deficit
            and trajectory.

        alerts_in_window_fn(staff_code, days) → int
            Count of #11 alerts in the lookback window.

        stale_microtasks_fn(staff_code, age_days) → int
            Count of incomplete micro-tasks older than age_days.

        manager_lookup_fn(staff_code) → manager_code | None
            Used to route the alert. Default uses target_cascade.

        weights: signal weights (defaults to DEFAULT_WEIGHTS).
        """
        self._staff_lookup    = staff_lookup_fn    or _default_staff_lookup
        self._bsc_history     = bsc_history_fn     or _default_bsc_history
        self._alerts_in_window = alerts_in_window_fn or _default_alerts_in_window
        self._stale_microtasks = stale_microtasks_fn or _default_stale_microtasks
        self._manager_lookup  = manager_lookup_fn  or _default_manager_lookup
        if weights is not None:
            assert abs(sum(weights.values()) - 1.0) < 0.01, (
                f"weights must sum to ~1.0; got {weights}"
            )
            self._weights = weights
        else:
            self._weights = dict(DEFAULT_WEIGHTS)

    # ──────────────────────────────────────────────────────────────────
    # Spec entry
    # ──────────────────────────────────────────────────────────────────

    def assess_burnout_risk(
        self, staff_code: str, today: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Returns {risk_score, risk_level, signals, recommendations,
        alert: dict|None, meta}.

        Returns {} when the staff has opted out of wellness monitoring
        (wellness_monitoring_disabled=true on user record), or when
        staff is unknown. Defensive: never raises, never produces
        speculative emotional/medical claims.
        """
        if today is None:
            today = date.today()

        staff = self._staff_lookup(staff_code)
        if not staff:
            return {}
        if staff.get("wellness_monitoring_disabled"):
            return {}    # respect opt-out

        # Compute observable signals (each in [0, 1])
        signals = {
            "sustained_pace_deficit": self._signal_pace_deficit(staff_code),
            "alert_frequency":        self._signal_alert_frequency(staff_code),
            "microtask_overflow":     self._signal_microtask_overflow(staff_code),
            "declining_trajectory":   self._signal_declining_trajectory(staff_code),
        }
        for k in self._weights:
            signals.setdefault(k, 0.0)

        # Weighted sum
        risk_score = sum(
            signals[k] * w for k, w in self._weights.items()
        )
        risk_score = max(0.0, min(1.0, risk_score))

        if risk_score < RISK_LOW_CEILING:
            risk_level = "Low"
        elif risk_score < RISK_MODERATE_CEILING:
            risk_level = "Moderate"
        else:
            risk_level = "High"

        recommendations = self._build_recommendations(risk_level, signals)

        alert: Optional[Dict[str, Any]] = None
        if risk_level == "High":
            manager_code = self._manager_lookup(staff_code)
            alert = {
                "staff_code":      staff_code,
                "manager_code":    manager_code or "",
                "risk_level":      "High",
                "risk_score":      round(risk_score, 3),
                "recommendations": recommendations,
                "assessed_at":     datetime.now(timezone.utc).isoformat(),
            }

        return {
            "risk_score":       round(risk_score, 3),
            "risk_level":       risk_level,
            "signals":          {k: round(v, 3) for k, v in signals.items()},
            "recommendations":  recommendations,
            "alert":            alert,
            "meta": {
                "staff_code":   staff_code,
                "today":        today.isoformat(),
                "weights":      self._weights,
                "thresholds":   {
                    "low_ceiling":      RISK_LOW_CEILING,
                    "moderate_ceiling": RISK_MODERATE_CEILING,
                    "high_floor":       RISK_HIGH_FLOOR,
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Signal computations (each returns 0..1)
    # ──────────────────────────────────────────────────────────────────

    def _signal_pace_deficit(self, staff_code: str) -> float:
        """Fraction of last N periods finished below 80%."""
        history = self._bsc_history(staff_code, PACE_DEFICIT_LOOKBACK) or []
        if not history:
            return 0.0
        below = sum(1 for _, pct in history if pct is not None and pct < PACE_DEFICIT_THRESHOLD_PCT)
        return below / len(history)

    def _signal_alert_frequency(self, staff_code: str) -> float:
        """Saturated linear: 8+ alerts → 1.0; 0 → 0.0."""
        n = self._alerts_in_window(staff_code, ALERT_LOOKBACK_DAYS) or 0
        return min(n / ALERT_FREQUENCY_SATURATION, 1.0)

    def _signal_microtask_overflow(self, staff_code: str) -> float:
        """Saturated linear: 5+ stale tasks → 1.0; 0 → 0.0."""
        n = self._stale_microtasks(staff_code, MICROTASK_OVERFLOW_DAYS) or 0
        return min(n / MICROTASK_OVERFLOW_SATURATION, 1.0)

    def _signal_declining_trajectory(self, staff_code: str) -> float:
        """Returns 1.0 if the last 3 periods are strictly decreasing,
        0.5 if monotonically non-increasing, 0.0 otherwise."""
        history = self._bsc_history(staff_code, TRAJECTORY_LOOKBACK) or []
        if len(history) < TRAJECTORY_LOOKBACK:
            return 0.0
        # history is most-recent first → reverse for chronological
        chrono = list(reversed(history))
        values = [pct for _, pct in chrono if pct is not None]
        if len(values) < TRAJECTORY_LOOKBACK:
            return 0.0
        if all(values[i+1] < values[i] for i in range(len(values) - 1)):
            return 1.0
        if all(values[i+1] <= values[i] for i in range(len(values) - 1)):
            return 0.5
        return 0.0

    def _build_recommendations(
        self, risk_level: str, signals: Dict[str, float],
    ) -> List[str]:
        """Conservative recommendations only. NEVER medical/clinical."""
        if risk_level == "Low":
            return []
        recs: List[str] = []
        if risk_level == "Moderate":
            recs.append(
                "Schedule a 1:1 conversation to check in on workload "
                "and priorities"
            )
        else:  # High
            recs.append(
                "Schedule a 1:1 conversation as soon as possible to "
                "discuss workload and pace"
            )
            recs.append(
                "Review whether current targets are realistic given "
                "recent performance and capacity"
            )
        if signals.get("microtask_overflow", 0) > 0.6:
            recs.append(
                "Help triage and clear overdue micro-tasks; reassign "
                "if appropriate"
            )
        if signals.get("alert_frequency", 0) > 0.5:
            recs.append(
                "Review the pattern of recent pace alerts together "
                "to identify root causes"
            )
        if signals.get("declining_trajectory", 0) > 0.5:
            recs.append(
                "Examine what changed across the last few periods "
                "(workload shift, team changes, system issues, etc.)"
            )
        return recs


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _safe_load(path: Path, default):
    try:
        from utils.db import db
        return db.load_json(path, default=default)
    except Exception as e:
        logger.warning("wellness: could not load %s: %s", path, e)
        return default


def _default_staff_lookup(staff_code: str) -> Optional[dict]:
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return None
    for username, info in users.items():
        if isinstance(info, dict) and str(info.get("staff_code", "")) == str(staff_code):
            return {**info, "username": username}
    return None


def _default_bsc_history(staff_code: str, n: int) -> List[Tuple[str, float]]:
    raw = _safe_load(DATA_DIR / "bsc_scores.json", {})
    if not isinstance(raw, dict):
        return []
    entries = raw.get(str(staff_code), [])
    if isinstance(entries, dict):
        pairs = sorted(entries.items(), key=lambda kv: kv[0], reverse=True)
        return [(p, float(v)) for p, v in pairs[:n] if v is not None]
    if isinstance(entries, list):
        try:
            entries = sorted(
                [e for e in entries if isinstance(e, dict)],
                key=lambda e: e.get("period", ""), reverse=True,
            )
        except Exception:
            pass
        out = []
        for e in entries[:n]:
            p = e.get("period")
            v = e.get("overall_pct") or e.get("overall") or e.get("score")
            if p and v is not None:
                try:
                    out.append((p, float(v)))
                except (TypeError, ValueError):
                    continue
        return out
    return []


def _default_alerts_in_window(staff_code: str, days: int) -> int:
    """Count #11 nudge alerts (not recognitions) in the last N days."""
    raw = _safe_load(DATA_DIR / "nudges.json", [])
    if not isinstance(raw, list):
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    count = 0
    for n in raw:
        if not isinstance(n, dict):
            continue
        if str(n.get("staff_code", "")) != str(staff_code):
            continue
        if n.get("type") != "alert":
            continue
        created = n.get("created_at") or n.get("generated_at", "")
        if created and created >= cutoff:
            count += 1
    return count


def _default_stale_microtasks(staff_code: str, age_days: int) -> int:
    """Count incomplete micro-tasks older than age_days."""
    raw = _safe_load(DATA_DIR / "microtasks.json", [])
    if not isinstance(raw, list):
        return 0
    cutoff = (date.today() - timedelta(days=age_days)).isoformat()
    count = 0
    for t in raw:
        if not isinstance(t, dict):
            continue
        if str(t.get("staff_code", "")) != str(staff_code):
            continue
        if t.get("completed_at"):
            continue
        for_date = t.get("for_date", "")
        if for_date and for_date < cutoff:
            count += 1
    return count


def _default_manager_lookup(staff_code: str) -> Optional[str]:
    """Find first manager via target_cascade.json allocations."""
    cascade = _safe_load(DATA_DIR / "target_cascade.json", {})
    if not isinstance(cascade, dict):
        return None
    for _, block in cascade.items():
        if not isinstance(block, dict):
            continue
        for alloc in block.get("allocations", []) or []:
            if isinstance(alloc, dict) and str(alloc.get("to_code", "")) == str(staff_code):
                return str(block.get("from_code", ""))
    return None


# ─────────────────────────────────────────────────────────────────────
# Persistence (alerts only, signals are NOT persisted)
# ─────────────────────────────────────────────────────────────────────

def save_alert(alert: dict) -> bool:
    """Persist a high-risk alert. Per the privacy rules, only the alert
    record is written — not the underlying signal values used to derive it.
    """
    if not alert or alert.get("risk_level") != "High":
        return False
    try:
        from utils.db import db
        existing = db.load_json(ALERTS_FILE, default=[])
    except Exception:
        existing = []
    if not isinstance(existing, list):
        existing = []
    # Idempotent: don't duplicate same staff alert on same day
    today_str = datetime.now(timezone.utc).date().isoformat()
    sc = str(alert.get("staff_code", ""))
    existing = [
        a for a in existing
        if not (
            isinstance(a, dict)
            and str(a.get("staff_code", "")) == sc
            and (a.get("assessed_at", "")[:10] == today_str)
        )
    ]
    existing.append(alert)
    try:
        from utils.db import db
        db.save_json(ALERTS_FILE, existing)
        return True
    except Exception as e:
        logger.error("wellness: could not save alert: %s", e)
        return False


def list_alerts_for_manager(manager_code: str) -> List[dict]:
    try:
        from utils.db import db
        all_alerts = db.load_json(ALERTS_FILE, default=[])
    except Exception:
        return []
    if not isinstance(all_alerts, list):
        return []
    return [
        a for a in all_alerts
        if isinstance(a, dict) and str(a.get("manager_code", "")) == str(manager_code)
    ]


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.wellness self-test")

    # Mock data for several risk levels
    staff_data = {
        "S100": {"full_name": "OK", "wellness_monitoring_disabled": False},   # low risk
        "S200": {"full_name": "Strained", "wellness_monitoring_disabled": False},  # high
        "S300": {"full_name": "Opted Out", "wellness_monitoring_disabled": True},
        "S400": {"full_name": "Moderate", "wellness_monitoring_disabled": False},
    }
    history_data = {
        # Low: 4 periods at 95-110%
        "S100": [("2026-04", 105), ("2026-03", 110), ("2026-02", 100), ("2026-01", 95)],
        # High risk: 4 periods steadily declining + below 80%
        "S200": [("2026-04", 50), ("2026-03", 60), ("2026-02", 70), ("2026-01", 75)],
        # Moderate: 1 below threshold + 1 declining
        "S400": [("2026-04", 75), ("2026-03", 82), ("2026-02", 88), ("2026-01", 92)],
    }
    alerts_data = {
        "S100": 0,
        "S200": 8,    # max
        "S400": 3,
    }
    stale_data = {
        "S100": 0,
        "S200": 6,
        "S400": 2,
    }
    manager_data = {
        "S100": "MGR1",
        "S200": "MGR1",
        "S400": "MGR2",
    }

    eng = WellnessEngine(
        staff_lookup_fn=lambda sc: staff_data.get(sc),
        bsc_history_fn=lambda sc, n: history_data.get(sc, [])[:n],
        alerts_in_window_fn=lambda sc, d: alerts_data.get(sc, 0),
        stale_microtasks_fn=lambda sc, a: stale_data.get(sc, 0),
        manager_lookup_fn=lambda sc: manager_data.get(sc),
    )

    # Case 1: Low risk
    r = eng.assess_burnout_risk("S100", today=date(2026, 4, 29))
    assert r["risk_level"] == "Low"
    assert r["alert"] is None
    assert r["recommendations"] == []
    print(f"  ✅ S100 Low: score={r['risk_score']}, signals={r['signals']}")

    # Case 2: High risk → alert with manager
    r = eng.assess_burnout_risk("S200", today=date(2026, 4, 29))
    assert r["risk_level"] == "High"
    assert r["alert"] is not None
    assert r["alert"]["manager_code"] == "MGR1"
    assert r["alert"]["risk_level"] == "High"
    assert len(r["recommendations"]) >= 2
    # Honesty rule: no medical/emotional claims
    joined = " ".join(r["recommendations"]).lower()
    forbidden = ["depressed", "burnt out", "stress disorder", "mental health"]
    for word in forbidden:
        assert word not in joined, f"forbidden word in recommendations: {word!r}"
    print(f"  ✅ S200 High: score={r['risk_score']}, manager={r['alert']['manager_code']}, "
          f"{len(r['recommendations'])} conservative recs")

    # Case 3: Opt-out → empty
    r = eng.assess_burnout_risk("S300")
    assert r == {}
    print(f"  ✅ S300 opted out → {{}}")

    # Case 4: Moderate
    r = eng.assess_burnout_risk("S400")
    assert r["risk_level"] in ("Low", "Moderate")
    assert r["alert"] is None
    print(f"  ✅ S400: score={r['risk_score']}, level={r['risk_level']}")

    # Case 5: Unknown staff → empty
    assert eng.assess_burnout_risk("UNKNOWN") == {}
    print(f"  ✅ unknown → {{}}")

    # Case 6: Signal computations
    # Pace deficit on S200: 4/4 = 1.0
    sig = eng._signal_pace_deficit("S200")
    assert sig == 1.0
    # Alert frequency on S200: 8/8 = 1.0
    sig = eng._signal_alert_frequency("S200")
    assert sig == 1.0
    # Trajectory on S200: 75 → 70 → 60 → 50 (chronological), strictly decreasing → 1.0
    sig = eng._signal_declining_trajectory("S200")
    assert sig == 1.0, f"got {sig}"
    print(f"  ✅ signal computations correct")

    # Case 7: BADGES catalog spec compliance — no, that's #17. Skip.
    # Verify: 100% of high-risk cases produce a non-None alert (G30 claim)
    high_risk_staff = [sc for sc in ("S100", "S200", "S400")
                       if (r := eng.assess_burnout_risk(sc)).get("risk_level") == "High"]
    for sc in high_risk_staff:
        r = eng.assess_burnout_risk(sc)
        assert r["alert"] is not None, f"{sc} High but no alert"
    print(f"  ✅ 100% high-risk cases produce alerts ({len(high_risk_staff)} cases)")

    print("\n  ALL TESTS PASSED")
