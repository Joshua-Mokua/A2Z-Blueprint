"""Cleanup stale batch backup directories under data/_v10*_backups/.

Per v10.421 (Phase 2d data integrity housekeeping):
After v10.345-v10.420 arc, ~173 MB of backup directories have
accumulated. This script applies a retention policy.

Default policy:
  - Preserve all backups < 1 MB (cheap historical reference)
  - Preserve the 3 most recent _v10*_backups directories
  - Delete everything else

SAFETY: dry-run is the default. To actually delete, pass --confirm.

Examples:
    # See what would be deleted (no FS changes)
    python scripts/cleanup_backups.py

    # Actually delete
    python scripts/cleanup_backups.py --confirm

    # Adjust retention (keep top 5)
    python scripts/cleanup_backups.py --keep-recent 5

    # Adjust size threshold (preserve <2 MB)
    python scripts/cleanup_backups.py --size-threshold-mb 2
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--keep-recent", type=int, default=3,
                   help="Preserve top-N most recent backup dirs (default: 3)")
    p.add_argument("--size-threshold-mb", type=float, default=1.0,
                   help="Preserve backups smaller than this (MB, default: 1.0)")
    p.add_argument("--confirm", action="store_true",
                   help="Actually delete (default: dry-run)")
    args = p.parse_args()

    from utils.backup_retention_engine import (
        audit_backup_retention, apply_retention_policy,
    )

    threshold_bytes = int(args.size_threshold_mb * 1024 * 1024)

    print("Backup Retention Cleanup (v10.421)")
    print("=" * 60)

    audit = audit_backup_retention(
        keep_recent_n=args.keep_recent,
        size_threshold_bytes=threshold_bytes,
    )

    print(f"\nAUDIT:")
    print(f"  Policy:               keep top {args.keep_recent}, preserve <{args.size_threshold_mb} MB")
    print(f"  Total backup dirs:    {audit.total_dirs}")
    print(f"  Total size:           {audit.total_mb:.1f} MB")
    print(f"  Will preserve:        {audit.will_keep}")
    print(f"  Will delete:          {audit.will_delete}")
    print(f"  Will reclaim:         {audit.mb_to_reclaim:.1f} MB")

    print(f"\nPer-directory breakdown:")
    for d in sorted(audit.dirs, key=lambda x: x.version, reverse=True):
        flag = "✗ DEL " if d.will_delete else "✓ KEEP"
        print(f"  {flag} v{d.version}: {d.total_mb:6.2f} MB, "
              f"{d.file_count:3d} files — {d.note}")

    if audit.will_delete == 0:
        print("\n✓ Nothing to delete — backup retention is already clean.")
        return 0

    if not args.confirm:
        print(f"\n[DRY RUN] No files were deleted.")
        print(f"To actually delete the {audit.will_delete} dirs and reclaim "
              f"{audit.mb_to_reclaim:.1f} MB, re-run with --confirm")
        return 0

    print(f"\nDELETING {audit.will_delete} directories...")
    result = apply_retention_policy(
        keep_recent_n=args.keep_recent,
        size_threshold_bytes=threshold_bytes,
        dry_run=False,
    )
    print(f"\nDONE:")
    print(f"  Deleted:    {result.dirs_deleted} dirs")
    print(f"  Reclaimed:  {result.mb_reclaimed:.1f} MB")
    if result.errors:
        print(f"\n✗ {len(result.errors)} errors:")
        for err in result.errors:
            print(f"    {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
