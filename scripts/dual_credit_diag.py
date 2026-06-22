#!/usr/bin/env python3
"""dual_credit_diag.py — READ-ONLY. Confirm the credit_watchlist vs watchlist
split: which exists, row counts, and a sample rm_name from each. Writes nothing.

    python scripts\\dual_credit_diag.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    from utils.db import db
    for tbl in ("credit_watchlist", "watchlist"):
        try:
            n = db.fetch_one(f"SELECT COUNT(*) AS n FROM {tbl}", ())
            print(f"{tbl}: EXISTS, {n['n']} rows")
        except Exception as e:
            print(f"{tbl}: NOT readable — {type(e).__name__}: {str(e)[:80]}")
            continue
        try:
            samp = db.fetch_all(
                f"SELECT rm_code, rm_name, branch_name FROM {tbl} "
                f"WHERE rm_name IS NOT NULL LIMIT 5", ())
            for r in samp:
                print(f"    {r.get('rm_code')}  {r.get('rm_name')}  | {r.get('branch_name')}")
        except Exception as e:
            # credit_watchlist keeps identity in risk_data JSONB; try that
            try:
                samp = db.fetch_all(
                    f"SELECT rm_code, rm_name, risk_data FROM {tbl} LIMIT 3", ())
                for r in samp:
                    print(f"    {r.get('rm_code')}  {r.get('rm_name')}  risk_data={str(r.get('risk_data'))[:90]}")
            except Exception as e2:
                print(f"    sample error: {e2}")
    print("\nThe API credit drill reads credit_watchlist FIRST (falls back to "
          "watchlist only if credit_watchlist has no rm_code rows).")


if __name__ == "__main__":
    main()
