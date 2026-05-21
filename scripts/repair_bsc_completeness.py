"""Complete incomplete BSCs via canonical role_kpis.

Per v10.427 (BSC Rescue batch 3):
v10.424's audit found 6 chiefs at 2/8 KPIs + 2 at 7/8 KPIs (8 incomplete).
v10.427's engine extends the check to 'configured vs current' and found 9
incomplete chiefs (added Gregory Chirchir at 9/14 configured).

The canonical role_kpis configuration exists in kpi_library.json — these
chiefs simply weren't populated. This script generates the missing rows.

SAFETY: defaults to dry-run. Pass --confirm to actually write.
Creates backups in data/_v10427_backups/.

Examples:
    # Audit + dry-run preview
    python scripts/repair_bsc_completeness.py

    # Run the migration
    python scripts/repair_bsc_completeness.py --confirm
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

    from utils.bsc_completeness_engine import (
        audit_bsc_completeness, repair_bsc_completeness,
        repair_code_alias_artifacts,
    )

    print("BSC Completeness Repair (v10.427)")
    print("=" * 60)

    audit = audit_bsc_completeness()
    print(f"\nAUDIT:")
    print(f"  Total staff with role_kpis config: {audit.total_staff}")
    print(f"  Incomplete BSCs:                   {audit.incomplete_count}")
    print(f"  Rows would be added:               {audit.rows_would_be_added}")

    if audit.gaps:
        print(f"\nIncomplete staff:")
        for g in audit.gaps:
            print(f"  {g.role:50} — {g.staff_name:25} "
                  f"({g.current_kpi_count}/{g.configured_kpi_count} KPIs, "
                  f"{len(g.missing_kpis)} missing)")

    if not args.confirm:
        print(f"\n[DRY RUN] To migrate, re-run with --confirm")
        return 0

    print(f"\nStage 1: Adding missing rows...")
    result = repair_bsc_completeness(dry_run=False)
    print(f"  Staff repaired:        {result.staff_repaired}")
    print(f"  Rows added:            {result.rows_added}")
    print(f"  Weights renormalized:  {result.weights_renormalized}")
    print(f"  Backup:                {result.backup_path}")

    print(f"\nStage 2: Cleaning code-alias artifacts...")
    cleanup = repair_code_alias_artifacts(dry_run=False)
    print(f"  Rows renamed:          {cleanup.rows_added}")
    print(f"  Library aliases added: {cleanup.weights_renormalized}")
    print(f"  Note:                  {cleanup.note}")

    # Post-audit
    post = audit_bsc_completeness()
    if post.incomplete_count == 0:
        print(f"\n✓ All staff with role_kpis config now have complete BSC")
        return 0
    print(f"\n✗ {post.incomplete_count} still incomplete — investigate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
