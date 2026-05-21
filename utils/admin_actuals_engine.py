"""utils/admin_actuals_engine.py — v10.455 Admin Auto-Actuals.

Per Joshua doctrine Phase 5 applied to Admin module (Central Nervous
System Coordination per Document 2). Auto-actuals for admin KPIs:
audit trail volume, compliance, RBAC coverage, standards wiring health.

Coverage (5 KPI auto-computers):
  - K_ADM_001 Audit Trail Volume (events)    <- audit_log entries
  - K_ADM_002 RBAC Coverage (%)              <- pages with require_access
  - K_ADM_003 Standards Wiring Coverage (%)  <- standards_wiring_audit_engine
  - K_ADM_004 User Active Rate (%)           <- users.json active flag
  - K_ADM_005 Module Configuration Health    <- canonical_admin checks

Public API (API-first, ZERO streamlit):
  - compute_kpi_actual(staff_code, kpi_id_or_name, period)
  - compute_all_admin_actuals_for_staff(staff_code, period)
  - compute_bank_wide_admin_kpi(kpi_id_or_name, period)
  - audit_auto_actuals_coverage()

Shipped: v10.455.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
PAGES_DIR = REPO_ROOT / "pages"
UTILS_DIR = REPO_ROOT / "utils"

ADMIN_KPI_SOURCES: Dict[str, Dict[str, str]] = {
    "K_ADM_001": {"name": "Audit Trail Volume",
                  "source": "data/audit_log.json",
                  "module": "Admin Audit"},
    "K_ADM_002": {"name": "RBAC Coverage (%)",
                  "source": "pages/ require_access scan",
                  "module": "Admin Security"},
    "K_ADM_003": {"name": "Standards Wiring Coverage (%)",
                  "source": "standards_wiring_audit_engine",
                  "module": "Admin Standards"},
    "K_ADM_004": {"name": "User Active Rate (%)",
                  "source": "data/users.json",
                  "module": "Admin Users"},
    "K_ADM_005": {"name": "Module Configuration Health",
                  "source": "utils/canonical_admin checks",
                  "module": "Admin Config"},
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
    total_admin_kpis: int
    auto_populated: int
    partial: int
    manual: int
    coverage_pct: float
    auto_kpi_ids: List[str]
    manual_kpi_ids: List[str]
    timestamp: str

    def to_dict(self): return asdict(self)


def _compute_k_adm_001(staff_code, period) -> Optional[float]:
    """Audit trail volume (event count)."""
    audit_file = DATA_DIR / "audit_log.json"
    if not audit_file.exists():
        return None
    try:
        data = json.loads(audit_file.read_text(encoding="utf-8"))
        events = data if isinstance(data, list) else data.get("events", [])
        if period:
            events = [e for e in events if isinstance(e, dict)
                     and str(e.get("timestamp", ""))[:7] == period]
        return float(len(events))
    except Exception:
        return None


def _compute_k_adm_002(staff_code, period) -> Optional[float]:
    """RBAC coverage % across all pages."""
    try:
        pages = list(PAGES_DIR.glob("*.py"))
        if not pages:
            return None
        with_rbac = 0
        for p in pages:
            try:
                if "require_access" in p.read_text(encoding="utf-8"):
                    with_rbac += 1
            except Exception:
                pass
        return float(with_rbac / len(pages) * 100)
    except Exception:
        return None


def _compute_k_adm_003(staff_code, period) -> Optional[float]:
    """Standards wiring coverage % from standards_wiring_audit_engine."""
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utils.standards_wiring_audit_engine import audit_standards_wiring
        result = audit_standards_wiring()
        return float(result.coverage_pct
                    if hasattr(result, "coverage_pct") else 0.0)
    except Exception:
        return None


def _compute_k_adm_004(staff_code, period) -> Optional[float]:
    """User active rate %."""
    users_file = DATA_DIR / "users.json"
    if not users_file.exists():
        return None
    try:
        data = json.loads(users_file.read_text(encoding="utf-8"))
        users = data.get("users", data) if isinstance(data, dict) else data
        if not isinstance(users, list):
            users = list(data.values()) if isinstance(data, dict) else []
        total = sum(1 for u in users if isinstance(u, dict))
        active = sum(1 for u in users if isinstance(u, dict) and u.get("active"))
        return float(active / total * 100) if total > 0 else 0.0
    except Exception:
        return None


def _compute_k_adm_005(staff_code, period) -> Optional[float]:
    """Module configuration health (canonical files present)."""
    canonical_files = [
        "users.json", "kpi_library.json", "target_cascade.json",
        "balanced_scorecards.json",
    ]
    present = sum(1 for f in canonical_files if (DATA_DIR / f).exists())
    return float(present / len(canonical_files) * 100)


_COMPUTERS = {
    "K_ADM_001": _compute_k_adm_001,
    "K_ADM_002": _compute_k_adm_002,
    "K_ADM_003": _compute_k_adm_003,
    "K_ADM_004": _compute_k_adm_004,
    "K_ADM_005": _compute_k_adm_005,
}


def compute_kpi_actual(staff_code, kpi_id_or_name, period) -> AutoActualResult:
    kpi_id = kpi_id_or_name
    info = ADMIN_KPI_SOURCES.get(kpi_id, {})
    name = info.get("name", kpi_id_or_name)
    if kpi_id in _COMPUTERS:
        try:
            val = _COMPUTERS[kpi_id](staff_code, period)
            return AutoActualResult(
                kpi_id=kpi_id, kpi_name=name, staff_code=staff_code,
                period=period, actual_value=val,
                source="auto" if val is not None else "partial",
                module=info.get("module", "Admin"),
                timestamp=datetime.now().isoformat(),
            )
        except Exception as exc:
            return AutoActualResult(
                kpi_id=kpi_id, kpi_name=name, staff_code=staff_code,
                period=period, actual_value=None, source="partial",
                module=info.get("module", "Admin"),
                timestamp=datetime.now().isoformat(),
                notes=f"compute error: {exc}",
            )
    return AutoActualResult(
        kpi_id=kpi_id, kpi_name=name, staff_code=staff_code,
        period=period, actual_value=None, source="manual",
        module=info.get("module", "Admin"),
        timestamp=datetime.now().isoformat(),
    )


def compute_all_admin_actuals_for_staff(staff_code, period):
    return [compute_kpi_actual(staff_code, kpi_id, period)
            for kpi_id in ADMIN_KPI_SOURCES]


def compute_bank_wide_admin_kpi(kpi_id_or_name, period):
    return compute_kpi_actual(None, kpi_id_or_name, period)


def audit_auto_actuals_coverage() -> CoverageAudit:
    auto_ids = list(_COMPUTERS.keys())
    manual_ids = [k for k in ADMIN_KPI_SOURCES if k not in _COMPUTERS]
    total = len(ADMIN_KPI_SOURCES)
    pct = len(auto_ids) / total * 100 if total else 0.0
    return CoverageAudit(
        total_admin_kpis=total,
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
    print(f"Admin auto-actuals coverage: {a.coverage_pct}%")
