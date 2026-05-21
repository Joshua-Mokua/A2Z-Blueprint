"""BSC Cascade Linkage Engine — v10.429 (BSC Rescue, closing batch 5 of 5).

Per v10.424 audit: 10 cascade staff missing from BSC by code. Root cause:
those 10 staff have BSC rows under WRONG codes — specifically the 10
chief officers' codes (300001-300010), creating code collisions with
their canonical codes (301500-301509 per staff_register).

The conflict came from buggy code assignment during BSC generation —
the Area Managers + Head of Branches got the first 10 chief codes
instead of their canonical 30150x codes. Cascade was generated against
canonical codes, so the 10 cascade staff appeared "missing" from BSC.

Fix strategy: rewrite Staff Code in BSC actuals to match staff_register
canonical codes (per Staff Name). Idempotent: re-running on aligned
state yields 0 changes.

Public API (API-first, ZERO streamlit, dry_run=True default):
  - audit_bsc_code_alignment() -> CodeAlignmentAudit
  - fix_bsc_codes(dry_run=True) -> CodeAlignmentResult

After this batch, all 7 BSC audit categories should be clean →
BSC overall health = 100%.

Shipped: v10.429.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class CodeMismatch:
    staff_name: str
    bsc_code: str
    register_code: str
    rows_affected: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CodeAlignmentAudit:
    total_bsc_codes: int
    total_register_codes: int
    bsc_codes_not_in_register: List[str]
    register_codes_not_in_bsc: List[str]
    mismatches: List[CodeMismatch]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_bsc_codes": self.total_bsc_codes,
            "total_register_codes": self.total_register_codes,
            "bsc_codes_not_in_register": self.bsc_codes_not_in_register,
            "register_codes_not_in_bsc": self.register_codes_not_in_bsc,
            "mismatches": [m.to_dict() for m in self.mismatches],
            "timestamp": self.timestamp,
        }


@dataclass
class CodeAlignmentResult:
    dry_run: bool
    staff_corrected: int
    rows_updated: int
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


def _load_register(register_path: Optional[Path] = None) -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    if register_path is None:
        register_path = DATA_DIR / "staff_register.xlsx"
    if not register_path.exists():
        return None
    try:
        return pd.read_excel(register_path)
    except Exception:  # noqa: BLE001
        return None


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def audit_bsc_code_alignment(
    actuals_path: Optional[Path] = None,
    register_path: Optional[Path] = None,
) -> CodeAlignmentAudit:
    """Find staff whose BSC Staff Code != register Staff Code.

    The register is the canonical source of truth for staff codes.
    BSC actuals should mirror register codes for every staff.
    """
    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return CodeAlignmentAudit(0, 0, [], [], [], datetime.now().isoformat())

    df = _load_actuals_df(actuals_path)
    reg = _load_register(register_path)
    if df is None or reg is None:
        return CodeAlignmentAudit(0, 0, [], [], [], datetime.now().isoformat())

    # Build name -> canonical code map from register
    name_to_canonical_code: Dict[str, str] = {}
    for _, row in reg.iterrows():
        name = str(row["Staff Name"]).strip() if row.get("Staff Name") else ""
        code = str(row["Staff Code"]).strip() if row.get("Staff Code") else ""
        if name and code:
            name_to_canonical_code[name] = code

    bsc_codes = set(df["Staff Code"].dropna().astype(str).str.strip())
    reg_codes = set(reg["Staff Code"].dropna().astype(str).str.strip())

    bsc_not_in_reg = sorted(bsc_codes - reg_codes)
    reg_not_in_bsc = sorted(reg_codes - bsc_codes)

    # Find mismatches: BSC rows where Staff Code != register code for that name
    mismatches_by_name: Dict[str, CodeMismatch] = {}
    for _, row in df.iterrows():
        name = str(row.get("Staff Name", "")).strip()
        bsc_code = str(row.get("Staff Code", "")).strip()
        if not name:
            continue
        canonical = name_to_canonical_code.get(name)
        if canonical is None:
            continue
        if bsc_code != canonical:
            if name not in mismatches_by_name:
                mismatches_by_name[name] = CodeMismatch(
                    staff_name=name,
                    bsc_code=bsc_code,
                    register_code=canonical,
                    rows_affected=0,
                )
            mismatches_by_name[name].rows_affected += 1

    return CodeAlignmentAudit(
        total_bsc_codes=len(bsc_codes),
        total_register_codes=len(reg_codes),
        bsc_codes_not_in_register=bsc_not_in_reg,
        register_codes_not_in_bsc=reg_not_in_bsc,
        mismatches=list(mismatches_by_name.values()),
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Fix (default dry-run)
# ════════════════════════════════════════════════════════════════════

def fix_bsc_codes(
    dry_run: bool = True,
    actuals_path: Optional[Path] = None,
    register_path: Optional[Path] = None,
) -> CodeAlignmentResult:
    """Rewrite BSC Staff Code values to match register canonical codes.

    For each staff whose BSC code differs from their register code,
    update all their BSC rows to use the canonical code.

    Safety:
      - dry_run=True default
      - Creates .before backup at data/_v10429_backups/
      - Idempotent
    """
    import pandas as pd

    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return CodeAlignmentResult(
            dry_run=dry_run, staff_corrected=0, rows_updated=0,
            backup_path="", timestamp=datetime.now().isoformat(),
            note="No actuals file found",
        )

    audit = audit_bsc_code_alignment(actuals_path, register_path)

    if dry_run:
        return CodeAlignmentResult(
            dry_run=True,
            staff_corrected=len(audit.mismatches),
            rows_updated=sum(m.rows_affected for m in audit.mismatches),
            backup_path="",
            timestamp=datetime.now().isoformat(),
            note=(f"Dry-run: would correct {len(audit.mismatches)} staff "
                  f"codes across {sum(m.rows_affected for m in audit.mismatches)} rows"
                  if audit.mismatches else "No mismatches detected"),
        )

    if not audit.mismatches:
        return CodeAlignmentResult(
            dry_run=False, staff_corrected=0, rows_updated=0,
            backup_path="", timestamp=datetime.now().isoformat(),
            note="Codes already aligned — no changes",
        )

    # Backup
    backup_dir = DATA_DIR / "_v10429_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{actuals_path.name}.before"
    shutil.copy2(actuals_path, backup_path)

    df = _load_actuals_df(actuals_path)

    # Apply fixes
    rows_updated = 0
    staff_corrected = 0
    # Cast Staff Code column to object/string to allow mixed assignment
    df["Staff Code"] = df["Staff Code"].astype(str).str.strip()
    for mismatch in audit.mismatches:
        mask = (df["Staff Name"] == mismatch.staff_name) & (
            df["Staff Code"] == mismatch.bsc_code
        )
        n = int(mask.sum())
        if n > 0:
            df.loc[mask, "Staff Code"] = str(mismatch.register_code)
            rows_updated += n
            staff_corrected += 1

    # Write back
    _save_actuals_df(df, actuals_path)

    return CodeAlignmentResult(
        dry_run=False,
        staff_corrected=staff_corrected,
        rows_updated=rows_updated,
        backup_path=str(backup_path),
        timestamp=datetime.now().isoformat(),
        note=f"Corrected {staff_corrected} staff codes across {rows_updated} rows",
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ bsc_cascade_linkage_engine self-test ─")
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

    # Synthetic test
    tmp = Path(tempfile.mkdtemp())
    try:
        # Build synthetic actuals + register
        actuals = tmp / "actuals_test.xlsx"
        register = tmp / "staff_register.xlsx"

        actuals_df = pd.DataFrame({
            "Staff Name":     ["Alice", "Alice", "Bob"],
            "Staff Code":     ["WRONG1", "WRONG1", "S002"],  # Alice has wrong code
            "Role":           ["Mgr"]*2 + ["Off"],
            "Unit":           ["A"]*2 + ["B"],
            "Category":       ["X"]*2 + ["Y"],
            "Staff Status":   ["Active"]*3,
            "KPI":            ["K1", "K2", "K1"],
            "Pillar":         ["Financial"]*3,
            "Weight":         [0.5, 0.5, 1.0],
            "Annual Target":  [100]*3,
            "YTD_Actual":     [50]*3,
            "Dec-25":         [10]*3,
            "Annual Actual":  [60]*3,
        })
        register_df = pd.DataFrame({
            "Staff Code": ["S001", "S002"],
            "Staff Name": ["Alice", "Bob"],
            "Role":       ["Mgr", "Off"],
            "Unit":       ["A", "B"],
        })

        with pd.ExcelWriter(actuals, engine="openpyxl") as w:
            pd.DataFrame([[""] * len(actuals_df.columns)],
                         columns=actuals_df.columns).to_excel(
                w, sheet_name="KPI Data", index=False, header=False)
            actuals_df.to_excel(w, sheet_name="KPI Data",
                          startrow=1, index=False)
        register_df.to_excel(register, index=False)

        # Audit
        audit = audit_bsc_code_alignment(actuals, register)
        assert len(audit.mismatches) == 1
        assert audit.mismatches[0].staff_name == "Alice"
        assert audit.mismatches[0].register_code == "S001"
        assert audit.mismatches[0].rows_affected == 2
        print(f"  ✓ Audit: {len(audit.mismatches)} mismatches found")

        # Dry-run
        dry = fix_bsc_codes(actuals_path=actuals, register_path=register, dry_run=True)
        assert dry.dry_run is True
        assert dry.staff_corrected == 1
        print(f"  ✓ Dry-run: {dry.staff_corrected} staff, {dry.rows_updated} rows")

        # Real fix
        global DATA_DIR
        original_dd = DATA_DIR
        DATA_DIR = tmp
        try:
            result = fix_bsc_codes(actuals_path=actuals, register_path=register, dry_run=False)
            assert result.dry_run is False
            assert result.staff_corrected == 1
            assert result.rows_updated == 2
        finally:
            DATA_DIR = original_dd

        # Verify
        post_df = pd.read_excel(actuals, skiprows=1)
        alice_codes = post_df[post_df["Staff Name"] == "Alice"]["Staff Code"].unique()
        assert list(alice_codes) == ["S001"], f"Expected ['S001'], got {list(alice_codes)}"
        print(f"  ✓ Real fix: Alice now under S001")

        # Idempotency
        DATA_DIR = tmp
        try:
            r2 = fix_bsc_codes(actuals_path=actuals, register_path=register, dry_run=False)
            assert r2.staff_corrected == 0
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
