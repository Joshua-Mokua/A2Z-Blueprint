"""KPI Library Dedup Engine — v10.420 (Phase 2d).

Per Joshua's locked backlog: 4 KPI alias pairs marked as duplicates in
_v10403_dedup_pending but never actually merged. v10.420 ships the
migration that consolidates them.

The 4 pairs (duplicate → canonical):

  NEW_ACCOUNTS → K006              (both "New Accounts Opened")
  K069         → K024              (both "Digital Channel Adoption (%)")
  K048         → K028              (both "Collateral Review Completion (%)")
  NIM          → NET_INTEREST_MARGIN  (both "Net Interest Margin")

Migration steps for each pair (duplicate, canonical):
  1. role_kpis: replace duplicate ID with canonical, dedupe each role's list
  2. kpi_weights: keep canonical weight; remove duplicate entry
  3. kpis: remove duplicate definition
  4. role_normalized_weights (v10.419): remove duplicate keys, re-normalize
  5. Stamp _v10420_dedup_complete metadata

The migration is IDEMPOTENT: running on an already-deduped library
produces no changes.

ARCHITECTURAL NOTE: API-first per v10.412. ZERO streamlit imports.

Shipped: v10.420.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
KPI_LIBRARY_FILE = DATA_DIR / "kpi_library.json"
BANK_TARGETS_FILE = DATA_DIR / "bank_targets.json"

# Canonical alias map: {duplicate_id: canonical_id}
KPI_ALIAS_PAIRS: Dict[str, str] = {
    "NEW_ACCOUNTS": "K006",
    "K069": "K024",
    "K048": "K028",
    "NIM": "NET_INTEREST_MARGIN",
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class AliasPairAudit:
    """One alias pair's reference counts before migration."""
    duplicate_id: str
    canonical_id: str
    duplicate_in_kpis: bool
    canonical_in_kpis: bool
    duplicate_role_refs: int          # roles using duplicate
    canonical_role_refs: int          # roles using canonical
    overlapping_roles: int            # roles using BOTH (would double-count)
    duplicate_in_kpi_weights: bool
    canonical_in_kpi_weights: bool
    duplicate_in_bank_targets: int
    canonical_in_bank_targets: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DedupAudit:
    """Bank-wide dedup audit."""
    total_pairs: int
    already_migrated: int             # pairs where duplicate is fully gone
    pending: int                      # pairs still needing migration
    pair_audits: List[AliasPairAudit] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DedupMigrationResult:
    """Result of running the dedup migration."""
    pairs_migrated: int
    role_kpis_updated: int            # # of role entries that had a duplicate
    kpi_definitions_removed: int      # # of dup entries removed from kpis list
    kpi_weights_removed: int
    bank_targets_updated: int
    normalized_weights_rebuilt: bool  # True if role_normalized_weights re-migrated
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# I/O helpers
# ════════════════════════════════════════════════════════════════════

def _load_library() -> Dict[str, Any]:
    if not KPI_LIBRARY_FILE.exists():
        return {}
    try:
        return json.loads(KPI_LIBRARY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_library(lib: Dict[str, Any]) -> bool:
    try:
        KPI_LIBRARY_FILE.write_text(
            json.dumps(lib, indent=2, default=str), encoding="utf-8",
        )
        return True
    except OSError:
        return False


def _load_bank_targets() -> Dict[str, Any]:
    if not BANK_TARGETS_FILE.exists():
        return {}
    try:
        return json.loads(BANK_TARGETS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_bank_targets(bt: Dict[str, Any]) -> bool:
    try:
        BANK_TARGETS_FILE.write_text(
            json.dumps(bt, indent=2, default=str), encoding="utf-8",
        )
        return True
    except OSError:
        return False


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def _audit_pair(
    duplicate: str, canonical: str,
    library: Dict[str, Any], bank_targets: Dict[str, Any],
) -> AliasPairAudit:
    """Audit one alias pair's references."""
    kpis = library.get("kpis", [])
    kpi_ids = {k.get("id") for k in kpis if isinstance(k, dict)}
    role_kpis = library.get("role_kpis", {})
    kpi_weights = library.get("kpi_weights", {})

    # Role references
    dup_refs = 0
    canon_refs = 0
    overlap = 0
    for role, kpi_list in role_kpis.items():
        if role.startswith("_") or not isinstance(kpi_list, list):
            continue
        has_dup = duplicate in kpi_list
        has_canon = canonical in kpi_list
        if has_dup:
            dup_refs += 1
        if has_canon:
            canon_refs += 1
        if has_dup and has_canon:
            overlap += 1

    # Bank targets references
    dup_bt = 0
    canon_bt = 0
    for period, items in bank_targets.items():
        if not isinstance(items, dict):
            continue
        if duplicate in items:
            dup_bt += 1
        if canonical in items:
            canon_bt += 1

    return AliasPairAudit(
        duplicate_id=duplicate,
        canonical_id=canonical,
        duplicate_in_kpis=duplicate in kpi_ids,
        canonical_in_kpis=canonical in kpi_ids,
        duplicate_role_refs=dup_refs,
        canonical_role_refs=canon_refs,
        overlapping_roles=overlap,
        duplicate_in_kpi_weights=duplicate in kpi_weights,
        canonical_in_kpi_weights=canonical in kpi_weights,
        duplicate_in_bank_targets=dup_bt,
        canonical_in_bank_targets=canon_bt,
    )


def audit_kpi_dedup(
    library: Optional[Dict[str, Any]] = None,
    bank_targets: Optional[Dict[str, Any]] = None,
) -> DedupAudit:
    """Bank-wide dedup audit."""
    if library is None:
        library = _load_library()
    if bank_targets is None:
        bank_targets = _load_bank_targets()

    pair_audits = [
        _audit_pair(dup, canon, library, bank_targets)
        for dup, canon in KPI_ALIAS_PAIRS.items()
    ]

    already = 0
    pending = 0
    for a in pair_audits:
        # "already migrated" = duplicate gone from kpis AND all reference locations
        if (not a.duplicate_in_kpis
                and a.duplicate_role_refs == 0
                and not a.duplicate_in_kpi_weights
                and a.duplicate_in_bank_targets == 0):
            already += 1
        else:
            pending += 1

    return DedupAudit(
        total_pairs=len(KPI_ALIAS_PAIRS),
        already_migrated=already,
        pending=pending,
        pair_audits=pair_audits,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Migration
# ════════════════════════════════════════════════════════════════════

def migrate_dedup_kpi_library(
    library: Optional[Dict[str, Any]] = None,
    bank_targets: Optional[Dict[str, Any]] = None,
    write_back: bool = True,
    rebuild_normalized_weights: bool = True,
) -> DedupMigrationResult:
    """Consolidate the 4 alias pairs into canonical IDs.

    Steps per pair (duplicate, canonical):
      1. role_kpis: in each role's list, replace duplicate with canonical;
         dedupe to avoid double-counting if both present
      2. kpi_weights: drop duplicate entry (canonical kept)
      3. kpis list: remove duplicate definition
      4. bank_targets: in each period, if duplicate present, drop it
         (canonical assumed to be the source of truth — if missing,
         canonical inherits the duplicate's target)
      5. role_normalized_weights: cleared, then re-migrated to reflect dedup

    Args:
      library: optional pre-loaded; if None, load from disk
      bank_targets: optional pre-loaded; if None, load from disk
      write_back: if True and either was loaded, write back to disk
      rebuild_normalized_weights: re-run v10.419 migration after dedup

    Returns DedupMigrationResult with counts.
    """
    lib_loaded = library is None
    bt_loaded = bank_targets is None
    if lib_loaded:
        library = _load_library()
    if bt_loaded:
        bank_targets = _load_bank_targets()

    role_kpis_updated = 0
    kpis_removed = 0
    weights_removed = 0
    bt_updated = 0

    # Step 1 & 4: role_kpis + bank_targets
    role_kpis = library.get("role_kpis", {})
    for role, kpi_list in role_kpis.items():
        if role.startswith("_") or not isinstance(kpi_list, list):
            continue
        original = list(kpi_list)
        new_list: List[str] = []
        for k in kpi_list:
            if k in KPI_ALIAS_PAIRS:
                # Replace with canonical
                canon = KPI_ALIAS_PAIRS[k]
                if canon not in new_list:
                    new_list.append(canon)
            else:
                if k not in new_list:
                    new_list.append(k)
        if new_list != original:
            role_kpis[role] = new_list
            role_kpis_updated += 1

    # Step 4: bank_targets
    for period, items in list(bank_targets.items()):
        if not isinstance(items, dict):
            continue
        for dup, canon in KPI_ALIAS_PAIRS.items():
            if dup in items:
                # If canonical missing, promote the duplicate's value
                if canon not in items:
                    items[canon] = items[dup]
                del items[dup]
                bt_updated += 1

    # Step 2: kpi_weights
    kpi_weights = library.get("kpi_weights", {})
    for dup in KPI_ALIAS_PAIRS:
        if dup in kpi_weights:
            del kpi_weights[dup]
            weights_removed += 1

    # Step 3: kpis list (remove duplicate definitions)
    kpis = library.get("kpis", [])
    new_kpis: List[Dict[str, Any]] = []
    for kpi in kpis:
        if not isinstance(kpi, dict):
            new_kpis.append(kpi)
            continue
        if kpi.get("id") in KPI_ALIAS_PAIRS:
            kpis_removed += 1
            continue
        new_kpis.append(kpi)
    library["kpis"] = new_kpis

    # Step 5: rebuild role_normalized_weights via v10.419 migration
    rebuilt = False
    if rebuild_normalized_weights:
        try:
            from utils.role_weight_engine import migrate_normalize_all_roles
            # Clear stale entries first
            library.pop("role_normalized_weights", None)
            migrate_normalize_all_roles(library, write_back=False)
            rebuilt = True
        except Exception:  # noqa: BLE001
            rebuilt = False

    # Stamp metadata
    library["_v10420_dedup_complete"] = {
        "shipped": "v10.420",
        "ts": datetime.now().isoformat(),
        "pairs_migrated": dict(KPI_ALIAS_PAIRS),
        "role_kpis_updated": role_kpis_updated,
        "kpi_definitions_removed": kpis_removed,
        "kpi_weights_removed": weights_removed,
        "bank_targets_updated": bt_updated,
        "normalized_weights_rebuilt": rebuilt,
    }

    # Write back
    if write_back and lib_loaded:
        _save_library(library)
    if write_back and bt_loaded:
        _save_bank_targets(bank_targets)

    return DedupMigrationResult(
        pairs_migrated=len(KPI_ALIAS_PAIRS),
        role_kpis_updated=role_kpis_updated,
        kpi_definitions_removed=kpis_removed,
        kpi_weights_removed=weights_removed,
        bank_targets_updated=bt_updated,
        normalized_weights_rebuilt=rebuilt,
        note=f"Migrated {len(KPI_ALIAS_PAIRS)} pairs; cleaned references across role_kpis, kpis, kpi_weights, bank_targets",
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ kpi_dedup_engine self-test ─")

    # Synthetic library + bank targets with all 4 alias pairs
    lib = {
        "kpis": [
            {"id": "NEW_ACCOUNTS", "name": "New Accounts Opened"},
            {"id": "K006", "name": "New Accounts Opened"},
            {"id": "K069", "name": "Digital Channel Adoption"},
            {"id": "K024", "name": "Digital Channel Adoption"},
            {"id": "K048", "name": "Collateral Review"},
            {"id": "K028", "name": "Collateral Review"},
            {"id": "NIM", "name": "Net Interest Margin"},
            {"id": "NET_INTEREST_MARGIN", "name": "Net Interest Margin"},
            {"id": "OTHER_KPI", "name": "Unrelated"},
        ],
        "role_kpis": {
            "RoleA": ["NEW_ACCOUNTS", "K069", "OTHER_KPI"],
            "RoleB": ["K006", "K069"],          # overlap: K006+K069 (where K069 dedup to K024)
            "RoleC": ["NIM", "NET_INTEREST_MARGIN"],  # both present — should dedupe
            "RoleD": ["K048", "K028"],          # both present
            "_meta": ["skip"],
        },
        "kpi_weights": {
            "NEW_ACCOUNTS": 0.03,
            "K006": 0.05,
            "K069": 0.02,
            "K024": 0.04,
            "NIM": 0.05,
            "OTHER_KPI": 0.10,
        },
    }
    bt = {
        "2026": {
            "NEW_ACCOUNTS": {"target": 100, "period": "2026"},
            "OTHER_KPI": {"target": 50, "period": "2026"},
        },
    }

    # Audit before migration
    audit = audit_kpi_dedup(lib, bt)
    assert audit.total_pairs == 4
    assert audit.pending == 4
    print(f"  ✓ Pre-audit: {audit.pending}/{audit.total_pairs} pairs pending")

    # Run migration (write_back=False since synthetic)
    result = migrate_dedup_kpi_library(
        lib, bt, write_back=False, rebuild_normalized_weights=False,
    )
    assert result.pairs_migrated == 4
    print(f"  ✓ Migration: {result.role_kpis_updated} roles updated, "
          f"{result.kpi_definitions_removed} dupes removed")

    # Post-checks
    # RoleA: NEW_ACCOUNTS → K006, K069 → K024
    assert set(lib["role_kpis"]["RoleA"]) == {"K006", "K024", "OTHER_KPI"}
    # RoleB: K006 already present, K069 → K024 (dedup, K006+K024)
    assert set(lib["role_kpis"]["RoleB"]) == {"K006", "K024"}
    # RoleC: NIM → NET_INTEREST_MARGIN, dedupe with existing → just NET_INTEREST_MARGIN
    assert lib["role_kpis"]["RoleC"] == ["NET_INTEREST_MARGIN"]
    # RoleD: K048 → K028, dedupe
    assert lib["role_kpis"]["RoleD"] == ["K028"]
    print(f"  ✓ Role lists deduplicated correctly")

    # kpis list: duplicates removed
    remaining_ids = {k.get("id") for k in lib["kpis"]}
    assert "NEW_ACCOUNTS" not in remaining_ids
    assert "K069" not in remaining_ids
    assert "K048" not in remaining_ids
    assert "NIM" not in remaining_ids
    assert "K006" in remaining_ids
    assert "K024" in remaining_ids
    assert "K028" in remaining_ids
    assert "NET_INTEREST_MARGIN" in remaining_ids
    print(f"  ✓ {len(remaining_ids)} canonical KPI definitions remain")

    # kpi_weights: dupes removed
    assert "NEW_ACCOUNTS" not in lib["kpi_weights"]
    assert "K069" not in lib["kpi_weights"]
    assert "NIM" not in lib["kpi_weights"]
    print(f"  ✓ kpi_weights cleaned: {result.kpi_weights_removed} entries removed")

    # bank_targets: NEW_ACCOUNTS migrated to K006
    assert "NEW_ACCOUNTS" not in bt["2026"]
    assert "K006" in bt["2026"]
    assert bt["2026"]["K006"]["target"] == 100
    print(f"  ✓ bank_targets migrated: {result.bank_targets_updated} entries")

    # Idempotency: re-run should produce no changes
    audit_after = audit_kpi_dedup(lib, bt)
    assert audit_after.pending == 0
    assert audit_after.already_migrated == 4
    print(f"  ✓ Idempotent: re-audit shows {audit_after.already_migrated}/{audit_after.total_pairs} already migrated")

    # Re-run migration — should be a no-op
    result2 = migrate_dedup_kpi_library(
        lib, bt, write_back=False, rebuild_normalized_weights=False,
    )
    assert result2.role_kpis_updated == 0  # nothing left to update
    print(f"  ✓ Idempotent migration: 2nd run = no changes")

    # Zero streamlit imports
    import re
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports (React-ready)")

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
