"""Normalize non-canonical pillar values in BSC actuals file.

Per v10.425 (BSC Rescue batch 1):
v10.424's BSC audit found 221 rows in data/actuals_*.xlsx using the
non-canonical pillar "Operational" instead of "Operational Excellence".
This script normalizes them via the engine.

SAFETY: defaults to dry-run. Pass --confirm to actually write.
The migration creates a .before backup in data/_v10425_backups/.

Examples:
    # Audit only (no FS changes)
    python scripts/normalize_pillars.py

    # Run the migration
    python scripts/normalize_pillars.py --confirm
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--confirm", action="store_true",
                   help="Actually perform the migration (default: dry-run)")
    args = p.parse_args()

    from utils.bsc_pillar_normalize_engine import (
        audit_actuals_pillars, migrate_actuals_pillars,
    )

    print("BSC Pillar Normalization (v10.425)")
    print("=" * 60)

    audit = audit_actuals_pillars()
    print(f"\nAUDIT:")
    print(f"  Actuals file:     {audit.actuals_path}")
    print(f"  Total rows:       {audit.total_rows}")
    print(f"  Pillars seen:     {audit.pillars_seen}")
    print(f"  Non-canonical:    {audit.non_canonical_counts}")
    print(f"  Rows to migrate:  {audit.rows_to_migrate}")
    print(f"  Affected KPIs:    {len(audit.affected_kpis)}")

    if audit.affected_kpis:
        print(f"\n  Sample affected KPIs:")
        for kpi, n in list(audit.affected_kpis.items())[:15]:
            print(f"    {n:3d}  {kpi}")

    if audit.rows_to_migrate == 0:
        print("\n✓ No non-canonical pillars — actuals already clean.")
        return 0

    if not args.confirm:
        print(f"\n[DRY RUN] To migrate {audit.rows_to_migrate} rows, re-run with --confirm")
        return 0

    print(f"\nRunning migration...")
    result = migrate_actuals_pillars(dry_run=False)
    print(f"  Rows migrated:    {result.rows_migrated}")
    print(f"  Aliases applied:  {result.aliases_applied}")
    print(f"  Backup:           {result.backup_path}")
    print(f"  Note:             {result.note}")

    # Post-audit
    post = audit_actuals_pillars()
    print(f"\nPOST-MIGRATION:")
    print(f"  Pillars in actuals: {post.pillars_seen}")
    print(f"  Rows still non-canonical: {post.rows_to_migrate}")

    if post.rows_to_migrate == 0:
        print(f"\n✓ All pillars now canonical")
        return 0
    print(f"\n✗ {post.rows_to_migrate} rows still non-canonical — investigate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
