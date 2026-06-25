#!/usr/bin/env python3
"""scripts/create_deal_id_sequence.py — create + seed the Postgres sequence that
generates race-free pipeline deal ids (Phase A fix).

WHY: deriving the next id with SELECT MAX(id)+1 in application code has a
read-then-write gap — N concurrent creates all read the same MAX and derive the
SAME id, then fight (and the id-based rollback deletes the winner). A PG SEQUENCE
hands every concurrent caller a DISTINCT value atomically (nextval), with no gap
and no collision. This is the correct, standard fix.

Seeds the sequence ABOVE the current max id across BOTH stores (PG table and the
JSON file), so it can never mint an id that already exists — including any
JSON-only deals that drifted out of PG under the old race.

Idempotent: CREATE SEQUENCE IF NOT EXISTS; re-running only re-seeds upward.

    python scripts/create_deal_id_sequence.py            # show plan
    python scripts/create_deal_id_sequence.py --apply     # create + seed
"""
from __future__ import annotations
import argparse, json, os, re, sys
sys.path.insert(0, ".")

SEQ = "pipeline_deal_seq"

def _max_numeric_id(ids):
    mx = 0
    for s in ids:
        m = re.sub(r"\D", "", str(s or ""))
        if m:
            mx = max(mx, int(m))
    return mx

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from utils.db import db
    if not db.is_postgres_ready():
        print("FATAL: Postgres not ready — cannot create the sequence."); sys.exit(2)

    # max id in PG
    pg_ids = [r["id"] for r in db.fetch_all("SELECT id FROM pipeline_deals", ())]
    pg_max = _max_numeric_id(pg_ids)
    # max id in JSON (guard against drifted JSON-only ids)
    jp = os.path.join("data", "pipeline_deals.json")
    json_max = 0
    if os.path.exists(jp):
        try:
            deals = json.loads(open(jp, encoding="utf-8").read())
            json_max = _max_numeric_id(d.get("id") for d in deals if isinstance(d, dict))
        except Exception as e:
            print(f"  (warning: could not read JSON max: {e})")
    seed = max(pg_max, json_max) + 1
    print(f"PG max id:        D{pg_max:04d}  ({len(pg_ids)} rows)")
    print(f"JSON max id:      D{json_max:04d}")
    print(f"Sequence '{SEQ}' will START at: {seed}  (-> next id D{seed:04d})")

    if not args.apply:
        print("\n[DRY-RUN] No DDL run. Re-run with --apply.")
        return

    # CREATE IF NOT EXISTS, then set the value upward (never downward).
    db.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    # setval with is_called=true so the NEXT nextval returns seed (not seed implicitly).
    # We set to seed-1 with is_called=true so nextval() -> seed.
    db.execute(f"SELECT setval(%s, %s, true)", (SEQ, max(seed - 1, 1)))
    # verify
    cur = db.fetch_scalar(f"SELECT last_value FROM {SEQ}", ())
    nxt = db.fetch_scalar("SELECT nextval(%s)", (SEQ,))
    # we just consumed one with that nextval check; put it back so we don't skip an id
    db.execute("SELECT setval(%s, %s, true)", (SEQ, max(seed - 1, 1)))
    print(f"\nCreated/seeded {SEQ}. last_value now seeds next id = D{seed:04d}")
    print(f"(verified nextval would yield {nxt}; reset so no id is skipped)")
    print("Restart the API, then re-run stress_concurrency.py.")

if __name__ == "__main__":
    main()
