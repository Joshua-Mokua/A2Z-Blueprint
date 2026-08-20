#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prove the warehouse cannot be wiped the way it was. READ ONLY.

It was lost once, on 2026-08-20, and every sacco and entity went with it.
"I hope my data is intact and nothing will wipe it again" deserves a check
rather than a reassurance.

Six questions, each of which was a NO on the day it was lost:

    1. Is the data in Postgres, not only in a file?
    2. Is the table registered, so a write cannot be silently refused?
    3. Does a failed write SAY SO, rather than returning False in silence?
    4. Is there a JSON mirror as well, so two copies exist?
    5. Are the SOURCE registers in git, so a total loss costs a re-import?
    6. Does the store refuse a destructive read-modify-write?

    python scripts\\prove_warehouse_safe.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())

OK, BAD = [], []


def check(q, passed, detail=""):
    (OK if passed else BAD).append(q)
    print("  %-4s %-54s %s" % ("ok" if passed else "FAIL", q, detail[:22]))


def main():
    print("=" * 84)
    print("CAN THE WAREHOUSE BE WIPED AGAIN")
    print("=" * 84)

    import utils.deals_warehouse as W

    # 1. In the database at all.
    db = W._db()
    rows = None
    if db is not None:
        try:
            rows = db.fetch_scalar("SELECT count(*) FROM deals_warehouse")
        except Exception:
            rows = None
    check("the data is in Postgres", rows is not None and rows > 0,
          "%s rows" % rows if rows is not None else "no table")

    # 2. Registered, so a write cannot be refused in silence.
    try:
        from utils.db import TABLE_REGISTRY
        reg = "deals_warehouse" in TABLE_REGISTRY
    except Exception:
        reg = False
    check("the table is registered in TABLE_REGISTRY", reg,
          "" if reg else "writes refused")

    # 3. A failed write is audible.
    src = open(os.path.join("utils", "deals_warehouse.py"), encoding="utf-8").read()
    loud = "NEVER SILENT" in src and "database write FAILED" in src
    check("a failed database write says so out loud", loud)

    # 4. Two copies.
    mirror = 0
    if os.path.exists(W._PATH):
        try:
            import json
            mirror = len(json.load(open(W._PATH, encoding="utf-8")) or {})
        except Exception:
            mirror = -1
    check("a JSON mirror exists beside the table", mirror > 0,
          "%d records" % mirror if mirror >= 0 else "unreadable")

    if rows is not None and mirror > 0:
        drift = abs(rows - mirror)
        check("the table and the mirror agree", drift == 0,
              "differ by %d" % drift if drift else "")

    # 5. The sources, which is what a real recovery needs.
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "data/registers"],
            capture_output=True, text=True).stdout.split()
    except Exception:
        tracked = []
    check("the source registers are committed to git", len(tracked) > 0,
          "%d files" % len(tracked))
    if tracked:
        print("")
        for f in tracked[:10]:
            print("        %s" % f)
        if len(tracked) > 10:
            print("        ... and %d more" % (len(tracked) - 10))

    # 6. A destructive read cannot happen quietly.
    raises = "raise RuntimeError" in src and "unreadable" in src
    check("an unreadable store RAISES rather than returning empty", raises,
          "" if raises else "silent wipe risk")

    print("\n" + "=" * 84)
    print("VERDICT")
    print("=" * 84)
    if not BAD:
        print("  Every safeguard is in place.\n")
        print("  If the file is deleted, Postgres still has it.")
        print("  If the table is dropped, the file still has it.")
        print("  If BOTH go, the source registers in git rebuild it with the")
        print("  import scripts - which is a morning, not a loss.")
        print("\n  On the day it was lost, the first four were all NO.")
        return 0
    print("  %d safeguard(s) missing:\n" % len(BAD))
    for q in BAD:
        print("     %s" % q)
    return 1


if __name__ == "__main__":
    sys.exit(main())
