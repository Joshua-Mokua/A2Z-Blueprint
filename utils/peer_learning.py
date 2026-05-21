"""utils.peer_learning — Peer Learning Network (Standard #14, v5.41).

Per the master spec:

    class PeerLearningNetwork:
        def share_best_practice(self, staff_code, kpi_id):
            top_performers = self.get_top_performers(kpi_id, limit=5)
            for performer in top_performers:
                self.create_learning_card({"strategies": patterns.key_tactics})

Verification:
  - 5+ best practices shared weekly  ← verifiable in code (G25)

The spec hand-waves on "patterns.key_tactics" — there's no honest way
to extract tactical advice ("I call clients at 7am") from the
observable data we have. So this engine produces what we CAN
honestly assemble:

  - WHO the top performers are (attributable, falsifiable)
  - WHAT we can observe about them (deal mix, segment focus,
    consistent over-performance on prior periods)
  - HOW to engage them ("ask them to share their approach in your
    next 1:1")

The engine explicitly does NOT fabricate tactical content. Real
"key tactics" require human-to-human knowledge transfer; the engine
surfaces top performers and structures the conversation invitation.

Two production paths
--------------------
1. share_best_practice(struggling_staff_code, kpi_id, period) — given
   a staff who's behind on a KPI, find the top performers on that
   KPI in the same period and produce learning cards.

2. match_for_skill(skill_name, requesting_staff_code) — given a
   skill the requester has a gap in, find staff whose assessed level
   exceeds the requirement (and the requester's level). Composes
   with Standard #12 (growth paths).

3. generate_weekly_cards(period, kpis) — batch helper that produces
   one card-set per KPI for the week. Used by the weekly scheduler.

Persistence
-----------
data/learning_cards.json  — rolling list of cards. The engine writes;
                            the UI reads. Each card has an id, week,
                            kpi/skill, performer info, observed
                            patterns, conversation prompts.

learning_cards_results.json — weekly summary. G25 reads this.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.peer_learning")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CARDS_FILE = DATA_DIR / "learning_cards.json"

# ── Spec-aligned defaults ──────────────────────────────────────────────
DEFAULT_TOP_N           = 5      # spec: "limit=5"
DEFAULT_MIN_OUTPERFORM  = Decimal("1.10")   # top performers ≥110% of target
DEFAULT_HISTORY_PERIODS = 3      # how many prior periods to inspect for consistency
WEEKLY_TARGET_CARDS     = 5      # spec verification: "5+ shared weekly"


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class LearningCard:
    """A peer-learning card. Persisted to data/learning_cards.json.

    The card structure is designed to surface what's observable
    (top performer identity + measurable patterns) and frame the
    conversation invitation, NOT fabricate tactical advice.
    """
    id:                   str   = ""
    week:                 str   = ""        # "YYYY-WNN" ISO week
    period:               str   = ""        # "YYYY-MM" or "YYYY-Qn"
    card_type:            str   = ""        # "kpi" | "skill"
    kpi_id:               Optional[str] = None
    skill_name:           Optional[str] = None
    requesting_staff:     Optional[str] = None  # who triggered (for skill cards)
    performer_staff_code: str = ""
    performer_role:       str = ""
    performer_unit:       str = ""
    achievement_pct:      Optional[float] = None    # for kpi cards
    skill_level:          Optional[float] = None    # for skill cards
    observed_patterns:    List[str] = field(default_factory=list)
    conversation_prompts: List[str] = field(default_factory=list)
    consistency_periods:  Optional[int] = None      # how many prior periods
                                                    # they were also on top
    generated_at:         str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class PeerLearningNetwork:
    """Standard #14 — Peer Learning Network.

    Stateless: each call returns 0+ LearningCards. Persistence is the
    caller's responsibility (use save_learning_cards).
    """

    def __init__(
        self,
        kpi_leaderboard_fn:   Optional[Callable[[str, str, int], List[dict]]] = None,
        skill_leaderboard_fn: Optional[Callable[[str, int], List[dict]]] = None,
        staff_lookup_fn:      Optional[Callable[[str], Optional[dict]]] = None,
        target_lookup_fn:     Optional[Callable[[str, str, str], Optional[Decimal]]] = None,
        history_lookup_fn:    Optional[Callable[[str, str, str, int], List[Tuple[str, Decimal, Decimal]]]] = None,
        pipeline_lookup_fn:   Optional[Callable[[str], Dict[str, Any]]] = None,
        top_n: int = DEFAULT_TOP_N,
    ):
        """All collaborators injectable for testability.

        kpi_leaderboard_fn(kpi_id, period, n) -> [{
            "staff_code", "achievement_pct", "actual", "target"
        }]
            Top n performers on a KPI in a period. Default reads
            target_cascade.json + bsc_engine actuals.

        skill_leaderboard_fn(skill_name, n) -> [{
            "staff_code", "level"
        }]
            Top n staff by assessed level for a given skill.
            Default reads data/staff_skills.json.

        staff_lookup_fn(staff_code) -> dict | None
            Standard staff record lookup (role, unit, etc.).

        target_lookup_fn(staff_code, kpi_id, period) -> Decimal | None
            Target lookup (used to compute achievement_pct).

        history_lookup_fn(staff_code, kpi_id, period, n) ->
            [(period, actual, target), ...]
            Prior n periods. Used to detect consistent top performers.

        pipeline_lookup_fn(staff_code) -> dict
            Returns observable pipeline characteristics for the
            performer (deal mix, segment focus, etc.). Used to
            populate observed_patterns.

        top_n: how many performers per leaderboard (default 5,
            matching spec).
        """
        self._kpi_leaderboard   = kpi_leaderboard_fn   or _default_kpi_leaderboard
        self._skill_leaderboard = skill_leaderboard_fn or _default_skill_leaderboard
        self._staff_lookup      = staff_lookup_fn      or _default_staff_lookup
        self._target_lookup     = target_lookup_fn     or _default_target_lookup
        self._history_lookup    = history_lookup_fn    or _default_history_lookup
        self._pipeline_lookup   = pipeline_lookup_fn   or _default_pipeline_lookup
        self._top_n             = top_n

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def share_best_practice(
        self,
        staff_code: str,
        kpi_id: str,
        period: Optional[str] = None,
        today: Optional[date] = None,
    ) -> List[LearningCard]:
        """Spec-shaped entry: given a struggling staff + KPI, find top
        performers on that KPI and produce learning cards.

        Cards are NOT generated for the requesting staff themselves
        if they happen to be a top performer (the engine assumes the
        caller wants peers, not self-cards).
        """
        if today is None:
            today = date.today()
        if period is None:
            period = f"{today.year:04d}-{today.month:02d}"

        leaderboard = self._kpi_leaderboard(kpi_id, period, self._top_n) or []
        cards: List[LearningCard] = []
        for entry in leaderboard:
            performer_code = str(entry.get("staff_code", ""))
            if not performer_code or performer_code == staff_code:
                continue
            card = self._build_kpi_card(
                performer_code, entry, kpi_id, period, today,
                requesting_staff=staff_code,
            )
            if card:
                cards.append(card)
        return cards

    def match_for_skill(
        self,
        skill_name: str,
        requesting_staff_code: str,
        today: Optional[date] = None,
    ) -> List[LearningCard]:
        """Composition with Standard #12: given a skill the requester
        has a gap in, find staff whose assessed level exceeds it.

        Returns 0+ LearningCards. The requester's own level (if any)
        is used as the floor — only peers strictly above are returned.
        """
        if today is None:
            today = date.today()

        leaderboard = self._skill_leaderboard(skill_name, self._top_n * 2) or []
        # Determine requester's own level for filtering
        requester_skills = _safe_load_dict(DATA_DIR / "staff_skills.json")
        requester_level = 0.0
        try:
            r = requester_skills.get(requesting_staff_code, {}) if isinstance(requester_skills, dict) else {}
            requester_level = float(r.get(skill_name, 0)) if isinstance(r, dict) else 0.0
        except (TypeError, ValueError):
            requester_level = 0.0

        cards: List[LearningCard] = []
        for entry in leaderboard:
            performer_code = str(entry.get("staff_code", ""))
            level = float(entry.get("level", 0))
            if not performer_code or performer_code == requesting_staff_code:
                continue
            if level <= requester_level:
                continue   # peer must exceed requester's level
            card = self._build_skill_card(
                performer_code, skill_name, level, today,
                requesting_staff=requesting_staff_code,
            )
            if card:
                cards.append(card)
            if len(cards) >= self._top_n:
                break
        return cards

    def generate_weekly_cards(
        self,
        kpis: List[str],
        period: str,
        today: Optional[date] = None,
    ) -> List[LearningCard]:
        """Weekly batch: produce learning cards for each KPI in scope.

        Used by the scheduler. Each KPI contributes up to top_n cards
        (one per top performer). Spec target: 5+ cards/week is met
        with even ONE active KPI of broad scope.
        """
        if today is None:
            today = date.today()
        all_cards: List[LearningCard] = []
        for kpi_id in kpis:
            leaderboard = self._kpi_leaderboard(kpi_id, period, self._top_n) or []
            for entry in leaderboard:
                code = str(entry.get("staff_code", ""))
                if not code:
                    continue
                card = self._build_kpi_card(
                    code, entry, kpi_id, period, today, requesting_staff=None,
                )
                if card:
                    all_cards.append(card)
        return all_cards

    def generate_weekly_skill_cards(
        self,
        skills: List[str],
        today: Optional[date] = None,
    ) -> List[LearningCard]:
        """Weekly batch (skill axis). Used as a fallback when KPI actuals
        aren't yet populated, OR alongside the KPI batch to surface
        skill-based mentor connections.

        Each skill contributes up to top_n cards. The "requesting_staff"
        is None — these are general mentor-availability cards, not
        targeted matches.
        """
        if today is None:
            today = date.today()
        all_cards: List[LearningCard] = []
        for skill_name in skills:
            leaderboard = self._skill_leaderboard(skill_name, self._top_n) or []
            for entry in leaderboard:
                code = str(entry.get("staff_code", ""))
                level = float(entry.get("level", 0))
                if not code or level <= 0:
                    continue
                card = self._build_skill_card(
                    code, skill_name, level, today, requesting_staff="",
                )
                if card:
                    all_cards.append(card)
        return all_cards

    # ──────────────────────────────────────────────────────────────────
    # Card construction
    # ──────────────────────────────────────────────────────────────────

    def _build_kpi_card(
        self,
        performer_code: str,
        leaderboard_entry: dict,
        kpi_id: str,
        period: str,
        today: date,
        requesting_staff: Optional[str],
    ) -> Optional[LearningCard]:
        """Assemble a learning card for a KPI top performer."""
        performer = self._staff_lookup(performer_code) or {}

        achievement_pct: Optional[float] = None
        try:
            ap = leaderboard_entry.get("achievement_pct")
            if ap is not None:
                achievement_pct = float(ap)
        except (TypeError, ValueError):
            pass

        # Filter: must be ≥110% of target to qualify as "best practice"
        if achievement_pct is not None and achievement_pct < float(DEFAULT_MIN_OUTPERFORM) * 100:
            return None

        # Consistency: how many of the last N periods were they top performer?
        consistency = self._compute_consistency(performer_code, kpi_id, period)

        # Observable patterns (data-driven, not fabricated)
        patterns = self._observe_kpi_patterns(
            performer_code, performer, kpi_id, achievement_pct, consistency,
        )

        prompts = self._kpi_conversation_prompts(performer, kpi_id)

        card_id = self._make_card_id(
            "kpi", performer_code, kpi_id, period, requesting_staff,
        )
        return LearningCard(
            id=                   card_id,
            week=                 _iso_week_str(today),
            period=               period,
            card_type=            "kpi",
            kpi_id=               kpi_id,
            requesting_staff=     requesting_staff,
            performer_staff_code= performer_code,
            performer_role=       performer.get("role", ""),
            performer_unit=       performer.get("unit", ""),
            achievement_pct=      achievement_pct,
            observed_patterns=    patterns,
            conversation_prompts= prompts,
            consistency_periods=  consistency,
        )

    def _build_skill_card(
        self,
        performer_code: str,
        skill_name: str,
        level: float,
        today: date,
        requesting_staff: str,
    ) -> Optional[LearningCard]:
        """Assemble a learning card for a skill leaderboard entry."""
        performer = self._staff_lookup(performer_code) or {}
        # Targeted (requesting_staff set) → "above your level" phrasing
        # General (no requester) → just the level statement
        if requesting_staff:
            patterns = self._observe_skill_patterns_targeted(
                performer_code, performer, skill_name, level,
            )
        else:
            patterns = self._observe_skill_patterns_general(
                performer_code, performer, skill_name, level,
            )
        prompts = self._skill_conversation_prompts(performer, skill_name)
        card_id = self._make_card_id(
            "skill", performer_code, skill_name, "", requesting_staff or "",
        )
        return LearningCard(
            id=                   card_id,
            week=                 _iso_week_str(today),
            period=               "",
            card_type=            "skill",
            skill_name=           skill_name,
            requesting_staff=     requesting_staff or None,
            performer_staff_code= performer_code,
            performer_role=       performer.get("role", ""),
            performer_unit=       performer.get("unit", ""),
            skill_level=          level,
            observed_patterns=    patterns,
            conversation_prompts= prompts,
        )

    # ──────────────────────────────────────────────────────────────────
    # Pattern observation (deliberately conservative)
    # ──────────────────────────────────────────────────────────────────

    def _observe_kpi_patterns(
        self,
        performer_code: str,
        performer: dict,
        kpi_id: str,
        achievement_pct: Optional[float],
        consistency: Optional[int],
    ) -> List[str]:
        """Return data-driven, attributable observations.

        Deliberate non-goal: fabricating tactical advice. We surface
        WHAT IS OBSERVABLE; the human conversation discovers HOW.
        """
        patterns: List[str] = []

        if achievement_pct is not None:
            patterns.append(
                f"Achieved {achievement_pct:.0f}% of target this period"
            )

        if consistency is not None and consistency > 0:
            patterns.append(
                f"Consistent over-performer: also exceeded target in "
                f"{consistency} of the last {DEFAULT_HISTORY_PERIODS} periods"
            )

        # Pipeline characteristics (if relevant to this KPI class)
        kpi_upper = (kpi_id or "").upper()
        if any(s in kpi_upper for s in ("DEPOSIT", "DEP_", "LOAN", "DEAL", "SALES")):
            try:
                p = self._pipeline_lookup(performer_code) or {}
                if p:
                    deal_mix = p.get("deal_mix", {})
                    if deal_mix:
                        top_cat, top_pct = max(
                            deal_mix.items(), key=lambda kv: kv[1] or 0
                        )
                        patterns.append(
                            f"Pipeline skews toward {top_cat} "
                            f"({float(top_pct):.0f}% of deals)"
                        )
                    segment = p.get("primary_segment")
                    if segment:
                        patterns.append(f"Primary customer segment: {segment}")
                    deal_count = p.get("deal_count")
                    if deal_count is not None:
                        patterns.append(
                            f"Active pipeline of {int(deal_count)} deals"
                        )
            except Exception:
                pass

        # Role + unit context (always observable)
        unit = performer.get("unit") or performer.get("department")
        if unit:
            patterns.append(f"Based in {unit}")

        return patterns

    def _observe_skill_patterns_targeted(
        self,
        performer_code: str,
        performer: dict,
        skill_name: str,
        level: float,
    ) -> List[str]:
        patterns = [
            f"Assessed at {level:.1f} on {skill_name} (above your level)",
        ]
        role = performer.get("role")
        if role:
            patterns.append(f"Role: {role}")
        unit = performer.get("unit") or performer.get("department")
        if unit:
            patterns.append(f"Unit: {unit}")
        band = performer.get("band")
        if band:
            patterns.append(f"Band: {band}")
        return patterns

    def _observe_skill_patterns_general(
        self,
        performer_code: str,
        performer: dict,
        skill_name: str,
        level: float,
    ) -> List[str]:
        patterns = [
            f"Top assessed level on {skill_name}: {level:.1f}",
        ]
        role = performer.get("role")
        if role:
            patterns.append(f"Role: {role}")
        unit = performer.get("unit") or performer.get("department")
        if unit:
            patterns.append(f"Unit: {unit}")
        band = performer.get("band")
        if band:
            patterns.append(f"Band: {band}")
        return patterns

    # Backwards-compatible alias used by the self-test
    def _observe_skill_patterns(self, performer_code, performer, skill_name, level):
        return self._observe_skill_patterns_targeted(
            performer_code, performer, skill_name, level
        )

    def _kpi_conversation_prompts(self, performer: dict, kpi_id: str) -> List[str]:
        """Conversation invitations — the engine surfaces top performers,
        humans extract tactics."""
        name = performer.get("full_name") or performer.get("name") or "this peer"
        return [
            f"Reach out to {name} and ask: \"What's one thing you do "
            f"differently on {kpi_id} that I should try?\"",
            f"Request a 30-min shadow session — sit in on one of their "
            f"client meetings or pipeline reviews",
            f"Ask your manager to facilitate a brown-bag session where "
            f"{name} shares their approach",
        ]

    def _skill_conversation_prompts(self, performer: dict, skill_name: str) -> List[str]:
        name = performer.get("full_name") or performer.get("name") or "this peer"
        return [
            f"Ask {name} how they built their proficiency in {skill_name}",
            f"Request a one-on-one mentoring conversation focused on {skill_name}",
            f"Look for opportunities to co-work on a task involving {skill_name}",
        ]

    def _compute_consistency(self, staff_code: str, kpi_id: str, period: str) -> int:
        """How many of the last DEFAULT_HISTORY_PERIODS prior periods
        did this staff exceed target on this KPI?"""
        try:
            history = self._history_lookup(
                staff_code, kpi_id, period, DEFAULT_HISTORY_PERIODS
            ) or []
        except Exception:
            return 0
        count = 0
        for entry in history:
            try:
                _, actual, target = entry
                if target and actual and Decimal(str(actual)) >= Decimal(str(target)):
                    count += 1
            except (TypeError, ValueError):
                continue
        return count

    @staticmethod
    def _make_card_id(
        card_type: str,
        performer_code: str,
        topic: str,
        period: str,
        requesting_staff: Optional[str],
    ) -> str:
        """Deterministic card ID. Re-generating with same inputs yields
        same ID (idempotent persist)."""
        components = [card_type, performer_code, topic, period, requesting_staff or ""]
        raw = "|".join(components)
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"{card_type}-{digest}"


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _safe_load_dict(path: Path):
    try:
        from utils.db import db
        d = db.load_json(path, default={})
        return d
    except Exception as e:
        logger.warning("peer_learning: could not load %s: %s", path, e)
        return {}


def _default_kpi_leaderboard(kpi_id: str, period: str, n: int) -> List[dict]:
    """Build leaderboard from target_cascade.json + bsc_engine actuals.

    The cascade shape is:
        {"<from_code>|<kpi>|<year>": {
            "kpi": "...", "period": "...",
            "allocations": [{"to_code", "to_name", "amount"}, ...]
        }}

    For a given KPI we union the `to_code → amount` mappings across
    all cascade entries for that KPI.

    Returns [] when there's no actuals data — caller should consider
    falling back to a skill-based leaderboard."""
    cascade = _safe_load_dict(DATA_DIR / "target_cascade.json")
    if not isinstance(cascade, dict):
        return []
    try:
        from utils import bsc_engine
    except Exception:
        bsc_engine = None

    # Aggregate per-staff targets for this KPI across all cascade entries.
    # Last write wins (deterministic but not summed) — multiple
    # cascades to the same staff for the same KPI shouldn't happen.
    staff_targets: Dict[str, float] = {}
    for cascade_key, block in cascade.items():
        if not isinstance(block, dict):
            continue
        if str(block.get("kpi", "")) != kpi_id:
            continue
        for alloc in block.get("allocations", []) or []:
            if not isinstance(alloc, dict):
                continue
            code = str(alloc.get("to_code", ""))
            amount = alloc.get("amount")
            if code and amount is not None:
                try:
                    staff_targets[code] = float(amount)
                except (TypeError, ValueError):
                    continue

    if not staff_targets:
        return []

    rows: List[Tuple[float, dict]] = []
    for code, target in staff_targets.items():
        if target <= 0:
            continue
        actual: Optional[Decimal] = None
        if bsc_engine is not None:
            try:
                actual = bsc_engine.get_actual(code, kpi_id, period)
            except Exception:
                actual = None
        if actual is None:
            continue   # without an actual we can't rank
        achievement_pct = float(Decimal(str(actual)) / Decimal(str(target)) * 100)
        rows.append((achievement_pct, {
            "staff_code":       code,
            "achievement_pct":  achievement_pct,
            "actual":           float(actual),
            "target":           target,
        }))
    rows.sort(key=lambda kv: kv[0], reverse=True)
    return [r[1] for r in rows[:n]]


def _default_skill_leaderboard(skill_name: str, n: int) -> List[dict]:
    raw = _safe_load_dict(DATA_DIR / "staff_skills.json")
    if not isinstance(raw, dict):
        return []
    rows: List[Tuple[float, dict]] = []
    for staff_code, skills in raw.items():
        if not isinstance(skills, dict):
            continue
        level = skills.get(skill_name)
        if level is None:
            continue
        try:
            level_f = float(level)
        except (TypeError, ValueError):
            continue
        rows.append((level_f, {"staff_code": staff_code, "level": level_f}))
    rows.sort(key=lambda kv: kv[0], reverse=True)
    return [r[1] for r in rows[:n]]


def _default_staff_lookup(staff_code: str) -> Optional[dict]:
    """Find user by staff_code (users.json is keyed by username)."""
    users = _safe_load_dict(DATA_DIR / "users.json")
    if not isinstance(users, dict):
        return None
    for username, info in users.items():
        if isinstance(info, dict) and str(info.get("staff_code", "")) == str(staff_code):
            return {**info, "username": username}
    return None


def _default_target_lookup(staff_code: str, kpi_id: str, period: str) -> Optional[Decimal]:
    """Look up the cascaded target for a staff/kpi/period.

    The cascade shape is keyed by `<from_code>|<kpi>|<year>`; we walk
    every entry for the kpi and find this staff in the allocations list.
    """
    cascade = _safe_load_dict(DATA_DIR / "target_cascade.json")
    if not isinstance(cascade, dict):
        return None
    for _, block in cascade.items():
        if not isinstance(block, dict):
            continue
        if str(block.get("kpi", "")) != kpi_id:
            continue
        for alloc in block.get("allocations", []) or []:
            if not isinstance(alloc, dict):
                continue
            if str(alloc.get("to_code", "")) == str(staff_code):
                amount = alloc.get("amount")
                if amount is None:
                    continue
                try:
                    return Decimal(str(amount))
                except Exception:
                    return None
    return None


def _default_history_lookup(
    staff_code: str, kpi_id: str, period: str, n: int,
) -> List[Tuple[str, Decimal, Decimal]]:
    """Return [(period, actual, target), ...] for the last n periods."""
    try:
        from utils import bsc_engine
    except Exception:
        return []
    prior = _enumerate_prior_periods(period, n)
    target = _default_target_lookup(staff_code, kpi_id, period)
    out: List[Tuple[str, Decimal, Decimal]] = []
    for p in prior:
        try:
            actual = bsc_engine.get_actual(staff_code, kpi_id, p)
        except Exception:
            actual = None
        if actual is None or target is None:
            continue
        out.append((p, Decimal(str(actual)), Decimal(str(target))))
    return out


def _default_pipeline_lookup(staff_code: str) -> Dict[str, Any]:
    """Read pipeline_deals.json and summarise this staff's deals.

    Returns a dict shape: {deal_count, deal_mix: {category: pct},
    primary_segment}. Returns {} on missing data."""
    raw = _safe_load_dict(DATA_DIR / "pipeline_deals.json")
    if isinstance(raw, dict):
        # could be table-shape {rows: [...]}; tolerate
        deals = raw.get("rows") if isinstance(raw.get("rows"), list) else []
    elif isinstance(raw, list):
        deals = raw
    else:
        deals = []
    own = [
        d for d in deals
        if isinstance(d, dict) and str(d.get("staff_code", "")) == str(staff_code)
    ]
    if not own:
        return {}
    total = len(own)
    by_cat: Dict[str, int] = {}
    by_seg: Dict[str, int] = {}
    for d in own:
        cat = d.get("deal_category") or d.get("category") or "Uncategorised"
        by_cat[cat] = by_cat.get(cat, 0) + 1
        seg = d.get("segment") or d.get("unit")
        if seg:
            by_seg[seg] = by_seg.get(seg, 0) + 1
    deal_mix = {k: round(v / total * 100, 1) for k, v in by_cat.items()}
    primary_seg = max(by_seg.items(), key=lambda kv: kv[1])[0] if by_seg else None
    return {
        "deal_count":      total,
        "deal_mix":        deal_mix,
        "primary_segment": primary_seg,
    }


# ─────────────────────────────────────────────────────────────────────
# Helpers — period / week
# ─────────────────────────────────────────────────────────────────────

def _iso_week_str(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def _enumerate_prior_periods(current: str, n: int) -> List[str]:
    """Walk back n periods (monthly only here; matches bsc_engine usage)."""
    if not current or "-Q" in current:
        return []   # quarterly history: out of scope for v5.41
    try:
        year_str, m_str = current.split("-", 1)
        year = int(year_str); m = int(m_str)
    except (ValueError, IndexError):
        return []
    out = []
    for _ in range(n):
        m -= 1
        if m < 1:
            m = 12; year -= 1
        out.append(f"{year}-{m:02d}")
    return list(reversed(out))


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_learning_cards(cards: List[LearningCard]) -> int:
    """Append cards. Idempotent on card.id (deterministic)."""
    if not cards:
        return 0
    try:
        from utils.db import db
        existing = db.load_json(CARDS_FILE, default=[])
    except Exception:
        existing = []
    if not isinstance(existing, list):
        existing = []
    by_id = {
        c.get("id"): c for c in existing if isinstance(c, dict) and c.get("id")
    }
    for c in cards:
        d = asdict(c)
        by_id[c.id] = d
    out = list(by_id.values())
    try:
        from utils.db import db
        db.save_json(CARDS_FILE, out)
    except Exception as e:
        logger.error("peer_learning: could not save cards: %s", e)
        return 0
    return len(cards)


def list_cards_for_week(week: str) -> List[dict]:
    """Return cards for a specific ISO week ('YYYY-WNN')."""
    try:
        from utils.db import db
        all_cards = db.load_json(CARDS_FILE, default=[])
    except Exception:
        return []
    if not isinstance(all_cards, list):
        return []
    return [c for c in all_cards if isinstance(c, dict) and c.get("week") == week]


def list_cards_for_staff(staff_code: str, limit: int = 20) -> List[dict]:
    """Cards relevant to a staff member: either their own (as performer)
    or shared with them (as requesting_staff)."""
    try:
        from utils.db import db
        all_cards = db.load_json(CARDS_FILE, default=[])
    except Exception:
        return []
    if not isinstance(all_cards, list):
        return []
    relevant = [
        c for c in all_cards
        if isinstance(c, dict)
        and (
            str(c.get("performer_staff_code", "")) == str(staff_code)
            or str(c.get("requesting_staff", "")) == str(staff_code)
        )
    ]
    relevant.sort(key=lambda c: c.get("generated_at", ""), reverse=True)
    return relevant[:limit]


# ─────────────────────────────────────────────────────────────────────
# Self-test (`python -m utils.peer_learning`)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.peer_learning self-test")

    # Mock leaderboard + staff for deterministic testing
    leaderboard_data = {
        ("DEP_GROWTH", "2026-04"): [
            {"staff_code": "S100", "achievement_pct": 152.0, "actual": 152, "target": 100},
            {"staff_code": "S101", "achievement_pct": 138.0, "actual": 138, "target": 100},
            {"staff_code": "S102", "achievement_pct": 125.0, "actual": 125, "target": 100},
            {"staff_code": "S103", "achievement_pct": 105.0, "actual": 105, "target": 100},  # below 110% threshold
            {"staff_code": "S104", "achievement_pct": 115.0, "actual": 115, "target": 100},
        ],
    }
    skill_data = {
        "Risk Management": [
            {"staff_code": "S200", "level": 4.5},
            {"staff_code": "S201", "level": 4.2},
            {"staff_code": "S202", "level": 3.8},
        ],
    }
    staff_data = {
        "S100": {"role": "Branch Manager", "unit": "Mombasa", "band": "M3", "full_name": "Jane Doe"},
        "S101": {"role": "Personal Banker", "unit": "Nairobi", "band": "M5", "full_name": "Bob Smith"},
        "S102": {"role": "RM Corporate", "unit": "Nairobi", "band": "M2", "full_name": "Carol Jones"},
        "S104": {"role": "RM Retail", "unit": "Kisumu", "band": "M4", "full_name": "Dan Kim"},
        "S200": {"role": "Senior Credit Analyst", "unit": "Risk", "band": "M2", "full_name": "Eve Lee"},
        "S201": {"role": "Credit Analyst", "unit": "Risk", "band": "M4", "full_name": "Frank Park"},
    }

    history_data = {
        ("S100", "DEP_GROWTH"): [
            ("2026-01", Decimal("130"), Decimal("100")),
            ("2026-02", Decimal("140"), Decimal("100")),
            ("2026-03", Decimal("145"), Decimal("100")),
        ],
    }
    pipeline_data = {
        "S100": {"deal_count": 24, "deal_mix": {"Trade Finance": 60.0, "Lending": 30.0, "Treasury": 10.0}, "primary_segment": "SME"},
    }

    eng = PeerLearningNetwork(
        kpi_leaderboard_fn=  lambda k, p, n: leaderboard_data.get((k, p), [])[:n],
        skill_leaderboard_fn=lambda s, n:    skill_data.get(s, [])[:n],
        staff_lookup_fn=     lambda sc:      staff_data.get(sc),
        target_lookup_fn=    lambda sc, k, p: Decimal("100"),
        history_lookup_fn=   lambda sc, k, p, n: history_data.get((sc, k), []),
        pipeline_lookup_fn=  lambda sc:      pipeline_data.get(sc, {}),
    )

    # Case 1: share_best_practice — struggling staff S999 wants peers
    cards = eng.share_best_practice("S999", "DEP_GROWTH", "2026-04",
                                     today=date(2026, 4, 15))
    # S100, S101, S102, S104 should produce cards (S103 is below 110% so excluded)
    assert len(cards) == 4, f"expected 4 cards (S103 excluded), got {len(cards)}"
    s100 = next(c for c in cards if c.performer_staff_code == "S100")
    assert s100.achievement_pct == 152.0
    assert s100.consistency_periods == 3   # all 3 prior periods exceeded
    assert any("Trade Finance" in p for p in s100.observed_patterns), s100.observed_patterns
    assert s100.card_type == "kpi"
    assert s100.kpi_id == "DEP_GROWTH"
    assert s100.requesting_staff == "S999"
    # No card for S103 (below threshold)
    assert all(c.performer_staff_code != "S103" for c in cards)
    print(f"  ✅ share_best_practice produced {len(cards)} cards "
          f"(S103 below threshold correctly excluded)")

    # Case 2: requester is themselves a top performer → not in their own cards
    cards2 = eng.share_best_practice("S100", "DEP_GROWTH", "2026-04",
                                      today=date(2026, 4, 15))
    assert all(c.performer_staff_code != "S100" for c in cards2)
    print(f"  ✅ requester filtered from their own card set")

    # Case 3: match_for_skill
    # Without the requester level = 0 from disk, S200/S201/S202 are all > 0
    # but the requester level lookup reads from disk; we'll test against
    # in-memory (level 0)
    cards3 = eng.match_for_skill("Risk Management", "S999",
                                  today=date(2026, 4, 15))
    # Should yield S200 (4.5), S201 (4.2), S202 (3.8) — all above level 0
    assert len(cards3) >= 3, f"got {len(cards3)} skill cards"
    assert cards3[0].performer_staff_code == "S200"
    assert cards3[0].skill_level == 4.5
    assert cards3[0].card_type == "skill"
    print(f"  ✅ match_for_skill produced {len(cards3)} cards "
          f"(top: {cards3[0].performer_staff_code} at {cards3[0].skill_level})")

    # Case 4: weekly batch
    cards4 = eng.generate_weekly_cards(["DEP_GROWTH"], "2026-04",
                                        today=date(2026, 4, 15))
    # Same leaderboard, but no requester filter. S103 still excluded for low achievement.
    # S100, S101, S102, S104 → 4 cards
    assert len(cards4) == 4, f"weekly: got {len(cards4)}"
    print(f"  ✅ weekly batch produced {len(cards4)} cards")

    # Case 5: deterministic IDs
    c1 = eng._make_card_id("kpi", "S100", "DEP_GROWTH", "2026-04", None)
    c2 = eng._make_card_id("kpi", "S100", "DEP_GROWTH", "2026-04", None)
    c3 = eng._make_card_id("kpi", "S100", "DEP_GROWTH", "2026-05", None)
    assert c1 == c2 and c1 != c3
    print(f"  ✅ card IDs deterministic")

    # Case 6: empty leaderboard → no cards
    cards6 = eng.share_best_practice("S001", "UNKNOWN_KPI", "2026-04",
                                      today=date(2026, 4, 15))
    assert cards6 == []
    print(f"  ✅ unknown KPI returned 0 cards")

    # Case 7: prior-period enumeration
    assert _enumerate_prior_periods("2026-04", 3) == ["2026-01", "2026-02", "2026-03"]
    assert _enumerate_prior_periods("2026-Q2", 3) == []   # quarterly out of scope
    print(f"  ✅ prior period enumeration")

    # Case 8: consistency counting
    consistency = eng._compute_consistency("S100", "DEP_GROWTH", "2026-04")
    assert consistency == 3, f"expected 3, got {consistency}"
    print(f"  ✅ consistency counting (S100: {consistency} of {DEFAULT_HISTORY_PERIODS} periods)")

    print("\n  ALL TESTS PASSED")
