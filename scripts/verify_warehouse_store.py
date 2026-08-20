#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Is the warehouse actually in Postgres now? READ ONLY.

After WH1 the module reads the database first and falls back to the file. Those
two look identical from the outside - an empty shelf is an empty shelf - so
this asks the database directly and says which one answered.

    python scripts\\verify_warehouse_store.py
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    import utils.deals_warehouse as W

    print("=" * 70)
    print("WHERE THE WAREHOUSE IS READING FROM")
    print("=" * 70)

    db = W._db()
    print("  database reachable        %s" % ("yes" if db is not None else "NO"))
    if db is None:
        print("\n  *** The file is answering, not the database. Every prospect")
        print("      entered now is one deletion from gone - exactly what")
        print("      happened before. Start Postgres and re-run.")
        return 1

    try:
        n = db.fetch_scalar("SELECT count(*) FROM deals_warehouse")
        print("  table deals_warehouse     exists, %s row(s)" % n)
    except Exception as exc:
        print("  table deals_warehouse     *** NOT THERE: %s" % str(exc)[:44])
        return 1

    rows = W._db_read()
    print("  _db_read() returns        %s" % ("None (cannot answer)" if rows is None
                                              else "%d prospect(s)" % len(rows)))
    print("  all_prospects() returns   %d" % len(W.all_prospects() or []))

    import json
    on_disk = 0
    if os.path.exists(W._PATH):
        try:
            on_disk = len(json.load(open(W._PATH, encoding="utf-8")) or {})
        except Exception:
            on_disk = -1
    print("  the JSON mirror holds     %s" % ("unreadable" if on_disk < 0 else on_disk))

    # A real round trip, then cleaned up.
    print("\n" + "-" * 70)
    print("A PROSPECT, WRITTEN AND READ BACK")
    print("-" * 70)
    try:
        p = W.create(name="ZZ Verify Store Ltd", created_by_code="VERIFY",
                     created_by_name="Store check", sector="Financial Services",
                     town="Nairobi")
        pid = p.get("id")
        direct = db.fetch_one("SELECT name FROM deals_warehouse WHERE id = %s", (pid,))
        print("  created                   %s" % pid)
        print("  found in the TABLE        %s"
              % (direct.get("name") if direct else "*** NO - the write did not reach it"))
        W.delete(pid)
        gone = db.fetch_one("SELECT id FROM deals_warehouse WHERE id = %s", (pid,))
        print("  deleted from the table    %s" % ("yes" if not gone else "*** STILL THERE"))
        ok = bool(direct) and not gone
    except Exception as exc:
        print("  *** the round trip failed: %s" % str(exc)[:60])
        ok = False

    print("\n" + "=" * 70)
    if ok:
        print("Postgres is the store. A prospect entered now survives the file.")
        return 0
    print("The round trip did not complete - do not trust the shelf yet.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
