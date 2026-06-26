#!/usr/bin/env python3
"""
scripts/migrate_credit_admin_to_pg.py  —  Batch CA-1, step 2 (CA-1b).

One-time backfill of data/credit_admin.json into the credit_admin table, with
HARD reconciliation. Re-runnable (upsert). Read-only against the JSON file.
Run from repo root, venv active, AFTER apply_credit_admin_schema.

CA-1b fixes:
  - Pre-checks the table exists (clear message instead of a raw traceback).
  - Calls the sync with swallow=False so the ok/fail tally is TRUTHFUL
    (the previous version trusted the best-effort sync and printed a false ok=405).

    python scripts\\migrate_credit_admin_to_pg.py
"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    from utils.db import db
    from utils.credit_admin_db_sync import _db_sync_credit_admin_case

    if not db.is_postgres_ready():
        print("!! Postgres not ready in THIS shell — confirm with "
              "storage_readiness_probe.py, then retry.")
        sys.exit(2)

    if not db.fetch_scalar("SELECT to_regclass('public.credit_admin') IS NOT NULL"):
        print("!! credit_admin table does not exist yet. Run step 1 first:")
        print("     python scripts\\apply_credit_admin_schema.py")
        sys.exit(1)

    try:
        from utils.core import DATA_DIR
        jf = Path(DATA_DIR) / "credit_admin.json"
    except Exception:
        jf = ROOT / "data" / "credit_admin.json"
    if not jf.exists():
        print(f"!! {jf} not found.")
        sys.exit(2)

    cases = json.loads(jf.read_text(encoding="utf-8") or "[]")
    if not isinstance(cases, list):
        print("!! credit_admin.json is not a list.")
        sys.exit(2)

    json_ids = {str(c.get("id", "") or "") for c in cases if c.get("id")}
    print(f"  JSON cases: {len(cases)}  (distinct ids: {len(json_ids)})")

    ok = fail = 0
    for c in cases:
        try:
            _db_sync_credit_admin_case(c, conflict="update", swallow=False)  # truthful tally
            ok += 1
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"   [fail] {c.get('id')}: {e}")
    print(f"  upserts: ok={ok} fail={fail}")
    if fail:
        print("  !! some upserts failed — see errors above. Migration INCOMPLETE.")
        sys.exit(1)

    # ── HARD reconciliation gate ──────────────────────────────────────────
    pg_count = db.fetch_scalar("SELECT count(*) FROM credit_admin") or 0
    pg_ids = {r["id"] for r in db.fetch_all("SELECT id FROM credit_admin")}
    missing = json_ids - pg_ids
    print(f"\n  PG rows: {pg_count}  | JSON ids present in PG: "
          f"{len(json_ids & pg_ids)}/{len(json_ids)}")
    if missing:
        print(f"  !! {len(missing)} JSON ids did NOT land in PG (e.g. "
              f"{list(missing)[:5]}). Migration INCOMPLETE.")
        sys.exit(1)

    print("  [PASS] every JSON case id is present in Postgres.")
    print("  Next: python scripts\\verify_credit_admin_roundtrip.py")


if __name__ == "__main__":
    main()
