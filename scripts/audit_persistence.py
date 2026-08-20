#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Which stores are actually in Postgres, and which are one file deletion from
gone. READ ONLY.

RULING, stated repeatedly and not honoured everywhere: "we are to be fully
PostgreSQL, JSON is just backup. This is a bank system."

The deals warehouse was lost on 2026-08-20. Every sacco and entity the team had
entered went with it. There was nothing to recover from: deals_warehouse.py
touches no database, the file was never tracked in git, and it was not
gitignored either - so it existed in exactly one place, on one disk, and then
it did not.

That is not a mistake about one store. It is a gap between what the system is
supposed to be and what parts of it actually are, and the only honest way to
close it is to say plainly which parts are which.

For every JSON store this reports:

    IN POSTGRES     a table exists AND the code writes to it
    MIRRORED        written to Postgres, but read from JSON first
    JSON ONLY       no database at all - one deletion from gone
    tracked in git  a poor backup, but a backup

    python scripts\\audit_persistence.py
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.getcwd())


def main():
    data_dir = "data"
    if not os.path.isdir(data_dir):
        print("ABORT: no data/ directory - run from the project root.")
        return 1

    stores = sorted(f for f in os.listdir(data_dir)
                    if f.endswith(".json") and not f.startswith("."))
    if not stores:
        print("No JSON stores found.")
        return 0

    # Everything the utils layer says, in one string - cheaper than reopening
    # eight files per store.
    src = []
    for root, _dirs, files in os.walk("utils"):
        for f in files:
            if f.endswith(".py"):
                try:
                    src.append(open(os.path.join(root, f), encoding="utf-8").read())
                except Exception:
                    pass
    blob = "\n".join(src)

    # Which tables exist, if we can reach the database at all.
    tables = set()
    reachable = False
    try:
        from utils.db import get_conn  # type: ignore
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public'")
                tables = {r[0] for r in cur.fetchall()}
        reachable = True
    except Exception:
        try:
            import utils.api as A
            reachable = bool(A._db_available())
        except Exception:
            reachable = False

    try:
        tracked = set(subprocess.run(
            ["git", "ls-tree", "--name-only", "HEAD", "data/"],
            capture_output=True, text=True).stdout.split())
    except Exception:
        tracked = set()

    print("=" * 84)
    print("WHERE THE BANK'S DATA ACTUALLY LIVES")
    print("=" * 84)
    print("  database reachable from here: %s" % ("yes" if reachable else "no"))
    if tables:
        print("  tables in public schema:      %d" % len(tables))
    print("")
    print("  %-32s %-10s %-14s %s" % ("STORE", "SIZE", "PERSISTENCE", "IN GIT"))

    at_risk = []
    for f in stores:
        path = os.path.join(data_dir, f)
        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0
        stem = f[:-5]

        # Does anything write this store to the database?
        near = []
        for m in re.finditer(re.escape(f), blob):
            near.append(blob[max(0, m.start() - 1500):m.start() + 1500])
        window = "\n".join(near)
        writes = bool(re.search(r"(INSERT|UPDATE|_db_sync|upsert|execute\()",
                                window, re.I)) if window else False
        # A table whose name resembles the store.
        guess = {t for t in tables
                 if stem.replace("_", "") in t.replace("_", "")
                 or t.replace("_", "") in stem.replace("_", "")}
        has_table = bool(guess)

        if writes and has_table:
            state = "IN POSTGRES"
        elif writes:
            state = "writes, no table"
        elif has_table:
            state = "table, no write"
        else:
            state = "*** JSON ONLY"

        in_git = "yes" if ("data/" + f) in tracked else "no"
        if state.startswith("***") and in_git == "no":
            at_risk.append((f, size))
        print("  %-32s %-10s %-14s %s"
              % (f[:32], "%d B" % size if size < 10240 else "%d KB" % (size // 1024),
                 state, in_git))

    print("\n" + "=" * 84)
    print("VERDICT")
    print("=" * 84)
    print("  stores examined      %d" % len(stores))
    print("  ONE DELETION FROM GONE   %d" % len(at_risk))
    if at_risk:
        print("\n  No database, and not in git. If the file goes, the data is")
        print("  gone - which is what happened to the deals warehouse:\n")
        for f, size in at_risk:
            print("     %-34s %s" % (f, "%d B" % size if size < 10240
                                     else "%d KB" % (size // 1024)))
        print("\n  Each of these needs either a table and a sync, or - if the")
        print("  data is genuinely disposable - saying so in writing, so the")
        print("  next person does not assume it is safe.")
    else:
        print("\n  Every store is either in Postgres or tracked in git.")

    if not reachable:
        print("\n  *** The database was not reachable, so 'table' could not be")
        print("      confirmed for anything. Re-run with Postgres up before")
        print("      trusting the middle column.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
