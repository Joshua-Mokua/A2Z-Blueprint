#!/usr/bin/env python3
"""wl_table_diag.py — READ-ONLY. Dump the live `watchlist` DB table's columns,
row count, and one sample row, so the remap targets the real schema.
Writes nothing.

    python scripts\\wl_table_diag.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    from utils.db import db

    # columns from information_schema
    try:
        cols = db.fetch_all(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'watchlist' ORDER BY ordinal_position", ())
        print("=== watchlist columns ===")
        for c in cols:
            print(f"  {c['column_name']:<22} {c['data_type']}")
    except Exception as e:
        print(f"[columns error] {e}")

    try:
        n = db.fetch_one("SELECT COUNT(*) AS n FROM watchlist", ())
        print(f"\nrow count: {n['n'] if n else '?'}")
    except Exception as e:
        print(f"[count error] {e}")

    try:
        row = db.fetch_one("SELECT * FROM watchlist LIMIT 1", ())
        print("\n=== sample row ===")
        print(json.dumps({k: str(v)[:80] for k, v in (row or {}).items()}, indent=2))
    except Exception as e:
        print(f"[sample error] {e}")

    # distinct branch + how many rm_codes resolve to live register
    try:
        b = db.fetch_all(
            "SELECT branch_name, COUNT(*) AS n FROM watchlist "
            "GROUP BY branch_name ORDER BY n DESC LIMIT 5", ())
        print("\n=== top branch_name (sanity) ===")
        for r in b:
            print(f"  {r['n']:>5}  {r['branch_name']}")
    except Exception as e:
        print(f"[branch error] {e}")


if __name__ == "__main__":
    main()
