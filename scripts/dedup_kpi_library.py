"""One-time migration: dedup 4 KPI alias pairs in kpi_library.json.

Per v10.420 (Phase 2d data integrity housekeeping):

4 KPI alias pairs were marked as duplicates in _v10403_dedup_pending
but never actually merged. This migration consolidates them.

Pairs (duplicate → canonical):
  NEW_ACCOUNTS → K006
  K069         → K024
  K048         → K028
  NIM          → NET_INTEREST_MARGIN

Run from repo root:
    python scripts/dedup_kpi_library.py

To preview without writing:
    python scripts/dedup_kpi_library.py --dry-run
"""
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main(dry_run: bool = False) -> int:
    from utils.kpi_dedup_engine import audit_kpi_dedup, migrate_dedup_kpi_library

    print("KPI Library Dedup Migration (v10.420)")
    print("=" * 60)

    pre = audit_kpi_dedup()
    print(f"\nPRE-MIGRATION audit:")
    print(f"  Total alias pairs:   {pre.total_pairs}")
    print(f"  Already migrated:    {pre.already_migrated}")
    print(f"  Pending:             {pre.pending}")
    print(f"\nPair details:")
    for a in pre.pair_audits:
        print(f"  {a.duplicate_id:>20} -> {a.canonical_id}")
        print(f"    duplicate_role_refs:   {a.duplicate_role_refs}")
        print(f"    canonical_role_refs:   {a.canonical_role_refs}")
        print(f"    overlapping_roles:     {a.overlapping_roles}")
        print(f"    duplicate in weights:  {a.duplicate_in_kpi_weights}")
        print(f"    duplicate in targets:  {a.duplicate_in_bank_targets}")

    if dry_run:
        print("\n[DRY RUN] No changes written.")
        return 0

    if pre.pending == 0:
        print("\n✓ Library already deduped — nothing to do.")
        return 0

    print("\nRunning migration...")
    result = migrate_dedup_kpi_library(
        write_back=True, rebuild_normalized_weights=True,
    )
    print(f"\nMIGRATION RESULT:")
    print(f"  Pairs migrated:               {result.pairs_migrated}")
    print(f"  Role lists updated:           {result.role_kpis_updated}")
    print(f"  KPI definitions removed:      {result.kpi_definitions_removed}")
    print(f"  kpi_weights entries removed:  {result.kpi_weights_removed}")
    print(f"  bank_targets entries updated: {result.bank_targets_updated}")
    print(f"  Normalized weights rebuilt:   {result.normalized_weights_rebuilt}")

    post = audit_kpi_dedup()
    print(f"\nPOST-MIGRATION audit:")
    print(f"  Pending pairs: {post.pending}")
    if post.pending == 0:
        print(f"\n✓ All 4 alias pairs consolidated successfully")
        return 0
    print(f"\n✗ {post.pending} pairs still pending — investigate")
    return 1


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(main(dry_run=dry))
