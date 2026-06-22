#!/usr/bin/env python3
"""
prune_seed_cruft.py — reconcile Postgres pipeline_deals with the JSON source-of-truth.

ROOT CAUSE (proven by fx_diag.py): _db_sync_pipeline_deal only upserts, never
deletes. As the JSON store was trimmed over time, the DB accumulated stale
SEED00xxx rows (DB=1650 vs JSON=1050). ~140 carry FCY value, so analytics
(DB-first) over-counts FCY vs the dashboard (JSON), producing the invariant
~1.53B FX-reconciliation gap.

SURGICAL: deletes ONLY rows whose id starts with 'SEED' AND is absent from the
JSON store. Real deals (D####, LMS-linked, etc.) are never touched. The harness
samples its out-of-scope deal dynamically (first violation not owned by 300731),
so no SEED keep-list is required.

SAFE BY DEFAULT: dry-run unless --apply is passed. Backs up the table to a
timestamped JSON before any delete.

    python scripts\\prune_seed_cruft.py            # dry-run: report only
    python scripts\\prune_seed_cruft.py --apply    # back up, then delete
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_DEALS = DATA_DIR / "pipeline_deals.json"


def load_json_ids():
    raw = json.loads(JSON_DEALS.read_text(encoding="utf-8"))
    deals = raw.get("deals", raw) if isinstance(raw, dict) else raw
    return {str(d.get("id")) for d in deals if isinstance(d, dict) and d.get("id")}


def main():
    apply = "--apply" in sys.argv
    from utils.db import db

    json_ids = load_json_ids()
    print(f"JSON source-of-truth: {len(json_ids)} deal ids")

    rows = db.fetch_all("SELECT id FROM pipeline_deals", ())
    db_ids = [str(r["id"]) for r in rows]
    print(f"DB pipeline_deals:    {len(db_ids)} rows")

    # Orphans = in DB, not in JSON. Surgical filter to SEED-prefixed only.
    orphans = [i for i in db_ids if i not in json_ids]
    seed_orphans = sorted(i for i in orphans if i.upper().startswith("SEED"))
    non_seed_orphans = sorted(i for i in orphans if not i.upper().startswith("SEED"))

    print(f"\nDB rows absent from JSON: {len(orphans)}")
    print(f"  SEED-prefixed (PRUNE TARGET): {len(seed_orphans)}")
    print(f"  non-SEED (LEFT UNTOUCHED):    {len(non_seed_orphans)}")
    if non_seed_orphans:
        print(f"    e.g. {non_seed_orphans[:10]}  <- NOT deleted (surgical SEED-only)")

    if not seed_orphans:
        print("\nNothing to prune. DB already reconciled with JSON.")
        return

    print(f"\nFirst 15 SEED orphans to delete: {seed_orphans[:15]}")

    if not apply:
        print("\n[DRY-RUN] No changes made. Re-run with --apply to back up + delete.")
        return

    # ---- backup the full table before mutation ----
    full = db.fetch_all("SELECT * FROM pipeline_deals", ())
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DATA_DIR / f"pipeline_deals_db_table.pre_prune_{ts}.json"

    def _ser(o):
        try:
            return str(o)
        except Exception:
            return None
    backup.write_text(json.dumps(full, default=_ser, indent=2), encoding="utf-8")
    print(f"\n[backup] {len(full)} DB rows -> {backup.name}")

    # ---- delete in one parametrized statement ----
    placeholders = ",".join(["%s"] * len(seed_orphans))
    db.execute(f"DELETE FROM pipeline_deals WHERE id IN ({placeholders})",
               tuple(seed_orphans))

    after = db.fetch_all("SELECT id FROM pipeline_deals", ())
    print(f"[apply] deleted {len(seed_orphans)} SEED orphans.")
    print(f"[apply] DB pipeline_deals now: {len(after)} rows (was {len(db_ids)}).")
    print("\nRestart the API, then re-run the harness — FX check should reconcile.")


if __name__ == "__main__":
    main()
