"""utils.efficiency — Personal Efficiency Index (Standard #18, v5.44).

Per the master spec:

    class EfficiencyEngine:
        def calculate_efficiency_scores(self, staff_code, period):
            efficiency_by_kpi = {}
            for kpi_id in outputs.keys():
                time_invested = sum([t.duration for t in tasks if t.kpi == kpi_id])
                efficiency_by_kpi[kpi_id] = outputs[kpi_id] / time_invested
            return {"personal_efficiency": ..., "vs_peer_average": comparison}

Verification:
  - 80% task coverage  ← deployed-runtime metric (% of staff with
                          time-tracking data populated). OUT OF SCOPE.

The verifiable claim is structural correctness: given labeled
(outputs, time_invested) inputs, the math is right.

THE HONESTY PROBLEM
-------------------
"time_invested" assumes timesheet data we do not collect. Fabricating
hours per KPI would be dishonest. The honest move: derive PROXY
time-invested from observable signals — micro-task records (#13)
that already track per-task time estimates.

PROXY: time_invested(kpi_id) = sum of estimated_minutes from
microtasks completed in the period for that KPI. Each micro-task
type has a published estimate (e.g. "Make 5 outbound prospect calls"
≈ 30 minutes).

If a staff has no micro-task records for a KPI, efficiency_by_kpi
omits that KPI rather than fabricating a denominator. The output
clearly labels which KPIs have proxy time-invested vs which have
none.

The vs_peer_average comparison
------------------------------
Compares this staff to other staff with the same role + the same
KPI. Falls back to "no peer comparison available" when fewer than
3 peers have data. Never produces a single-peer comparison (would
be misleading).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.efficiency")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
EFFICIENCY_FILE = DATA_DIR / "efficiency_scores.json"

# Default proxy time per micro-task action, in minutes.
# These are EDUCATED estimates — not measured ground truth — and the
# engine documents them in result.meta.time_estimate_basis so callers
# know what they're consuming.
DEFAULT_TASK_TIME_ESTIMATES_MIN: Dict[str, int] = {
    "Make 5 outbound prospect calls today":           30,
    "Call the 3 oldest delinquent accounts today":     45,
    "Clear at least 2 AML alerts today":               60,
    "Resolve any open customer complaints in your queue today": 30,
    "Process 3 pending approvals before noon":         45,
    "Identify one specific action for this KPI today and execute it": 60,
}
GENERIC_TASK_TIME_MIN = 30   # used when task text isn't in the catalog
MIN_PEERS_FOR_COMPARISON = 3


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class EfficiencyScore:
    kpi_id:                 str = ""
    output:                 float = 0.0
    time_invested_minutes:  int = 0
    efficiency:             float = 0.0    # output per minute
    has_proxy_time:         bool = True


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class EfficiencyEngine:
    """Standard #18 — Personal Efficiency Index."""

    def __init__(
        self,
        outputs_fn:           Optional[Callable[[str, str], Dict[str, float]]] = None,
        completed_tasks_fn:   Optional[Callable[[str, str], List[dict]]] = None,
        peer_lookup_fn:       Optional[Callable[[str, str], List[str]]] = None,
        peer_efficiency_fn:   Optional[Callable[[str, str, str], Optional[float]]] = None,
        task_time_estimates:  Optional[Dict[str, int]] = None,
    ):
        """All collaborators injectable.

        outputs_fn(staff_code, period) → {kpi_id: actual_value}
            Returns the staff's outputs (BSC actuals) for the period.

        completed_tasks_fn(staff_code, period) → [{kpi_id, task, ...}]
            Returns micro-tasks completed by this staff in this period.
            Default reads data/microtasks.json filtered to completed.

        peer_lookup_fn(staff_code, period) → list[peer_staff_codes]
            Returns staff with the same role for vs_peer_average.

        peer_efficiency_fn(peer_staff_code, kpi_id, period) → float | None
            Returns the peer's efficiency on a KPI for the same period.

        task_time_estimates: dict[task_text, minutes] — defaults to
            module-level catalog.
        """
        self._outputs          = outputs_fn          or _default_outputs
        self._completed_tasks  = completed_tasks_fn  or _default_completed_tasks
        self._peer_lookup      = peer_lookup_fn      or _default_peer_lookup
        self._peer_efficiency  = peer_efficiency_fn  or _default_peer_efficiency
        self._task_estimates   = task_time_estimates or DEFAULT_TASK_TIME_ESTIMATES_MIN

    # ──────────────────────────────────────────────────────────────────
    # Spec entry
    # ──────────────────────────────────────────────────────────────────

    def calculate_efficiency_scores(
        self, staff_code: str, period: str,
    ) -> Dict[str, Any]:
        """Returns the spec-shaped dict.

        {
          "personal_efficiency": {kpi_id: efficiency_per_minute, ...},
          "vs_peer_average":     {kpi_id: ratio_or_None, ...},
          "meta":                {...full traceability...},
        }

        Returns {} for unknown staff / unknown period. Individual
        KPIs without proxy time are EXCLUDED from personal_efficiency
        rather than fabricated.
        """
        if not staff_code or not period:
            return {}
        outputs = self._outputs(staff_code, period) or {}
        if not outputs:
            return {}
        completed = self._completed_tasks(staff_code, period) or []

        # Aggregate proxy minutes per KPI from completed tasks
        time_by_kpi: Dict[str, int] = {}
        task_count_by_kpi: Dict[str, int] = {}
        for t in completed:
            if not isinstance(t, dict):
                continue
            kpi_id = t.get("kpi_id")
            if not kpi_id:
                continue
            task_text = t.get("task", "")
            mins = self._task_estimates.get(task_text, GENERIC_TASK_TIME_MIN)
            time_by_kpi[kpi_id] = time_by_kpi.get(kpi_id, 0) + int(mins)
            task_count_by_kpi[kpi_id] = task_count_by_kpi.get(kpi_id, 0) + 1

        personal: Dict[str, float] = {}
        scores: Dict[str, EfficiencyScore] = {}
        for kpi_id, output_value in outputs.items():
            try:
                output_f = float(output_value)
            except (TypeError, ValueError):
                continue
            if output_f < 0:
                continue
            mins = time_by_kpi.get(kpi_id, 0)
            if mins <= 0:
                # No proxy time → don't fabricate efficiency
                continue
            efficiency = output_f / mins
            personal[kpi_id] = round(efficiency, 6)
            scores[kpi_id] = EfficiencyScore(
                kpi_id=                kpi_id,
                output=                output_f,
                time_invested_minutes= mins,
                efficiency=            efficiency,
                has_proxy_time=        True,
            )

        # vs_peer_average
        vs_peer: Dict[str, Optional[float]] = {}
        peers = self._peer_lookup(staff_code, period) or []
        for kpi_id, my_eff in personal.items():
            peer_effs: List[float] = []
            for peer in peers:
                pe = self._peer_efficiency(peer, kpi_id, period)
                if pe is not None and pe > 0:
                    peer_effs.append(pe)
            if len(peer_effs) >= MIN_PEERS_FOR_COMPARISON:
                avg = sum(peer_effs) / len(peer_effs)
                vs_peer[kpi_id] = round(my_eff / avg, 4) if avg > 0 else None
            else:
                vs_peer[kpi_id] = None   # too few peers — refuse

        skipped = [
            kpi for kpi in outputs
            if kpi not in personal
        ]

        return {
            "personal_efficiency": personal,
            "vs_peer_average":     vs_peer,
            "meta": {
                "staff_code":           staff_code,
                "period":               period,
                "kpis_in_outputs":      list(outputs.keys()),
                "kpis_with_proxy_time": list(personal.keys()),
                "kpis_skipped":         skipped,
                "completed_tasks":      sum(task_count_by_kpi.values()),
                "tasks_per_kpi":        task_count_by_kpi,
                "time_estimate_basis":  "completed micro-task counts × per-action estimate",
                "min_peers_required":   MIN_PEERS_FOR_COMPARISON,
                "generated_at":         datetime.now(timezone.utc).isoformat(),
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _safe_load(path: Path, default):
    try:
        from utils.db import db
        return db.load_json(path, default=default)
    except Exception as e:
        logger.warning("efficiency: could not load %s: %s", path, e)
        return default


def _default_outputs(staff_code: str, period: str) -> Dict[str, float]:
    """Read BSC actuals via bsc_engine for all KPIs assigned to staff."""
    try:
        from utils import bsc_engine
    except Exception:
        return {}
    cascade = _safe_load(DATA_DIR / "target_cascade.json", {})
    if not isinstance(cascade, dict):
        return {}
    out: Dict[str, float] = {}
    seen: set = set()
    for _, block in cascade.items():
        if not isinstance(block, dict):
            continue
        kpi_id = block.get("kpi", "")
        if not kpi_id or kpi_id in seen:
            continue
        for alloc in block.get("allocations", []) or []:
            if isinstance(alloc, dict) and str(alloc.get("to_code", "")) == str(staff_code):
                try:
                    actual = bsc_engine.get_actual(staff_code, kpi_id, period)
                except Exception:
                    actual = None
                if actual is not None:
                    try:
                        out[kpi_id] = float(actual)
                        seen.add(kpi_id)
                    except (TypeError, ValueError):
                        continue
                break
    return out


def _default_completed_tasks(staff_code: str, period: str) -> List[dict]:
    """Read data/microtasks.json filtered to completed in this period."""
    raw = _safe_load(DATA_DIR / "microtasks.json", [])
    if not isinstance(raw, list):
        return []
    return [
        t for t in raw
        if isinstance(t, dict)
        and str(t.get("staff_code", "")) == str(staff_code)
        and str(t.get("period", "")) == str(period)
        and t.get("completed_at")
    ]


def _default_peer_lookup(staff_code: str, period: str) -> List[str]:
    """Find peers with same role from users.json."""
    users = _safe_load(DATA_DIR / "users.json", {})
    if not isinstance(users, dict):
        return []
    my_role = None
    for _, info in users.items():
        if isinstance(info, dict) and str(info.get("staff_code", "")) == str(staff_code):
            my_role = info.get("role")
            break
    if not my_role:
        return []
    peers: List[str] = []
    for _, info in users.items():
        if not isinstance(info, dict) or not info.get("active"):
            continue
        if info.get("role") == my_role:
            sc = str(info.get("staff_code", ""))
            if sc and sc != staff_code:
                peers.append(sc)
    return peers


def _default_peer_efficiency(peer_code: str, kpi_id: str, period: str) -> Optional[float]:
    """Compute peer's efficiency on a KPI by recursing into the
    engine. To prevent infinite recursion, we use a simpler direct
    calculation here."""
    outputs = _default_outputs(peer_code, period) or {}
    output = outputs.get(kpi_id)
    if output is None:
        return None
    completed = _default_completed_tasks(peer_code, period) or []
    mins = 0
    for t in completed:
        if isinstance(t, dict) and t.get("kpi_id") == kpi_id:
            task_text = t.get("task", "")
            mins += DEFAULT_TASK_TIME_ESTIMATES_MIN.get(task_text, GENERIC_TASK_TIME_MIN)
    if mins <= 0:
        return None
    try:
        return float(output) / mins
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_efficiency_scores(staff_code: str, period: str, scores: dict) -> bool:
    if not scores or not staff_code or not period:
        return False
    try:
        from utils.db import db
        existing = db.load_json(EFFICIENCY_FILE, default={})
    except Exception:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    by_staff = existing.setdefault(str(staff_code), {})
    if not isinstance(by_staff, dict):
        by_staff = {}
        existing[str(staff_code)] = by_staff
    by_staff[period] = scores
    try:
        from utils.db import db
        db.save_json(EFFICIENCY_FILE, existing)
        return True
    except Exception as e:
        logger.error("efficiency: could not save: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.efficiency self-test")

    outputs_data = {
        ("S001", "2026-04"): {"DEP_GROWTH": 100, "NPL_PCT": 80},
    }
    tasks_data = {
        ("S001", "2026-04"): [
            {"kpi_id": "DEP_GROWTH", "task": "Make 5 outbound prospect calls today"},  # 30
            {"kpi_id": "DEP_GROWTH", "task": "Make 5 outbound prospect calls today"},  # 30
            {"kpi_id": "NPL_PCT",    "task": "Call the 3 oldest delinquent accounts today"},  # 45
            # Note: no AML tasks, so AML_SLA wouldn't be in the result
        ],
    }
    peers_data = {
        ("S001", "2026-04"): ["S002", "S003", "S004"],
    }
    peer_eff_data = {
        ("S002", "DEP_GROWTH", "2026-04"): 1.5,
        ("S003", "DEP_GROWTH", "2026-04"): 1.6,
        ("S004", "DEP_GROWTH", "2026-04"): 1.7,
        ("S002", "NPL_PCT",    "2026-04"): 1.0,
        ("S003", "NPL_PCT",    "2026-04"): 1.2,
        # Only 2 peers with data → vs_peer_average for NPL = None
    }

    eng = EfficiencyEngine(
        outputs_fn=          lambda sc, p: outputs_data.get((sc, p), {}),
        completed_tasks_fn=  lambda sc, p: tasks_data.get((sc, p), []),
        peer_lookup_fn=      lambda sc, p: peers_data.get((sc, p), []),
        peer_efficiency_fn=  lambda sc, k, p: peer_eff_data.get((sc, k, p)),
    )

    # Case 1: Spec contract
    r = eng.calculate_efficiency_scores("S001", "2026-04")
    assert "personal_efficiency" in r
    assert "vs_peer_average" in r

    # Case 2: Math correctness
    # DEP_GROWTH: output=100, mins=60 → eff = 100/60 ≈ 1.667
    assert abs(r["personal_efficiency"]["DEP_GROWTH"] - (100/60)) < 1e-4
    # NPL_PCT: output=80, mins=45 → eff = 80/45 ≈ 1.778
    assert abs(r["personal_efficiency"]["NPL_PCT"] - (80/45)) < 1e-4
    print(f"  ✅ math correct: DEP={r['personal_efficiency']['DEP_GROWTH']:.3f}, "
          f"NPL={r['personal_efficiency']['NPL_PCT']:.3f}")

    # Case 3: vs_peer_average (3 peers w/ data)
    # peer avg = (1.5+1.6+1.7)/3 = 1.6; me = 1.667 → ratio = 1.04
    ratio = r["vs_peer_average"]["DEP_GROWTH"]
    assert ratio is not None
    assert 1.0 < ratio < 1.10
    print(f"  ✅ vs_peer_average DEP: {ratio:.3f} (3 peers)")

    # Case 4: Insufficient peers (<3) → None
    assert r["vs_peer_average"]["NPL_PCT"] is None
    print(f"  ✅ vs_peer_average NPL: None (only 2 peers)")

    # Case 5: KPI without proxy time SKIPPED, not fabricated
    # AML_SLA is not in outputs, but if it were we'd skip
    outputs_with_aml = {
        ("S001", "2026-04"): {"DEP_GROWTH": 100, "AML_SLA": 50},  # AML has no tasks
    }
    eng2 = EfficiencyEngine(
        outputs_fn=lambda sc, p: outputs_with_aml.get((sc, p), {}),
        completed_tasks_fn=  lambda sc, p: tasks_data.get((sc, p), []),
        peer_lookup_fn=      lambda sc, p: [],
        peer_efficiency_fn=  lambda sc, k, p: None,
    )
    r2 = eng2.calculate_efficiency_scores("S001", "2026-04")
    assert "DEP_GROWTH" in r2["personal_efficiency"]
    assert "AML_SLA" not in r2["personal_efficiency"]   # SKIPPED
    assert "AML_SLA" in r2["meta"]["kpis_skipped"]
    print(f"  ✅ AML_SLA correctly skipped (no proxy time)")

    # Case 6: Empty outputs → empty result
    eng3 = EfficiencyEngine(
        outputs_fn=lambda sc, p: {},
        completed_tasks_fn=lambda sc, p: [],
        peer_lookup_fn=lambda sc, p: [],
        peer_efficiency_fn=lambda sc, k, p: None,
    )
    assert eng3.calculate_efficiency_scores("S999", "2026-04") == {}
    print(f"  ✅ no outputs → {{}}")

    # Case 7: Bad inputs → empty
    assert eng.calculate_efficiency_scores("", "2026-04") == {}
    assert eng.calculate_efficiency_scores("S001", "") == {}
    print(f"  ✅ bad inputs → {{}}")

    # Case 8: Meta block traceability
    assert r["meta"]["kpis_with_proxy_time"] == ["DEP_GROWTH", "NPL_PCT"]
    assert r["meta"]["completed_tasks"] == 3
    assert r["meta"]["tasks_per_kpi"] == {"DEP_GROWTH": 2, "NPL_PCT": 1}
    print(f"  ✅ meta block populated: {r['meta']['completed_tasks']} tasks across "
          f"{len(r['meta']['kpis_with_proxy_time'])} KPIs")

    print("\n  ALL TESTS PASSED")
