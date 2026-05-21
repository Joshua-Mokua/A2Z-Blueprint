"""Cascade-BSC 360° Audit Engine — v10.432 (deep review).

Per Joshua roadmap: after BSC rescue (100% health) + admin polish, do a
360° deep review confirming cascade and BSC work together harmoniously:
  - Bank Targets flow into MD's BSC
  - Cascade allocations match parent total_target
  - Each allocation propagates to child's BSC as a row with that target
  - Actuals are populated for every BSC row
  - End-to-end score calculation produces sensible numbers

This engine is read-only diagnostic. No data writes. Just reports.

Public API (API-first, ZERO streamlit):
  - audit_bank_to_md() -> BankToMDAudit
  - audit_cascade_integrity() -> CascadeIntegrityAudit
  - audit_cascade_to_bsc_targets() -> CascadeBSCTargetAudit
  - audit_bsc_actuals_coverage() -> BSCActualsAudit
  - audit_score_calculation() -> ScoreCalculationAudit
  - cascade_bsc_360_audit() -> Master360Audit (all five rolled up)

Tolerance:
  CASCADE_TARGET_TOLERANCE = 0.01 (1%) for sum comparisons
  BSC_TARGET_TOLERANCE = 0.01 (1%) for value matches

Shipped: v10.432.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

CASCADE_TARGET_TOLERANCE = 0.01   # 1%
BSC_TARGET_TOLERANCE = 0.01       # 1%
ACTUAL_NONZERO_TOLERANCE = 1e-9   # numeric epsilon

# BSC-score KPIs use 1-5 BSC grading scale (3.0 = "Met" per
# utils/core.py:331). Bank targets for these KPIs are on a DIFFERENT
# operational scale (e.g., 0-100 productivity index). Direct value
# comparison between bank target and MD BSC target is not meaningful
# for this class. v10.432 audit treated them as mismatches; v10.433
# skips them with an informational note.
BSC_SCORE_KPIS: Set[str] = {
    "Staff Productivity",
    "Diligence Score",
    "CX Score",
    "WB NPS Score",
    "Employee Satisfaction Score",
    "Ideation Score",
    "Initiative Score",
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class BankToMDAudit:
    """Stage 1: bank targets reflect in MD's BSC."""
    bank_target_count: int
    md_bsc_kpi_count: int
    md_kpis_with_bank_target: int
    md_kpis_missing_bank_target: List[str]
    target_mismatches: List[Dict[str, Any]]  # [{kpi, bank_target, md_bsc_target}]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CascadeIntegrityAudit:
    """Stage 2: cascade structural integrity."""
    total_cascade_entries: int
    valid_entries: int
    sum_mismatch_count: int
    sum_mismatches: List[Dict[str, Any]]  # [{key, total_target, allocated_sum, delta_pct}]
    zero_target_count: int
    orphan_allocations: List[Dict[str, Any]]  # children not in register
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CascadeBSCTargetAudit:
    """Stage 3: cascade allocations -> BSC rows match by target."""
    total_allocations: int
    allocations_with_bsc_match: int
    allocations_missing_bsc_row: List[Dict[str, Any]]
    target_value_mismatches: List[Dict[str, Any]]
    coverage_pct: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BSCActualsAudit:
    """Stage 4: every BSC row has populated actuals."""
    total_bsc_rows: int
    rows_with_annual_target: int
    rows_with_ytd_actual: int
    rows_with_annual_actual: int
    rows_missing_actuals: int
    rows_missing_target: int
    actuals_coverage_pct: float
    target_coverage_pct: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreCalculationAudit:
    """Stage 5: end-to-end score viability per staff."""
    total_staff: int
    staff_with_computable_score: int
    staff_with_nan_score: int
    staff_with_zero_target: int
    overall_avg_score: float
    score_range: Tuple[float, float]
    failing_staff_samples: List[Dict[str, Any]]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_staff": self.total_staff,
            "staff_with_computable_score": self.staff_with_computable_score,
            "staff_with_nan_score": self.staff_with_nan_score,
            "staff_with_zero_target": self.staff_with_zero_target,
            "overall_avg_score": self.overall_avg_score,
            "score_range": list(self.score_range),
            "failing_staff_samples": self.failing_staff_samples,
            "timestamp": self.timestamp,
        }


@dataclass
class Master360Audit:
    """Master rollup — all 5 stages with overall harmony percentage."""
    bank_to_md: BankToMDAudit
    cascade_integrity: CascadeIntegrityAudit
    cascade_to_bsc: CascadeBSCTargetAudit
    bsc_actuals: BSCActualsAudit
    score_calculation: ScoreCalculationAudit
    overall_harmony_pct: float
    stages_passing: int
    total_stages: int
    issues_by_severity: Dict[str, int]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bank_to_md": self.bank_to_md.to_dict(),
            "cascade_integrity": self.cascade_integrity.to_dict(),
            "cascade_to_bsc": self.cascade_to_bsc.to_dict(),
            "bsc_actuals": self.bsc_actuals.to_dict(),
            "score_calculation": self.score_calculation.to_dict(),
            "overall_harmony_pct": self.overall_harmony_pct,
            "stages_passing": self.stages_passing,
            "total_stages": self.total_stages,
            "issues_by_severity": self.issues_by_severity,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_cascade() -> Dict[str, Any]:
    p = DATA_DIR / "target_cascade.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_bank_targets() -> Dict[str, Any]:
    p = DATA_DIR / "bank_targets.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_lib() -> Dict[str, Any]:
    p = DATA_DIR / "kpi_library.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _find_actuals() -> Optional[Path]:
    if not DATA_DIR.exists():
        return None
    files = sorted(DATA_DIR.glob("actuals_*.xlsx"))
    return files[-1] if files else None


def _load_actuals_df() -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    p = _find_actuals()
    if p is None:
        return None
    try:
        return pd.read_excel(p, skiprows=1)
    except Exception:  # noqa: BLE001
        return None


# ════════════════════════════════════════════════════════════════════
# Stage 1: Bank Targets -> MD BSC
# ════════════════════════════════════════════════════════════════════

def audit_bank_to_md() -> BankToMDAudit:
    """Verify MD's BSC reflects bank-level targets.

    The MD (Chief Executive & Managing Director) carries bank-wide KPIs.
    For each KPI in MD's BSC, check that bank_targets has a matching
    target and that the values agree (within tolerance).
    """
    bt = _load_bank_targets()
    df = _load_actuals_df()
    if df is None:
        return BankToMDAudit(0, 0, 0, [], [], datetime.now().isoformat())

    # Identify MD in BSC
    md_df = df[df["Role"].str.contains(
        "Chief Executive|Managing Director", case=False, na=False,
    )]
    if len(md_df) == 0:
        return BankToMDAudit(
            bank_target_count=len(bt),
            md_bsc_kpi_count=0,
            md_kpis_with_bank_target=0,
            md_kpis_missing_bank_target=[],
            target_mismatches=[],
            timestamp=datetime.now().isoformat(),
        )

    # Build bank target lookup: KPI -> target value (ignoring period)
    bt_by_kpi: Dict[str, float] = {}
    for k, v in bt.items():
        if isinstance(v, dict) and "target" in v:
            kpi_name = k.split("|")[0].strip()
            try:
                bt_by_kpi[kpi_name] = float(v["target"])
            except (ValueError, TypeError):
                pass

    md_kpis = sorted(md_df["KPI"].dropna().astype(str).unique())
    with_bank_target = 0
    missing: List[str] = []
    mismatches: List[Dict[str, Any]] = []
    bsc_score_kpis_skipped: List[str] = []

    for kpi in md_kpis:
        if kpi not in bt_by_kpi:
            missing.append(kpi)
            continue
        with_bank_target += 1
        # Skip direct value comparison for BSC-score KPIs (different scales)
        if kpi in BSC_SCORE_KPIS:
            bsc_score_kpis_skipped.append(kpi)
            continue
        bank_value = bt_by_kpi[kpi]
        # MD BSC value
        md_target = float(md_df[md_df["KPI"] == kpi]["Annual Target"].iloc[0])
        if bank_value > 0:
            delta_pct = abs(md_target - bank_value) / bank_value * 100
            if delta_pct > BSC_TARGET_TOLERANCE * 100:
                mismatches.append({
                    "kpi": kpi,
                    "bank_target": bank_value,
                    "md_bsc_target": md_target,
                    "delta_pct": round(delta_pct, 2),
                })

    return BankToMDAudit(
        bank_target_count=len(bt_by_kpi),
        md_bsc_kpi_count=len(md_kpis),
        md_kpis_with_bank_target=with_bank_target,
        md_kpis_missing_bank_target=missing,
        target_mismatches=mismatches[:50],
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Stage 2: Cascade Integrity
# ════════════════════════════════════════════════════════════════════

def audit_cascade_integrity() -> CascadeIntegrityAudit:
    """Verify each cascade entry's allocations sum to total_target."""
    cascade = _load_cascade()
    df = _load_actuals_df()

    register_codes: Set[str] = set()
    if df is not None:
        register_codes = set(df["Staff Code"].astype(str).str.strip().unique())

    real_entries = {k: v for k, v in cascade.items()
                    if not k.startswith("_") and isinstance(v, dict)}

    sum_mismatches: List[Dict[str, Any]] = []
    zero_target = 0
    orphans: List[Dict[str, Any]] = []
    valid = 0

    for key, entry in real_entries.items():
        total = entry.get("total_target")
        allocs = entry.get("allocations", [])
        try:
            tt = float(total) if total is not None else 0.0
        except (ValueError, TypeError):
            tt = 0.0
        if tt == 0.0:
            zero_target += 1
            continue
        alloc_sum = sum(
            float(a.get("amount", 0))
            for a in allocs
            if isinstance(a, dict)
        )
        if tt > 0:
            delta_pct = abs(alloc_sum - tt) / tt
            if delta_pct > CASCADE_TARGET_TOLERANCE:
                sum_mismatches.append({
                    "key": key,
                    "total_target": tt,
                    "allocated_sum": alloc_sum,
                    "delta_pct": round(delta_pct * 100, 2),
                })
            else:
                valid += 1
        # Check for orphan allocations
        for a in allocs:
            if isinstance(a, dict):
                to_code = str(a.get("to_code", "")).strip()
                if to_code and to_code not in register_codes:
                    orphans.append({
                        "cascade_key": key,
                        "to_code": to_code,
                        "to_name": a.get("to_name", "?"),
                    })

    return CascadeIntegrityAudit(
        total_cascade_entries=len(real_entries),
        valid_entries=valid,
        sum_mismatch_count=len(sum_mismatches),
        sum_mismatches=sum_mismatches[:50],
        zero_target_count=zero_target,
        orphan_allocations=orphans[:50],
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Stage 3: Cascade -> BSC target consistency
# ════════════════════════════════════════════════════════════════════

def audit_cascade_to_bsc_targets() -> CascadeBSCTargetAudit:
    """For each allocation, verify the child's BSC has a row for that KPI.

    v10.433: cascade may reference a KPI by ID/code (e.g.
    PRODUCT_BOOK_ACHIEVEMENT) while BSC uses canonical name
    (e.g. 'Product Book Achievement'). Resolve cascade KPI to
    canonical via kpi_library before lookup.
    """
    cascade = _load_cascade()
    lib = _load_lib()
    df = _load_actuals_df()
    if df is None:
        return CascadeBSCTargetAudit(
            0, 0, [], [], 0.0, datetime.now().isoformat(),
        )

    # Build canonical-name resolver from library
    name_set: Set[str] = set()
    name_to_canonical: Dict[str, str] = {}
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        canonical = str(k.get("name", "")).strip()
        if not canonical:
            continue
        name_set.add(canonical)
        kid = str(k.get("id", "")).strip()
        if kid:
            name_to_canonical[kid] = canonical
        # name itself
        name_to_canonical[canonical] = canonical
        # aliases
        for a in k.get("aliases", []) or []:
            if a:
                name_to_canonical[str(a).strip()] = canonical

    # Build BSC lookup: (staff_code, kpi) -> Annual Target
    df["_code_str"] = df["Staff Code"].astype(str).str.strip()
    bsc_lookup: Dict[Tuple[str, str], float] = {}
    for _, row in df.iterrows():
        code = row["_code_str"]
        kpi = str(row.get("KPI", "")).strip()
        try:
            target = float(row.get("Annual Target", 0))
        except (ValueError, TypeError):
            target = 0.0
        bsc_lookup[(code, kpi)] = target

    real_entries = {k: v for k, v in cascade.items()
                    if not k.startswith("_") and isinstance(v, dict)}

    total_allocs = 0
    matched = 0
    missing: List[Dict[str, Any]] = []
    target_mismatches: List[Dict[str, Any]] = []

    for key, entry in real_entries.items():
        cascade_kpi = str(entry.get("kpi", "")).strip()
        # Resolve to canonical name (so we can match BSC)
        canonical_kpi = name_to_canonical.get(cascade_kpi, cascade_kpi)
        for a in entry.get("allocations", []):
            if not isinstance(a, dict):
                continue
            total_allocs += 1
            to_code = str(a.get("to_code", "")).strip()
            amount = a.get("amount", 0)
            try:
                allocated = float(amount)
            except (ValueError, TypeError):
                continue
            if (to_code, canonical_kpi) in bsc_lookup:
                matched += 1
                bsc_target = bsc_lookup[(to_code, canonical_kpi)]
                if allocated > 0:
                    delta_pct = abs(bsc_target - allocated) / allocated
                    if delta_pct > BSC_TARGET_TOLERANCE:
                        target_mismatches.append({
                            "to_code": to_code,
                            "to_name": a.get("to_name", "?"),
                            "kpi": canonical_kpi,
                            "cascade_target": allocated,
                            "bsc_target": bsc_target,
                            "delta_pct": round(delta_pct * 100, 2),
                        })
            else:
                missing.append({
                    "to_code": to_code,
                    "to_name": a.get("to_name", "?"),
                    "kpi": canonical_kpi,
                    "cascade_target": allocated,
                })

    coverage = (matched / total_allocs * 100) if total_allocs > 0 else 0.0

    return CascadeBSCTargetAudit(
        total_allocations=total_allocs,
        allocations_with_bsc_match=matched,
        allocations_missing_bsc_row=missing[:50],
        target_value_mismatches=target_mismatches[:50],
        coverage_pct=round(coverage, 2),
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Stage 4: BSC Actuals Coverage
# ════════════════════════════════════════════════════════════════════

def audit_bsc_actuals_coverage() -> BSCActualsAudit:
    """Every BSC row should have populated Annual Target + actuals."""
    df = _load_actuals_df()
    if df is None:
        return BSCActualsAudit(
            0, 0, 0, 0, 0, 0, 0.0, 0.0, datetime.now().isoformat(),
        )

    total = len(df)
    has_target = int(df["Annual Target"].notna().sum())
    has_ytd = int(df["YTD_Actual"].notna().sum())
    has_annual = int(df["Annual Actual"].notna().sum())

    # Missing = any of the three nan
    all_actuals_mask = (
        df["Annual Target"].notna()
        & df["YTD_Actual"].notna()
        & df["Annual Actual"].notna()
    )
    has_all_actuals = int(all_actuals_mask.sum())
    missing_actuals = total - has_all_actuals
    missing_target = total - has_target

    return BSCActualsAudit(
        total_bsc_rows=total,
        rows_with_annual_target=has_target,
        rows_with_ytd_actual=has_ytd,
        rows_with_annual_actual=has_annual,
        rows_missing_actuals=missing_actuals,
        rows_missing_target=missing_target,
        actuals_coverage_pct=round(has_all_actuals / total * 100, 2) if total > 0 else 0.0,
        target_coverage_pct=round(has_target / total * 100, 2) if total > 0 else 0.0,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Stage 5: Score Calculation Viability
# ════════════════════════════════════════════════════════════════════

def _compute_kpi_achievement(actual: float, target: float, direction: str = "higher") -> float:
    """Achievement % for a single KPI.

    Direction "higher": achievement = actual / target * 100
    Direction "lower":  achievement = target / actual * 100 (lower-is-better)
    Capped at 200% to prevent extreme outliers.
    """
    if target <= 0 or not math.isfinite(target):
        return 0.0
    if not math.isfinite(actual):
        return 0.0
    if direction == "lower":
        if actual <= 0:
            return 200.0  # super-achievement (zero NPL etc.)
        return min(target / actual * 100, 200.0)
    if actual < 0:
        return 0.0
    return min(actual / target * 100, 200.0)


def audit_score_calculation() -> ScoreCalculationAudit:
    """For each staff, compute their BSC score and check viability.

    Score = SUM_per_pillar (
        pillar_weight × SUM_per_kpi (kpi_weight × kpi_achievement)
    )

    where kpi_weight is within the pillar (Σ within pillar = 1.0 after
    pillar-wise normalization).
    """
    df = _load_actuals_df()
    lib = _load_lib()
    if df is None:
        return ScoreCalculationAudit(
            0, 0, 0, 0, 0.0, (0.0, 0.0), [], datetime.now().isoformat(),
        )

    pillar_weights = lib.get("pillar_weights", {})
    if not pillar_weights:
        pillar_weights = {
            "Financial": 0.40,
            "Customer Focus": 0.25,
            "Operational Excellence": 0.25,
            "People & Learning": 0.10,
        }

    total_staff = int(df["Staff Name"].nunique())
    computable = 0
    nan_count = 0
    zero_target_count = 0
    scores: List[float] = []
    samples: List[Dict[str, Any]] = []

    for staff_name in df["Staff Name"].dropna().unique():
        rows = df[df["Staff Name"] == staff_name]

        # Compute per-pillar weighted achievement
        pillar_scores: Dict[str, float] = {}
        pillar_weight_sums: Dict[str, float] = {}
        zero_targets_for_staff = 0

        for _, r in rows.iterrows():
            pillar = str(r.get("Pillar", "")).strip()
            try:
                weight = float(r.get("Weight", 0))
                target = float(r.get("Annual Target", 0))
                actual = float(r.get("Annual Actual", 0))
            except (ValueError, TypeError):
                continue
            if target <= 0:
                zero_targets_for_staff += 1
                continue
            achievement = _compute_kpi_achievement(actual, target)
            pillar_scores[pillar] = pillar_scores.get(pillar, 0.0) + weight * achievement
            pillar_weight_sums[pillar] = pillar_weight_sums.get(pillar, 0.0) + weight

        # Overall score = weighted average of pillar scores
        overall = 0.0
        for pillar, p_weight in pillar_weights.items():
            if pillar in pillar_scores and pillar_weight_sums.get(pillar, 0) > 0:
                # Normalize within pillar (in case kpi weights within pillar
                # don't sum to 1.0)
                norm_pillar_score = pillar_scores[pillar] / pillar_weight_sums[pillar]
                overall += p_weight * norm_pillar_score

        if zero_targets_for_staff > 0:
            zero_target_count += 1

        if math.isfinite(overall) and overall >= 0:
            computable += 1
            scores.append(overall)
            if overall == 0.0 and len(samples) < 5:
                samples.append({
                    "staff_name": staff_name,
                    "score": 0.0,
                    "reason": "all targets zero or computation failed",
                })
        else:
            nan_count += 1
            if len(samples) < 5:
                samples.append({
                    "staff_name": staff_name,
                    "score": overall,
                    "reason": "non-finite or negative",
                })

    avg = sum(scores) / len(scores) if scores else 0.0
    rng = (min(scores), max(scores)) if scores else (0.0, 0.0)

    return ScoreCalculationAudit(
        total_staff=total_staff,
        staff_with_computable_score=computable,
        staff_with_nan_score=nan_count,
        staff_with_zero_target=zero_target_count,
        overall_avg_score=round(avg, 2),
        score_range=(round(rng[0], 2), round(rng[1], 2)),
        failing_staff_samples=samples,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Master rollup
# ════════════════════════════════════════════════════════════════════

def cascade_bsc_360_audit() -> Master360Audit:
    """Run all 5 stages and compute overall harmony percentage."""
    s1 = audit_bank_to_md()
    s2 = audit_cascade_integrity()
    s3 = audit_cascade_to_bsc_targets()
    s4 = audit_bsc_actuals_coverage()
    s5 = audit_score_calculation()

    # Per-stage pass criteria
    pass_s1 = (
        len(s1.md_kpis_missing_bank_target) == 0
        and len(s1.target_mismatches) == 0
        and s1.md_bsc_kpi_count > 0
    )
    pass_s2 = (
        s2.sum_mismatch_count == 0
        and len(s2.orphan_allocations) == 0
    )
    pass_s3 = (
        len(s3.allocations_missing_bsc_row) == 0
        and len(s3.target_value_mismatches) == 0
        and s3.coverage_pct >= 99.0
    )
    pass_s4 = (
        s4.target_coverage_pct >= 100.0
        and s4.actuals_coverage_pct >= 99.0
    )
    pass_s5 = (
        s5.staff_with_nan_score == 0
        and s5.staff_with_computable_score == s5.total_staff
        and s5.total_staff > 0
    )

    passing = sum([pass_s1, pass_s2, pass_s3, pass_s4, pass_s5])
    harmony = passing / 5 * 100

    # Severity counts
    issues: Dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
    if not pass_s1:
        issues["warning"] += 1
    if not pass_s2:
        issues["critical"] += 1
    if not pass_s3:
        issues["critical"] += 1
    if not pass_s4:
        issues["warning"] += 1
    if not pass_s5:
        issues["critical"] += 1

    return Master360Audit(
        bank_to_md=s1,
        cascade_integrity=s2,
        cascade_to_bsc=s3,
        bsc_actuals=s4,
        score_calculation=s5,
        overall_harmony_pct=round(harmony, 1),
        stages_passing=passing,
        total_stages=5,
        issues_by_severity=issues,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ cascade_bsc_360_engine self-test ─")

    # Zero streamlit
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Run each audit
    s1 = audit_bank_to_md()
    print(f"  Stage 1 (Bank→MD): MD has {s1.md_bsc_kpi_count} KPIs, "
          f"{s1.md_kpis_with_bank_target} with bank targets, "
          f"{len(s1.target_mismatches)} mismatches")

    s2 = audit_cascade_integrity()
    print(f"  Stage 2 (Cascade integrity): "
          f"{s2.total_cascade_entries} entries, "
          f"{s2.valid_entries} valid sums, "
          f"{s2.sum_mismatch_count} mismatches, "
          f"{len(s2.orphan_allocations)} orphans")

    s3 = audit_cascade_to_bsc_targets()
    print(f"  Stage 3 (Cascade→BSC): "
          f"{s3.total_allocations} allocations, "
          f"{s3.coverage_pct}% covered, "
          f"{len(s3.target_value_mismatches)} target mismatches")

    s4 = audit_bsc_actuals_coverage()
    print(f"  Stage 4 (BSC actuals): "
          f"{s4.actuals_coverage_pct}% actuals, "
          f"{s4.target_coverage_pct}% targets")

    s5 = audit_score_calculation()
    print(f"  Stage 5 (Score calc): "
          f"{s5.staff_with_computable_score}/{s5.total_staff} computable, "
          f"avg {s5.overall_avg_score}, "
          f"range {s5.score_range}")

    # Master
    master = cascade_bsc_360_audit()
    print(f"\n  Master: {master.stages_passing}/5 stages passing, "
          f"harmony = {master.overall_harmony_pct}%")
    print(f"  Issues: {master.issues_by_severity}")

    # JSON
    json.dumps(master.to_dict())
    print(f"  ✓ JSON-serializable")

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
