"""utils.performance_insights — Performance Amplification API service
(Standard #20, v5.44).

Per the master spec:

    @app.get("/api/v2/performance/insights/{staff_code}")
    def get_performance_insights(staff_code):
        return {
            "overall_score":       3.8,
            "strengths":           ["Loan Disbursement"],
            "promotion_readiness": 0.75,
        }

Verification:
  - 10+ external consumers     ← deployed-runtime metric, OUT OF SCOPE
  - Webhooks deliver <5 seconds ← deployed-runtime metric, OUT OF SCOPE

The verifiable structural claim G31 enforces:
  - The route is defined and discoverable in the FastAPI app
  - It returns the spec-shaped JSON for valid staff
  - Auth dependency is declared (per G12)
  - Synthetic latency on a single call is <500ms

This is the FIRST standard where the V2 engines compose into an API
deliverable that external systems can consume. The insights aggregate:

  overall_score     ← BSC engine current overall achievement
  strengths         ← KPIs at ≥110% achievement (top performers)
  promotion_readiness ← from #12 GrowthPathEngine

Engines stay decoupled at runtime: this module imports the function
APIs of #12 + bsc_engine, but doesn't import anything from
#11/#13/#14/#15/#16. Each composition path is independent.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("a2z.insights")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

# Strengths threshold: KPIs at this achievement_pct or above qualify
STRENGTH_THRESHOLD_PCT = 110.0
DEFAULT_MAX_STRENGTHS  = 5


# ─────────────────────────────────────────────────────────────────────
# Service function (the API route delegates here)
# ─────────────────────────────────────────────────────────────────────

def get_performance_insights(
    staff_code: str,
    today: Optional[date] = None,
    kpi_status_fn: Optional[Callable[[str], List[dict]]] = None,
    growth_plan_fn: Optional[Callable[[str], dict]] = None,
    overall_score_fn: Optional[Callable[[str, str], Optional[float]]] = None,
) -> Dict[str, Any]:
    """Aggregate insights for one staff member.

    Returns the spec-shaped dict:
      {
        "overall_score":       float,   # BSC overall (0-5 scale)
        "strengths":           [str],   # KPIs at ≥110% achievement
        "promotion_readiness": float,   # from growth plan (0-1)
      }

    Returns {} for unknown staff (defensive). Individual fields fall
    back gracefully when source data is unavailable:
      - overall_score → 0.0
      - strengths → []
      - promotion_readiness → 0.0

    Caller can detect missing-data scenarios via meta.signals_present.
    """
    if not staff_code:
        return {}
    if today is None:
        today = date.today()
    period = f"{today.year:04d}-{today.month:02d}"

    # Resolve collaborators
    kpi_status_fn    = kpi_status_fn    or _default_kpi_status
    growth_plan_fn   = growth_plan_fn   or _default_growth_plan
    overall_score_fn = overall_score_fn or _default_overall_score

    # Validate staff exists
    staff = _staff_lookup(staff_code)
    if not staff:
        return {}

    kpi_rows = kpi_status_fn(staff_code) or []
    plan = growth_plan_fn(staff_code) or {}
    overall = overall_score_fn(staff_code, period) or 0.0

    # Strengths: KPIs at threshold or above, sorted desc by achievement
    sorted_strengths = sorted(
        [r for r in kpi_rows if (r.get("achievement_pct") or 0) >= STRENGTH_THRESHOLD_PCT],
        key=lambda r: r.get("achievement_pct", 0),
        reverse=True,
    )
    strengths = [r.get("kpi_id") for r in sorted_strengths[:DEFAULT_MAX_STRENGTHS]]

    promotion_readiness = float(plan.get("promotion_readiness", 0)) if isinstance(plan, dict) else 0.0
    # Clamp to [0, 1]
    promotion_readiness = max(0.0, min(1.0, promotion_readiness))

    return {
        "overall_score":       round(float(overall), 2),
        "strengths":           strengths,
        "promotion_readiness": round(promotion_readiness, 2),
        "meta": {
            "staff_code":       staff_code,
            "staff_name":       staff.get("full_name", ""),
            "period":           period,
            "today":            today.isoformat(),
            "kpi_count":        len(kpi_rows),
            "signals_present": {
                "kpi_status":          len(kpi_rows) > 0,
                "growth_plan":         bool(plan),
                "overall_score":       overall > 0,
            },
            "generated_at":     datetime.now(timezone.utc).isoformat(),
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Default collaborators (read-only, gracefully degrading)
# ─────────────────────────────────────────────────────────────────────

def _safe_load(path: Path, default):
    try:
        from utils.db import db
        return db.load_json(path, default=default)
    except Exception as e:
        logger.warning("insights: could not load %s: %s", path, e)
        return default


def _staff_lookup(staff_code: str):
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return None
    for username, info in users.items():
        if isinstance(info, dict) and str(info.get("staff_code", "")) == str(staff_code):
            return {**info, "username": username}
    return None


def _default_kpi_status(staff_code: str) -> List[dict]:
    """Compose with target_cascade + bsc_engine.get_actual."""
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
    seen: set = set()
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
            if (kpi_id, str(alloc.get("to_code"))) in seen:
                continue
            seen.add((kpi_id, str(alloc.get("to_code"))))
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
            })
    return rows


def _default_growth_plan(staff_code: str) -> dict:
    plans = _safe_load(DATA_DIR / "growth_plans.json", {})
    if not isinstance(plans, dict):
        return {}
    plan = plans.get(str(staff_code))
    return plan if isinstance(plan, dict) else {}


def _default_overall_score(staff_code: str, period: str) -> Optional[float]:
    """BSC overall on the 1-5 scale. Reads bsc_scores.json if present;
    otherwise computes from KPI achievements."""
    raw = _safe_load(DATA_DIR / "bsc_scores.json", {})
    if isinstance(raw, dict):
        entries = raw.get(str(staff_code), [])
        if isinstance(entries, list):
            for e in entries:
                if isinstance(e, dict) and e.get("period") == period:
                    v = e.get("overall") or e.get("score") or e.get("overall_pct")
                    if v is not None:
                        try:
                            v_f = float(v)
                            # If looks like a percentage, convert to 1-5
                            if v_f > 5:
                                return _pct_to_score(v_f)
                            return v_f
                        except (TypeError, ValueError):
                            return None
        if isinstance(entries, dict) and period in entries:
            v = entries[period]
            try:
                v_f = float(v)
                if v_f > 5:
                    return _pct_to_score(v_f)
                return v_f
            except (TypeError, ValueError):
                return None
    # Fall back: derive from KPI status
    rows = _default_kpi_status(staff_code) or []
    if not rows:
        return None
    avg_pct = sum(r.get("achievement_pct", 0) for r in rows) / len(rows)
    return _pct_to_score(avg_pct)


def _pct_to_score(pct: float) -> float:
    """Map achievement % to BSC 1-5 scale.
    150%+ → 5.0
    120%+ → 4.5
    100%+ → 4.0
    90%+  → 3.5
    80%+  → 3.0
    <80%  → linear scaling [0% → 1.0, 80% → 3.0]
    """
    if pct >= 150: return 5.0
    if pct >= 120: return 4.5
    if pct >= 100: return 4.0
    if pct >= 90:  return 3.5
    if pct >= 80:  return 3.0
    return round(1.0 + (pct / 80.0) * 2.0, 2)


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.performance_insights self-test")

    # Mock everything for deterministic test
    kpi_data = {
        "S001": [
            {"kpi_id": "DEP_GROWTH",  "achievement_pct": 130},
            {"kpi_id": "LOAN_GROWTH", "achievement_pct": 115},
            {"kpi_id": "NPL_PCT",     "achievement_pct": 95},
            {"kpi_id": "AML_SLA",     "achievement_pct": 80},
        ],
        "S002": [],
    }
    plan_data = {
        "S001": {"promotion_readiness": 0.75, "skill_gaps": []},
        "S002": {},
    }
    overall_data = {
        ("S001", "2026-04"): 3.8,
    }

    # Patch _staff_lookup via module monkey patch
    import utils.performance_insights as pi
    original_lookup = pi._staff_lookup
    pi._staff_lookup = lambda sc: {"full_name": "Test"} if sc in ("S001", "S002") else None

    try:
        r = pi.get_performance_insights(
            "S001", today=date(2026, 4, 15),
            kpi_status_fn=lambda sc: kpi_data.get(sc, []),
            growth_plan_fn=lambda sc: plan_data.get(sc, {}),
            overall_score_fn=lambda sc, p: overall_data.get((sc, p)),
        )
        # Spec contract
        assert "overall_score" in r
        assert "strengths" in r
        assert "promotion_readiness" in r
        assert r["overall_score"] == 3.8
        # Strengths: DEP_GROWTH (130) and LOAN_GROWTH (115) qualify
        assert r["strengths"] == ["DEP_GROWTH", "LOAN_GROWTH"]
        assert r["promotion_readiness"] == 0.75
        print(f"  ✅ S001 insights: overall={r['overall_score']}, "
              f"strengths={r['strengths']}, readiness={r['promotion_readiness']}")

        # Case 2: No data → graceful zeros, but staff exists so non-empty
        r2 = pi.get_performance_insights(
            "S002", today=date(2026, 4, 15),
            kpi_status_fn=lambda sc: kpi_data.get(sc, []),
            growth_plan_fn=lambda sc: plan_data.get(sc, {}),
            overall_score_fn=lambda sc, p: None,
        )
        assert r2["overall_score"] == 0.0
        assert r2["strengths"] == []
        assert r2["promotion_readiness"] == 0.0
        print(f"  ✅ S002 graceful zeros: {r2['overall_score']}, "
              f"{r2['strengths']}, {r2['promotion_readiness']}")

        # Case 3: Unknown staff → {}
        r3 = pi.get_performance_insights(
            "UNKNOWN",
            kpi_status_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {},
            overall_score_fn=lambda sc, p: None,
        )
        assert r3 == {}
        print(f"  ✅ unknown staff → {{}}")

        # Case 4: Bad input
        assert pi.get_performance_insights("") == {}
        print(f"  ✅ empty staff_code → {{}}")

        # Case 5: pct_to_score mapping
        assert pi._pct_to_score(150) == 5.0
        assert pi._pct_to_score(120) == 4.5
        assert pi._pct_to_score(100) == 4.0
        assert pi._pct_to_score(90) == 3.5
        assert pi._pct_to_score(80) == 3.0
        # Below 80: 0% → 1.0, 80% → 3.0
        assert pi._pct_to_score(0) == 1.0
        assert pi._pct_to_score(40) == 2.0
        print(f"  ✅ pct→score mapping correct")

        # Case 6: Strengths cap at 5
        many_strengths = {"K1": 200, "K2": 180, "K3": 160, "K4": 140,
                           "K5": 130, "K6": 120, "K7": 115}
        kpis_many = [{"kpi_id": k, "achievement_pct": v} for k, v in many_strengths.items()]
        r4 = pi.get_performance_insights(
            "S001", today=date(2026, 4, 15),
            kpi_status_fn=lambda sc: kpis_many,
            growth_plan_fn=lambda sc: {},
            overall_score_fn=lambda sc, p: 4.5,
        )
        assert len(r4["strengths"]) == 5  # cap
        # Sorted desc
        assert r4["strengths"] == ["K1", "K2", "K3", "K4", "K5"]
        print(f"  ✅ strengths capped at 5, sorted desc: {r4['strengths']}")

        # Case 7: Meta block
        assert "meta" in r
        assert r["meta"]["staff_code"] == "S001"
        assert "signals_present" in r["meta"]
        assert r["meta"]["signals_present"]["kpi_status"] is True
        print(f"  ✅ meta block: {r['meta']['signals_present']}")

    finally:
        pi._staff_lookup = original_lookup

    print("\n  ALL TESTS PASSED")
