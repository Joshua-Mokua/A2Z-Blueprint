"""One-time migration: normalize role weights into kpi_library.json.

Per v10.419 (Phase 2d data integrity housekeeping):

The current kpi_library.json stores ONLY global per-KPI weights
(kpi_weights). When a role's score is computed, weights are pulled from
this global dict for KPIs assigned to that role. The existing scoring
code auto-normalizes by dividing through the sum — but the implicit
assumption "sum of weights for a role = 1.0" was never explicitly stored
or verified, and the audit shows 221/227 roles have weight sums that
aren't 1.0.

This migration ADDS a new field `role_normalized_weights` to kpi_library.json:
  {role: {kpi: normalized_weight}}

where each role's weights are explicitly normalized to sum to 1.0.

It is ADDITIVE: the canonical kpi_weights dict is left untouched.
Existing code reading kpi_weights continues to work unchanged.

Run from repo root:
    python scripts/normalize_role_weights.py

To verify without writing:
    python scripts/normalize_role_weights.py --dry-run
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main(dry_run: bool = False) -> int:
    from utils.role_weight_engine import (
        bank_role_weight_audit,
        migrate_normalize_all_roles,
    )

    print("Role Weight Normalization Migration (v10.419)")
    print("=" * 60)

    # Pre-audit
    pre = bank_role_weight_audit()
    print(f"\nPRE-MIGRATION:")
    print(f"  Total roles:        {pre.total_roles}")
    print(f"  Already normalized: {pre.normalized_count}")
    print(f"  Broken (sum != 1):  {pre.broken_count}")
    print(f"  Zero-sum:           {pre.zero_sum_count}")
    if pre.broken_roles[:5]:
        print(f"  Sample broken roles: {', '.join(pre.broken_roles[:5])}")

    if dry_run:
        print("\n[DRY RUN] No changes written.")
        return 0

    # Run migration
    print("\nRunning migration (additive — existing kpi_weights left intact)...")
    audit, normalized = migrate_normalize_all_roles(write_back=True)

    print(f"\nMIGRATION RESULT:")
    print(f"  role_normalized_weights field added to kpi_library.json")
    print(f"  {len(normalized)} roles now have explicit normalized weights")

    # Verify
    lib_file = REPO / "data" / "kpi_library.json"
    lib = json.loads(lib_file.read_text(encoding="utf-8"))
    rnw = lib.get("role_normalized_weights", {})
    issues = 0
    for role, w_map in rnw.items():
        if not w_map:
            continue
        s = sum(w_map.values())
        if abs(s - 1.0) > 1e-6:
            issues += 1
            print(f"  ✗ {role}: sum = {s}")

    print(f"\nVERIFICATION: {issues} issues (target: 0)")
    if issues == 0:
        print(f"✓ All {len(rnw)} roles' normalized weights sum to 1.0")
    return 0 if issues == 0 else 1


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(main(dry_run=dry))
