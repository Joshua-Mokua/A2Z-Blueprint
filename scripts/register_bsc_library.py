"""Register unregistered BSC KPIs in the canonical library.

Per v10.426 (BSC Rescue batch 2):
v10.424's BSC audit found 81 BSC KPIs not in kpi_library.json. This
script consolidates them via a 4-layer migration:

  1. Add aliases to existing library entries (KNOWN_ALIAS_MAP)
  2. Fix non-canonical pillars in library (Process -> Operational Excellence)
  3. Normalize multi-pillar BSC actuals (MULTI_PILLAR_RESOLUTION)
  4. Register remaining new canonical KPIs

SAFETY: defaults to dry-run. Pass --confirm to actually write.
Creates backups in data/_v10426_backups/.

Examples:
    # Audit + dry-run preview
    python scripts/register_bsc_library.py

    # Run the migration
    python scripts/register_bsc_library.py --confirm
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

    from utils.bsc_library_register_engine import (
        audit_unregistered_bsc_kpis, apply_full_registration,
    )

    print("BSC Library Registration (v10.426)")
    print("=" * 60)

    audit = audit_unregistered_bsc_kpis()
    print(f"\nAUDIT:")
    print(f"  Total BSC KPIs:           {audit.total_bsc_kpis}")
    print(f"  Library universe:         {audit.library_universe}")
    print(f"  Aliases to add:           {len(audit.aliases_to_add)}")
    print(f"  Library pillars to fix:   {audit.pillar_fixes_library}")
    print(f"  Multi-pillar BSC KPIs:    {len(audit.multi_pillar_kpis)}")
    print(f"  Truly-new to register:    {len(audit.to_register)}")

    if audit.aliases_to_add:
        print(f"\nAliases to add (BSC name -> existing library entry):")
        for bsc_name, target_id in audit.aliases_to_add.items():
            print(f"  '{bsc_name}'  ->  {target_id}")

    if audit.multi_pillar_kpis:
        print(f"\nMulti-pillar BSC KPIs (canonical resolution):")
        for kpi in audit.multi_pillar_kpis:
            print(f"  {kpi}")

    if audit.to_register:
        print(f"\nTruly-new KPIs to register (first 20):")
        for u in audit.to_register[:20]:
            print(f"  [{u.pillar:24}] {u.name:45} (suggested_id={u.suggested_id})")
        if len(audit.to_register) > 20:
            print(f"  ... and {len(audit.to_register) - 20} more")

    if not args.confirm:
        print(f"\n[DRY RUN] To migrate, re-run with --confirm")
        return 0

    print(f"\nApplying full 4-layer migration...")
    result = apply_full_registration(dry_run=False)
    print(f"\nRESULT:")
    print(f"  Aliases added:              {result.aliases_added}")
    print(f"  Library pillars fixed:      {result.library_pillars_fixed}")
    print(f"  Actuals multipillar fixed:  {result.actuals_multipillar_fixed}")
    print(f"  New KPIs registered:        {result.new_kpis_registered}")
    print(f"  Library backup:             {result.backup_path_library}")
    print(f"  Actuals backup:             {result.backup_path_actuals}")

    # Post-audit
    post = audit_unregistered_bsc_kpis()
    if len(post.to_register) == 0 and not post.aliases_to_add:
        print(f"\n✓ All BSC KPIs are now registered in canonical library")
        return 0
    print(f"\n✗ {len(post.to_register)} still need registration — investigate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
