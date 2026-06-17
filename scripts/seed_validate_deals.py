"""Seed manager-validation onto a slice of pipeline deals.

Why: the analytics "assured" value, the MD dashboard "Assured" tile, the Pipeline
"Total Assured" card, and the Validated-pipeline funnel all read ACTIVE deals
where `manager_validated` is true. A fresh seed has none validated, so every one
of those reads zero / "no validated deals yet". This validates a realistic slice
so those surfaces come alive — using the SAME path the app uses
(PipelineManager.validate_deal), not a raw DB write.

SAFE + IDEMPOTENT:
- Targets the first N% of ACTIVE deals ordered by id (deterministic). Re-running
  validates exactly the same set and skips ones already validated — the validated
  count converges to the target, it does not grow unbounded.
- --dry-run touches nothing (no writes); prints what would change.

Usage (in the project venv):
  python scripts\\seed_validate_deals.py --dry-run
  python scripts\\seed_validate_deals.py --pct 60
"""
from __future__ import annotations
import argparse
import sys


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate a slice of pipeline deals.")
    ap.add_argument("--pct", type=int, default=60,
                    help="Percent of ACTIVE deals (by id order) to mark validated (default 60).")
    ap.add_argument("--by", default="seed_admin",
                    help="validated_by tag recorded on each deal (default seed_admin).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change; write nothing.")
    args = ap.parse_args()

    if not (0 <= args.pct <= 100):
        raise SystemExit("--pct must be between 0 and 100")

    try:
        from utils.core import PipelineManager, ACTIVE_STAGES
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Could not import the app layer (run in the project venv): {e}")

    pm = PipelineManager()
    deals = pm.get_deals()

    active = [d for d in deals if d.get("stage") in ACTIVE_STAGES]
    active.sort(key=lambda d: str(d.get("id", "")))

    target_n = int(len(active) * args.pct / 100)
    target = active[:target_n]

    already = [d for d in target if d.get("manager_validated")]
    todo = [d for d in target if not d.get("manager_validated")]

    total_active = len(active)
    already_validated_all = sum(1 for d in active if d.get("manager_validated"))

    print(f"Active deals:            {total_active}")
    print(f"Already validated (all): {already_validated_all}")
    print(f"Target ({args.pct}% of active): {target_n}")
    print(f"  - already validated in target: {len(already)}")
    print(f"  - to validate now:             {len(todo)}")

    if args.dry_run:
        print("\n[dry-run] no changes written.")
        for d in todo[:10]:
            print(f"  would validate {d.get('id')} | {d.get('stage')} | {d.get('client_name','')}")
        if len(todo) > 10:
            print(f"  … and {len(todo) - 10} more")
        return

    # Validate in the JSON store (pending-count source) AND sync to the DB
    # (the analytics assured/funnel read deals DB-first). Existing file-validated
    # deals still need the DB sync, so we sync every target deal, not just new
    # validations.
    try:
        from utils.api import _db_sync_pipeline_deal
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Could not import _db_sync_pipeline_deal: {e}")

    validated_n = 0
    synced_n = 0
    for d in target:
        did = str(d["id"])
        if not d.get("manager_validated"):
            pm.validate_deal(did, args.by, True, "seed assurance (demo)")
            validated_n += 1
        vd = pm.get_deal(did) or d
        try:
            _db_sync_pipeline_deal(vd)
            synced_n += 1
        except Exception as e:  # noqa: BLE001
            print(f"  warn: DB sync failed for {did}: {e}")

    print(f"\nNewly validated: {validated_n}")
    print(f"Synced to DB:    {synced_n} / {len(target)}")
    print("Funnel + Assured (dashboard / analytics / pipeline) will now populate "
          "once the API is restarted.")


if __name__ == "__main__":
    sys.exit(main())
