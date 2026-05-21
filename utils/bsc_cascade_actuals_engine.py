"""utils/bsc_cascade_actuals_engine.py — v10.455 BSC & Cascade Auto-Actuals.

Per Joshua doctrine Phase 5 applied to BSC & Target Cascade module
(Brain Intelligence, Direction & Decision Flow per Document 2).
Auto-actuals for BSC-meta KPIs: scorecard completion, target lock
status, pillar weight invariants, cascade depth, score computability.

Coverage (5 KPI auto-computers):
  - K_BSC_001 Scorecard Completion (%)        <- balanced_scorecards.json
  - K_BSC_002 Target Cascade Lock Rate (%)    <- target_cascade locks
  - K_BSC_003 Pillar Weight Invariant Health  <- kpi_library weights = 1.0
  - K_BSC_004 360 Harmony (%)                 <- cascade_bsc_360_engine
  - K_BSC_005 BSC Engine Health (%)           <- bsc_audit_engine

Public API (API-first, ZERO streamlit):
  - compute_kpi_actual(staff_code, kpi_id_or_name, period)
  - compute_all_bsc_actuals_for_staff(staff_code, period)
  - compute_bank_wide_bsc_kpi(kpi_id_or_name, period)
  - audit_auto_actuals_coverage()

Shipped: v10.455.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

BSC_KPI_SOURCES: Dict[str, Dict[str, str]] = {
    "K_BSC_001": {"name": "Scorecard Completion (%)",
                  "source": "data/balanced_scorecards.json",
                  "module": "BSC Engine"},
    "K_BSC_002": {"name": "Target Cascade Lock Rate (%)",
                  "source": "data/target_cascade.json",
                  "module": "Target Cascade"},
    "K_BSC_003": {"name": "Pillar Weight Invariant Health",
                  "source": "kpi_library.json (role_kpis weight sums)",
                  "module": "KPI Library"},
    "K_BSC_004": {"name": "360 Harmony (%)",
                  "source": "cascade_bsc_360_engine",
                  "module": "Cascade-BSC 360"},
    "K_BSC_005": {"name": "BSC Engine Health (%)",
                  "source": "bsc_audit_engine",
                  "module": "BSC Audit"},
}


@dataclass
class AutoActualResult:
    kpi_id: str
    kpi_name: str
    staff_code: Optional[str]
    period: str
    actual_value: Optional[float]
    source: str
    module: str
    timestamp: str
    notes: str = ""

    def to_dict(self): return asdict(self)


@dataclass
class CoverageAudit:
    total_bsc_kpis: int
    auto_populated: int
    partial: int
    manual: int
    coverage_pct: float
    auto_kpi_ids: List[str]
    manual_kpi_ids: List[str]
    timestamp: str

    def to_dict(self): return asdict(self)


def _compute_k_bsc_001(staff_code, period) -> Optional[float]:
    """Scorecard completion %."""
    bsc_file = DATA_DIR / "balanced_scorecards.json"
    if not bsc_file.exists():
        return None
    try:
        data = json.loads(bsc_file.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("rows", [])
        if period:
            rows = [r for r in rows if isinstance(r, dict)
                   and r.get("period") == period]
        if not rows:
            return 0.0
        with_score = sum(1 for r in rows if isinstance(r, dict)
                        and r.get("final_score") is not None)
        return float(with_score / len(rows) * 100)
    except Exception:
        return None


def _compute_k_bsc_002(staff_code, period) -> Optional[float]:
    """Target cascade lock rate %."""
    tc_file = DATA_DIR / "target_cascade.json"
    if not tc_file.exists():
        return None
    try:
        data = json.loads(tc_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        # Count nodes with targets vs total
        total = 0
        with_targets = 0

        def _walk(node):
            nonlocal total, with_targets
            if isinstance(node, dict):
                if "targets" in node or "target" in node or "kpis" in node:
                    total += 1
                    if (node.get("targets") or node.get("target")
                        or node.get("kpis")):
                        with_targets += 1
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for v in node:
                    _walk(v)

        _walk(data)
        return float(with_targets / total * 100) if total > 0 else 0.0
    except Exception:
        return None


def _compute_k_bsc_003(staff_code, period) -> Optional[float]:
    """Pillar weight invariant: % of roles with weights summing to 1.0."""
    kpi_file = DATA_DIR / "kpi_library.json"
    if not kpi_file.exists():
        return None
    try:
        data = json.loads(kpi_file.read_text(encoding="utf-8"))
        role_kpis = data.get("role_kpis", {}) if isinstance(data, dict) else {}
        if not role_kpis:
            return None
        valid = 0
        total = 0
        for role, kpis in role_kpis.items():
            if not isinstance(kpis, list):
                continue
            total += 1
            weights = sum(float(k.get("weight", 0)) for k in kpis
                         if isinstance(k, dict))
            if abs(weights - 1.0) < 0.01:
                valid += 1
        return float(valid / total * 100) if total > 0 else 0.0
    except Exception:
        return None


def _compute_k_bsc_004(staff_code, period) -> Optional[float]:
    """360 harmony % from cascade_bsc_360_engine."""
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
        result = cascade_bsc_360_audit()
        return float(result.overall_harmony_pct)
    except Exception:
        return None


def _compute_k_bsc_005(staff_code, period) -> Optional[float]:
    """BSC engine health % from bsc_audit_engine."""
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utils.bsc_audit_engine import bsc_full_audit
        result = bsc_full_audit()
        return float(result.overall_health_pct)
    except Exception:
        return None


_COMPUTERS = {
    "K_BSC_001": _compute_k_bsc_001,
    "K_BSC_002": _compute_k_bsc_002,
    "K_BSC_003": _compute_k_bsc_003,
    "K_BSC_004": _compute_k_bsc_004,
    "K_BSC_005": _compute_k_bsc_005,
}


def compute_kpi_actual(staff_code, kpi_id_or_name, period) -> AutoActualResult:
    kpi_id = kpi_id_or_name
    info = BSC_KPI_SOURCES.get(kpi_id, {})
    name = info.get("name", kpi_id_or_name)
    if kpi_id in _COMPUTERS:
        try:
            val = _COMPUTERS[kpi_id](staff_code, period)
            return AutoActualResult(
                kpi_id=kpi_id, kpi_name=name, staff_code=staff_code,
                period=period, actual_value=val,
                source="auto" if val is not None else "partial",
                module=info.get("module", "BSC"),
                timestamp=datetime.now().isoformat(),
            )
        except Exception as exc:
            return AutoActualResult(
                kpi_id=kpi_id, kpi_name=name, staff_code=staff_code,
                period=period, actual_value=None, source="partial",
                module=info.get("module", "BSC"),
                timestamp=datetime.now().isoformat(),
                notes=f"compute error: {exc}",
            )
    return AutoActualResult(
        kpi_id=kpi_id, kpi_name=name, staff_code=staff_code,
        period=period, actual_value=None, source="manual",
        module=info.get("module", "BSC"),
        timestamp=datetime.now().isoformat(),
    )


def compute_all_bsc_actuals_for_staff(staff_code, period):
    return [compute_kpi_actual(staff_code, kpi_id, period)
            for kpi_id in BSC_KPI_SOURCES]


def compute_bank_wide_bsc_kpi(kpi_id_or_name, period):
    return compute_kpi_actual(None, kpi_id_or_name, period)


def audit_auto_actuals_coverage() -> CoverageAudit:
    auto_ids = list(_COMPUTERS.keys())
    manual_ids = [k for k in BSC_KPI_SOURCES if k not in _COMPUTERS]
    total = len(BSC_KPI_SOURCES)
    pct = len(auto_ids) / total * 100 if total else 0.0
    return CoverageAudit(
        total_bsc_kpis=total,
        auto_populated=len(auto_ids),
        partial=0,
        manual=len(manual_ids),
        coverage_pct=round(pct, 1),
        auto_kpi_ids=auto_ids,
        manual_kpi_ids=manual_ids,
        timestamp=datetime.now().isoformat(),
    )


if __name__ == "__main__":  # pragma: no cover
    a = audit_auto_actuals_coverage()
    print(f"BSC auto-actuals coverage: {a.coverage_pct}%")
