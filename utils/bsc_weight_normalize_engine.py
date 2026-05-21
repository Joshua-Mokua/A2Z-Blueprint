"""BSC Weight Normalization Engine — v10.428 (BSC Rescue, batch 4 of N).

Per v10.424 audit: 491 staff in BSC actuals have Weight column sums != 1.0,
range 1.0 - 4.28. Root cause: KPIs were assigned to each staff using
library default_weight values from simulate_v2.py, with no per-staff
renormalization. Staff with many KPIs ended up with weight sums >> 1.0.

Strategy: per-staff proportional rescale.
  new_weight[i] = old_weight[i] / sum(old_weights_for_staff)

This preserves the relative importance the generator assigned (more
weighty KPIs stay relatively more weighty) while ensuring per-staff
weights sum to exactly 1.0 — which is required for valid BSC score
aggregation downstream.

Tolerance: WEIGHT_TOLERANCE = 0.01 (1%). Staff whose weight sum is
already within tolerance get a no-op rescale (multiply by ~1.0).
Idempotent: re-running on already-normalized state yields 0 changes.

Public API (API-first per v10.412, ZERO streamlit, dry_run=True default):
  - audit_actuals_weights() -> WeightAuditResult
  - renormalize_actuals_weights(dry_run=True) -> WeightNormResult

ARCHITECTURAL NOTE: This is the v10.428 batch's complement to v10.419
(which normalized role weights in kpi_library). v10.419 fixed the
library; v10.428 fixes the actuals.

Shipped: v10.428.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# Tolerance for "already normalized" check
WEIGHT_TOLERANCE = 0.01  # 1%


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class StaffWeightProfile:
    staff_name: str
    staff_code: str
    role: str
    kpi_count: int
    current_weight_sum: float
    after_renorm_sum: float    # expected = 1.0
    rescale_factor: float       # multiplier to reach 1.0
    is_normalized: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WeightAuditResult:
    total_staff: int
    normalized_count: int
    not_normalized_count: int
    not_normalized_profiles: List[StaffWeightProfile]
    avg_weight_sum: float
    min_weight_sum: float
    max_weight_sum: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_staff": self.total_staff,
            "normalized_count": self.normalized_count,
            "not_normalized_count": self.not_normalized_count,
            "not_normalized_profiles": [p.to_dict() for p in self.not_normalized_profiles[:50]],
            "avg_weight_sum": self.avg_weight_sum,
            "min_weight_sum": self.min_weight_sum,
            "max_weight_sum": self.max_weight_sum,
            "timestamp": self.timestamp,
        }


@dataclass
class WeightNormResult:
    dry_run: bool
    staff_renormalized: int
    rows_modified: int
    avg_rescale_factor: float
    pre_min_sum: float
    pre_max_sum: float
    post_min_sum: float
    post_max_sum: float
    backup_path: str
    timestamp: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _find_actuals(data_dir: Optional[Path] = None) -> Optional[Path]:
    if data_dir is None:
        data_dir = DATA_DIR
    if not data_dir.exists():
        return None
    files = sorted(data_dir.glob("actuals_*.xlsx"))
    return files[-1] if files else None


def _load_actuals_df(path: Path) -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    try:
        return pd.read_excel(path, skiprows=1)
    except Exception:  # noqa: BLE001
        return None


def _save_actuals_df(df: "pandas.DataFrame", path: Path) -> None:  # type: ignore
    import pandas as pd
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame([[""] * len(df.columns)],
                     columns=df.columns).to_excel(
            w, sheet_name="KPI Data", index=False, header=False)
        df.to_excel(w, sheet_name="KPI Data",
                    startrow=1, index=False)


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def audit_actuals_weights(
    actuals_path: Optional[Path] = None,
) -> WeightAuditResult:
    """Identify staff whose weight sums are not 1.0 (within tolerance)."""
    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return WeightAuditResult(
            0, 0, 0, [], 0.0, 0.0, 0.0, datetime.now().isoformat(),
        )

    df = _load_actuals_df(actuals_path)
    if df is None:
        return WeightAuditResult(
            0, 0, 0, [], 0.0, 0.0, 0.0, datetime.now().isoformat(),
        )

    grouped = df.groupby(["Staff Name", "Staff Code", "Role"]).agg(
        kpi_count=("KPI", "nunique"),
        weight_sum=("Weight", "sum"),
    ).reset_index()

    profiles: List[StaffWeightProfile] = []
    norm_count = 0
    not_norm_count = 0

    for _, row in grouped.iterrows():
        ws = float(row["weight_sum"])
        is_norm = abs(ws - 1.0) <= WEIGHT_TOLERANCE
        if is_norm:
            norm_count += 1
            continue
        not_norm_count += 1
        rescale = (1.0 / ws) if ws > 0 else 0.0
        profiles.append(StaffWeightProfile(
            staff_name=str(row["Staff Name"]),
            staff_code=str(row["Staff Code"]),
            role=str(row["Role"]),
            kpi_count=int(row["kpi_count"]),
            current_weight_sum=round(ws, 4),
            after_renorm_sum=1.0,
            rescale_factor=round(rescale, 4),
            is_normalized=False,
        ))

    return WeightAuditResult(
        total_staff=len(grouped),
        normalized_count=norm_count,
        not_normalized_count=not_norm_count,
        not_normalized_profiles=profiles,
        avg_weight_sum=round(float(grouped["weight_sum"].mean()), 3),
        min_weight_sum=round(float(grouped["weight_sum"].min()), 3),
        max_weight_sum=round(float(grouped["weight_sum"].max()), 3),
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Renormalize (default dry-run)
# ════════════════════════════════════════════════════════════════════

def renormalize_actuals_weights(
    dry_run: bool = True,
    actuals_path: Optional[Path] = None,
) -> WeightNormResult:
    """Per-staff proportional rescale so weight sums to 1.0.

    For each staff with weight sum != 1.0 (within WEIGHT_TOLERANCE):
        new_weight[i] = old_weight[i] / sum(old_weights_for_staff)

    Preserves relative importance; produces sum = 1.0 exactly.
    Staff already within tolerance are untouched.

    Safety:
      - dry_run=True default
      - Creates .before backup at data/_v10428_backups/
      - Idempotent (re-run on clean state = no change)
    """
    import pandas as pd

    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return WeightNormResult(
            dry_run=dry_run, staff_renormalized=0, rows_modified=0,
            avg_rescale_factor=1.0,
            pre_min_sum=0.0, pre_max_sum=0.0,
            post_min_sum=0.0, post_max_sum=0.0,
            backup_path="",
            timestamp=datetime.now().isoformat(),
            note="No actuals file found",
        )

    audit = audit_actuals_weights(actuals_path)

    if dry_run:
        rescales = [p.rescale_factor for p in audit.not_normalized_profiles]
        avg_rescale = sum(rescales) / len(rescales) if rescales else 1.0
        return WeightNormResult(
            dry_run=True,
            staff_renormalized=audit.not_normalized_count,
            rows_modified=0,   # don't know exact row count until applied
            avg_rescale_factor=round(avg_rescale, 4),
            pre_min_sum=audit.min_weight_sum,
            pre_max_sum=audit.max_weight_sum,
            post_min_sum=1.0,
            post_max_sum=1.0,
            backup_path="",
            timestamp=datetime.now().isoformat(),
            note=(f"Dry-run: {audit.not_normalized_count} staff would be "
                  f"rescaled (rescale factor avg {round(avg_rescale, 3)})"),
        )

    if audit.not_normalized_count == 0:
        return WeightNormResult(
            dry_run=False, staff_renormalized=0, rows_modified=0,
            avg_rescale_factor=1.0,
            pre_min_sum=audit.min_weight_sum,
            pre_max_sum=audit.max_weight_sum,
            post_min_sum=audit.min_weight_sum,
            post_max_sum=audit.max_weight_sum,
            backup_path="",
            timestamp=datetime.now().isoformat(),
            note="All weights already normalized — no changes",
        )

    # Backup
    backup_dir = DATA_DIR / "_v10428_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{actuals_path.name}.before"
    shutil.copy2(actuals_path, backup_path)

    df = _load_actuals_df(actuals_path)

    # Apply renormalization
    rows_modified = 0
    staff_renormalized = 0
    rescales: List[float] = []

    not_norm_names = {p.staff_name for p in audit.not_normalized_profiles}
    for staff_name in not_norm_names:
        mask = df["Staff Name"] == staff_name
        total = float(df.loc[mask, "Weight"].sum())
        if total <= 0:
            continue
        if abs(total - 1.0) <= WEIGHT_TOLERANCE:
            continue
        rescale = 1.0 / total
        df.loc[mask, "Weight"] = df.loc[mask, "Weight"] * rescale
        rows_modified += int(mask.sum())
        staff_renormalized += 1
        rescales.append(rescale)

    # Write back
    _save_actuals_df(df, actuals_path)

    # Post-audit for confirmation
    post = audit_actuals_weights(actuals_path)
    avg_rescale = sum(rescales) / len(rescales) if rescales else 1.0

    return WeightNormResult(
        dry_run=False,
        staff_renormalized=staff_renormalized,
        rows_modified=rows_modified,
        avg_rescale_factor=round(avg_rescale, 4),
        pre_min_sum=audit.min_weight_sum,
        pre_max_sum=audit.max_weight_sum,
        post_min_sum=post.min_weight_sum,
        post_max_sum=post.max_weight_sum,
        backup_path=str(backup_path),
        timestamp=datetime.now().isoformat(),
        note=(f"Renormalized {staff_renormalized} staff "
              f"({rows_modified} rows touched)"),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ bsc_weight_normalize_engine self-test ─")
    import tempfile
    import pandas as pd

    # Zero streamlit
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Constants
    assert WEIGHT_TOLERANCE == 0.01
    print(f"  ✓ Constants: WEIGHT_TOLERANCE={WEIGHT_TOLERANCE}")

    # Build synthetic actuals
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / "actuals_test.xlsx"
        synth = pd.DataFrame({
            "Staff Name":     ["Alice", "Alice", "Alice", "Bob", "Bob"],
            "Staff Code":     ["S1", "S1", "S1", "S2", "S2"],
            "Role":           ["Manager"]*3 + ["Officer"]*2,
            "Unit":           ["A"]*3 + ["B"]*2,
            "Category":       ["X"]*3 + ["Y"]*2,
            "Staff Status":   ["Active"]*5,
            "KPI":            ["K1", "K2", "K3", "K1", "K2"],
            "Pillar":         ["Financial", "Customer Focus",
                              "Operational Excellence",
                              "Financial", "Operational Excellence"],
            # Alice: 0.30+0.40+0.30 = 1.0 (normalized)
            # Bob: 0.50+1.50 = 2.0 (NOT normalized)
            "Weight":         [0.30, 0.40, 0.30, 0.50, 1.50],
            "Annual Target":  [100]*5,
            "YTD_Actual":     [50]*5,
            "Dec-25":         [10]*5,
            "Annual Actual":  [60]*5,
        })
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            pd.DataFrame([[""] * len(synth.columns)],
                         columns=synth.columns).to_excel(
                w, sheet_name="KPI Data", index=False, header=False)
            synth.to_excel(w, sheet_name="KPI Data",
                          startrow=1, index=False)

        # Audit
        audit = audit_actuals_weights(actuals_path=path)
        assert audit.normalized_count == 1   # Alice
        assert audit.not_normalized_count == 1  # Bob
        assert audit.max_weight_sum == 2.0
        print(f"  ✓ Audit: 1 normalized, 1 not normalized")

        # Dry-run
        dry = renormalize_actuals_weights(actuals_path=path, dry_run=True)
        assert dry.dry_run is True
        assert dry.staff_renormalized == 1
        print(f"  ✓ Dry-run: would rescale {dry.staff_renormalized} staff")

        # Real run — override DATA_DIR for test isolation
        global DATA_DIR
        original_dd = DATA_DIR
        DATA_DIR = tmp
        try:
            result = renormalize_actuals_weights(actuals_path=path, dry_run=False)
            assert result.dry_run is False
            assert result.staff_renormalized == 1
            assert result.rows_modified == 2  # Bob has 2 rows
            assert result.post_max_sum == 1.0
            assert result.post_min_sum >= 0.99
        finally:
            DATA_DIR = original_dd
        print(f"  ✓ Real run: {result.staff_renormalized} staff, "
              f"{result.rows_modified} rows; post sums {result.post_min_sum}-{result.post_max_sum}")

        # Verify Bob's weights now sum to 1.0
        post_df = pd.read_excel(path, skiprows=1)
        bob_sum = float(post_df[post_df["Staff Name"] == "Bob"]["Weight"].sum())
        assert abs(bob_sum - 1.0) <= 0.01
        # Bob: 0.50/2.0 = 0.25 and 1.50/2.0 = 0.75 — relative ratio preserved
        bob_weights = post_df[post_df["Staff Name"] == "Bob"]["Weight"].tolist()
        assert sorted(bob_weights) == [0.25, 0.75]
        print(f"  ✓ Bob's weights: {sorted(bob_weights)} (relative ratio preserved)")

        # Idempotency
        DATA_DIR = tmp
        try:
            r2 = renormalize_actuals_weights(actuals_path=path, dry_run=False)
            assert r2.staff_renormalized == 0
        finally:
            DATA_DIR = original_dd
        print(f"  ✓ Idempotent: re-run yields 0 changes")

        # JSON
        json.dumps(audit.to_dict())
        json.dumps(result.to_dict())
        print(f"  ✓ JSON-serializable")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
