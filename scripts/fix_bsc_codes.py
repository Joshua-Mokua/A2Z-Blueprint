"""Align BSC Staff Codes with canonical register codes.

Per v10.429 (BSC Rescue closing batch):
v10.424's audit found 10 cascade staff missing from BSC by code. Root
cause: 10 senior staff (Head of Branches + 9 Area Managers) had BSC rows
under the wrong codes (300001–300010, colliding with chief officers).
Their canonical register codes are 301500–301509.

SAFETY: defaults to dry-run. Pass --confirm to actually write.
Creates backup in data/_v10429_backups/.

Examples:
    # Audit + dry-run preview
    python scripts/fix_bsc_codes.py

    # Apply fix
    python scripts/fix_bsc_codes.py --confirm
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
                   help="Actually perform the fix (default: dry-run)")
    args = p.parse_args()

    from utils.bsc_cascade_linkage_engine import (
        audit_bsc_code_alignment, fix_bsc_codes,
    )

    print("BSC Cascade-BSC Linkage Fix (v10.429)")
    print("=" * 60)

    audit = audit_bsc_code_alignment()
    print(f"\nAUDIT:")
    print(f"  Total BSC codes:          {audit.total_bsc_codes}")
    print(f"  Total register codes:     {audit.total_register_codes}")
    print(f"  BSC codes not in register: {len(audit.bsc_codes_not_in_register)}")
    print(f"  Register codes not in BSC: {len(audit.register_codes_not_in_bsc)}")
    print(f"  Mismatches:                {len(audit.mismatches)}")

    if audit.mismatches:
        print(f"\nStaff with wrong codes in BSC:")
        for m in audit.mismatches:
            print(f"  {m.staff_name:25} "
                  f"BSC={m.bsc_code:6} → canonical={m.register_code:6} "
                  f"({m.rows_affected} rows)")

    if audit.register_codes_not_in_bsc:
        print(f"\nRegister codes NOT in BSC (cascade-linkage gaps):")
        for code in audit.register_codes_not_in_bsc:
            print(f"  {code}")

    if not audit.mismatches and not audit.register_codes_not_in_bsc:
        print(f"\n✓ All codes aligned — no changes needed")
        return 0

    if not args.confirm:
        print(f"\n[DRY RUN] To apply fix, re-run with --confirm")
        return 0

    print(f"\nApplying fix...")
    result = fix_bsc_codes(dry_run=False)
    print(f"  Staff corrected:          {result.staff_corrected}")
    print(f"  Rows updated:             {result.rows_updated}")
    print(f"  Backup:                   {result.backup_path}")
    print(f"  Note:                     {result.note}")

    post = audit_bsc_code_alignment()
    if not post.mismatches and not post.register_codes_not_in_bsc:
        print(f"\n✓ All codes now aligned with canonical register")
        return 0
    print(f"\n✗ {len(post.mismatches)} mismatches remain — investigate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
