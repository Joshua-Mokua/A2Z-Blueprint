"""BSC Pillar Normalize Engine — v10.425 (BSC Rescue, batch 1 of N).

Per v10.424 audit: 221 BSC rows in data/actuals_*.xlsx use the
non-canonical "Operational" pillar instead of the canonical
"Operational Excellence". This engine normalizes them.

Root cause: simulate_v2.py (the actuals generator) had 19 KPI
definitions hardcoded with `"pillar": "Operational"`. The v10.425
batch fixes simulate_v2.py directly (mechanical str_replace, since
the values are well-bounded) AND ships this engine to migrate the
existing actuals file.

Public API (pure compute, no I/O until migrate):
  - audit_actuals_pillars(actuals_path)  -> ActualsPillarAudit
  - migrate_actuals_pillars(actuals_path, dry_run=True) -> PillarMigrationResult

The migration is ADDITIVE in the sense that it only flips non-canonical
pillar values to their canonical equivalents. No rows are added or
removed; no other columns are touched. ALIAS_MAP defines all known
mappings — currently just {"Operational": "Operational Excellence"}.

After migrating actuals + fixing simulate_v2.py, the audit gate G310
should report pillar_canonical with zero non-canonical pillars.

ARCHITECTURAL NOTE: API-first per v10.412. ZERO streamlit imports.
SAFETY-FIRST: migrate defaults to dry_run=True.

Shipped: v10.425.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# Canonical pillars (must match utils/bsc_audit_engine.CANONICAL_PILLARS
# and data/kpi_library.json::pillar_weights keys, applied v10.423)
CANONICAL_PILLARS: List[str] = [
    "Financial",
    "Customer Focus",
    "Operational Excellence",
    "People & Learning",
]

# Known non-canonical aliases that should be normalized.
# Keys are the alias (incorrect form); values are the canonical name.
ALIAS_MAP: Dict[str, str] = {
    "Operational": "Operational Excellence",
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class ActualsPillarAudit:
    actuals_path: str
    total_rows: int
    pillars_seen: List[str]
    non_canonical_counts: Dict[str, int]   # {alias: row_count}
    canonical_counts: Dict[str, int]
    rows_to_migrate: int
    affected_kpis: Dict[str, int]
    affected_roles: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PillarMigrationResult:
    dry_run: bool
    actuals_path: str
    backup_path: str                       # empty if dry-run
    rows_migrated: int
    aliases_applied: Dict[str, int]        # {alias: count flipped}
    affected_kpis_count: int
    output_size_bytes: int                 # 0 if dry-run
    timestamp: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _find_latest_actuals(data_dir: Optional[Path] = None) -> Optional[Path]:
    if data_dir is None:
        data_dir = DATA_DIR
    if not data_dir.exists():
        return None
    candidates = sorted(data_dir.glob("actuals_*.xlsx"))
    return candidates[-1] if candidates else None


def _load_actuals_df(actuals_path: Path) -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    try:
        return pd.read_excel(actuals_path, skiprows=1)
    except Exception:  # noqa: BLE001
        return None


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def audit_actuals_pillars(
    actuals_path: Optional[Path] = None,
) -> ActualsPillarAudit:
    """Audit the BSC actuals file for non-canonical pillar values."""
    if actuals_path is None:
        actuals_path = _find_latest_actuals()
    if actuals_path is None or not actuals_path.exists():
        return ActualsPillarAudit(
            actuals_path=str(actuals_path) if actuals_path else "",
            total_rows=0, pillars_seen=[], non_canonical_counts={},
            canonical_counts={}, rows_to_migrate=0,
            affected_kpis={}, affected_roles={},
        )

    df = _load_actuals_df(actuals_path)
    if df is None or "Pillar" not in df.columns:
        return ActualsPillarAudit(
            actuals_path=str(actuals_path), total_rows=0, pillars_seen=[],
            non_canonical_counts={}, canonical_counts={},
            rows_to_migrate=0, affected_kpis={}, affected_roles={},
        )

    pillars_seen = sorted(df["Pillar"].dropna().unique().tolist())
    counts = df["Pillar"].value_counts().to_dict()
    non_canonical = {
        p: int(c) for p, c in counts.items()
        if p not in CANONICAL_PILLARS
    }
    canonical = {
        p: int(c) for p, c in counts.items()
        if p in CANONICAL_PILLARS
    }

    affected_kpis: Dict[str, int] = {}
    affected_roles: Dict[str, int] = {}
    if non_canonical:
        nc_mask = df["Pillar"].isin(non_canonical.keys())
        affected_kpis = {
            str(k): int(v)
            for k, v in df[nc_mask]["KPI"].value_counts().head(30).items()
        }
        affected_roles = {
            str(k): int(v)
            for k, v in df[nc_mask]["Role"].value_counts().head(20).items()
        }

    return ActualsPillarAudit(
        actuals_path=str(actuals_path),
        total_rows=len(df),
        pillars_seen=pillars_seen,
        non_canonical_counts=non_canonical,
        canonical_counts=canonical,
        rows_to_migrate=sum(non_canonical.values()),
        affected_kpis=affected_kpis,
        affected_roles=affected_roles,
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Migration (default dry_run for safety)
# ════════════════════════════════════════════════════════════════════

def migrate_actuals_pillars(
    actuals_path: Optional[Path] = None,
    dry_run: bool = True,
    alias_map: Optional[Dict[str, str]] = None,
) -> PillarMigrationResult:
    """Flip non-canonical pillar values to canonical equivalents.

    Args:
        actuals_path: path to actuals_*.xlsx. If None, latest is found.
        dry_run: if True (default), no FS changes — returns what would change.
        alias_map: override the default ALIAS_MAP if needed.

    Returns PillarMigrationResult with counts + backup path.

    SAFETY:
      - dry_run=True default
      - Creates a .before backup before writing (when dry_run=False)
      - Preserves all columns and rows; only modifies the Pillar column
    """
    import pandas as pd

    if alias_map is None:
        alias_map = dict(ALIAS_MAP)

    if actuals_path is None:
        actuals_path = _find_latest_actuals()
    if actuals_path is None or not actuals_path.exists():
        return PillarMigrationResult(
            dry_run=dry_run, actuals_path="", backup_path="",
            rows_migrated=0, aliases_applied={},
            affected_kpis_count=0, output_size_bytes=0,
            timestamp=datetime.now().isoformat(),
            note="No actuals file found",
        )

    df = _load_actuals_df(actuals_path)
    if df is None or "Pillar" not in df.columns:
        return PillarMigrationResult(
            dry_run=dry_run, actuals_path=str(actuals_path), backup_path="",
            rows_migrated=0, aliases_applied={},
            affected_kpis_count=0, output_size_bytes=0,
            timestamp=datetime.now().isoformat(),
            note="Actuals file unreadable or missing Pillar column",
        )

    # Compute changes
    aliases_applied: Dict[str, int] = {}
    for alias, canonical in alias_map.items():
        count = int((df["Pillar"] == alias).sum())
        if count > 0:
            aliases_applied[alias] = count

    rows_migrated = sum(aliases_applied.values())
    affected_kpis_count = 0
    if aliases_applied:
        mask = df["Pillar"].isin(aliases_applied.keys())
        affected_kpis_count = int(df[mask]["KPI"].nunique())

    if dry_run:
        return PillarMigrationResult(
            dry_run=True, actuals_path=str(actuals_path), backup_path="",
            rows_migrated=rows_migrated, aliases_applied=aliases_applied,
            affected_kpis_count=affected_kpis_count, output_size_bytes=0,
            timestamp=datetime.now().isoformat(),
            note=("Dry-run: no file changes" if rows_migrated > 0
                  else "No non-canonical pillars found"),
        )

    if rows_migrated == 0:
        return PillarMigrationResult(
            dry_run=False, actuals_path=str(actuals_path), backup_path="",
            rows_migrated=0, aliases_applied={},
            affected_kpis_count=0,
            output_size_bytes=actuals_path.stat().st_size,
            timestamp=datetime.now().isoformat(),
            note="No non-canonical pillars; file unchanged",
        )

    # Create backup
    backup_dir = DATA_DIR / "_v10425_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{actuals_path.name}.before"
    shutil.copy2(actuals_path, backup_path)

    # Apply migration
    for alias, canonical in alias_map.items():
        df.loc[df["Pillar"] == alias, "Pillar"] = canonical

    # Write back — preserve the 2-row header pattern of original
    # (Row 0 was a banner row; row 1 contained the column names.)
    with pd.ExcelWriter(actuals_path, engine="openpyxl") as writer:
        # Banner row
        pd.DataFrame([[""] * len(df.columns)],
                     columns=df.columns).to_excel(
            writer, sheet_name="KPI Data", index=False, header=False)
        # Headers + data
        df.to_excel(writer, sheet_name="KPI Data",
                    startrow=1, index=False)

    return PillarMigrationResult(
        dry_run=False, actuals_path=str(actuals_path),
        backup_path=str(backup_path),
        rows_migrated=rows_migrated, aliases_applied=aliases_applied,
        affected_kpis_count=affected_kpis_count,
        output_size_bytes=actuals_path.stat().st_size,
        timestamp=datetime.now().isoformat(),
        note=f"Migrated {rows_migrated} rows; backup at {backup_path.name}",
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ bsc_pillar_normalize_engine self-test ─")
    import tempfile
    import pandas as pd

    # Zero streamlit check
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports (React-ready)")

    # Constants
    assert "Operational Excellence" in CANONICAL_PILLARS
    assert ALIAS_MAP["Operational"] == "Operational Excellence"
    print(f"  ✓ Constants: 4 canonical pillars + {len(ALIAS_MAP)} alias mapping(s)")

    # Build synthetic actuals
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / "actuals_test.xlsx"
        synth = pd.DataFrame({
            "Staff Name":     ["Alice", "Bob", "Carol", "Dave"],
            "Staff Code":     ["S1", "S2", "S3", "S4"],
            "Role":           ["Manager", "Officer", "Manager", "Officer"],
            "Unit":           ["A", "A", "B", "B"],
            "Category":       ["X", "X", "Y", "Y"],
            "Staff Status":   ["Active"] * 4,
            "KPI":            ["K1", "K2", "K3", "K4"],
            "Pillar":         ["Financial", "Operational",
                               "Customer Focus", "Operational"],
            "Weight":         [0.5, 0.5, 0.5, 0.5],
            "Annual Target":  [100] * 4,
            "YTD_Actual":     [50] * 4,
            "Dec-25":         [10] * 4,
            "Annual Actual":  [60] * 4,
        })
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame([[""] * len(synth.columns)],
                         columns=synth.columns).to_excel(
                writer, sheet_name="KPI Data", index=False, header=False)
            synth.to_excel(writer, sheet_name="KPI Data",
                          startrow=1, index=False)

        # Audit
        audit = audit_actuals_pillars(actuals_path=path)
        assert audit.total_rows == 4
        assert audit.non_canonical_counts.get("Operational") == 2
        assert audit.rows_to_migrate == 2
        print(f"  ✓ Audit: {audit.rows_to_migrate} rows to migrate")

        # Dry-run migrate
        dry = migrate_actuals_pillars(actuals_path=path, dry_run=True)
        assert dry.dry_run is True
        assert dry.rows_migrated == 2
        assert dry.backup_path == ""
        # File NOT modified
        audit2 = audit_actuals_pillars(actuals_path=path)
        assert audit2.rows_to_migrate == 2
        print(f"  ✓ Dry-run: reports {dry.rows_migrated} but no FS change")

        # Real migrate — backups to default DATA_DIR. Override DATA_DIR
        # for the test so backups land in tmp/_v10425_backups not real data/.
        global DATA_DIR
        original_data_dir = DATA_DIR
        DATA_DIR = tmp
        try:
            real = migrate_actuals_pillars(actuals_path=path, dry_run=False)
            assert real.dry_run is False
            assert real.rows_migrated == 2
            assert real.backup_path != ""
            assert Path(real.backup_path).exists()
        finally:
            DATA_DIR = original_data_dir

        # Verify post-migration audit shows 0
        audit3 = audit_actuals_pillars(actuals_path=path)
        assert audit3.rows_to_migrate == 0
        assert "Operational" not in audit3.non_canonical_counts
        assert audit3.canonical_counts.get("Operational Excellence") == 2
        print(f"  ✓ Post-migrate: 0 rows non-canonical; "
              f"2 rows now 'Operational Excellence'")

        # Idempotency
        DATA_DIR = tmp
        try:
            again = migrate_actuals_pillars(actuals_path=path, dry_run=False)
            assert again.rows_migrated == 0
        finally:
            DATA_DIR = original_data_dir
        print(f"  ✓ Idempotent: re-run yields 0 changes")

        # JSON serialization
        import json
        json.dumps(audit.to_dict())
        json.dumps(real.to_dict())
        print(f"  ✓ JSON-serializable")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
