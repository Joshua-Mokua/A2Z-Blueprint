#!/usr/bin/env python3
"""
sync_deals_to_db.py — push the JSON pipeline deals (source of truth) into Postgres.

Pipeline reads are DB-first (_PIPELINE_READ_DB_FIRST=True), but remap_deals.py
edited the JSON store directly, so the DB mirror is stale (old owners, empty units
-> "Unassigned" in analytics). This upserts every JSON deal into pipeline_deals via
the app's own _db_sync_pipeline_deal (ON CONFLICT DO UPDATE), realigning the stores.
Run AFTER remap_deals.py, on the machine with the DB.

    python scripts\\sync_deals_to_db.py --dry-run
    python scripts\\sync_deals_to_db.py
"""
import argparse
from collections import Counter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from utils.core import PipelineManager
    from utils.api import _db_sync_pipeline_deal, _db_available

    pm = PipelineManager()
    deals = pm.get_deals()
    print(f"JSON deals (source of truth): {len(deals)}")
    print(f"DB available: {_db_available()}")
    units = Counter(str(d.get("unit") or "Unassigned") for d in deals)
    print("unit spread in JSON (post re-home):")
    for u, n in sorted(units.items(), key=lambda x: -x[1])[:20]:
        print(f"   {n:>4}  {u}")

    if not _db_available():
        print("[abort] Postgres not available — nothing to sync.")
        return
    if args.dry_run:
        print(f"\n[dry-run] would upsert {len(deals)} deals into pipeline_deals.")
        return

    synced, failed = 0, []
    for d in deals:
        try:
            _db_sync_pipeline_deal(d)
            synced += 1
        except Exception as e:  # noqa: BLE001
            failed.append((d.get("id"), str(e)[:80]))
    print(f"\n[ok] upserted {synced}/{len(deals)} deals into Postgres.")
    if failed:
        print(f"[warn] {len(failed)} failed:")
        for did, err in failed[:10]:
            print(f"   {did}: {err}")


if __name__ == "__main__":
    main()
