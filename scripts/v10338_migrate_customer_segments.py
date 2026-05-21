"""
v10.338 — Customer segment migration.

Per the v10.338 design Q1: the canonical Individual taxonomy is
Affluent / Core Middle / Mass (3 tiers). The virtual-bank test
data (customer_intelligence.json) currently uses 4 tiers:

  Mass (1,520)         → Mass         (stays)
  Mass Affluent (920)  → Core Middle  (rename)
  Affluent (402)       → Affluent     (stays)
  Premium (158)        → Affluent     (fold up)

KAIZEN principle: this script is REVERSIBLE. It tags every migrated
record with the original segment in `_v10338_previous_segment` and
saves a one-shot rollback file `data/_v10338_segment_migration.json`
recording the diff.

Re-running the script is idempotent — already-migrated records are
skipped (segment is already canonical AND _v10338_previous_segment
is set).

Also tags business customers (currently 0 in the virtual bank dataset)
with `customer_type` for future business-data ingestion.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CIS_PATH = ROOT / "data" / "customer_intelligence.json"
ROLLBACK_PATH = ROOT / "data" / "_v10338_segment_migration.json"

# Migration map: legacy display → canonical code (display_name from segment_config)
LEGACY_TO_CANONICAL = {
    "Mass":          ("MASS",        "Mass"),
    "Mass Affluent": ("CORE_MIDDLE", "Core Middle"),
    "Core Middle":   ("CORE_MIDDLE", "Core Middle"),
    "Affluent":      ("AFFLUENT",    "Affluent"),
    "Premium":       ("AFFLUENT",    "Affluent"),
}


def apply():
    from utils.db import db as _db

    cis = _db.load_json(CIS_PATH, default={}) or {}
    if not cis:
        print("  customer_intelligence.json empty — nothing to migrate")
        return

    # Backup the original (idempotent)
    backup_path = CIS_PATH.with_suffix(".json.v10338.bak")
    if not backup_path.exists():
        _db.save_json(backup_path, cis)
        print(f"  Backup written: {backup_path.name}")

    migrated = 0
    skipped = 0
    diff_log = {}

    for cif, rec in cis.items():
        if not isinstance(rec, dict):
            continue
        current_seg = (rec.get("segment") or "").strip()
        if not current_seg:
            continue

        # Already migrated?
        if (
            current_seg in ("Mass", "Core Middle", "Affluent")
            and "_v10338_previous_segment" in rec
        ):
            skipped += 1
            continue

        mapping = LEGACY_TO_CANONICAL.get(current_seg)
        if not mapping:
            continue

        canonical_code, canonical_display = mapping
        if current_seg != canonical_display:
            rec["_v10338_previous_segment"] = current_seg
            rec["segment"] = canonical_display
            diff_log[cif] = {
                "from": current_seg,
                "to":   canonical_display,
                "code": canonical_code,
            }
            migrated += 1
        else:
            # Already canonical display, just tag _v10338_previous_segment for traceability
            rec["_v10338_previous_segment"] = current_seg
            rec["segment_code"] = canonical_code
            skipped += 1

        # Stamp the canonical code on every record
        rec["segment_code"] = canonical_code
        # Mark as individual (the virtual bank dataset is 100% individual)
        rec.setdefault("customer_type", "individual")

    _db.save_json(CIS_PATH, cis)

    # Write rollback log
    rollback = {
        "shipped": "v10.338",
        "ts": datetime.now(timezone.utc).isoformat(),
        "migrated_count": migrated,
        "skipped_count":  skipped,
        "mapping_used": {
            k: {"code": v[0], "display": v[1]}
            for k, v in LEGACY_TO_CANONICAL.items()
        },
        "diff": diff_log,
        "rationale": (
            "Migrated customer_intelligence.json from 4-tier "
            "(Mass/Mass Affluent/Affluent/Premium) to canonical 3-tier "
            "(Mass/Core Middle/Affluent) per v10.338 spec Q1. "
            "Premium folded into Affluent; Mass Affluent renamed to "
            "Core Middle. Reversible via _v10338_previous_segment tag "
            "on each migrated record."
        ),
    }
    _db.save_json(ROLLBACK_PATH, rollback)
    print(f"  Migrated: {migrated}, Already canonical: {skipped}")
    print(f"  Rollback log: {ROLLBACK_PATH.name}")

    # Verify post-migration distribution
    from collections import Counter
    cis_after = _db.load_json(CIS_PATH, default={}) or {}
    seg_counter = Counter(
        r.get("segment_code", "?") for r in cis_after.values()
        if isinstance(r, dict)
    )
    print("  Post-migration distribution:")
    for seg, n in seg_counter.most_common():
        print(f"    {seg}: {n}")


if __name__ == "__main__":
    apply()
    print("\nv10.338 customer segment migration complete.")
