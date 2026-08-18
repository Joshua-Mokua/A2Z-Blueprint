#!/usr/bin/env python3
"""
scripts/diag_troops_persist.py — surface WHY a route-level troops mutation on a
backfilled case returns 200 but does not persist to Postgres.

Runs in-process (no HTTP), so the swallowed exception in the save()-hook is made
visible. Read-ish: it mutates one case's troops_status in memory and attempts the
upsert; it does NOT disburse. Pick any cleared case id via --id (default below).

    python scripts\\diag_troops_persist.py
    python scripts\\diag_troops_persist.py --id CALMS00121
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="CALMS00121")
    cid = ap.parse_args().id

    from utils.db import db
    from utils.core import CreditAdminManager
    from utils.credit_admin_db_sync import _db_sync_credit_admin_case, _row_from_case

    print(f"PG ready: {db.is_postgres_ready()}  table_uses_db('credit_admin'): {db.table_uses_db('credit_admin')}")

    cam = CreditAdminManager()
    case = cam.get(cid)
    if not case:
        print(f"!! {cid} not found in manager (loaded {len(cam.cases)} cases)"); sys.exit(1)
    print(f"loaded {cid}: troops_status={case.get('troops_status')!r} "
          f"cleared={case.get('cleared_for_disbursement')!r} disbursed={case.get('disbursed')!r}")

    # mutate exactly like troops_book (route-level)
    case["troops_status"] = "booked"
    case["cbs_account_no"] = "ECODIAGTEST"

    print("\n-- scalar row that would be written --")
    row = _row_from_case(case)
    for k, v in row.items():
        if k != "data":
            print(f"   {k:24} = {v!r}  ({type(v).__name__})")

    print("\n-- direct upsert with swallow=False (surfaces the hidden error) --")
    try:
        _db_sync_credit_admin_case(case, conflict="update", swallow=False)
        print("   upsert returned OK")
    except Exception as e:
        print(f"   !! UPSERT RAISED: {type(e).__name__}: {e}")

    print("\n-- re-read from PG --")
    try:
        r = db.fetch_one("SELECT data FROM credit_admin WHERE id=%s", (cid,))
        d = r["data"] if isinstance(r.get("data"), dict) else json.loads(r["data"])
        print(f"   PG troops_status now: {d.get('troops_status')!r}  cbs_account_no: {d.get('cbs_account_no')!r}")
    except Exception as e:
        print(f"   !! re-read failed: {e}")

    print("\n-- full save() path (save()-hook, swallow=True) then fresh load --")
    cam.save()
    cam2 = CreditAdminManager()
    print(f"   fresh-load troops_status: {cam2.get(cid).get('troops_status')!r}")


if __name__ == "__main__":
    main()
