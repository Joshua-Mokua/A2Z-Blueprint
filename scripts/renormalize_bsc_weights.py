"""Renormalize BSC actuals weights to sum to 1.0 per staff.

Per v10.428 (BSC Rescue batch 4):
491 staff have Weight column sums ≠ 1.0 (range 1.0–4.28). The fix
is per-staff proportional rescale, preserving relative importance.

SAFETY: defaults to dry-run. Pass --confirm to actually write.
Creates backup in data/_v10428_backups/.

Examples:
    # Audit + dry-run preview
    python scripts/renormalize_bsc_weights.py

    # Apply renormalization
    python scripts/renormalize_bsc_weights.py --confirm
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
                   help="Actually perform the renormalization (default: dry-run)")
    args = p.parse_args()

    from utils.bsc_weight_normalize_engine import (
        audit_actuals_weights, renormalize_actuals_weights,
    )

    print("BSC Weight Renormalization (v10.428)")
    print("=" * 60)

    audit = audit_actuals_weights()
    print(f"\nAUDIT:")
    print(f"  Total staff:           {audit.total_staff}")
    print(f"  Normalized (≈1.0):     {audit.normalized_count}")
    print(f"  Not normalized:        {audit.not_normalized_count}")
    print(f"  Weight sum range:      {audit.min_weight_sum} – {audit.max_weight_sum}")
    print(f"  Avg weight sum:        {audit.avg_weight_sum}")

    if audit.not_normalized_profiles:
        print(f"\nSample staff to renormalize (first 10):")
        for p in audit.not_normalized_profiles[:10]:
            print(f"  {p.staff_name:25} {p.role:35} "
                  f"sum={p.current_weight_sum} factor={p.rescale_factor}")

    if audit.not_normalized_count == 0:
        print(f"\n✓ All weights already normalized")
        return 0

    if not args.confirm:
        print(f"\n[DRY RUN] To renormalize {audit.not_normalized_count} staff, re-run with --confirm")
        return 0

    print(f"\nRenormalizing...")
    result = renormalize_actuals_weights(dry_run=False)
    print(f"  Staff renormalized:    {result.staff_renormalized}")
    print(f"  Rows modified:         {result.rows_modified}")
    print(f"  Avg rescale factor:    {result.avg_rescale_factor}")
    print(f"  Pre sum range:         {result.pre_min_sum} – {result.pre_max_sum}")
    print(f"  Post sum range:        {result.post_min_sum} – {result.post_max_sum}")
    print(f"  Backup:                {result.backup_path}")

    post = audit_actuals_weights()
    if post.not_normalized_count == 0:
        print(f"\n✓ All staff weights now sum to 1.0 (within tolerance)")
        return 0
    print(f"\n✗ {post.not_normalized_count} staff still not normalized — investigate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
