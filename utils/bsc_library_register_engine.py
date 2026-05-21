"""BSC Library Register Engine — v10.426 (BSC Rescue, batch 2 of N).

Per v10.424 audit + Joshua's directive: register all unregistered
BSC KPIs in the canonical kpi_library.json, ensuring NO duplicates
or aliases.

This engine resolves alignment at four layers:

  Layer 1 — ALIAS DETECTION: Find BSC KPI names that map to existing
            library entries via fuzzy/exact name semantic match.
            Add to the library entry's `aliases` field (no duplicate
            registration). 4 known alias cases pre-mapped.

  Layer 2 — LIBRARY PILLAR FIX: 13 existing library KPIs have a
            non-canonical pillar value of "Process". Normalize to
            "Operational Excellence" (the closest canonical match).

  Layer 3 — MULTI-PILLAR ACTUALS FIX: 5 BSC KPIs (4 FD-prefix + NIM)
            are tagged with DIFFERENT pillars across rows in actuals.
            Resolve to a single canonical pillar per KPI.

  Layer 4 — REGISTRATION: Remaining truly-new BSC KPIs (~70) added to
            kpi_library.json::kpis with full schema (id, name, pillar,
            weight, unit, direction, active, description, source).

After all 4 layers, library_alignment audit should report 100%.

Default canonical pillar resolution for multi-pillar BSC actuals:
  - Net Interest Margin       -> Financial (semantically a margin KPI)
  - FD Approval Rate          -> Operational Excellence (workflow KPI)
  - FD Rate Variance vs Market -> Operational Excellence
  - FD Ratification TAT       -> Operational Excellence
  - FD Ratification Volume    -> Operational Excellence

ARCHITECTURAL NOTE: API-first per v10.412. ZERO streamlit. SAFETY-FIRST:
all migrations default to dry_run=True.

Shipped: v10.426.
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

# Canonical pillars (v10.423)
CANONICAL_PILLARS: List[str] = [
    "Financial",
    "Customer Focus",
    "Operational Excellence",
    "People & Learning",
]

# Layer 1: known alias mappings (BSC KPI name -> existing library entry id)
# These are confirmed manually via fuzzy match + semantic review.
# Adding to the library entry's aliases field, NOT creating new entries.
KNOWN_ALIAS_MAP: Dict[str, str] = {
    "Bancassurance Premium":          "K023",                  # Bancassurance Premium (KES M)
    "Credit TAT — Standard Lane":     "CREDIT_TAT_STANDARD",   # Credit TAT - Standard
    "Credit TAT — Express Lane":      "CREDIT_TAT_EXPRESS",    # Credit TAT - Express
    "Credit TAT — Complex Lane":      "CREDIT_TAT_COMPLEX",    # Credit TAT - Complex
    # "New Accounts" is ALREADY aliased to K006 (verified live).
}

# Layer 2: non-canonical pillars in library to normalize -> canonical
# v10.426: "Process" -> "Operational Excellence"
# v10.431: extended with "Risk" -> "Financial" after validation engine
# surfaced 3 KPIs (PRODUCT_NPL_RATE, LCR, NSFR) using Risk pillar.
LIBRARY_PILLAR_FIX_MAP: Dict[str, str] = {
    "Process": "Operational Excellence",
    "Risk": "Financial",
}

# Layer 3: multi-pillar BSC actuals — canonical pillar resolution.
# Keyed by BSC KPI name; values are the canonical pillar to enforce.
MULTI_PILLAR_RESOLUTION: Dict[str, str] = {
    "Net Interest Margin":          "Financial",
    "FD Approval Rate":             "Operational Excellence",
    "FD Rate Variance vs Market":   "Operational Excellence",
    "FD Ratification TAT":          "Operational Excellence",
    "FD Ratification Volume":       "Operational Excellence",
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class UnregisteredKPI:
    name: str
    pillar: str          # canonical or non-canonical as found in actuals
    occurrences: int
    avg_weight: float
    suggested_id: str    # generated upper-snake from name

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegistrationAudit:
    total_bsc_kpis: int
    library_universe: int               # ids + names + aliases
    aliases_to_add: Dict[str, str]      # BSC name -> existing lib id
    pillar_fixes_library: int           # # of library entries needing pillar fix
    multi_pillar_kpis: List[str]
    to_register: List[UnregisteredKPI]  # truly new
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_bsc_kpis": self.total_bsc_kpis,
            "library_universe": self.library_universe,
            "aliases_to_add": self.aliases_to_add,
            "pillar_fixes_library": self.pillar_fixes_library,
            "multi_pillar_kpis": self.multi_pillar_kpis,
            "to_register": [u.to_dict() for u in self.to_register],
            "timestamp": self.timestamp,
        }


@dataclass
class RegistrationResult:
    dry_run: bool
    aliases_added: int
    library_pillars_fixed: int
    actuals_multipillar_fixed: int
    new_kpis_registered: int
    backup_path_library: str
    backup_path_actuals: str
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


def _save_lib(lib: Dict[str, Any]) -> bool:
    try:
        KPI_LIBRARY_FILE.write_text(
            json.dumps(lib, indent=2, default=str), encoding="utf-8",
        )
        return True
    except OSError:
        return False


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


def _name_to_id(name: str) -> str:
    """Convert 'New Customers Acquired' -> 'NEW_CUSTOMERS_ACQUIRED'."""
    s = re.sub(r"[^\w\s]", "", name)
    s = re.sub(r"\s+", "_", s.strip())
    return s.upper()


def _build_lib_universe(lib: Dict[str, Any]) -> Tuple[set, set, set]:
    """Return (ids, names, aliases) sets."""
    ids, names, aliases = set(), set(), set()
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        if k.get("id"):
            ids.add(str(k["id"]).strip())
        if k.get("name"):
            names.add(str(k["name"]).strip())
        for a in k.get("aliases", []) or []:
            if a:
                aliases.add(str(a).strip())
    return ids, names, aliases


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def audit_unregistered_bsc_kpis(
    actuals_path: Optional[Path] = None,
) -> RegistrationAudit:
    """Identify BSC KPIs needing registration, after alias consideration."""
    import pandas as pd

    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return RegistrationAudit(0, 0, {}, 0, [], [], datetime.now().isoformat())

    df = _load_actuals_df(actuals_path)
    if df is None:
        return RegistrationAudit(0, 0, {}, 0, [], [], datetime.now().isoformat())

    lib = _load_lib()
    ids, names, aliases = _build_lib_universe(lib)
    universe = ids | names | aliases

    bsc_kpis = set(df["KPI"].dropna().astype(str).str.strip().unique())

    # Identify aliases to add (BSC name that matches a known alias_map AND
    # the target library entry doesn't already have this alias)
    aliases_to_add: Dict[str, str] = {}
    for bsc_name, target_id in KNOWN_ALIAS_MAP.items():
        if bsc_name in bsc_kpis and bsc_name not in aliases:
            aliases_to_add[bsc_name] = target_id

    # Library entries needing pillar fix
    pillar_fixes = sum(
        1 for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("pillar") in LIBRARY_PILLAR_FIX_MAP
    )

    # Multi-pillar BSC KPIs
    pillar_per_kpi = df.groupby("KPI")["Pillar"].nunique()
    multi_pillar = sorted(pillar_per_kpi[pillar_per_kpi > 1].index.tolist())

    # To register: BSC KPIs not in universe AND not in known alias_map
    pre_aliased_targets = set(aliases_to_add.keys())
    unreg_candidates = bsc_kpis - universe - pre_aliased_targets

    # Build metadata for each candidate
    meta = df.groupby(["KPI", "Pillar"]).agg(
        occurrences=("Staff Name", "count"),
        avg_weight=("Weight", "mean"),
    ).reset_index()
    to_register: List[UnregisteredKPI] = []
    seen_kpis = set()
    for kpi in sorted(unreg_candidates):
        if kpi in seen_kpis:
            continue
        seen_kpis.add(kpi)
        # Pick canonical pillar:
        #   if in MULTI_PILLAR_RESOLUTION use that
        #   else use most-occurring pillar in actuals
        if kpi in MULTI_PILLAR_RESOLUTION:
            canon_pillar = MULTI_PILLAR_RESOLUTION[kpi]
        else:
            kpi_rows = meta[meta["KPI"] == kpi]
            if len(kpi_rows) > 0:
                top = kpi_rows.sort_values("occurrences", ascending=False).iloc[0]
                canon_pillar = str(top["Pillar"])
                # Apply library pillar fix map (Process -> Operational Excellence)
                canon_pillar = LIBRARY_PILLAR_FIX_MAP.get(canon_pillar, canon_pillar)
            else:
                canon_pillar = "Operational Excellence"  # safe fallback

        # Aggregate occurrences + avg weight across pillars
        kpi_rows_all = meta[meta["KPI"] == kpi]
        total_occ = int(kpi_rows_all["occurrences"].sum())
        avg_w = float(kpi_rows_all["avg_weight"].mean()) if len(kpi_rows_all) > 0 else 0.05

        to_register.append(UnregisteredKPI(
            name=kpi,
            pillar=canon_pillar,
            occurrences=total_occ,
            avg_weight=round(avg_w, 4),
            suggested_id=_name_to_id(kpi),
        ))

    return RegistrationAudit(
        total_bsc_kpis=len(bsc_kpis),
        library_universe=len(universe),
        aliases_to_add=aliases_to_add,
        pillar_fixes_library=pillar_fixes,
        multi_pillar_kpis=multi_pillar,
        to_register=to_register,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Migration (default dry_run)
# ════════════════════════════════════════════════════════════════════

def apply_full_registration(
    dry_run: bool = True,
    actuals_path: Optional[Path] = None,
) -> RegistrationResult:
    """Run all 4 layers in order. Atomic — either all dry-run or all real.

    Layers:
      1. Add aliases to existing library entries (KNOWN_ALIAS_MAP)
      2. Fix non-canonical pillars in library (Process -> Operational Excellence)
      3. Normalize multi-pillar BSC actuals (MULTI_PILLAR_RESOLUTION)
      4. Register new canonical KPIs from remaining unregistered

    Safety:
      - dry_run=True default
      - Creates backups before modifying both library and actuals
    """
    import pandas as pd

    if actuals_path is None:
        actuals_path = _find_actuals()
    if actuals_path is None or not actuals_path.exists():
        return RegistrationResult(
            dry_run=dry_run, aliases_added=0, library_pillars_fixed=0,
            actuals_multipillar_fixed=0, new_kpis_registered=0,
            backup_path_library="", backup_path_actuals="",
            timestamp=datetime.now().isoformat(),
            note="No actuals file found",
        )

    # Audit first to know what to do
    audit = audit_unregistered_bsc_kpis(actuals_path)

    if dry_run:
        return RegistrationResult(
            dry_run=True,
            aliases_added=len(audit.aliases_to_add),
            library_pillars_fixed=audit.pillar_fixes_library,
            actuals_multipillar_fixed=len(audit.multi_pillar_kpis),
            new_kpis_registered=len(audit.to_register),
            backup_path_library="",
            backup_path_actuals="",
            timestamp=datetime.now().isoformat(),
            note="Dry-run: no FS changes",
        )

    # Real run — create backups
    backup_dir = DATA_DIR / "_v10426_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    lib_backup = backup_dir / "kpi_library.json.before"
    actuals_backup = backup_dir / f"{actuals_path.name}.before"

    if KPI_LIBRARY_FILE.exists():
        shutil.copy2(KPI_LIBRARY_FILE, lib_backup)
    shutil.copy2(actuals_path, actuals_backup)

    # Load fresh copies
    lib = _load_lib()
    df = _load_actuals_df(actuals_path)

    # Layer 1: aliases
    aliases_added = 0
    for bsc_name, target_id in audit.aliases_to_add.items():
        for k in lib.get("kpis", []):
            if not isinstance(k, dict):
                continue
            if str(k.get("id", "")).strip() == target_id:
                aliases = k.get("aliases", [])
                if not isinstance(aliases, list):
                    aliases = []
                if bsc_name not in aliases:
                    aliases.append(bsc_name)
                    k["aliases"] = aliases
                    aliases_added += 1
                break

    # Layer 2: library pillar fixes
    library_pillars_fixed = 0
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        cur_pillar = k.get("pillar")
        if cur_pillar in LIBRARY_PILLAR_FIX_MAP:
            k["pillar"] = LIBRARY_PILLAR_FIX_MAP[cur_pillar]
            library_pillars_fixed += 1

    # Layer 3: actuals multi-pillar fixes
    actuals_multipillar_fixed = 0
    for kpi_name, canon_pillar in MULTI_PILLAR_RESOLUTION.items():
        mask = df["KPI"] == kpi_name
        if mask.any():
            wrong_mask = mask & (df["Pillar"] != canon_pillar)
            n_to_fix = int(wrong_mask.sum())
            if n_to_fix > 0:
                df.loc[wrong_mask, "Pillar"] = canon_pillar
                actuals_multipillar_fixed += n_to_fix

    # Layer 4: register new canonical KPIs
    new_kpis_registered = 0
    existing_ids = {str(k.get("id", "")).strip() for k in lib.get("kpis", []) if isinstance(k, dict)}
    for ureg in audit.to_register:
        # Ensure id is unique — append _2, _3 etc if collision
        base_id = ureg.suggested_id
        new_id = base_id
        suffix = 2
        while new_id in existing_ids:
            new_id = f"{base_id}_{suffix}"
            suffix += 1
        existing_ids.add(new_id)

        new_kpi = {
            "id": new_id,
            "name": ureg.name,
            "pillar": ureg.pillar,
            "weight": ureg.avg_weight if ureg.avg_weight > 0 else 0.05,
            "unit": "value",   # generic — can be refined later
            "direction": "higher",
            "active": True,
            "description": (
                f"{ureg.name} — registered v10.426 from BSC actuals "
                f"(observed in {ureg.occurrences} staff rows)"
            ),
            "source": "bsc_actuals",
            "_origin": "v10.426_bsc_library_register",
        }
        lib.setdefault("kpis", []).append(new_kpi)
        new_kpis_registered += 1

    # Stamp migration metadata
    lib["_v10426_bsc_library_register"] = {
        "shipped": "v10.426",
        "ts": datetime.now().isoformat(),
        "aliases_added": aliases_added,
        "library_pillars_fixed": library_pillars_fixed,
        "actuals_multipillar_fixed": actuals_multipillar_fixed,
        "new_kpis_registered": new_kpis_registered,
    }

    # Write back
    _save_lib(lib)
    _save_actuals_df(df, actuals_path)

    return RegistrationResult(
        dry_run=False,
        aliases_added=aliases_added,
        library_pillars_fixed=library_pillars_fixed,
        actuals_multipillar_fixed=actuals_multipillar_fixed,
        new_kpis_registered=new_kpis_registered,
        backup_path_library=str(lib_backup),
        backup_path_actuals=str(actuals_backup),
        timestamp=datetime.now().isoformat(),
        note=f"All 4 layers applied successfully",
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ bsc_library_register_engine self-test ─")

    # Zero streamlit
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Constants
    assert "Process" in LIBRARY_PILLAR_FIX_MAP
    assert LIBRARY_PILLAR_FIX_MAP["Process"] == "Operational Excellence"
    assert "Net Interest Margin" in MULTI_PILLAR_RESOLUTION
    assert MULTI_PILLAR_RESOLUTION["Net Interest Margin"] == "Financial"
    assert "K023" == KNOWN_ALIAS_MAP["Bancassurance Premium"]
    print(f"  ✓ Constants: {len(KNOWN_ALIAS_MAP)} alias maps, "
          f"{len(LIBRARY_PILLAR_FIX_MAP)} pillar fix maps, "
          f"{len(MULTI_PILLAR_RESOLUTION)} multi-pillar resolutions")

    # Name to ID conversion
    assert _name_to_id("New Customers Acquired") == "NEW_CUSTOMERS_ACQUIRED"
    assert _name_to_id("Credit TAT — Standard Lane") == "CREDIT_TAT_STANDARD_LANE"
    assert _name_to_id("PBT") == "PBT"
    print(f"  ✓ Name-to-ID conversion works")

    # Dry-run on real data
    audit = audit_unregistered_bsc_kpis()
    print(f"  ✓ Real audit: {len(audit.to_register)} to register, "
          f"{len(audit.aliases_to_add)} aliases to add, "
          f"{audit.pillar_fixes_library} library pillars to fix, "
          f"{len(audit.multi_pillar_kpis)} multi-pillar KPIs")

    result = apply_full_registration(dry_run=True)
    assert result.dry_run is True
    print(f"  ✓ Dry-run result: {result.aliases_added} aliases, "
          f"{result.library_pillars_fixed} pillar fixes, "
          f"{result.actuals_multipillar_fixed} multipillar (will be calculated), "
          f"{result.new_kpis_registered} new")

    # JSON serializable
    json.dumps(audit.to_dict())
    json.dumps(result.to_dict())
    print(f"  ✓ JSON-serializable")

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
