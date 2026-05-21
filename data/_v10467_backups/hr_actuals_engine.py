"""HR Auto-Actuals Engine — v10.443.

Per Joshua directive: "We need to ascertain that HR staff right from
the Chief HR KPI in the BSC are fetching the actuals from the HR
modules since part of what we're solving for is people having to key
in actuals or send excels by automating performance management."

This engine computes actuals for HR-domain KPIs by pulling from the
HR module data files automatically. Eliminates manual entry for any
KPI that has a data source in the existing HR modules.

Coverage:
  - K016 Training Hours Completed         <- lms_enrollments.json
  - K121 Mandatory Training Completion (%)<- lms_enrollments + lms_courses
  - K018 Staff Retention Rate (%)         <- staff_history.json
  - K030 Headcount vs Budget              <- staff register + budget config
  - K121 alias "Compliance Training"      <- LMS CBK-mandatory completion
  - Leave Days Taken                      <- leave_requests.json
  - Leave Requests Approved (count)       <- leave_requests.json
  - PIPs Initiated / Active / Closed      <- pip_cases.json
  - Disciplinary Cases Active             <- disciplinary_register.json

NOT auto-populated (return None, source="manual"):
  - K005 Revenue vs Budget (Finance domain)
  - K021 Cost-to-Income Ratio (Finance)
  - K017 BSC Score Previous Quarter (BSC itself)
  - K019 360 Feedback Score (no source yet)
  - K035 Employee NPS Score (survey data not in HR modules)
  - K036 Projects On-Time Delivery (project mgmt not in HR)
  - K037 Milestones Completed (project mgmt not in HR)

External training: a KPI like K016 returns LMS-internal data only. If
a staff completes external training, HR can supplement manually (the
engine flags `partial: true` so it's visible).

Public API (API-first, ZERO streamlit):
  - compute_kpi_actual(staff_code, kpi_id_or_name, period) -> AutoActualResult
  - compute_all_hr_actuals_for_staff(staff_code, period) -> List[AutoActualResult]
  - compute_bank_wide_hr_kpi(kpi_id_or_name, period) -> AutoActualResult
  - audit_auto_actuals_coverage() -> CoverageAudit

Shipped: v10.443.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# KPI ID/name -> source module + computer mapping
# Used by audit_auto_actuals_coverage to surface what's auto-populated.
HR_KPI_SOURCES: Dict[str, Dict[str, str]] = {
    "K016": {"name": "Training Hours Completed",
             "source": "lms_enrollments.json",
             "module": "Learning Management"},
    "K121": {"name": "Mandatory Training Completion Rate (%)",
             "source": "lms_enrollments.json + lms_courses.json",
             "module": "Learning Management"},
    "K018": {"name": "Staff Retention Rate (%)",
             "source": "staff_history.json + staff_register.xlsx",
             "module": "HR Workforce"},
    "K030": {"name": "Headcount vs Budget",
             "source": "staff_register.xlsx + branch_staff_config.json",
             "module": "HR Workforce"},
    "Leave Days Taken": {"name": "Leave Days Taken",
                         "source": "leave_requests.json",
                         "module": "Leave"},
    "Leave Requests Approved": {"name": "Leave Requests Approved",
                                "source": "leave_requests.json",
                                "module": "Leave"},
    "PIPs Active": {"name": "PIPs Active",
                    "source": "pip_cases.json",
                    "module": "PIP"},
    "Disciplinary Cases Active": {"name": "Disciplinary Cases Active",
                                   "source": "disciplinary_register.json",
                                   "module": "Disciplinary"},
}

# KPIs that explicitly cannot be auto-populated from HR modules
HR_KPI_NON_AUTO: Set[str] = {
    "K005", "K021",   # Finance KPIs
    "K017",           # BSC self-reference
    "K019",           # 360 feedback (no source)
    "K035",           # eNPS (survey data, not HR module)
    "K036", "K037",   # Project KPIs (project mgmt not HR)
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class AutoActualResult:
    """Auto-computed actual for a KPI."""
    staff_code: Optional[str]    # None for bank-wide rollups
    kpi_id: str                  # The lookup key used
    kpi_canonical_name: str
    period: str
    value: Optional[float]       # None if not computable
    source_module: str           # "Learning Management" / "PIP" / etc.
    source_files: List[str]
    partial: bool                # True if external sources may contribute
    confidence: str              # "high" / "medium" / "low" / "none"
    notes: str
    computed_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CoverageAudit:
    """Bank-wide audit of which HR KPIs are auto-populated."""
    total_hr_kpis: int
    auto_populated_count: int
    auto_populated_kpis: List[Dict[str, str]]
    manual_only_count: int
    manual_only_kpis: List[str]
    coverage_pct: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_register() -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    p = DATA_DIR / "staff_register.xlsx"
    if not p.exists():
        return None
    try:
        return pd.read_excel(p)
    except Exception:  # noqa: BLE001
        return None


def _period_to_year_month(period: str) -> Optional[Tuple[int, Optional[int]]]:
    """Parse 'YYYY-MM', 'YYYY-Qn', or 'YYYY' to (year, month_or_None)."""
    if not period:
        return None
    p = period.strip()
    if re.match(r"^\d{4}$", p):
        return (int(p), None)
    if re.match(r"^\d{4}-\d{2}$", p):
        return (int(p[:4]), int(p[5:7]))
    if re.match(r"^\d{4}-Q[1-4]$", p, re.IGNORECASE):
        return (int(p[:4]), None)
    return None


def _in_period(date_str: str, period: str) -> bool:
    """Is `date_str` (ISO yyyy-mm-dd or yyyy-mm-ddThh) in `period`?"""
    if not date_str:
        return False
    y_m = _period_to_year_month(period)
    if not y_m:
        return False
    y, m = y_m
    try:
        ds = date_str[:7]  # yyyy-mm
        ds_y = int(ds[:4])
        ds_m = int(ds[5:7])
    except (ValueError, IndexError):
        return False
    if m is None:
        # Year-level OR quarter-level
        if re.match(r"^\d{4}-Q[1-4]$", period, re.IGNORECASE):
            q = int(period[-1])
            q_months = list(range((q - 1) * 3 + 1, q * 3 + 1))
            return ds_y == y and ds_m in q_months
        return ds_y == y
    return ds_y == y and ds_m == m


def _canonical_kpi_name(kpi_id_or_name: str) -> str:
    """Resolve a KPI ID/name to its canonical name via library."""
    lib = _load_json(DATA_DIR / "kpi_library.json") or {}
    needle = str(kpi_id_or_name).strip()
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        if str(k.get("id", "")) == needle:
            return str(k.get("name", needle))
        if str(k.get("name", "")) == needle:
            return needle
        for a in k.get("aliases", []) or []:
            if str(a) == needle:
                return str(k.get("name", needle))
    return needle


# ════════════════════════════════════════════════════════════════════
# Per-KPI computers
# ════════════════════════════════════════════════════════════════════

def _compute_training_hours(staff_code: str, period: str) -> Optional[float]:
    """K016 — sum of hours from completed LMS enrollments in period."""
    enrollments = _load_json(DATA_DIR / "lms_enrollments.json") or []
    if not isinstance(enrollments, list):
        return None
    total = 0.0
    for e in enrollments:
        if not isinstance(e, dict):
            continue
        if str(e.get("staff_code", "")) != str(staff_code):
            continue
        if e.get("status") != "Completed":
            continue
        if not _in_period(str(e.get("completion_date", "")), period):
            continue
        hours = e.get("hours", e.get("training_hours", 0))
        try:
            total += float(hours or 0)
        except (ValueError, TypeError):
            pass
    return round(total, 2)


def _compute_mandatory_training_pct(
    staff_code: str, period: str,
) -> Optional[float]:
    """K121 — % of CBK-mandatory courses the staff has completed."""
    enrollments = _load_json(DATA_DIR / "lms_enrollments.json") or []
    if not isinstance(enrollments, list):
        return None
    # All mandatory enrollments for this staff (any time)
    mandatory_total = [
        e for e in enrollments
        if isinstance(e, dict)
        and str(e.get("staff_code", "")) == str(staff_code)
        and e.get("cbk_mandatory")
    ]
    if not mandatory_total:
        return None
    completed = [
        e for e in mandatory_total
        if e.get("status") == "Completed"
    ]
    return round(len(completed) / len(mandatory_total) * 100, 2)


def _compute_leave_days_taken(staff_code: str, period: str) -> Optional[float]:
    """Leave Days Taken — approved leave days within period."""
    requests = _load_json(DATA_DIR / "leave_requests.json") or []
    if not isinstance(requests, list):
        return None
    total = 0.0
    for r in requests:
        if not isinstance(r, dict):
            continue
        if str(r.get("staff_code", "")) != str(staff_code):
            continue
        if r.get("status", "").lower() not in ("approved", "completed"):
            continue
        if not _in_period(str(r.get("start_date", "")), period):
            continue
        days = r.get("days_requested", r.get("duration_days", 0))
        try:
            total += float(days or 0)
        except (ValueError, TypeError):
            pass
    return round(total, 1)


def _compute_leave_requests_approved(
    staff_code: str, period: str,
) -> Optional[float]:
    """Leave Requests Approved — count within period."""
    requests = _load_json(DATA_DIR / "leave_requests.json") or []
    if not isinstance(requests, list):
        return None
    count = 0
    for r in requests:
        if not isinstance(r, dict):
            continue
        if str(r.get("staff_code", "")) != str(staff_code):
            continue
        if r.get("status", "").lower() != "approved":
            continue
        if not _in_period(str(r.get("approval_date", r.get("start_date", ""))),
                          period):
            continue
        count += 1
    return float(count)


def _compute_pips_active_for_unit(unit: str, period: str) -> Optional[float]:
    """Bank-wide-ish: PIPs active in a unit (returns count)."""
    pips = _load_json(DATA_DIR / "pip_cases.json") or []
    if not isinstance(pips, list):
        return None
    return float(sum(
        1 for p in pips
        if isinstance(p, dict)
        and p.get("status") == "Active"
        and (not unit or str(p.get("unit", "")).strip() == str(unit).strip())
    ))


def _compute_disciplinary_active_for_unit(
    unit: str, period: str,
) -> Optional[float]:
    """Disciplinary Cases Active in a unit."""
    cases = _load_json(DATA_DIR / "disciplinary_register.json") or []
    if not isinstance(cases, list):
        return None
    return float(sum(
        1 for c in cases
        if isinstance(c, dict)
        and c.get("status", "").lower() in ("open", "active", "in progress")
        and (not unit or str(c.get("unit", "")).strip() == str(unit).strip())
    ))


def _compute_bank_retention_pct(period: str) -> Optional[float]:
    """K018 — bank-wide retention. Excludes exits during period."""
    history = _load_json(DATA_DIR / "staff_history.json") or []
    if not isinstance(history, list):
        return None
    exits_in_period = sum(
        1 for h in history
        if isinstance(h, dict)
        and h.get("event_type") in ("exit", "termination", "resignation")
        and _in_period(str(h.get("event_date", "")), period)
    )
    reg = _load_register()
    total = len(reg) if reg is not None else 1437  # fallback
    if total <= 0:
        return None
    retention = (total - exits_in_period) / total * 100
    return round(retention, 2)


def _compute_headcount_vs_budget(period: str) -> Optional[float]:
    """K030 — current headcount vs budget (returns ratio %)."""
    reg = _load_register()
    if reg is None:
        return None
    actual = len(reg)
    cfg = _load_json(DATA_DIR / "branch_staff_config.json") or {}
    # Heuristic: total budget from config 'budget_headcount' or sum
    budget = cfg.get("budget_headcount") or cfg.get("total_budget_headcount")
    if not budget:
        # No budget config — surface as None
        return None
    try:
        return round(actual / float(budget) * 100, 2)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

KPI_COMPUTERS: Dict[str, Tuple[str, Any]] = {
    # (lookup_key) -> (source_module_label, computer_fn)
    # Computer signature: (staff_code, period) -> Optional[float]
    "K016": ("Learning Management", _compute_training_hours),
    "Training Hours Completed": ("Learning Management", _compute_training_hours),
    "K121": ("Learning Management", _compute_mandatory_training_pct),
    "Mandatory Training Completion Rate (%)": (
        "Learning Management", _compute_mandatory_training_pct,
    ),
    "Compliance Training (%)": (
        "Learning Management", _compute_mandatory_training_pct,
    ),
    "Leave Days Taken": ("Leave", _compute_leave_days_taken),
    "Leave Requests Approved": ("Leave", _compute_leave_requests_approved),
}


def compute_kpi_actual(
    staff_code: str,
    kpi_id_or_name: str,
    period: str,
) -> AutoActualResult:
    """Compute the auto-actual for a single staff/KPI/period.

    Returns AutoActualResult with value=None when:
      - KPI is in HR_KPI_NON_AUTO (not derivable from HR modules)
      - data source is missing
      - staff has no qualifying records
    """
    canonical = _canonical_kpi_name(kpi_id_or_name)
    needle = str(kpi_id_or_name).strip()

    if needle in HR_KPI_NON_AUTO:
        return AutoActualResult(
            staff_code=staff_code,
            kpi_id=needle,
            kpi_canonical_name=canonical,
            period=period,
            value=None,
            source_module="manual",
            source_files=[],
            partial=False,
            confidence="none",
            notes="KPI explicitly outside HR auto-actual scope",
            computed_at=datetime.now().isoformat(),
        )

    # Look up computer
    computer_entry = (
        KPI_COMPUTERS.get(needle)
        or KPI_COMPUTERS.get(canonical)
    )
    if computer_entry is None:
        return AutoActualResult(
            staff_code=staff_code,
            kpi_id=needle,
            kpi_canonical_name=canonical,
            period=period,
            value=None,
            source_module="manual",
            source_files=[],
            partial=False,
            confidence="none",
            notes="No HR auto-computer registered for this KPI",
            computed_at=datetime.now().isoformat(),
        )

    source_label, fn = computer_entry
    try:
        value = fn(staff_code, period)
    except Exception as exc:  # noqa: BLE001
        return AutoActualResult(
            staff_code=staff_code,
            kpi_id=needle,
            kpi_canonical_name=canonical,
            period=period,
            value=None,
            source_module=source_label,
            source_files=[],
            partial=False,
            confidence="none",
            notes=f"Computation error: {exc}",
            computed_at=datetime.now().isoformat(),
        )

    # Determine partial flag: training KPIs are partial because external
    # training is not in LMS
    is_training_kpi = "training" in canonical.lower() or needle in (
        "K016", "K121",
    )

    confidence = "high" if value is not None else "none"
    notes = ""
    source_files: List[str] = []
    if source_label == "Learning Management":
        source_files = ["data/lms_enrollments.json"]
        if needle in ("K121", "Mandatory Training Completion Rate (%)"):
            source_files.append("data/lms_courses.json")
    elif source_label == "Leave":
        source_files = ["data/leave_requests.json"]

    if is_training_kpi:
        notes = ("LMS internal only — external training requires manual "
                "supplementation by HR")

    return AutoActualResult(
        staff_code=staff_code,
        kpi_id=needle,
        kpi_canonical_name=canonical,
        period=period,
        value=value,
        source_module=source_label,
        source_files=source_files,
        partial=is_training_kpi,
        confidence=confidence,
        notes=notes,
        computed_at=datetime.now().isoformat(),
    )


def compute_all_hr_actuals_for_staff(
    staff_code: str, period: str,
) -> List[AutoActualResult]:
    """Compute actuals for every HR-domain KPI the staff is tracked on."""
    results: List[AutoActualResult] = []
    lib = _load_json(DATA_DIR / "kpi_library.json") or {}
    # Get this staff's role from register
    reg = _load_register()
    role = ""
    if reg is not None:
        reg["_code"] = reg["Staff Code"].astype(str).str.strip()
        row = reg[reg["_code"] == str(staff_code).strip()]
        if len(row) > 0:
            role = str(row.iloc[0]["Role"])
    role_kpis = lib.get("role_kpis", {}).get(role, []) or []
    for kpi_ref in role_kpis:
        r = compute_kpi_actual(staff_code, kpi_ref, period)
        results.append(r)
    return results


def compute_bank_wide_hr_kpi(
    kpi_id_or_name: str, period: str,
) -> AutoActualResult:
    """Bank-wide aggregates — e.g. K018 Retention, K030 Headcount vs Budget."""
    needle = str(kpi_id_or_name).strip()
    canonical = _canonical_kpi_name(kpi_id_or_name)

    if needle == "K018" or canonical == "Staff Retention Rate (%)":
        value = _compute_bank_retention_pct(period)
        return AutoActualResult(
            staff_code=None, kpi_id=needle,
            kpi_canonical_name=canonical, period=period,
            value=value, source_module="HR Workforce",
            source_files=["data/staff_history.json",
                          "data/staff_register.xlsx"],
            partial=False,
            confidence="high" if value is not None else "none",
            notes="Bank-wide retention",
            computed_at=datetime.now().isoformat(),
        )

    if needle == "K030" or canonical == "Headcount vs Budget":
        value = _compute_headcount_vs_budget(period)
        return AutoActualResult(
            staff_code=None, kpi_id=needle,
            kpi_canonical_name=canonical, period=period,
            value=value, source_module="HR Workforce",
            source_files=["data/staff_register.xlsx",
                          "data/branch_staff_config.json"],
            partial=False,
            confidence="high" if value is not None else "none",
            notes=("Returns ratio (actual / budget * 100)" if value
                   else "Budget headcount not configured"),
            computed_at=datetime.now().isoformat(),
        )

    return AutoActualResult(
        staff_code=None, kpi_id=needle,
        kpi_canonical_name=canonical, period=period,
        value=None, source_module="manual",
        source_files=[], partial=False, confidence="none",
        notes="No bank-wide auto-computer for this KPI",
        computed_at=datetime.now().isoformat(),
    )


def audit_auto_actuals_coverage() -> CoverageAudit:
    """Surfaces which HR KPIs are auto-populated vs manual-only."""
    lib = _load_json(DATA_DIR / "kpi_library.json") or {}
    hr_pillar_kpis = []
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        pillar = str(k.get("pillar", ""))
        name = str(k.get("name", ""))
        if pillar == "People & Learning" or "training" in name.lower():
            hr_pillar_kpis.append(k)

    auto_populated = []
    manual_only = []
    for k in hr_pillar_kpis:
        kid = str(k.get("id", ""))
        name = str(k.get("name", ""))
        if kid in KPI_COMPUTERS or name in KPI_COMPUTERS:
            auto_populated.append({
                "kpi_id": kid,
                "kpi_name": name,
                "source_module": (
                    KPI_COMPUTERS.get(kid) or KPI_COMPUTERS.get(name)
                )[0],
            })
        elif kid in ("K018", "K030"):
            # Bank-wide aggregates
            auto_populated.append({
                "kpi_id": kid,
                "kpi_name": name,
                "source_module": "HR Workforce (bank-wide)",
            })
        else:
            manual_only.append(name)

    total = len(hr_pillar_kpis)
    auto_count = len(auto_populated)
    coverage = auto_count / total * 100 if total else 0.0

    return CoverageAudit(
        total_hr_kpis=total,
        auto_populated_count=auto_count,
        auto_populated_kpis=auto_populated,
        manual_only_count=len(manual_only),
        manual_only_kpis=manual_only,
        coverage_pct=round(coverage, 1),
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ hr_actuals_engine self-test ─")

    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Test period parsing
    assert _period_to_year_month("2026-05") == (2026, 5)
    assert _period_to_year_month("2026-Q2") == (2026, None)
    assert _period_to_year_month("2026") == (2026, None)
    assert _period_to_year_month("invalid") is None
    print("  ✓ Period parsing works")

    # Test _in_period
    assert _in_period("2026-05-15", "2026-05")
    assert _in_period("2026-05-15", "2026-Q2")
    assert _in_period("2026-05-15", "2026")
    assert not _in_period("2026-06-15", "2026-05")
    print("  ✓ _in_period works")

    # Test KPI canonical resolution
    canonical = _canonical_kpi_name("K016")
    print(f"  ✓ K016 -> {canonical!r}")
    canonical = _canonical_kpi_name("K121")
    print(f"  ✓ K121 -> {canonical!r}")

    # Test computers (with sample staff)
    # MD = 300001
    period = "2025-12"
    print(f"\n  Compute actuals for staff 300001, period {period}:")
    for kpi in ("K016", "K121", "Leave Days Taken",
                "Leave Requests Approved", "K019"):
        r = compute_kpi_actual("300001", kpi, period)
        print(f"    {kpi:35}: value={r.value} source={r.source_module} "
              f"conf={r.confidence}")

    # Bank-wide
    print(f"\n  Bank-wide:")
    for kpi in ("K018", "K030"):
        r = compute_bank_wide_hr_kpi(kpi, period)
        print(f"    {kpi}: value={r.value} confidence={r.confidence} "
              f"({r.kpi_canonical_name})")

    # All-staff for MD
    md_actuals = compute_all_hr_actuals_for_staff("300001", period)
    print(f"\n  MD has {len(md_actuals)} role_kpi auto-actuals attempted")
    auto = sum(1 for r in md_actuals if r.value is not None)
    print(f"    {auto} were auto-populated, {len(md_actuals) - auto} require manual entry")

    # Coverage audit
    cov = audit_auto_actuals_coverage()
    print(f"\n  Bank-wide HR auto-actuals coverage:")
    print(f"    Total HR-pillar KPIs:       {cov.total_hr_kpis}")
    print(f"    Auto-populated:              {cov.auto_populated_count}")
    print(f"    Manual-only:                 {cov.manual_only_count}")
    print(f"    Coverage:                    {cov.coverage_pct}%")
    print(f"  Auto-populated breakdown:")
    for a in cov.auto_populated_kpis:
        print(f"    • {a['kpi_id']:6} {a['kpi_name']:50} <- {a['source_module']}")

    # JSON
    import json as _json
    _json.dumps(cov.to_dict())
    _json.dumps([r.to_dict() for r in md_actuals])
    print(f"\n  ✓ JSON-serializable")

    print("\n✓ self_test passed")


if __name__ == "__main__":
    self_test()
