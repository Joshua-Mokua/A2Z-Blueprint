"""utils.daily_strategy_integration — Strategy-to-BSC Daily Integration
(Standard ENH-153, v10.137). Phase 1 Strategy Module — sixth engine.
**Long-awaited link between Strategy module and existing BSC engine.**

Per Continuation.docx §Standard #153 (Eco Bank QA spec):
    DailyStrategyIntegration — daily strategy metrics visible in
    individual BSC dashboards. Every employee sees their contribution
    to strategy daily (not just quarterly).

WHAT THIS MODULE SHIPS
----------------------
1. DailyStrategyIntegration class with:
   - create_personal_strategy_scorecard(employee_code, period=None) —
     produces per-employee daily strategy view: which pillars they
     contribute to, their KPIs, today's targets/actuals, trend, nudge
   - map_employee_to_strategy(employee_code) — resolves employee →
     department → workstreams → pillars (via reverse lookup)
   - get_bank_strategy_health() — aggregate of all pillar health
   - get_priority_action(employee_code) — biggest gap → action
   - get_nudge(kpi) — rule-based motivational/corrective message

2. BSC pillar → Strategic pillar mapping (default):
   - financial_score → Sustainable Growth (CFO pillar)
   - customer_score → Customer Experience Excellence (CCO pillar)
   - process_score  → Operational Excellence (COO pillar)
   - people_score   → Sustainable Growth (people-as-investment dim)

3. Honest cadence disclosure: BSC scorecards are quarterly. The "daily"
   view presents the latest available period as a snapshot with
   explicit `cadence_note` field. Banks running daily-cadence OLTP
   inject their own daily aggregator via a hook (deferred for v10.137).

INTEGRATION WITH EXISTING BSC ENGINE
------------------------------------
This engine READS from data sources that the BSC engine
(utils.bsc_engine) writes to:
- data/bsc_scores.json     — quarterly BSC scorecards (123 rows)
- data/users.json          — employee directory with department
- data/kpi_library.json    — KPI master catalog

It does NOT write to performance.* tables directly (Rule 7 from BSC
contract). Strategy → BSC writes happen via bsc_engine.submit() in
downstream caller code (e.g., the cockpit Streamlit page); this engine
only produces VIEW payloads.

HONESTY DISCIPLINE
------------------
- Cadence: explicit `cadence_note` says "BSC is quarterly; latest
  period rendered as today's snapshot. Daily granularity requires
  bank to inject daily aggregator."
- Trend: computed from current vs prior quarter (the 2 most recent
  periods); when only 1 period available, trend="insufficient_history"
- Nudges are templated, transparent, and reproducible
- Pillar health is the average of contributing BSC pillar scores
  (not a fabricated index)
- When employee not found, returns shape with explicit error rather
  than silent empty result

RELATED STANDARDS
-----------------
- ENH-141 SWOT — provides pillar's external context
- ENH-143 Strategic Pillars — provides pillar definitions
- ENH-145 Enhanced Cascade — provides individual OKRs (not consumed
  yet in v10.137; integration deferred to v10.139 ENH-150 Health
  Dashboard)
- BSC engine (utils.bsc_engine) — read-only consumer of bsc_scores.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.daily_strategy_integration")


# ════════════════════════════════════════════════════════════════════
# BSC pillar → Strategic pillar default mapping
# ════════════════════════════════════════════════════════════════════

# BSC framework: 4 pillars (financial, customer, process, people)
# Strategic framework: 5 pillars from ENH-143
# Mapping is N:M — some BSC pillars contribute to multiple strategic
# pillars. Note: bank's BSC framework (per kpi_library.json) has no
# Risk-specific pillar; operational risk dimensions live under
# process_score, so process_score contributes to both Operational
# Excellence and Risk & Compliance Leadership.
BSC_TO_STRATEGIC_PILLAR = {
    "financial_score": ["Sustainable Growth"],
    "customer_score":  ["Customer Experience Excellence"],
    "process_score":   ["Operational Excellence",
                        "Risk & Compliance Leadership"],
    "people_score":    ["Sustainable Growth",
                        "Customer Experience Excellence"],
}

# BSC pillar target (per ENH-141 convention; 0-5 scale, target=4.0)
BSC_PILLAR_TARGET = 4.0

# Trend thresholds (delta in points on 0-5 scale)
TREND_UP_THRESHOLD = 0.20
TREND_DOWN_THRESHOLD = -0.20


# ════════════════════════════════════════════════════════════════════
# DailyStrategyIntegration
# ════════════════════════════════════════════════════════════════════

class DailyStrategyIntegration:
    """Integrate strategy metrics into daily BSC views.

    Caller pattern:

        from utils.daily_strategy_integration import DailyStrategyIntegration

        integ = DailyStrategyIntegration()
        scorecard = integ.create_personal_strategy_scorecard("301340")
        # scorecard["strategic_pillars"] → list of pillar contributions
        # scorecard["my_impact"] → percentile rank in their pillars
        # scorecard["next_priority_action"] → top action to take
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 daily_aggregator_fn: Optional[
                     Callable[[str, str], Dict]] = None):
        """
        Args:
            data_dir: where to read bsc_scores.json / users.json from.
                Defaults to repo's data/ directory.
            daily_aggregator_fn: optional callable(staff_code, kpi_id) →
                {today_target, today_actual} for true daily-cadence
                values. When None, uses latest quarterly snapshot with
                explicit cadence_note.
        """
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.daily_aggregator_fn = daily_aggregator_fn
        self._users_cache: Optional[Dict] = None
        self._bsc_cache: Optional[List] = None

    # ── Data loaders (cached) ──

    def _load_users(self) -> Dict[str, Dict[str, Any]]:
        if self._users_cache is not None:
            return self._users_cache
        path = self.data_dir / "users.json"
        if not path.exists():
            self._users_cache = {}
            return self._users_cache
        try:
            with open(path, encoding="utf-8") as f:
                self._users_cache = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"users.json unreadable: {e}")
            self._users_cache = {}
        return self._users_cache

    def _load_bsc_scores(self) -> List[Dict[str, Any]]:
        if self._bsc_cache is not None:
            return self._bsc_cache
        path = self.data_dir / "bsc_scores.json"
        if not path.exists():
            self._bsc_cache = []
            return self._bsc_cache
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            self._bsc_cache = d if isinstance(d, list) else (
                list(d.values()) if isinstance(d, dict) else [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"bsc_scores.json unreadable: {e}")
            self._bsc_cache = []
        return self._bsc_cache

    def _find_employee(self, employee_code: str) -> Optional[Dict[str, Any]]:
        """Look up by staff_code OR username."""
        users = self._load_users()
        if not isinstance(users, dict):
            return None
        # First try as username key
        if employee_code in users:
            entry = dict(users[employee_code])
            entry["username"] = employee_code
            return entry
        # Else search by staff_code
        for uname, urec in users.items():
            if isinstance(urec, dict) and urec.get("staff_code") == employee_code:
                entry = dict(urec)
                entry["username"] = uname
                return entry
        return None

    def _employee_bsc_history(
            self, staff_code: str) -> List[Dict[str, Any]]:
        """All BSC scorecards for staff_code, sorted by period_end desc."""
        scores = self._load_bsc_scores()
        history = [r for r in scores
                   if r.get("staff_code") == staff_code]
        history.sort(key=lambda r: r.get("period_end", ""), reverse=True)
        return history

    # ── Employee → strategy mapping ──

    def map_employee_to_strategy(
            self, employee_code: str) -> Dict[str, Any]:
        """Resolve employee → department → workstreams → strategic
        pillars they contribute to.

        Returns:
            {
              "employee":     {full_name, staff_code, department, role, band},
              "department":   str,
              "workstreams":  [list of workstream strings],
              "pillars":      [list of pillar names],
              "found":        bool,
              "error":        str | None
            }
        """
        emp = self._find_employee(employee_code)
        if emp is None:
            return {
                "employee":    None,
                "department":  None,
                "workstreams": [],
                "pillars":     [],
                "found":       False,
                "error":       f"Employee not found: {employee_code}",
            }

        department = emp.get("department")
        # Reverse lookup: department → workstreams → pillars
        try:
            from utils.strategy_decomposition import (
                WORKSTREAM_TO_DEPARTMENTS, PILLAR_TEMPLATES)
        except ImportError:
            logger.warning(
                "strategy_decomposition not importable; pillars empty")
            WORKSTREAM_TO_DEPARTMENTS = {}
            PILLAR_TEMPLATES = []

        workstreams = sorted(
            ws for ws, depts in WORKSTREAM_TO_DEPARTMENTS.items()
            if department and department in depts)

        # Workstream → pillar lookup
        ws_to_pillar = {}
        for tpl in PILLAR_TEMPLATES:
            for ws in tpl.get("workstreams", []):
                ws_to_pillar[ws] = tpl["name"]
        pillars = sorted({ws_to_pillar[ws]
                          for ws in workstreams
                          if ws in ws_to_pillar})

        return {
            "employee": {
                "full_name":  emp.get("full_name"),
                "staff_code": emp.get("staff_code"),
                "department": department,
                "role":       emp.get("role"),
                "band":       emp.get("band"),
                "username":   emp.get("username"),
            },
            "department":  department,
            "workstreams": workstreams,
            "pillars":     pillars,
            "found":       True,
            "error":       None,
        }

    # ── Per-KPI today values + trend + nudge ──

    def _get_today_value(self,
                          staff_code: str,
                          bsc_pillar_field: str,
                          history: List[Dict[str, Any]]
                          ) -> Dict[str, Any]:
        """Compute today's target / actual / trend for a BSC pillar.

        If daily_aggregator_fn is wired, use it. Otherwise:
        - today_actual = latest period's pillar score
        - today_target = BSC_PILLAR_TARGET (4.0)
        - trend = current vs prior period delta
        """
        if self.daily_aggregator_fn is not None:
            try:
                d = self.daily_aggregator_fn(staff_code, bsc_pillar_field)
                return {
                    "today_target":  d.get("today_target",
                                           BSC_PILLAR_TARGET),
                    "today_actual":  d.get("today_actual"),
                    "trend":         d.get("trend", "unknown"),
                    "trend_delta":   d.get("trend_delta"),
                    "cadence":       "daily",
                    "cadence_note":  None,
                }
            except Exception as e:
                logger.warning(
                    f"daily_aggregator_fn failed: {e}; "
                    f"falling back to quarterly snapshot")

        # Fallback: latest quarterly snapshot
        if not history:
            return {
                "today_target":  BSC_PILLAR_TARGET,
                "today_actual":  None,
                "trend":         "no_data",
                "trend_delta":   None,
                "cadence":       "quarterly_proxy",
                "cadence_note":
                    "BSC is quarterly; no scorecard found for this "
                    "employee.",
            }

        latest = history[0]
        today_actual = latest.get(bsc_pillar_field)
        prior = history[1] if len(history) > 1 else None
        if prior is None:
            trend = "insufficient_history"
            trend_delta = None
        else:
            prior_val = prior.get(bsc_pillar_field)
            if (isinstance(today_actual, (int, float))
                    and isinstance(prior_val, (int, float))):
                trend_delta = round(today_actual - prior_val, 2)
                if trend_delta >= TREND_UP_THRESHOLD:
                    trend = "improving"
                elif trend_delta <= TREND_DOWN_THRESHOLD:
                    trend = "declining"
                else:
                    trend = "flat"
            else:
                trend = "unknown"
                trend_delta = None

        return {
            "today_target":  BSC_PILLAR_TARGET,
            "today_actual":  today_actual,
            "trend":         trend,
            "trend_delta":   trend_delta,
            "cadence":       "quarterly_proxy",
            "cadence_note":  (
                f"BSC is quarterly; showing {latest.get('quarter')} "
                f"as today's snapshot. Daily granularity requires bank "
                f"to inject daily_aggregator_fn."),
        }

    def get_nudge(self, kpi_view: Dict[str, Any]) -> str:
        """Rule-based nudge based on KPI status.

        Categories:
        - exceeding: actual > target * 1.10
        - on_track:  target * 0.90 ≤ actual ≤ target * 1.10
        - behind:    actual < target * 0.90
        Plus trend overlay (improving / declining).
        """
        actual = kpi_view.get("today_actual")
        target = kpi_view.get("today_target", BSC_PILLAR_TARGET)
        trend = kpi_view.get("trend", "unknown")
        if not isinstance(actual, (int, float)):
            return "Score not yet recorded — submit your contribution to BSC engine."

        ratio = actual / target if target else 0
        if ratio > 1.10:
            base = f"Strong performance ({actual:.2f}/{target}). Sustain momentum."
        elif ratio >= 0.90:
            base = f"On track ({actual:.2f}/{target}). Push to exceed."
        else:
            gap_pct = (1 - ratio) * 100
            base = (f"Behind target ({actual:.2f}/{target}, gap "
                    f"{gap_pct:.0f}%). Focus on this pillar this week.")

        # Trend overlay
        if trend == "declining":
            return base + " Note: trend is DOWN vs last period."
        if trend == "improving":
            return base + " Note: trend is UP — keep going."
        return base

    # ── Personal scorecard ──

    def create_personal_strategy_scorecard(
            self,
            employee_code: str) -> Dict[str, Any]:
        """Create personal daily strategy scorecard for an employee.

        Returns:
            {
              "employee": {...},
              "strategic_pillars": [
                {
                  "pillar":     str,
                  "my_kpis":    [{kpi, today_target, today_actual,
                                  trend, nudge, cadence}, ...],
                  "pillar_health": float,
                  "my_impact":  float,
                },
                ...
              ],
              "bank_strategy_health": float,
              "next_priority_action": str,
              "cadence_note":         str,
              "found":                bool,
              "error":                str | None,
              "generated_at":         ISO-8601,
            }
        """
        mapping = self.map_employee_to_strategy(employee_code)
        if not mapping["found"]:
            return {
                "employee":             None,
                "strategic_pillars":    [],
                "bank_strategy_health": None,
                "next_priority_action": None,
                "cadence_note":         None,
                "found":                False,
                "error":                mapping["error"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        emp = mapping["employee"]
        staff_code = emp["staff_code"]
        history = self._employee_bsc_history(staff_code)

        # Reverse: which BSC fields contribute to which pillar?
        pillar_to_bsc_fields: Dict[str, List[str]] = {}
        for bsc_field, pillars in BSC_TO_STRATEGIC_PILLAR.items():
            for p in pillars:
                pillar_to_bsc_fields.setdefault(p, []).append(bsc_field)

        # Build per-pillar view
        strategic_pillars_view = []
        for pillar in mapping["pillars"]:
            bsc_fields = pillar_to_bsc_fields.get(pillar, [])
            my_kpis = []
            actuals_for_health: List[float] = []
            for bsc_field in bsc_fields:
                kview = self._get_today_value(
                    staff_code, bsc_field, history)
                kview["kpi"] = bsc_field.replace("_", " ").title()
                kview["nudge"] = self.get_nudge(kview)
                my_kpis.append(kview)
                if isinstance(kview.get("today_actual"), (int, float)):
                    actuals_for_health.append(kview["today_actual"])

            pillar_health = (sum(actuals_for_health) / len(actuals_for_health)
                             if actuals_for_health else None)
            # my_impact: percentile vs all employees in same pillar_field
            # (rule-based: rank latest score against all bsc rows)
            my_impact = self._compute_my_impact_percentile(
                staff_code, bsc_fields)

            strategic_pillars_view.append({
                "pillar":         pillar,
                "my_kpis":        my_kpis,
                "pillar_health":  (round(pillar_health, 2)
                                   if pillar_health is not None else None),
                "my_impact":      my_impact,
            })

        bank_health = self.get_bank_strategy_health()
        priority = self.get_priority_action_from_view(strategic_pillars_view)

        cadence_note = (
            "BSC scorecards in this seed are quarterly. The 'daily' view "
            "presents the latest period as a snapshot. Banks with daily "
            "OLTP feeds inject daily_aggregator_fn to override.")

        return {
            "employee":             emp,
            "strategic_pillars":    strategic_pillars_view,
            "bank_strategy_health": bank_health,
            "next_priority_action": priority,
            "cadence_note":         cadence_note,
            "found":                True,
            "error":                None,
            "generated_at":         datetime.now(
                timezone.utc).isoformat(),
        }

    # ── Aggregates ──

    def _compute_my_impact_percentile(
            self,
            staff_code: str,
            bsc_fields: List[str]) -> Optional[float]:
        """Percentile rank of this employee's average across given
        bsc_fields vs all employees with scores."""
        scores = self._load_bsc_scores()
        if not scores or not bsc_fields:
            return None
        # Latest period per staff
        latest_by_staff: Dict[str, Dict] = {}
        for r in scores:
            sc = r.get("staff_code")
            pe = r.get("period_end", "")
            cur = latest_by_staff.get(sc)
            if cur is None or pe > cur.get("period_end", ""):
                latest_by_staff[sc] = r

        def avg_for(rec):
            vals = [rec.get(f) for f in bsc_fields
                    if isinstance(rec.get(f), (int, float))]
            return sum(vals) / len(vals) if vals else None

        all_avgs = []
        my_avg = None
        for sc, rec in latest_by_staff.items():
            a = avg_for(rec)
            if a is None:
                continue
            all_avgs.append(a)
            if sc == staff_code:
                my_avg = a
        if my_avg is None or not all_avgs:
            return None
        below = sum(1 for v in all_avgs if v < my_avg)
        return round(below / len(all_avgs) * 100, 2)

    def get_bank_strategy_health(self) -> Optional[float]:
        """Average of all BSC pillar scores across all employees in
        the latest period.

        Returns 0-5 score (proportional to BSC scale). When no data,
        returns None.
        """
        scores = self._load_bsc_scores()
        if not scores:
            return None
        # Use only the latest period overall
        latest_period = max(r.get("period_end", "") for r in scores)
        if not latest_period:
            return None
        latest_rows = [r for r in scores
                       if r.get("period_end") == latest_period]
        if not latest_rows:
            return None
        all_vals = []
        for r in latest_rows:
            for fld in ("financial_score", "customer_score",
                        "process_score", "people_score"):
                v = r.get(fld)
                if isinstance(v, (int, float)):
                    all_vals.append(v)
        if not all_vals:
            return None
        return round(sum(all_vals) / len(all_vals), 2)

    def get_priority_action_from_view(
            self,
            strategic_pillars_view: List[Dict[str, Any]]) -> str:
        """Return rule-based 'next priority action' — biggest gap pillar."""
        if not strategic_pillars_view:
            return ("No strategic pillars mapped for this employee. "
                    "Verify department assignment and pillar mapping.")

        # Find pillar with lowest health vs target
        gaps = []
        for sp in strategic_pillars_view:
            health = sp.get("pillar_health")
            if isinstance(health, (int, float)):
                gap = BSC_PILLAR_TARGET - health
                gaps.append((gap, sp["pillar"]))
        if not gaps:
            return ("BSC scores not yet recorded. Submit your "
                    "contribution to BSC engine.")
        gaps.sort(reverse=True)
        biggest_gap, pillar_name = gaps[0]
        if biggest_gap <= 0:
            return f"All pillars meeting target. Sustain {pillar_name} momentum."
        return (f"Biggest gap: {pillar_name} (gap {biggest_gap:.2f} "
                f"points below target {BSC_PILLAR_TARGET}). "
                f"Prioritize this pillar's KPIs this week.")

    def get_priority_action(self, employee_code: str) -> str:
        """Convenience: scorecard + extract priority."""
        scorecard = self.create_personal_strategy_scorecard(employee_code)
        if not scorecard["found"]:
            return scorecard.get("error",
                                 "Could not build priority action.")
        return scorecard.get("next_priority_action") or ""


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrappers
# ════════════════════════════════════════════════════════════════════

def create_personal_strategy_scorecard(
        employee_code: str) -> Dict[str, Any]:
    """Convenience wrapper — instantiate engine and build scorecard."""
    return DailyStrategyIntegration().create_personal_strategy_scorecard(
        employee_code)


def get_bank_strategy_health() -> Optional[float]:
    """Convenience wrapper — bank-level health snapshot."""
    return DailyStrategyIntegration().get_bank_strategy_health()
