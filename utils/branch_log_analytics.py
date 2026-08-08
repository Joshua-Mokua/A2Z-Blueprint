"""
A2Z Daily Log — analytics & impact engine (additive, backward-compatible).

New module. Does NOT modify existing branch_log.py behaviour. Provides:
  * impact-tier config helpers (admin 80/20 matrix): high / medium / low per activity
  * deadline-time + carried-forward reset-marker config
  * read-time CARRIED-FORWARD VARIANCE engine (running sum of validated index - target,
    honouring admin reset markers, healing automatically when a returned day is validated)
  * impact-tier breakdown of the productivity index (for the analytics pie)

Design notes:
  - Carried-forward variance is computed at READ time from each day's (index - target). It is
    never stored per row, so the admin reset rule and retroactive healing on validation fall out
    naturally. See DAILY_LOG_LIFECYCLE.md (READ-TIME C/F ALGORITHM).
  - "high-impact" = the set of activities the admin tagged "high" — the intended 20% that should
    carry ~80% of productive effort (the 80/20 thesis).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from utils.branch_log import (
    load_log_config,
    save_log_config,
    metric_keys,
    compute_index,
    daily_index_target,
)

# ── Impact-tier config (admin 80/20 matrix) ───────────────────────────────
_VALID_TIERS = ("high", "medium", "low")


def impact_tiers() -> dict:
    """Admin-assigned impact tier per activity key: {activity_key: 'high'|'medium'|'low'}.

    Activities with no explicit tier default to 'medium' at read time (see tier_of).
    """
    t = load_log_config().get("impact_tiers", {}) or {}
    return {str(k): str(v).lower() for k, v in t.items() if str(v).lower() in _VALID_TIERS}


def tier_of(activity_key: str) -> str:
    """Impact tier for an activity, defaulting to 'medium' when unassigned."""
    return impact_tiers().get(str(activity_key), "medium")


def set_impact_tier(activity_key: str, tier: str) -> dict:
    """Admin action: assign an activity to an impact tier. Returns the updated map."""
    tier = str(tier).lower()
    if tier not in _VALID_TIERS:
        raise ValueError(f"tier must be one of {_VALID_TIERS}, got {tier!r}")
    cfg = load_log_config()
    tiers = dict(cfg.get("impact_tiers", {}) or {})
    tiers[str(activity_key)] = tier
    cfg["impact_tiers"] = tiers
    save_log_config(cfg)
    return tiers


def high_impact_keys() -> set:
    """The set of activity keys tagged 'high' — the intended high-impact 20%."""
    return {k for k, v in impact_tiers().items() if v == "high"}


# ── Deadline + carried-forward reset config ───────────────────────────────
def deadline_time() -> str:
    """Fixed clock time (HH:MM) on day D+1 by which day D must be submitted.

    Default 09:00. Admin-configurable via branch_log_config.deadline_time.
    """
    t = str(load_log_config().get("deadline_time", "09:00") or "09:00").strip()
    # basic sanity; fall back on malformed values
    try:
        hh, mm = t.split(":")
        int(hh); int(mm)
        return t
    except Exception:
        return "09:00"


def cf_reset_markers() -> list:
    """Sorted list of admin carried-forward reset dates: [{'date': 'YYYY-MM-DD', 'by': str}].

    The read-time running sum restarts at 0 on/after each marker date.
    """
    raw = load_log_config().get("cf_reset_markers", []) or []
    out = []
    for m in raw:
        if isinstance(m, dict) and m.get("date"):
            out.append({"date": str(m["date"]), "by": str(m.get("by", ""))})
    return sorted(out, key=lambda m: m["date"])


def add_cf_reset_marker(reset_date: str, by: str) -> list:
    """Admin action: record a carried-forward reset effective on reset_date."""
    cfg = load_log_config()
    markers = list(cfg.get("cf_reset_markers", []) or [])
    markers.append({"date": str(reset_date), "by": str(by)})
    cfg["cf_reset_markers"] = markers
    save_log_config(cfg)
    return markers


# ── Per-day effective index (honours validation/auto-submit state) ────────
def _effective_index(log: dict) -> float:
    """The index that counts toward variance for a given day log.

    - A stored 'index' is used when present (submit/auto-submit already computed it).
    - Otherwise recompute from the day's metric fields.
    Auto-submitted/partial days already carry a deficit-bearing index (only keyed hours),
    so no special-casing is needed here — the deficit is inherent in the lower index.
    Returned-but-unvalidated days use their current index; when later corrected + validated,
    the higher index naturally heals the running sum on the next read.
    """
    idx = log.get("index")
    if idx is not None:
        try:
            return float(idx or 0)
        except (TypeError, ValueError):
            pass
    return compute_index({k: log.get(k, 0) for k in metric_keys()})


def _working_weight(log: dict) -> float:
    """Work-calendar weight for a log's date: 1.0 weekday, 0.5 Saturday,
    0.0 Sunday / public holiday.

    Falls back to 1.0 (a full working day) whenever the calendar cannot be
    consulted. Over-counting a working day is recoverable; silently zeroing
    everyone's target because a config file went missing is not.
    """
    try:
        from utils import workcal
        return float(workcal.target_weight(str(log.get("log_date", ""))[:10]))
    except Exception:
        return 1.0


def _is_working_day(log: dict) -> bool:
    """True when the log's date is one on which work was expected at all."""
    return _working_weight(log) > 0.0


def _target_for(log: dict) -> float:
    """Daily index target for a log's date, weighted by the work calendar.

    A Saturday carries half the weekday target (branches run half days); a
    Sunday or gazetted public holiday carries none. A per-role target can still
    slot in here later without changing callers.
    """
    return round(daily_index_target() * _working_weight(log), 2)


# ── Read-time carried-forward variance engine ─────────────────────────────
def carried_forward(logs: list) -> list:
    """Annotate each day log with variance + running carried-forward variance.

    Input: a list of day-log dicts for ONE staff member (any order).
    Output: the same logs sorted ascending by date, each gaining:
        'target'      — that day's index target
        'variance'    — effective_index - target (that day)
        'cf_variance' — running sum of variance from the last reset marker forward

    The running sum restarts at 0 on/after each admin reset marker (cf_reset_markers).
    Healing is automatic: a corrected+validated day has a higher effective index, so its
    variance and every subsequent cf_variance rise on the next read.
    """
    rows = sorted(
        [dict(l) for l in logs],
        key=lambda l: str(l.get("log_date", "")),
    )
    markers = [m["date"] for m in cf_reset_markers()]
    running = 0.0
    applied_marker = None
    for r in rows:
        d = str(r.get("log_date", ""))
        # apply the newest reset marker whose date is <= this day and not yet applied
        for mk in markers:
            if mk <= d and mk != applied_marker and (applied_marker is None or mk > applied_marker):
                running = 0.0
                applied_marker = mk
        idx = _effective_index(r)
        if not _is_working_day(r):
            # RULING: Sundays and public holidays are excluded from the walk
            # entirely — no target, so no deficit can accrue. Work genuinely
            # done on a rest day stays visible as `index` but is not banked
            # into the running balance either way.
            r["target"] = 0.0
            r["variance"] = 0.0
            r["cf_variance"] = running
            r["working_day"] = False
            continue
        tgt = _target_for(r)
        var = round(idx - tgt, 2)
        running = round(running + var, 2)
        r["target"] = tgt
        r["variance"] = var
        r["cf_variance"] = running
        r["working_day"] = True
    return rows


def latest_cf_variance(logs: list) -> float:
    """The most recent carried-forward variance for a staff member (0.0 if no logs)."""
    rows = carried_forward(logs)
    return rows[-1]["cf_variance"] if rows else 0.0


# ── Impact-tier breakdown (analytics pie, v1 = index share per tier) ──────
def impact_breakdown(logs: list) -> dict:
    """Aggregate the productivity index by impact tier across a set of day logs.

    v1 measures INDEX share per tier (index already = sum(count x weight)); when meetings
    (time-spans) land, a parallel TIME-share breakdown will be added. Each activity's index
    contribution = count x weight; that contribution is bucketed into the activity's tier.

    Returns:
        { 'high': float, 'medium': float, 'low': float,
          'high_pct': float, 'total': float,
          'by_activity': { activity_key: {'tier': str, 'index': float} } }
    """
    from utils.branch_log import activity_weights
    weights = activity_weights()
    tiers = impact_tiers()
    buckets = {"high": 0.0, "medium": 0.0, "low": 0.0}
    by_activity: dict = {}
    for log in logs:
        for k in metric_keys():
            try:
                cnt = float(log.get(k, 0) or 0)
            except (TypeError, ValueError):
                cnt = 0.0
            if cnt == 0:
                continue
            contrib = cnt * float(weights.get(k, 0) or 0)
            tier = tiers.get(k, "medium")
            buckets[tier] = round(buckets[tier] + contrib, 2)
            slot = by_activity.setdefault(k, {"tier": tier, "index": 0.0})
            slot["index"] = round(slot["index"] + contrib, 2)
    total = round(sum(buckets.values()), 2)
    high_pct = round((buckets["high"] / total) * 100, 1) if total else 0.0
    return {
        **buckets,
        "total": total,
        "high_pct": high_pct,
        "by_activity": by_activity,
    }
