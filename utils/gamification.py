"""utils.gamification — Gamification & Team Competitions
(Standard #17, v5.44).

Per the master spec:

    class GamificationEngine:
        BADGES = {
            "100_percent_achiever": "3 months at 100%+",
            "most_improved":         "1.5 point improvement",
        }
        def award_badge(self, staff_code, achievement_type):
            self.add_badge_to_profile(staff_code, achievement_type)
            self.announce_in_feed(staff_code, self.BADGES[achievement_type])

Verification:
  - 50%+ staff actively engaged ← deployed-runtime behavioral metric
                                   (whether staff log in, react to
                                   badges, etc.) OUT OF SCOPE.

The verifiable structural claim: given labeled BSC histories, the
engine awards the correct badges ≥90% of the time. Audit gate G28
enforces this.

Two halves of the standard
--------------------------
1. Badges (per-staff achievements based on observable history)
2. Team competitions (leaderboards by branch / unit)

Both produce events (badge_awarded, leaderboard_published) that the
notification feed can announce. The engine is stateless; persistence
helpers write to data/badges.json + data/leaderboards.json.

Honesty rules (same as prior engines)
-------------------------------------
The engine awards badges ONLY when the observable trigger condition
is met. NEVER fabricates achievements. NEVER awards based on
predicted/forecast values — only on materialised history.

Available badges
----------------
The spec ships two examples; we extend with a small honest set,
each with a strictly checkable trigger:

  100_percent_achiever : ≥3 consecutive periods at 100%+ overall BSC
  most_improved        : delta of +1.5 in overall BSC vs prior period
  consistent_high      : ≥6 consecutive periods at 90%+ overall BSC
  comeback_kid         : prior period <70%, current period ≥100%
  team_player          : averaged 100%+ AND unit ranks top quartile
  perfect_quarter      : 3 consecutive monthly periods at 100%+ on
                          ALL assigned KPIs (not just the average)

All triggers are computable from data we already have (BSC history).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.gamification")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
BADGES_FILE = DATA_DIR / "badges.json"
LEADERBOARDS_FILE = DATA_DIR / "leaderboards.json"


# ─────────────────────────────────────────────────────────────────────
# Badge catalog
# ─────────────────────────────────────────────────────────────────────

BADGES: Dict[str, str] = {
    "100_percent_achiever":  "3 consecutive periods at 100%+",
    "most_improved":          "Improvement of 1.5 points period-on-period",
    "consistent_high":        "6 consecutive periods at 90%+",
    "comeback_kid":           "Recovered from <70% to ≥100% in one period",
    "team_player":            "100%+ average AND unit ranks top quartile",
    "perfect_quarter":        "3 consecutive periods at 100%+ on ALL KPIs",
}

# Trigger thresholds (configurable — kept as constants for easy review)
THRESHOLD_100_ACHIEVER_PERIODS  = 3
THRESHOLD_100_ACHIEVER_PCT      = 100.0
THRESHOLD_MOST_IMPROVED_DELTA   = 1.5
THRESHOLD_CONSISTENT_HIGH_PERIODS = 6
THRESHOLD_CONSISTENT_HIGH_PCT     = 90.0
THRESHOLD_COMEBACK_BEFORE         = 70.0
THRESHOLD_COMEBACK_AFTER          = 100.0
THRESHOLD_TEAM_PLAYER_AVG_PCT     = 100.0
THRESHOLD_PERFECT_QUARTER_PERIODS = 3


# ─────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Badge:
    id:             str = ""
    staff_code:     str = ""
    badge_type:     str = ""
    description:    str = ""
    awarded_for:    str = ""    # e.g. "2026-04" period that triggered it
    awarded_at:     str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence:       Dict[str, Any] = field(default_factory=dict)


@dataclass
class LeaderboardRow:
    rank:                  int = 0
    unit:                  str = ""
    avg_achievement_pct:   float = 0.0
    staff_count:           int = 0
    top_quartile:          bool = False


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class GamificationEngine:
    """Standard #17 — Gamification & Team Competitions.

    Badge awards are stateless per-call. Persistence is the caller's
    responsibility (use save_badges / save_leaderboard).
    """

    BADGES = BADGES   # spec compliance — class attribute mirrors module dict

    def __init__(
        self,
        bsc_history_fn:    Optional[Callable[[str, int], List[Tuple[str, float]]]] = None,
        kpi_history_fn:    Optional[Callable[[str, int], List[dict]]] = None,
        staff_lookup_fn:   Optional[Callable[[str], Optional[dict]]] = None,
        unit_roster_fn:    Optional[Callable[[str], List[str]]] = None,
        all_units_fn:      Optional[Callable[[], List[str]]] = None,
    ):
        """All collaborators injectable for testability.

        bsc_history_fn(staff_code, n) → [(period, overall_pct), ...]
            Most-recent-first list of (period, overall achievement %)
            for the last n periods. Default reads bsc_engine.

        kpi_history_fn(staff_code, n) → list[dict]
            Per-period KPI breakdown. Each entry has period and a list
            of {kpi_id, achievement_pct}. For perfect_quarter check.

        staff_lookup_fn(staff_code) → dict | None
            Standard staff record (for unit lookup).

        unit_roster_fn(unit_name) → list[staff_codes]
        all_units_fn() → list of all known unit names

        Defaults read from bsc_engine + users.json.
        """
        self._bsc_history    = bsc_history_fn  or _default_bsc_history
        self._kpi_history    = kpi_history_fn  or _default_kpi_history
        self._staff_lookup   = staff_lookup_fn or _default_staff_lookup
        self._unit_roster    = unit_roster_fn  or _default_unit_roster
        self._all_units      = all_units_fn    or _default_all_units

    # ──────────────────────────────────────────────────────────────────
    # Spec entry
    # ──────────────────────────────────────────────────────────────────

    def award_badge(self, staff_code: str, achievement_type: str,
                    period: Optional[str] = None) -> Optional[Badge]:
        """Award a specific badge if the trigger condition is met.

        This is the spec entry. Returns the Badge if awarded; None if
        the trigger isn't met (no fabrication, no silent
        approximation).
        """
        if achievement_type not in BADGES:
            return None
        check_method = getattr(self, f"_check_{achievement_type}", None)
        if not check_method:
            return None
        result = check_method(staff_code, period)
        if not result:
            return None
        evidence = result if isinstance(result, dict) else {}
        return Badge(
            id=          f"{staff_code}:{achievement_type}:{evidence.get('period', period or '')}",
            staff_code=  staff_code,
            badge_type=  achievement_type,
            description= BADGES[achievement_type],
            awarded_for= evidence.get("period", period or ""),
            evidence=    evidence,
        )

    def evaluate_all_badges(self, staff_code: str,
                             period: Optional[str] = None) -> List[Badge]:
        """Run every badge check for a staff member; return all earned."""
        out: List[Badge] = []
        for bt in BADGES:
            b = self.award_badge(staff_code, bt, period=period)
            if b:
                out.append(b)
        return out

    # ──────────────────────────────────────────────────────────────────
    # Badge triggers — each returns evidence dict if earned, else None
    # ──────────────────────────────────────────────────────────────────

    def _check_100_percent_achiever(self, staff_code: str,
                                     period: Optional[str]) -> Optional[dict]:
        history = self._bsc_history(staff_code, THRESHOLD_100_ACHIEVER_PERIODS) or []
        if len(history) < THRESHOLD_100_ACHIEVER_PERIODS:
            return None
        if all(pct is not None and pct >= THRESHOLD_100_ACHIEVER_PCT
               for _, pct in history):
            return {
                "period":  history[0][0],
                "periods": [p for p, _ in history],
                "values":  [pct for _, pct in history],
            }
        return None

    def _check_most_improved(self, staff_code: str,
                              period: Optional[str]) -> Optional[dict]:
        history = self._bsc_history(staff_code, 2) or []
        if len(history) < 2:
            return None
        cur_period, cur_pct = history[0]
        prev_period, prev_pct = history[1]
        if cur_pct is None or prev_pct is None:
            return None
        delta = cur_pct - prev_pct
        if delta >= THRESHOLD_MOST_IMPROVED_DELTA:
            return {
                "period":     cur_period,
                "prev":       prev_pct,
                "current":    cur_pct,
                "delta":      delta,
            }
        return None

    def _check_consistent_high(self, staff_code: str,
                                period: Optional[str]) -> Optional[dict]:
        history = self._bsc_history(staff_code, THRESHOLD_CONSISTENT_HIGH_PERIODS) or []
        if len(history) < THRESHOLD_CONSISTENT_HIGH_PERIODS:
            return None
        if all(pct is not None and pct >= THRESHOLD_CONSISTENT_HIGH_PCT
               for _, pct in history):
            return {
                "period":  history[0][0],
                "periods": [p for p, _ in history],
                "values":  [pct for _, pct in history],
            }
        return None

    def _check_comeback_kid(self, staff_code: str,
                             period: Optional[str]) -> Optional[dict]:
        history = self._bsc_history(staff_code, 2) or []
        if len(history) < 2:
            return None
        cur_period, cur_pct = history[0]
        _, prev_pct = history[1]
        if cur_pct is None or prev_pct is None:
            return None
        if prev_pct < THRESHOLD_COMEBACK_BEFORE and cur_pct >= THRESHOLD_COMEBACK_AFTER:
            return {
                "period":  cur_period,
                "prev":    prev_pct,
                "current": cur_pct,
            }
        return None

    def _check_team_player(self, staff_code: str,
                            period: Optional[str]) -> Optional[dict]:
        """100%+ average + unit ranks top quartile."""
        history = self._bsc_history(staff_code, 1) or []
        if not history:
            return None
        cur_period, cur_pct = history[0]
        if cur_pct is None or cur_pct < THRESHOLD_TEAM_PLAYER_AVG_PCT:
            return None
        # Get staff's unit
        staff = self._staff_lookup(staff_code) or {}
        unit = staff.get("unit") or staff.get("department")
        if not unit:
            return None
        # Compute unit average in same period
        leaderboard = self._build_leaderboard_for_period(cur_period)
        if not leaderboard:
            return None
        # Find this unit's rank
        for row in leaderboard:
            if row.unit == unit and row.top_quartile:
                return {
                    "period":      cur_period,
                    "unit":        unit,
                    "unit_rank":   row.rank,
                    "unit_avg":    row.avg_achievement_pct,
                }
        return None

    def _check_perfect_quarter(self, staff_code: str,
                                period: Optional[str]) -> Optional[dict]:
        kpi_history = self._kpi_history(
            staff_code, THRESHOLD_PERFECT_QUARTER_PERIODS,
        ) or []
        if len(kpi_history) < THRESHOLD_PERFECT_QUARTER_PERIODS:
            return None
        all_at_100 = []
        for snapshot in kpi_history:
            if not isinstance(snapshot, dict):
                return None
            kpis = snapshot.get("kpis") or []
            if not kpis:
                return None
            for k in kpis:
                pct = k.get("achievement_pct")
                if pct is None or pct < 100.0:
                    return None
            all_at_100.append(snapshot.get("period"))
        return {
            "period":  kpi_history[0].get("period"),
            "periods": all_at_100,
        }

    # ──────────────────────────────────────────────────────────────────
    # Team leaderboards
    # ──────────────────────────────────────────────────────────────────

    def build_leaderboard(self, period: str) -> List[LeaderboardRow]:
        """Return a leaderboard of all units for the period, sorted
        by avg achievement_pct desc."""
        return self._build_leaderboard_for_period(period)

    def _build_leaderboard_for_period(self, period: str) -> List[LeaderboardRow]:
        units = self._all_units() or []
        rows: List[LeaderboardRow] = []
        for unit in units:
            roster = self._unit_roster(unit) or []
            if not roster:
                continue
            achievements: List[float] = []
            for sc in roster:
                history = self._bsc_history(sc, 1) or []
                if history:
                    p, pct = history[0]
                    if p == period and pct is not None:
                        achievements.append(pct)
            if not achievements:
                continue
            avg = sum(achievements) / len(achievements)
            rows.append(LeaderboardRow(
                unit=                 unit,
                avg_achievement_pct=  avg,
                staff_count=          len(achievements),
                top_quartile=         False,   # filled in after sort
            ))
        rows.sort(key=lambda r: r.avg_achievement_pct, reverse=True)
        for i, row in enumerate(rows):
            row.rank = i + 1
        # Mark top quartile
        n = len(rows)
        cutoff = max(1, n // 4)
        for i, row in enumerate(rows):
            row.top_quartile = i < cutoff
        return rows


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _safe_load(path: Path, default):
    try:
        from utils.db import db
        return db.load_json(path, default=default)
    except Exception as e:
        logger.warning("gamification: could not load %s: %s", path, e)
        return default


def _default_bsc_history(staff_code: str, n: int) -> List[Tuple[str, float]]:
    """Best-effort: read data/bsc_scores.json. Returns [] if absent."""
    raw = _safe_load(DATA_DIR / "bsc_scores.json", {})
    if not isinstance(raw, dict):
        return []
    entries = raw.get(str(staff_code), [])
    if isinstance(entries, dict):
        pairs = sorted(entries.items(), key=lambda kv: kv[0], reverse=True)
        out: List[Tuple[str, float]] = []
        for p, v in pairs[:n]:
            try:
                out.append((p, float(v)))
            except (TypeError, ValueError):
                continue
        return out
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


def _default_kpi_history(staff_code: str, n: int) -> List[dict]:
    """Read per-period KPI breakdowns. Default returns [] (data not yet
    in seed files)."""
    raw = _safe_load(DATA_DIR / "bsc_kpi_history.json", {})
    if not isinstance(raw, dict):
        return []
    entries = raw.get(str(staff_code), [])
    if not isinstance(entries, list):
        return []
    try:
        entries = sorted(
            [e for e in entries if isinstance(e, dict)],
            key=lambda e: e.get("period", ""), reverse=True,
        )
    except Exception:
        pass
    return entries[:n]


def _default_staff_lookup(staff_code: str) -> Optional[dict]:
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return None
    for username, info in users.items():
        if isinstance(info, dict) and str(info.get("staff_code", "")) == str(staff_code):
            return {**info, "username": username}
    return None


def _default_unit_roster(unit: str) -> List[str]:
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return []
    out: List[str] = []
    for _, info in users.items():
        if not isinstance(info, dict):
            continue
        if not info.get("active"):
            continue
        if (info.get("unit") or info.get("department")) == unit:
            sc = str(info.get("staff_code", ""))
            if sc:
                out.append(sc)
    return out


def _default_all_units() -> List[str]:
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return []
    units: set = set()
    for _, info in users.items():
        if isinstance(info, dict) and info.get("active"):
            unit = info.get("unit") or info.get("department")
            if unit:
                units.add(unit)
    return sorted(units)


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_badges(badges: List[Badge]) -> int:
    if not badges:
        return 0
    try:
        from utils.db import db
        existing = db.load_json(BADGES_FILE, default=[])
    except Exception:
        existing = []
    if not isinstance(existing, list):
        existing = []
    by_id = {
        b.get("id"): b for b in existing if isinstance(b, dict) and b.get("id")
    }
    for b in badges:
        d = asdict(b)
        by_id[b.id] = d
    out = list(by_id.values())
    try:
        from utils.db import db
        db.save_json(BADGES_FILE, out)
        return len(badges)
    except Exception as e:
        logger.error("gamification: could not save badges: %s", e)
        return 0


def list_badges_for_staff(staff_code: str) -> List[dict]:
    try:
        from utils.db import db
        all_badges = db.load_json(BADGES_FILE, default=[])
    except Exception:
        return []
    if not isinstance(all_badges, list):
        return []
    return [
        b for b in all_badges
        if isinstance(b, dict) and str(b.get("staff_code", "")) == str(staff_code)
    ]


def save_leaderboard(period: str, rows: List[LeaderboardRow]) -> bool:
    if not period or not rows:
        return False
    try:
        from utils.db import db
        existing = db.load_json(LEADERBOARDS_FILE, default={})
    except Exception:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing[period] = [asdict(r) for r in rows]
    try:
        from utils.db import db
        db.save_json(LEADERBOARDS_FILE, existing)
        return True
    except Exception as e:
        logger.error("gamification: could not save leaderboard: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.gamification self-test")

    history = {
        # Always 100%+ for last 3 periods → 100_percent_achiever
        "S100": [("2026-04", 110), ("2026-03", 105), ("2026-02", 100)],
        # Big jump from 80 → 95 → +1.5 not enough; from 80→82 not improved
        # Set: prev=80, current=95 → delta=15 → most_improved
        "S101": [("2026-04", 95), ("2026-03", 80)],
        # Recovery from 65 → 102 → comeback_kid + most_improved
        "S102": [("2026-04", 102), ("2026-03", 65)],
        # 6 consecutive 90+ → consistent_high
        "S103": [("2026-04", 95), ("2026-03", 92), ("2026-02", 91),
                 ("2026-01", 93), ("2025-12", 96), ("2025-11", 90)],
        # Steady 70%, no badges
        "S104": [("2026-04", 70), ("2026-03", 70), ("2026-02", 70)],
    }
    kpi_history_data = {
        # Perfect quarter: 3 periods, all KPIs at 100+
        "S100": [
            {"period": "2026-04", "kpis": [{"achievement_pct": 110}, {"achievement_pct": 105}]},
            {"period": "2026-03", "kpis": [{"achievement_pct": 102}, {"achievement_pct": 108}]},
            {"period": "2026-02", "kpis": [{"achievement_pct": 100}, {"achievement_pct": 101}]},
        ],
    }
    staff_data = {
        "S100": {"unit": "Mombasa"},
        "S101": {"unit": "Nairobi"},
        "S104": {"unit": "Mombasa"},
    }
    units_data = ["Mombasa", "Nairobi"]
    rosters_data = {"Mombasa": ["S100", "S104"], "Nairobi": ["S101"]}

    eng = GamificationEngine(
        bsc_history_fn=lambda sc, n: history.get(sc, [])[:n],
        kpi_history_fn=lambda sc, n: kpi_history_data.get(sc, [])[:n],
        staff_lookup_fn=lambda sc: staff_data.get(sc),
        unit_roster_fn=lambda u: rosters_data.get(u, []),
        all_units_fn=lambda: units_data,
    )

    # Case 1: 100_percent_achiever
    b = eng.award_badge("S100", "100_percent_achiever")
    assert b and b.badge_type == "100_percent_achiever"
    print(f"  ✅ S100 100_percent_achiever: {b.evidence['values']}")

    # Case 2: Not eligible (S104)
    b = eng.award_badge("S104", "100_percent_achiever")
    assert b is None
    print(f"  ✅ S104 not eligible for 100_percent_achiever")

    # Case 3: most_improved
    b = eng.award_badge("S101", "most_improved")
    assert b and b.evidence["delta"] == 15
    print(f"  ✅ S101 most_improved: delta={b.evidence['delta']}")

    # Case 4: comeback_kid
    b = eng.award_badge("S102", "comeback_kid")
    assert b and b.evidence["prev"] == 65 and b.evidence["current"] == 102
    print(f"  ✅ S102 comeback_kid: 65 → 102")

    # Case 5: consistent_high
    b = eng.award_badge("S103", "consistent_high")
    assert b and len(b.evidence["periods"]) == 6
    print(f"  ✅ S103 consistent_high: 6 periods")

    # Case 6: perfect_quarter
    b = eng.award_badge("S100", "perfect_quarter")
    assert b
    print(f"  ✅ S100 perfect_quarter: {b.evidence['periods']}")

    # Case 7: Unknown badge type
    b = eng.award_badge("S100", "unknown_badge_xyz")
    assert b is None
    print(f"  ✅ unknown badge type returns None")

    # Case 8: evaluate_all_badges for S100
    badges = eng.evaluate_all_badges("S100")
    types = {b.badge_type for b in badges}
    # Should include at least 100_percent_achiever and perfect_quarter
    # (Plus most_improved / consistent_high depending on history depth)
    assert "100_percent_achiever" in types
    assert "perfect_quarter" in types
    print(f"  ✅ S100 earned: {sorted(types)}")

    # Case 9: leaderboard
    lb = eng.build_leaderboard("2026-04")
    assert len(lb) == 2  # Mombasa + Nairobi
    # Mombasa avg = (110 + 70) / 2 = 90; Nairobi = 95 → Nairobi #1
    assert lb[0].unit == "Nairobi"
    assert lb[0].rank == 1
    assert lb[0].top_quartile is True
    print(f"  ✅ leaderboard: #{lb[0].rank} {lb[0].unit} ({lb[0].avg_achievement_pct:.1f})")

    # Case 10: BADGES catalog matches spec
    assert "100_percent_achiever" in BADGES
    assert "most_improved" in BADGES
    print(f"  ✅ BADGES catalog: {len(BADGES)} entries")

    print("\n  ALL TESTS PASSED")
