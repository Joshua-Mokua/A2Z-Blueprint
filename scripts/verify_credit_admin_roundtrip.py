#!/usr/bin/env python3
"""
scripts/verify_credit_admin_roundtrip.py  —  Batch CA-1, step 3 (the gate).

Proves the migration is LOSSLESS: for every case in credit_admin.json, the case
reconstructed from Postgres (_normalize_db_credit_admin_row over the `data`
JSONB) must deep-equal the JSON case. Any missing id, missing key, or value
drift is reported and fails the run.

This is the CA-1 exit gate. Only when this passes should CA-2 (route wiring +
DB-first read flip) proceed. Read-only.

    python scripts\\verify_credit_admin_roundtrip.py
"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _canon(v):
    """Canonicalise for comparison: JSON round-trip normalises tuples/ordering
    and int/float-from-json quirks the same way on both sides."""
    return json.dumps(v, sort_keys=True, default=str)


def main():
    from utils.db import db
    from utils.credit_admin_db_sync import _normalize_db_credit_admin_row

    if not db.is_postgres_ready():
        print("!! Postgres not ready.")
        sys.exit(2)

    try:
        from utils.core import DATA_DIR
        jf = Path(DATA_DIR) / "credit_admin.json"
    except Exception:
        jf = ROOT / "data" / "credit_admin.json"

    cases = json.loads(jf.read_text(encoding="utf-8") or "[]")
    json_by_id = {str(c["id"]): c for c in cases if c.get("id")}

    rows = db.fetch_all("SELECT id, data FROM credit_admin")
    pg_by_id = {}
    for r in rows:
        case = _normalize_db_credit_admin_row(r)
        if case and case.get("id"):
            pg_by_id[str(case["id"])] = case

    missing_ids, key_drift, value_drift = [], [], []
    for cid, jcase in json_by_id.items():
        pcase = pg_by_id.get(cid)
        if pcase is None:
            missing_ids.append(cid)
            continue
        jkeys, pkeys = set(jcase), set(pcase)
        if jkeys - pkeys:
            key_drift.append((cid, sorted(jkeys - pkeys)))
            continue
        for k, jv in jcase.items():
            if _canon(jv) != _canon(pcase.get(k)):
                value_drift.append((cid, k))
                break

    total = len(json_by_id)
    clean = total - len(missing_ids) - len(key_drift) - len(value_drift)
    print(f"  JSON cases checked : {total}")
    print(f"  lossless round-trip: {clean}/{total}")
    if missing_ids:
        print(f"  !! missing in PG ({len(missing_ids)}): {missing_ids[:5]}")
    if key_drift:
        print(f"  !! key loss ({len(key_drift)}): e.g. {key_drift[:3]}")
    if value_drift:
        print(f"  !! value drift ({len(value_drift)}): e.g. {value_drift[:5]}")

    if missing_ids or key_drift or value_drift:
        print("\n  [FAIL] round-trip is NOT lossless — do NOT proceed to CA-2.")
        sys.exit(1)

    print("\n  [PASS] credit_admin is a complete, lossless mirror in Postgres.")
    print("  CA-1 done. Reads still come from JSON (unchanged). Safe to commit.")
    print("  Re-run scripts\\simulate_credit_chain.py to confirm 295/295 unaffected.")


if __name__ == "__main__":
    main()
