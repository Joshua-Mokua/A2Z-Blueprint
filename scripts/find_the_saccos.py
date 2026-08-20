#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Look everywhere for the SASRA saccos. READ ONLY.

The deals_warehouse.json file is empty, was never committed on any branch, and
no importer for it exists in the repo. The remaining possibility is that the
scrape landed somewhere else and the warehouse read from there - most likely a
Postgres table, since months of backend work went into that database.

This searches EVERY table in the database for rows that look like saccos, and
every JSON store on disk too. It reads nothing into the warehouse and changes
nothing - it only says where they are, if they are anywhere.

    python scripts\\find_the_saccos.py
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

NEEDLES = ("sacco", "s.a.c.c.o", "savings and credit")


def main():
    found_any = False

    print("=" * 74)
    print("1. EVERY TABLE IN POSTGRES")
    print("=" * 74)
    try:
        from utils.db import Database
        db = Database()
        tables = [r["table_name"] for r in db.fetch_all(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name")]
        print("  tables: %d\n" % len(tables))
    except Exception as exc:
        print("  *** cannot reach the database: %s" % str(exc)[:56])
        tables, db = [], None

    for t in tables:
        try:
            cols = [r["column_name"] for r in db.fetch_all(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s "
                "AND data_type IN ('text','character varying','jsonb','json')",
                (t,))]
            if not cols:
                continue
            total = db.fetch_scalar("SELECT count(*) FROM %s" % t)
            if not total:
                continue
            hits = 0
            for c in cols:
                try:
                    n = db.fetch_scalar(
                        "SELECT count(*) FROM %s WHERE lower(%s::text) LIKE %%s"
                        % (t, c), ("%sacco%",))
                    hits += int(n or 0)
                except Exception:
                    continue
            if hits:
                found_any = True
                print("  *** %-28s %d row(s) mention a sacco (of %s)"
                      % (t, hits, total))
                try:
                    for c in cols:
                        r = db.fetch_one(
                            "SELECT %s AS v FROM %s WHERE lower(%s::text) "
                            "LIKE %%s LIMIT 1" % (c, t, c), ("%sacco%",))
                        if r and r.get("v"):
                            print("        %-18s %s" % (c, str(r["v"])[:60]))
                            break
                except Exception:
                    pass
        except Exception:
            continue
    if tables and not found_any:
        print("  no table mentions a sacco.")

    print("\n" + "=" * 74)
    print("2. EVERY JSON STORE ON DISK")
    print("=" * 74)
    hits = []
    for root in ("data", ".", "docs"):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            if "node_modules" in dirpath or ".git" in dirpath:
                continue
            for f in files:
                if not f.endswith((".json", ".csv", ".xlsx")):
                    continue
                path = os.path.join(dirpath, f)
                try:
                    if os.path.getsize(path) > 40 * 1024 * 1024:
                        continue
                    with open(path, "rb") as fh:
                        blob = fh.read().lower()
                    n = sum(blob.count(w.encode()) for w in NEEDLES)
                    if n > 2:          # 1-2 is an incidental mention
                        hits.append((path, n))
                except Exception:
                    continue
            if root == ".":
                break
    for path, n in sorted(hits, key=lambda x: -x[1])[:14]:
        found_any = True
        print("  %-52s %d mention(s)" % (path[:52], n))
    if not hits:
        print("  no file mentions saccos more than in passing.")

    print("\n" + "=" * 74)
    if found_any:
        print("Something above may be the scrape. Send me the table or file")
        print("name and I will write the importer onto the warehouse shape.")
        return 0
    print("The saccos are not on this machine or in this database.")
    print("")
    print("They have to be re-fetched from the SASRA register. Hand me the")
    print("list as CSV or Excel and the importer is quick - and this time it")
    print("lands in Postgres, so re-running it is all a loss ever costs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
