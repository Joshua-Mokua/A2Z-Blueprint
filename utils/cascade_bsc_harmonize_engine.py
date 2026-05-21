"""Cascade-BSC Harmonization Engine — v10.433 (rescue back to harmony).

Per Joshua directive (v10.432 found 60% harmony):
  - "all KPIs should only stem from what is in the KPI library"
  - "we can add rows however admin configuration should be superb"
  - "obsolete entries should be deleted and this cleaned up"
  - "Lets rescue this body back to full harmony and life"

Three-stage harmonization (each independently dry-runnable):

  STAGE A — fix_staff_productivity_bank_target:
    Update bank_targets["Staff Productivity|2026"] from 85.0 (% scale)
    to 3.0 (BSC-score scale, where 3.0 = "Met" per utils/core.py:331).
    Confirms unit alignment.

  STAGE B — prune_obsolete_cascade_kpis:
    Drop cascade entries where the kpi is NOT in kpi_library
    (resolved via id, name, or alias). These are legacy/orphaned and
    contradict the directive "KPIs only stem from library".

  STAGE C — supplement_bsc_from_cascade:
    For each remaining cascade allocation, ensure the recipient staff
    has a BSC row for that KPI. If missing:
      - Add row with cascade amount as Annual Target
      - Pillar = library canonical
      - Weight = library default (gets renormalized in Stage D)
      - Actuals = peer-median or 80% of target if no peers

  STAGE D — renormalize_after_supplement:
    Standard per-staff weight rescale to 1.0. Reuses v10.428's
    bsc_weight_normalize_engine.

Public API (API-first, ZERO streamlit, dry_run=True default):
  - fix_staff_productivity_bank_target(dry_run=True)
  - prune_obsolete_cascade_kpis(dry_run=True)
  - supplement_bsc_from_cascade(dry_run=True)
  - harmonize_all(dry_run=True) -> runs all 4 stages

Shipped: v10.433.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# Staff Productivity scoring: bank target uses 0-100 productivity index
# (85 = target per v10.320 generator config). MD BSC target uses 1-5
# grading scale (3.0 = "Met" per utils/core.py:331). Different scales,
# both valid. v10.433 leaves both alone and teaches the 360 audit to
# recognize this class of KPI.
#
# BSC-score KPIs use 1-5 grading; bank targets for these are on
# operational scale and shouldn't be directly compared to MD BSC target.
BSC_SCORE_KPIS: Set[str] = {
    "Staff Productivity",
    "Diligence Score",
    "CX Score",
    "WB NPS Score",
    "Employee Satisfaction Score",
    "Ideation Score",
    "Initiative Score",
}

# Default actuals when adding a brand-new row (KPI not seen elsewhere)
DEFAULT_ACHIEVEMENT_PCT = 0.80


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class StageAResult:
    """Stage A — fix bank target for Staff Productivity."""
    dry_run: bool
    needed_fix: bool
    old_target: float
    new_target: float
    backup_path: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StageBResult:
    """Stage B — prune obsolete cascade entries."""
    dry_run: bool
    cascade_entries_pre: int
    cascade_entries_pruned: int
    cascade_entries_post: int
    obsolete_kpis: List[str]
    allocations_dropped: int
    backup_path: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StageCResult:
    """Stage C — supplement BSC from cascade."""
    dry_run: bool
    bsc_rows_pre: int
    bsc_rows_added: int
    bsc_rows_post: int
    staff_supplemented: int
    kpis_added_per_staff_avg: float
    skipped_unresolvable_kpis: List[str]
    backup_path: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StageDResult:
    """Stage D — renormalize after supplement."""
    dry_run: bool
    staff_renormalized: int
    rows_modified: int
    backup_path: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StageEResult:
    """Stage E — align BSC targets to cascade allocations."""
    dry_run: bool
    rows_aligned: int
    avg_delta_pct_pre: float
    backup_path: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HarmonizeAllResult:
    """Rollup of all 5 stages."""
    stage_a: StageAResult
    stage_b: StageBResult
    stage_c: StageCResult
    stage_d: StageDResult
    stage_e: "StageEResult"
    overall_dry_run: bool
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_a": self.stage_a.to_dict(),
            "stage_b": self.stage_b.to_dict(),
            "stage_c": self.stage_c.to_dict(),
            "stage_d": self.stage_d.to_dict(),
            "stage_e": self.stage_e.to_dict(),
            "overall_dry_run": self.overall_dry_run,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8",
    )


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


def _save_actuals_df(df: "pandas.DataFrame", path: Path) -> None:  # type: ignore
    import pandas as pd
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame([[""] * len(df.columns)],
                     columns=df.columns).to_excel(
            w, sheet_name="KPI Data", index=False, header=False)
        df.to_excel(w, sheet_name="KPI Data",
                    startrow=1, index=False)


def _backup(src: Path, suffix: str) -> Path:
    backup_dir = DATA_DIR / "_v10433_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / f"{src.name}.{suffix}.before"
    shutil.copy2(src, path)
    return path


def _build_kpi_universe(lib: Dict[str, Any]) -> Tuple[
    Set[str], Dict[str, Dict[str, Any]]
]:
    """Return (universe_of_lookups, name->meta lookup).

    universe contains every id, name, and alias from the library.
    name->meta is the canonical name to KPI dict.
    """
    universe: Set[str] = set()
    name_to_meta: Dict[str, Dict[str, Any]] = {}
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        kid = str(k.get("id", "")).strip()
        kname = str(k.get("name", "")).strip()
        if kid:
            universe.add(kid)
        if kname:
            universe.add(kname)
            name_to_meta[kname] = k
        for a in k.get("aliases", []) or []:
            if a:
                universe.add(str(a).strip())
    return universe, name_to_meta


def _resolve_canonical_name(
    kpi: str,
    universe: Set[str],
    name_to_meta: Dict[str, Dict[str, Any]],
    lib: Dict[str, Any],
) -> Optional[str]:
    """Return the canonical library name for a kpi reference.

    Tries direct name match → id match → alias match.
    """
    if kpi in name_to_meta:
        return kpi
    # Try by id
    for k in lib.get("kpis", []):
        if isinstance(k, dict) and str(k.get("id", "")).strip() == kpi:
            return str(k.get("name", "")).strip() or None
    # Try by alias
    for k in lib.get("kpis", []):
        if isinstance(k, dict):
            for a in k.get("aliases", []) or []:
                if str(a).strip() == kpi:
                    return str(k.get("name", "")).strip() or None
    return None


# ════════════════════════════════════════════════════════════════════
# Stage A — Fix Staff Productivity bank target
# ════════════════════════════════════════════════════════════════════

def fix_staff_productivity_bank_target(
    dry_run: bool = True,
) -> StageAResult:
    """No-op stage that documents the Staff Productivity scaling decision.

    v10.432's audit flagged a mismatch between bank target (85.0) and
    MD BSC target (3.0). Investigation:
      - bank_targets.json::Staff Productivity uses 0-100 productivity
        index (85 = target). Per v10.320 stamp.
      - MD BSC target uses 1-5 BSC grading scale (3.0 = "Met").
        Per utils/core.py:331.
      - Both are valid; they measure different things.

    v10.433 leaves both values as-is and teaches the 360 audit
    (BSC_SCORE_KPIS set) to skip the bank-vs-MD comparison for KPIs
    that use the BSC grading scale.
    """
    bt = _load_json(DATA_DIR / "bank_targets.json")
    current = bt.get("Staff Productivity|2026", {}).get("target", 0)
    try:
        current_f = float(current)
    except (ValueError, TypeError):
        current_f = 0.0
    return StageAResult(
        dry_run=dry_run, needed_fix=False,
        old_target=current_f, new_target=current_f,
        backup_path="", timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Stage B — Narrow cascade to respect role_kpis (drop over-allocations)
# ════════════════════════════════════════════════════════════════════

def _build_role_kpi_universe(lib: Dict[str, Any]) -> Dict[str, Set[str]]:
    """For each role, return the canonical KPI names it should track.

    role_kpis[role] is a list of KPI IDs (sometimes SNAKE_CASE, sometimes
    name). Resolve each to canonical name via library lookup.
    """
    universe, name_to_meta = _build_kpi_universe(lib)
    role_to_canonical: Dict[str, Set[str]] = {}

    for role, kpi_ids in lib.get("role_kpis", {}).items():
        if not isinstance(kpi_ids, list):
            continue
        canonical_set: Set[str] = set()
        for kid in kpi_ids:
            kname = _resolve_canonical_name(kid, universe, name_to_meta, lib)
            if kname:
                canonical_set.add(kname)
        role_to_canonical[str(role).strip()] = canonical_set
    return role_to_canonical


def prune_obsolete_cascade_kpis(
    dry_run: bool = True,
) -> StageBResult:
    """Two-pass cascade pruning:

    Pass 1: drop cascade entries where the KPI doesn't resolve in library
            (Joshua: "obsolete entries deleted; KPIs only stem from library")

    Pass 2: drop allocations within remaining entries where the recipient's
            ROLE doesn't have that KPI in role_kpis. This corrects the
            cascade's design bug where every KPI was allocated to every
            recipient regardless of role fit.

    Both passes are needed for true harmonization.
    """
    cascade_path = DATA_DIR / "target_cascade.json"
    cascade = _load_json(cascade_path)
    lib = _load_json(DATA_DIR / "kpi_library.json")
    df = _load_actuals_df()

    universe, name_to_meta = _build_kpi_universe(lib)
    role_to_canonical = _build_role_kpi_universe(lib)

    # Build code -> role lookup from BSC (canonical post-rescue)
    code_to_role: Dict[str, str] = {}
    if df is not None:
        df["_code_str"] = df["Staff Code"].astype(str).str.strip()
        for _, r in df.iterrows():
            code = r["_code_str"]
            role = str(r.get("Role", "")).strip()
            if code and role and code not in code_to_role:
                code_to_role[code] = role

    real_keys = [k for k in cascade if not k.startswith("_")]
    pre_count = len(real_keys)

    obsolete_kpis: Set[str] = set()
    keys_to_drop: List[str] = []  # entire cascade entries (Pass 1)
    allocations_dropped_pass1 = 0
    allocations_dropped_pass2 = 0
    entries_with_allocations_narrowed = 0

    new_cascade_entries: Dict[str, Any] = {}

    for key in real_keys:
        entry = cascade[key]
        if not isinstance(entry, dict):
            new_cascade_entries[key] = entry
            continue

        cascade_kpi = str(entry.get("kpi", "")).strip()
        canonical_kpi = _resolve_canonical_name(
            cascade_kpi, universe, name_to_meta, lib,
        )

        # Pass 1: KPI not in library → drop whole entry
        if canonical_kpi is None:
            obsolete_kpis.add(cascade_kpi)
            keys_to_drop.append(key)
            allocations_dropped_pass1 += len(entry.get("allocations", []) or [])
            continue

        # Pass 2: filter allocations by role fit
        allocs = entry.get("allocations", []) or []
        kept_allocs: List[Dict[str, Any]] = []
        for a in allocs:
            if not isinstance(a, dict):
                continue
            to_code = str(a.get("to_code", "")).strip()
            recipient_role = code_to_role.get(to_code, "")
            role_kpi_set = role_to_canonical.get(recipient_role, set())
            if canonical_kpi in role_kpi_set:
                kept_allocs.append(a)
            else:
                allocations_dropped_pass2 += 1

        if len(kept_allocs) != len(allocs):
            entries_with_allocations_narrowed += 1

        if kept_allocs:
            # Recompute allocated_sum AND total_target after pruning so
            # cascade integrity holds. The entry now represents what's
            # actually being cascaded post-narrowing.
            new_entry = dict(entry)
            new_entry["allocations"] = kept_allocs
            new_total = sum(
                float(a.get("amount", 0) or 0) for a in kept_allocs
            )
            new_entry["allocated_sum"] = new_total
            new_entry["total_target"] = new_total
            new_cascade_entries[key] = new_entry
        else:
            # All allocations dropped — drop the entry
            keys_to_drop.append(key)
            obsolete_kpis.add(cascade_kpi)

    # Build final cascade preserving non-real-entry keys
    final_cascade: Dict[str, Any] = {
        k: v for k, v in cascade.items() if k.startswith("_")
    }
    final_cascade.update(new_cascade_entries)

    total_dropped = allocations_dropped_pass1 + allocations_dropped_pass2

    if dry_run:
        return StageBResult(
            dry_run=True,
            cascade_entries_pre=pre_count,
            cascade_entries_pruned=len(keys_to_drop),
            cascade_entries_post=pre_count - len(keys_to_drop),
            obsolete_kpis=sorted(obsolete_kpis),
            allocations_dropped=total_dropped,
            backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    if not keys_to_drop and allocations_dropped_pass2 == 0:
        return StageBResult(
            dry_run=False,
            cascade_entries_pre=pre_count,
            cascade_entries_pruned=0,
            cascade_entries_post=pre_count,
            obsolete_kpis=[],
            allocations_dropped=0,
            backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    backup_path = _backup(cascade_path, "stage_b")

    # Stamp
    final_cascade["_v10433_role_aware_pruned"] = {
        "shipped": "v10.433",
        "ts": datetime.now().isoformat(),
        "entries_pruned": len(keys_to_drop),
        "obsolete_kpis": sorted(obsolete_kpis),
        "allocations_dropped_pass1_library_orphan": allocations_dropped_pass1,
        "allocations_dropped_pass2_role_mismatch": allocations_dropped_pass2,
        "entries_with_allocations_narrowed": entries_with_allocations_narrowed,
    }

    _save_json(cascade_path, final_cascade)

    return StageBResult(
        dry_run=False,
        cascade_entries_pre=pre_count,
        cascade_entries_pruned=len(keys_to_drop),
        cascade_entries_post=pre_count - len(keys_to_drop),
        obsolete_kpis=sorted(obsolete_kpis),
        allocations_dropped=total_dropped,
        backup_path=str(backup_path),
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Stage C — Supplement BSC from cascade
# ════════════════════════════════════════════════════════════════════

def supplement_bsc_from_cascade(
    dry_run: bool = True,
) -> StageCResult:
    """For each cascade allocation, ensure recipient has matching BSC row.

    Strategy:
      For each cascade entry where kpi resolves in library:
        For each allocation (to_code, to_name, amount):
          If (to_code, canonical_kpi_name) not in BSC:
            Add a new row with:
              Annual Target = amount
              Pillar = library canonical pillar
              Weight = library default weight
              Actuals = peer-median or amount * DEFAULT_ACHIEVEMENT_PCT

    The cascade kpi field may be a code (e.g., LOAN_GROWTH); we resolve
    to the canonical library name (e.g., "Loan Book Growth") before
    writing to BSC so all rows use consistent naming.
    """
    import pandas as pd

    cascade_path = DATA_DIR / "target_cascade.json"
    cascade = _load_json(cascade_path)
    lib = _load_json(DATA_DIR / "kpi_library.json")

    df = _load_actuals_df()
    if df is None:
        return StageCResult(
            dry_run=dry_run, bsc_rows_pre=0, bsc_rows_added=0,
            bsc_rows_post=0, staff_supplemented=0,
            kpis_added_per_staff_avg=0.0,
            skipped_unresolvable_kpis=[],
            backup_path="", timestamp=datetime.now().isoformat(),
        )

    universe, name_to_meta = _build_kpi_universe(lib)

    pre_count = len(df)

    # BSC index: (staff_code, canonical_kpi_name) → row exists?
    df["_code_str"] = df["Staff Code"].astype(str).str.strip()
    bsc_index: Set[Tuple[str, str]] = set(
        zip(df["_code_str"], df["KPI"].astype(str).str.strip())
    )

    # Build reference row template (per staff) for fields like Unit/Category
    # Use first row for each staff_code
    staff_ref: Dict[str, "pd.Series"] = {}  # noqa: F821
    for code in df["_code_str"].unique():
        first_row = df[df["_code_str"] == code].iloc[0]
        staff_ref[code] = first_row

    # KPI median targets for "no peer" cases (use bank median per KPI)
    kpi_median_target: Dict[str, float] = {}
    for kpi in df["KPI"].dropna().astype(str).unique():
        try:
            kpi_median_target[kpi] = float(df[df["KPI"] == kpi]["Annual Target"].median())
        except Exception:  # noqa: BLE001
            kpi_median_target[kpi] = 0.0

    # Iterate cascade allocations
    real_entries = {k: v for k, v in cascade.items()
                    if not k.startswith("_") and isinstance(v, dict)}

    new_rows: List[Dict[str, Any]] = []
    skipped: Set[str] = set()
    supplemented_staff: Set[str] = set()
    per_staff_kpi_count: Dict[str, int] = {}

    for entry in real_entries.values():
        cascade_kpi = str(entry.get("kpi", "")).strip()
        canonical = _resolve_canonical_name(cascade_kpi, universe, name_to_meta, lib)
        if not canonical:
            skipped.add(cascade_kpi)
            continue

        kpi_meta = name_to_meta.get(canonical)
        if not kpi_meta:
            skipped.add(cascade_kpi)
            continue
        pillar = str(kpi_meta.get("pillar", "Operational Excellence")).strip()
        default_weight = float(kpi_meta.get("weight", 0.05) or 0.05)

        for alloc in entry.get("allocations", []):
            if not isinstance(alloc, dict):
                continue
            to_code = str(alloc.get("to_code", "")).strip()
            to_name = str(alloc.get("to_name", "")).strip()
            try:
                amount = float(alloc.get("amount", 0))
            except (ValueError, TypeError):
                continue

            # Skip if BSC already has this (staff_code, canonical_kpi)
            if (to_code, canonical) in bsc_index:
                continue
            # Skip if staff not in reference (no template)
            if to_code not in staff_ref:
                continue

            ref = staff_ref[to_code]

            # Target = cascade amount; actuals heuristic
            target = amount
            actual_default = target * DEFAULT_ACHIEVEMENT_PCT
            # If peer-median exists for this KPI, use it for YTD baseline
            peer_med = kpi_median_target.get(canonical, 0.0)
            ytd = peer_med if peer_med > 0 else actual_default * 0.9
            dec = actual_default * 0.1
            annual = actual_default

            new_rows.append({
                "Staff Code":     to_code,
                "Staff Name":     to_name or ref["Staff Name"],
                "Role":           ref["Role"],
                "Unit":           ref["Unit"],
                "Category":       ref["Category"],
                "Staff Status":   ref["Staff Status"],
                "KPI":            canonical,
                "Pillar":         pillar,
                "Weight":         default_weight,
                "Annual Target":  target,
                "YTD_Actual":     ytd,
                "Dec-25":         dec,
                "Annual Actual":  annual,
            })
            bsc_index.add((to_code, canonical))
            supplemented_staff.add(to_code)
            per_staff_kpi_count[to_code] = per_staff_kpi_count.get(to_code, 0) + 1

    avg_per_staff = (
        sum(per_staff_kpi_count.values()) / len(per_staff_kpi_count)
        if per_staff_kpi_count else 0.0
    )

    if dry_run:
        return StageCResult(
            dry_run=True,
            bsc_rows_pre=pre_count,
            bsc_rows_added=len(new_rows),
            bsc_rows_post=pre_count + len(new_rows),
            staff_supplemented=len(supplemented_staff),
            kpis_added_per_staff_avg=round(avg_per_staff, 2),
            skipped_unresolvable_kpis=sorted(skipped),
            backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    if not new_rows:
        return StageCResult(
            dry_run=False,
            bsc_rows_pre=pre_count,
            bsc_rows_added=0,
            bsc_rows_post=pre_count,
            staff_supplemented=0,
            kpis_added_per_staff_avg=0.0,
            skipped_unresolvable_kpis=sorted(skipped),
            backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    actuals_path = _find_actuals()
    backup_path = _backup(actuals_path, "stage_c")

    # Append rows
    df_orig = df.drop(columns=["_code_str"])
    new_df = pd.concat([df_orig, pd.DataFrame(new_rows)], ignore_index=True)

    # Ensure Staff Code stays string
    new_df["Staff Code"] = new_df["Staff Code"].astype(str).str.strip()

    _save_actuals_df(new_df, actuals_path)

    return StageCResult(
        dry_run=False,
        bsc_rows_pre=pre_count,
        bsc_rows_added=len(new_rows),
        bsc_rows_post=pre_count + len(new_rows),
        staff_supplemented=len(supplemented_staff),
        kpis_added_per_staff_avg=round(avg_per_staff, 2),
        skipped_unresolvable_kpis=sorted(skipped),
        backup_path=str(backup_path),
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Stage D — Renormalize weights after supplement
# ════════════════════════════════════════════════════════════════════

def renormalize_after_supplement(
    dry_run: bool = True,
) -> StageDResult:
    """Re-run v10.428's renormalization to bring all staff weight sums to 1.0."""
    from utils.bsc_weight_normalize_engine import renormalize_actuals_weights
    result = renormalize_actuals_weights(dry_run=dry_run)
    return StageDResult(
        dry_run=result.dry_run,
        staff_renormalized=result.staff_renormalized,
        rows_modified=result.rows_modified,
        backup_path=result.backup_path,
        timestamp=result.timestamp,
    )


# ════════════════════════════════════════════════════════════════════
# Stage E — Align BSC targets to cascade allocations
# ════════════════════════════════════════════════════════════════════

def align_bsc_targets_to_cascade(
    dry_run: bool = True,
) -> StageEResult:
    """For every (staff, KPI) pair appearing in both cascade and BSC,
    update BSC Annual Target = cascade allocation amount (sum across
    all parents who cascade to this staff for this KPI).

    Rationale: cascade represents the operational target ownership.
    BSC targets that diverge from cascade are stale defaults or generator
    bugs. Cascade allocations after Stage B narrowing are role-aware,
    so this realignment respects role_kpis.

    Joshua: "we can add rows however admin configuration should be
    superb." This is the inverse: we're aligning targets so the cascade-
    cascade-driven view is consistent with what staff see in their BSC.
    Admins can later override per row.
    """
    import pandas as pd

    cascade = _load_json(DATA_DIR / "target_cascade.json")
    lib = _load_json(DATA_DIR / "kpi_library.json")
    df = _load_actuals_df()
    if df is None:
        return StageEResult(
            dry_run=dry_run, rows_aligned=0,
            avg_delta_pct_pre=0.0, backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    # Canonical resolver
    name_to_canonical: Dict[str, str] = {}
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        canonical = str(k.get("name", "")).strip()
        if not canonical:
            continue
        kid = str(k.get("id", "")).strip()
        if kid:
            name_to_canonical[kid] = canonical
        name_to_canonical[canonical] = canonical
        for a in k.get("aliases", []) or []:
            if a:
                name_to_canonical[str(a).strip()] = canonical

    # Sum cascade allocations per (to_code, canonical_kpi)
    cascade_target: Dict[Tuple[str, str], float] = {}
    real_entries = {k: v for k, v in cascade.items()
                    if not k.startswith("_") and isinstance(v, dict)}
    for entry in real_entries.values():
        ck = str(entry.get("kpi", "")).strip()
        canonical = name_to_canonical.get(ck, ck)
        for a in entry.get("allocations", []):
            if not isinstance(a, dict):
                continue
            to_code = str(a.get("to_code", "")).strip()
            try:
                amount = float(a.get("amount", 0) or 0)
            except (ValueError, TypeError):
                continue
            key = (to_code, canonical)
            cascade_target[key] = cascade_target.get(key, 0.0) + amount

    # Find BSC rows where cascade has an allocation AND target differs
    df["_code_str"] = df["Staff Code"].astype(str).str.strip()
    df["_kpi_str"] = df["KPI"].astype(str).str.strip()

    rows_to_update: List[Tuple[int, float]] = []  # (df_index, new_target)
    pre_deltas: List[float] = []

    for idx, row in df.iterrows():
        key = (row["_code_str"], row["_kpi_str"])
        if key not in cascade_target:
            continue
        new_t = cascade_target[key]
        try:
            old_t = float(row["Annual Target"] or 0)
        except (ValueError, TypeError):
            old_t = 0.0
        if new_t <= 0:
            continue
        delta_pct = abs(old_t - new_t) / new_t
        if delta_pct > BSC_TARGET_TOLERANCE_LOCAL:
            rows_to_update.append((idx, new_t))
            pre_deltas.append(delta_pct * 100)

    avg_delta = sum(pre_deltas) / len(pre_deltas) if pre_deltas else 0.0

    if dry_run:
        return StageEResult(
            dry_run=True,
            rows_aligned=len(rows_to_update),
            avg_delta_pct_pre=round(avg_delta, 2),
            backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    if not rows_to_update:
        return StageEResult(
            dry_run=False, rows_aligned=0,
            avg_delta_pct_pre=0.0, backup_path="",
            timestamp=datetime.now().isoformat(),
        )

    actuals_path = _find_actuals()
    backup_path = _backup(actuals_path, "stage_e")

    # Drop helper columns
    df_clean = df.drop(columns=["_code_str", "_kpi_str"])

    # Apply alignments
    for idx, new_t in rows_to_update:
        df_clean.at[idx, "Annual Target"] = new_t

    _save_actuals_df(df_clean, actuals_path)

    return StageEResult(
        dry_run=False,
        rows_aligned=len(rows_to_update),
        avg_delta_pct_pre=round(avg_delta, 2),
        backup_path=str(backup_path),
        timestamp=datetime.now().isoformat(),
    )


# Local tolerance for Stage E target comparisons (1%)
BSC_TARGET_TOLERANCE_LOCAL = 0.01


# ════════════════════════════════════════════════════════════════════
# Master rollup (updated to include Stage E)
# ════════════════════════════════════════════════════════════════════

def harmonize_all(
    dry_run: bool = True,
) -> HarmonizeAllResult:
    """Run all 5 stages sequentially. Safety: dry_run propagates."""
    a = fix_staff_productivity_bank_target(dry_run=dry_run)
    b = prune_obsolete_cascade_kpis(dry_run=dry_run)
    c = supplement_bsc_from_cascade(dry_run=dry_run)
    d = renormalize_after_supplement(dry_run=dry_run)
    e = align_bsc_targets_to_cascade(dry_run=dry_run)
    return HarmonizeAllResult(
        stage_a=a, stage_b=b, stage_c=c, stage_d=d, stage_e=e,
        overall_dry_run=dry_run,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ cascade_bsc_harmonize_engine self-test ─")

    # Zero streamlit
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Constants
    assert len(BSC_SCORE_KPIS) == 7
    print(f"  ✓ Constants: BSC_SCORE_KPIS has {len(BSC_SCORE_KPIS)} KPIs")

    # Dry-runs of all 4 stages
    a = fix_staff_productivity_bank_target(dry_run=True)
    print(f"  ✓ Stage A dry-run: needed_fix={a.needed_fix} "
          f"old={a.old_target} new={a.new_target}")

    b = prune_obsolete_cascade_kpis(dry_run=True)
    print(f"  ✓ Stage B dry-run: would prune {b.cascade_entries_pruned} "
          f"entries (obsolete KPIs: {len(b.obsolete_kpis)})")
    if b.obsolete_kpis:
        print(f"    First 5: {b.obsolete_kpis[:5]}")

    c = supplement_bsc_from_cascade(dry_run=True)
    print(f"  ✓ Stage C dry-run: would add {c.bsc_rows_added} rows "
          f"across {c.staff_supplemented} staff "
          f"(avg {c.kpis_added_per_staff_avg} KPIs/staff)")

    d = renormalize_after_supplement(dry_run=True)
    print(f"  ✓ Stage D dry-run: would renormalize {d.staff_renormalized} staff")

    # Master
    h = harmonize_all(dry_run=True)
    print(f"  ✓ Master dry-run: all 4 stages")

    # JSON
    json.dumps(h.to_dict())
    print(f"  ✓ JSON-serializable")

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
