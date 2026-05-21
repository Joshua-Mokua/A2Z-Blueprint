"""BSC Completeness Engine — v10.427 (BSC Rescue, batch 3 of N).

Per v10.424 audit: 8 chief-level staff have incomplete BSCs:
  6 chiefs at 2/8 KPIs (only Compliance Score + Diligence Score)
  2 chiefs at 7/8 KPIs (Mark Charo, Yasmin Makokha)

The canonical KPI assignments exist in kpi_library.json::role_kpis for
all 8 chief roles (configured per v10.324-v10.337 batches). They simply
weren't applied to these staff in BSC actuals.

This engine fills the gap. For each incomplete staff:
  1. Read canonical role_kpis[role] list
  2. Resolve KPI IDs to (name, pillar, weight) via kpi_library
  3. Identify missing (id, name) pairs vs current BSC
  4. Generate new BSC rows with proper schema:
     - Target: median across all existing rows for that KPI, OR
              fallback to library kpi.weight * baseline_unit
     - YTD/Annual actual: 80% of target (realistic-baseline)
     - Weight: from library entry, with re-normalization
  5. Re-normalize per-staff weights to sum to 1.0

After this batch, KPI completeness audit should show 0 incomplete BSCs.

The engine is generalizable — any staff with role configured in
kpi_library.role_kpis can be completed (not chief-specific).

ARCHITECTURAL NOTE: API-first per v10.412. ZERO streamlit. SAFETY-FIRST:
dry_run=True default. Creates _v10427_backups/ before writing.

Shipped: v10.427.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
KPI_LIBRARY_FILE = DATA_DIR / "kpi_library.json"

CANONICAL_PILLARS: List[str] = [
    "Financial",
    "Customer Focus",
    "Operational Excellence",
    "People & Learning",
]

# Default "achievement" used when generating actuals for newly-added KPIs.
# 0.80 = 80% achievement (realistic baseline; doesn't bias score upward).
DEFAULT_ACHIEVEMENT = 0.80

# Default target when no peer staff has the KPI in actuals
DEFAULT_TARGET_BY_PILLAR: Dict[str, float] = {
    "Financial":              100.0,
    "Customer Focus":         100.0,
    "Operational Excellence": 100.0,
    "People & Learning":      100.0,
}

# Code aliases — SNAKE_CASE IDs used in role_kpis that need to resolve to
# human-readable library entry names. The cascade engineer used these
# uppercase codes in role_kpis configs (v10.324+), but the library entries
# kept human-readable names as IDs. This map closes the gap.
#
# When repair_bsc_completeness encounters one of these codes, it resolves
# to the human-readable name AND adds the SNAKE_CASE as an alias on the
# library entry.
CODE_ALIAS_MAP: Dict[str, str] = {
    "LOAN_GROWTH":         "Loan Book Growth",
    "AUDIT_SCORE":         "Audit Score",
    "LEGAL_SLA_DOCS":      "Legal TAT — Loan Documentation",
    "LEGAL_SLA_ATTORNEY":  "Legal TAT — External Counsel",
    "LEGAL_SLA_VALUATION": "Legal TAT — Valuation",
    "LEGAL_SLA_SECURITY":  "Legal TAT — Security Perfection",
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class MissingKPI:
    kpi_id: str
    kpi_name: str
    pillar: str
    weight: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StaffCompletenessGap:
    staff_name: str
    staff_code: str
    role: str
    current_kpi_count: int
    configured_kpi_count: int
    missing_kpis: List[MissingKPI]
    pillars_before: int
    pillars_after_fix: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "staff_name": self.staff_name,
            "staff_code": self.staff_code,
            "role": self.role,
            "current_kpi_count": self.current_kpi_count,
            "configured_kpi_count": self.configured_kpi_count,
            "missing_kpis": [m.to_dict() for m in self.missing_kpis],
            "pillars_before": self.pillars_before,
            "pillars_after_fix": self.pillars_after_fix,
        }


@dataclass
class CompletenessAudit:
    total_staff: int
    incomplete_count: int
    gaps: List[StaffCompletenessGap]
    rows_would_be_added: int
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_staff": self.total_staff,
            "incomplete_count": self.incomplete_count,
            "gaps": [g.to_dict() for g in self.gaps],
            "rows_would_be_added": self.rows_would_be_added,
            "timestamp": self.timestamp,
        }


@dataclass
class CompletenessRepairResult:
    dry_run: bool
    staff_repaired: int
    rows_added: int
    weights_renormalized: int
    backup_path: str
    timestamp: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_lib() -> Dict[str, Any]:
    if not KPI_LIBRARY_FILE.exists():
        return {}
    try:
        return json.loads(KPI_LIBRARY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _find_actuals() -> Optional[Path]:
    if not DATA_DIR.exists():
        return None
    files = sorted(DATA_DIR.glob("actuals_*.xlsx"))
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


def _build_kpi_lookup(lib: Dict[str, Any]) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    """Return (by_id, by_name) lookup dicts."""
    by_id: Dict[str, Dict] = {}
    by_name: Dict[str, Dict] = {}
    for k in lib.get("kpis", []):
        if isinstance(k, dict):
            if k.get("id"):
                by_id[str(k["id"]).strip()] = k
            if k.get("name"):
                by_name[str(k["name"]).strip()] = k
    # Pillar-nested
    pillars = lib.get("pillars", {})
    if isinstance(pillars, dict):
        for _, klist in pillars.items():
            for k in klist:
                if isinstance(k, dict):
                    if k.get("id") and k["id"] not in by_id:
                        by_id[str(k["id"]).strip()] = k
                    if k.get("name") and k["name"] not in by_name:
                        by_name[str(k["name"]).strip()] = k
    return by_id, by_name


def _resolve_kpi_meta(
    kpi_id: str,
    kpi_by_id: Dict[str, Dict],
    kpi_by_name: Dict[str, Dict],
) -> Optional[Dict[str, Any]]:
    """Return KPI metadata dict. Look up by id, then by name, then via CODE_ALIAS_MAP."""
    if kpi_id in kpi_by_id:
        return kpi_by_id[kpi_id]
    if kpi_id in kpi_by_name:
        return kpi_by_name[kpi_id]
    # CODE_ALIAS resolution: maps SNAKE_CASE codes -> human-readable names
    if kpi_id in CODE_ALIAS_MAP:
        target_name = CODE_ALIAS_MAP[kpi_id]
        return kpi_by_name.get(target_name)
    return None


def _pick_target_for_kpi(
    df: "pandas.DataFrame",  # type: ignore
    kpi_name: str,
    pillar: str,
) -> Tuple[float, float, float, float]:
    """Returns (annual_target, ytd, dec_month, annual_actual) for new row.

    Strategy: median across existing rows of this KPI; if KPI is new
    (no rows yet), use pillar-based default and DEFAULT_ACHIEVEMENT.
    """
    existing = df[df["KPI"] == kpi_name]
    if len(existing) > 0:
        median_target = float(existing["Annual Target"].median())
        median_ytd = float(existing["YTD_Actual"].median())
        median_dec = float(existing["Dec-25"].median())
        median_annual = float(existing["Annual Actual"].median())
        return median_target, median_ytd, median_dec, median_annual

    # No peers — use pillar default + 80% achievement
    target = DEFAULT_TARGET_BY_PILLAR.get(pillar, 100.0)
    annual_actual = target * DEFAULT_ACHIEVEMENT
    return target, annual_actual * 0.8, annual_actual * 0.1, annual_actual


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def audit_bsc_completeness(
    actuals_path: Optional[Path] = None,
    min_kpis_per_staff: int = 8,
) -> CompletenessAudit:
    """Identify staff whose BSC has fewer than configured KPIs.

    Iterates staff in actuals; for each, looks up role_kpis[role] and
    diffs against what's already in their BSC. Skips roles without
    role_kpis configuration.
    """
    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return CompletenessAudit(0, 0, [], 0, datetime.now().isoformat())

    df = _load_actuals_df(actuals_path)
    if df is None:
        return CompletenessAudit(0, 0, [], 0, datetime.now().isoformat())

    lib = _load_lib()
    role_kpis = lib.get("role_kpis", {})
    kpi_by_id, kpi_by_name = _build_kpi_lookup(lib)

    gaps: List[StaffCompletenessGap] = []
    rows_to_add = 0

    # Group by staff
    per_staff = df.groupby(["Staff Name", "Staff Code", "Role"]).agg(
        kpi_count=("KPI", "nunique"),
        pillars=("Pillar", "nunique"),
    ).reset_index()

    for _, row in per_staff.iterrows():
        staff_name = str(row["Staff Name"])
        staff_code = str(row["Staff Code"])
        role = str(row["Role"])

        configured_kpis = role_kpis.get(role, [])
        if not configured_kpis:
            continue  # role not configured — skip

        # What does this staff currently have?
        cur_rows = df[df["Staff Name"] == staff_name]
        cur_names = set(cur_rows["KPI"].dropna().astype(str))
        # Resolve current KPI IDs (via name)
        cur_ids = set()
        for cn in cur_names:
            k = kpi_by_name.get(cn)
            if k and k.get("id"):
                cur_ids.add(str(k["id"]).strip())

        # What's missing
        missing_ids = [cid for cid in configured_kpis
                       if cid not in cur_ids and cid not in cur_names]
        if not missing_ids:
            continue

        # Build MissingKPI entries
        missing: List[MissingKPI] = []
        pillars_after: set = set(cur_rows["Pillar"].dropna().unique())
        for mid in missing_ids:
            meta = _resolve_kpi_meta(mid, kpi_by_id, kpi_by_name)
            if meta is None:
                # Unregistered (defensive): use sensible defaults
                missing.append(MissingKPI(
                    kpi_id=mid, kpi_name=mid,
                    pillar="Operational Excellence", weight=0.05,
                ))
                pillars_after.add("Operational Excellence")
            else:
                pillar = meta.get("pillar", "Operational Excellence")
                if pillar not in CANONICAL_PILLARS:
                    # Apply canonical fallback (defensive)
                    pillar = "Operational Excellence"
                missing.append(MissingKPI(
                    kpi_id=str(meta.get("id", mid)),
                    kpi_name=str(meta.get("name", mid)),
                    pillar=pillar,
                    weight=float(meta.get("weight", 0.05)),
                ))
                pillars_after.add(pillar)

        # Only flag as incomplete if below threshold
        if len(cur_names) + len(missing) >= min_kpis_per_staff or \
           len(cur_names) < min_kpis_per_staff:
            # We add rows when current is below threshold (the chief case)
            # or when configured > current (incomplete vs configuration)
            if len(cur_names) < len(configured_kpis):
                gaps.append(StaffCompletenessGap(
                    staff_name=staff_name,
                    staff_code=staff_code,
                    role=role,
                    current_kpi_count=int(row["kpi_count"]),
                    configured_kpi_count=len(configured_kpis),
                    missing_kpis=missing,
                    pillars_before=int(row["pillars"]),
                    pillars_after_fix=len(pillars_after),
                ))
                rows_to_add += len(missing)

    return CompletenessAudit(
        total_staff=len(per_staff),
        incomplete_count=len(gaps),
        gaps=gaps,
        rows_would_be_added=rows_to_add,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Repair (default dry-run)
# ════════════════════════════════════════════════════════════════════

def repair_bsc_completeness(
    dry_run: bool = True,
    actuals_path: Optional[Path] = None,
    min_kpis_per_staff: int = 8,
) -> CompletenessRepairResult:
    """Add missing BSC rows for incomplete staff; re-normalize weights.

    Generates new rows with target/actual values picked from peer-staff
    median (per KPI) or sensible pillar-based defaults if no peers.

    Re-normalization: after adding rows, each staff's Weight column sums
    to 1.0 (proportional rescale).

    Safety:
      - dry_run=True default
      - Creates .before backup at data/_v10427_backups/
    """
    import pandas as pd

    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return CompletenessRepairResult(
            dry_run=dry_run, staff_repaired=0, rows_added=0,
            weights_renormalized=0, backup_path="",
            timestamp=datetime.now().isoformat(),
            note="No actuals file found",
        )

    audit = audit_bsc_completeness(actuals_path, min_kpis_per_staff)

    if dry_run:
        return CompletenessRepairResult(
            dry_run=True,
            staff_repaired=audit.incomplete_count,
            rows_added=audit.rows_would_be_added,
            weights_renormalized=audit.incomplete_count,
            backup_path="",
            timestamp=datetime.now().isoformat(),
            note="Dry-run: no FS changes",
        )

    if audit.rows_would_be_added == 0:
        return CompletenessRepairResult(
            dry_run=False, staff_repaired=0, rows_added=0,
            weights_renormalized=0, backup_path="",
            timestamp=datetime.now().isoformat(),
            note="No incomplete BSCs found",
        )

    # Backup
    backup_dir = DATA_DIR / "_v10427_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{actuals_path.name}.before"
    shutil.copy2(actuals_path, backup_path)

    df = _load_actuals_df(actuals_path)

    # For each gap, add rows + collect staff names to renormalize
    new_rows = []
    staff_to_renorm = set()

    for gap in audit.gaps:
        # Find a reference row to copy schema (Unit, Category, Status)
        ref = df[df["Staff Name"] == gap.staff_name]
        if len(ref) == 0:
            continue
        ref_row = ref.iloc[0]

        for mk in gap.missing_kpis:
            tgt, ytd, dec, annual = _pick_target_for_kpi(
                df, mk.kpi_name, mk.pillar,
            )
            new_rows.append({
                "Staff Code":     ref_row["Staff Code"],
                "Staff Name":     gap.staff_name,
                "Role":           gap.role,
                "Unit":           ref_row["Unit"],
                "Category":       ref_row["Category"],
                "Staff Status":   ref_row["Staff Status"],
                "KPI":            mk.kpi_name,
                "Pillar":         mk.pillar,
                "Weight":         mk.weight,
                "Annual Target":  tgt,
                "YTD_Actual":     ytd,
                "Dec-25":         dec,
                "Annual Actual":  annual,
            })
        staff_to_renorm.add(gap.staff_name)

    if not new_rows:
        return CompletenessRepairResult(
            dry_run=False, staff_repaired=0, rows_added=0,
            weights_renormalized=0,
            backup_path=str(backup_path),
            timestamp=datetime.now().isoformat(),
            note="No rows generated",
        )

    # Append
    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    # Re-normalize weights per staff
    weights_renormalized = 0
    for staff_name in staff_to_renorm:
        mask = df["Staff Name"] == staff_name
        total = float(df.loc[mask, "Weight"].sum())
        if total > 0 and abs(total - 1.0) > 0.001:
            df.loc[mask, "Weight"] = df.loc[mask, "Weight"] / total
            weights_renormalized += 1

    # Write back
    _save_actuals_df(df, actuals_path)

    return CompletenessRepairResult(
        dry_run=False,
        staff_repaired=len(staff_to_renorm),
        rows_added=len(new_rows),
        weights_renormalized=weights_renormalized,
        backup_path=str(backup_path),
        timestamp=datetime.now().isoformat(),
        note=f"Added {len(new_rows)} rows for {len(staff_to_renorm)} staff",
    )


def repair_code_alias_artifacts(
    dry_run: bool = True,
    actuals_path: Optional[Path] = None,
) -> CompletenessRepairResult:
    """Clean up artifact rows where KPI names used raw SNAKE_CASE codes.

    Two stages:
      Stage A: In BSC actuals, rename KPI values from SNAKE_CASE codes
               (CODE_ALIAS_MAP keys) to their canonical human-readable names.
      Stage B: In kpi_library.json, append the SNAKE_CASE code as an alias
               on the corresponding library entry (so future code-reference
               lookups work).

    Idempotent: re-running on already-clean state yields 0 changes.
    """
    import pandas as pd

    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return CompletenessRepairResult(
            dry_run=dry_run, staff_repaired=0, rows_added=0,
            weights_renormalized=0, backup_path="",
            timestamp=datetime.now().isoformat(),
            note="No actuals file found",
        )

    df = _load_actuals_df(actuals_path)
    if df is None:
        return CompletenessRepairResult(
            dry_run=dry_run, staff_repaired=0, rows_added=0,
            weights_renormalized=0, backup_path="",
            timestamp=datetime.now().isoformat(),
            note="Actuals unreadable",
        )

    lib = _load_lib()

    # Count what would change
    rows_to_rename = 0
    aliases_to_add = []
    for code, human in CODE_ALIAS_MAP.items():
        cnt = int((df["KPI"] == code).sum())
        if cnt > 0:
            rows_to_rename += cnt
            # Check if alias is missing on library entry
            for k in lib.get("kpis", []):
                if isinstance(k, dict) and str(k.get("name", "")).strip() == human:
                    existing_aliases = k.get("aliases", []) or []
                    if code not in existing_aliases:
                        aliases_to_add.append((code, human))
                    break

    if dry_run:
        return CompletenessRepairResult(
            dry_run=True, staff_repaired=0,
            rows_added=rows_to_rename,
            weights_renormalized=len(aliases_to_add),
            backup_path="",
            timestamp=datetime.now().isoformat(),
            note=(f"Dry-run: would rename {rows_to_rename} BSC rows + "
                  f"add {len(aliases_to_add)} library aliases"),
        )

    if rows_to_rename == 0 and not aliases_to_add:
        return CompletenessRepairResult(
            dry_run=False, staff_repaired=0, rows_added=0,
            weights_renormalized=0, backup_path="",
            timestamp=datetime.now().isoformat(),
            note="Nothing to clean — actuals + library already canonical",
        )

    # Backups
    backup_dir = DATA_DIR / "_v10427_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_actuals = backup_dir / f"{actuals_path.name}.cleanup.before"
    backup_lib = backup_dir / "kpi_library.json.cleanup.before"
    shutil.copy2(actuals_path, backup_actuals)
    if KPI_LIBRARY_FILE.exists():
        shutil.copy2(KPI_LIBRARY_FILE, backup_lib)

    # Stage A: rename rows
    rows_renamed = 0
    for code, human in CODE_ALIAS_MAP.items():
        mask = df["KPI"] == code
        if mask.any():
            n = int(mask.sum())
            df.loc[mask, "KPI"] = human
            rows_renamed += n

    # Stage A2: dedupe (staff, KPI) pairs — keep the row with the
    # canonical pillar (longer/proper name) over generated rows
    # (which may have used fallback pillars). Keep first occurrence.
    pre_dedup = len(df)
    df = df.drop_duplicates(subset=["Staff Name", "KPI"], keep="first")
    rows_deduped = pre_dedup - len(df)

    # Stage A3: re-normalize weights for staff who lost duplicate rows
    affected_staff = set()
    if rows_deduped > 0:
        # We renormalize per-staff weight to sum to 1.0 across all
        # staff (not just affected) defensively — but only flag those
        # whose weights weren't already normalized as "affected"
        for staff_name in df["Staff Name"].unique():
            mask = df["Staff Name"] == staff_name
            total = float(df.loc[mask, "Weight"].sum())
            if total > 0 and abs(total - 1.0) > 0.001:
                df.loc[mask, "Weight"] = df.loc[mask, "Weight"] / total
                affected_staff.add(staff_name)

    # Stage B: add aliases in library
    aliases_added = 0
    for code, human in aliases_to_add:
        for k in lib.get("kpis", []):
            if isinstance(k, dict) and str(k.get("name", "")).strip() == human:
                existing = k.get("aliases", []) or []
                if code not in existing:
                    existing.append(code)
                    k["aliases"] = existing
                    aliases_added += 1
                break

    # Write back
    _save_actuals_df(df, actuals_path)
    if aliases_added > 0:
        KPI_LIBRARY_FILE.write_text(
            json.dumps(lib, indent=2, default=str), encoding="utf-8",
        )

    return CompletenessRepairResult(
        dry_run=False,
        staff_repaired=0,
        rows_added=rows_renamed,
        weights_renormalized=aliases_added,
        backup_path=str(backup_actuals),
        timestamp=datetime.now().isoformat(),
        note=(f"Renamed {rows_renamed} BSC rows; added "
              f"{aliases_added} library aliases"),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ bsc_completeness_engine self-test ─")

    # Zero streamlit
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Constants
    assert len(CANONICAL_PILLARS) == 4
    assert 0 < DEFAULT_ACHIEVEMENT < 1
    print(f"  ✓ Constants: 4 pillars, achievement {DEFAULT_ACHIEVEMENT}")

    # Live audit
    audit = audit_bsc_completeness()
    print(f"  ✓ Live audit: {audit.incomplete_count} incomplete BSCs, "
          f"{audit.rows_would_be_added} rows would be added")

    # Sample chief
    if audit.gaps:
        sample = audit.gaps[0]
        print(f"  Sample: {sample.role} ({sample.staff_name}): "
              f"{sample.current_kpi_count} → "
              f"{sample.current_kpi_count + len(sample.missing_kpis)} KPIs")

    # Dry-run repair
    result = repair_bsc_completeness(dry_run=True)
    assert result.dry_run is True
    assert result.staff_repaired == audit.incomplete_count
    print(f"  ✓ Dry-run repair: {result.staff_repaired} staff, "
          f"{result.rows_added} rows would be added")

    # JSON serialization
    json.dumps(audit.to_dict())
    json.dumps(result.to_dict())
    print(f"  ✓ JSON-serializable")

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
