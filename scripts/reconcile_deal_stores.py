#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Where do the two deal stores disagree? READ ONLY unless --repair.

THE PROBLEM, STATED PLAINLY. Deals live in two places:

    data/pipeline_deals.json     what PipelineManager loads, always
    pipeline_deals (Postgres)    what the API reads, because
                                 _PIPELINE_READ_DB_FIRST is True

Nothing keeps them in step. A write through one path lands in one store, and
whichever screen reads the other simply does not see it. That is the whole
explanation for a count saying 1 and the list beneath it saying nothing, and
for a case appearing in a queue whose Review button opens an empty page.

It is not a mysterious data problem. It is two stores and no reconciliation.

WHAT THIS DOES. Reads both, matches on id, and reports:

    ONLY IN JSON      invisible to every DB-first screen
    ONLY IN THE DB    invisible to anything using PipelineManager
    DIFFERENT         same id, different content - the dangerous one, because
                      both screens show something and they disagree

--repair copies JSON-only deals INTO the database, because the database is the
side the application reads and therefore the side that decides what is true. It
never deletes and never overwrites a row that already exists: a difference is
reported for a person to settle, not resolved by a script picking a winner.

    python scripts\\reconcile_deal_stores.py
    python scripts\\reconcile_deal_stores.py --verbose
    python scripts\\reconcile_deal_stores.py --repair
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

# Fields worth comparing. Timestamps and derived values are excluded - they
# differ for innocent reasons and would bury the differences that matter.
COMPARE = ("stage", "client_name", "deal_value", "staff_code", "branch",
           "manager_validated", "client_type", "product_type", "segment")


def main():
    verbose = "--verbose" in sys.argv
    repair = "--repair" in sys.argv

    try:
        from utils.core import PipelineManager
        import utils.api as A
    except Exception as exc:
        print("ABORT: cannot load the application: %s" % exc)
        return 1

    print("=" * 78)
    print("DEAL STORE RECONCILIATION")
    print("=" * 78)

    pm = PipelineManager()
    j = {str(d.get("id")): d for d in (getattr(pm, "deals", []) or [])}
    print("  JSON  data/pipeline_deals.json   %d deal(s)" % len(j))

    if not A._db_available():
        print("  DB    NOT AVAILABLE")
        print("")
        print("  Every screen is falling back to JSON, so nothing is diverging")
        print("  right now - but _PIPELINE_READ_DB_FIRST is True, so the moment")
        print("  the database answers, the DB becomes what people see.")
        return 0

    try:
        from utils.db import db as _db
        rows = _db.fetch_all("SELECT * FROM pipeline_deals", tuple())
        d = {str(x.get("id")): x for x in
             (A._normalize_db_deal_row(r) for r in A._serialize(rows))}
    except Exception as exc:
        print("  DB    unreadable: %s" % str(exc)[:60])
        return 1
    print("  DB    pipeline_deals             %d deal(s)" % len(d))

    only_json = sorted(set(j) - set(d))
    only_db = sorted(set(d) - set(j))
    both = sorted(set(j) & set(d))

    differing = []
    for did in both:
        diffs = []
        for f in COMPARE:
            a, b = j[did].get(f), d[did].get(f)
            if a is None and b is None:
                continue
            if str(a or "").strip() != str(b or "").strip():
                diffs.append((f, a, b))
        if diffs:
            differing.append((did, diffs))

    print("\n  in both and identical   %d" % (len(both) - len(differing)))
    print("  in both but DIFFERENT   %d" % len(differing))
    print("  only in JSON            %d" % len(only_json))
    print("  only in the DB          %d" % len(only_db))

    if only_json:
        print("\n  ONLY IN JSON - invisible to every DB-first screen:")
        for did in (only_json if verbose else only_json[:10]):
            print("     %-22s %s" % (did, str(j[did].get("client_name"))[:34]))
        if not verbose and len(only_json) > 10:
            print("     ... and %d more (--verbose)" % (len(only_json) - 10))

    if only_db:
        print("\n  ONLY IN THE DB - invisible to anything using PipelineManager:")
        for did in (only_db if verbose else only_db[:10]):
            print("     %-22s %s" % (did, str(d[did].get("client_name"))[:34]))
        if not verbose and len(only_db) > 10:
            print("     ... and %d more (--verbose)" % (len(only_db) - 10))

    if differing:
        print("\n  *** SAME ID, DIFFERENT CONTENT - the dangerous ones. Both")
        print("      screens show something and the two disagree:")
        for did, diffs in (differing if verbose else differing[:8]):
            print("     %s" % did)
            for f, a, b in diffs[:4]:
                print("        %-18s json=%-22r db=%r" % (f, str(a)[:22], str(b)[:22]))
        if not verbose and len(differing) > 8:
            print("     ... and %d more (--verbose)" % (len(differing) - 8))

    if not (only_json or only_db or differing):
        print("\n  The two stores agree.")
        return 0

    print("\n" + "-" * 78)
    print("  WHAT TO DO")
    print("-" * 78)
    if only_json:
        print("  --repair copies the %d JSON-only deal(s) INTO the database."
              % len(only_json))
        print("  The database is what the application reads, so it is the side")
        print("  that decides what is true.")
    if only_db:
        print("  DB-only deals are left alone - they are already what people")
        print("  see. JSON is the stale copy there, not the missing one.")
    if differing:
        print("  DIFFERENCES ARE NOT TOUCHED. A script cannot know whether the")
        print("  JSON stage or the DB stage is the one somebody meant. Settle")
        print("  them by hand, or say which side wins and I will make it a rule.")

    if not repair:
        print("\nREAD ONLY - nothing changed. Re-run with --repair to copy")
        print("JSON-only deals into the database.")
        return 1

    if not only_json:
        print("\nNothing to copy.")
        return 0

    # THE APPLICATION'S OWN WRITE PATH, not a hand-rolled INSERT. Whatever
    # _db_sync_pipeline_deal does about column mapping, types and conflicts is
    # what every endpoint does; a second implementation here would be a third
    # way for the stores to diverge.
    sync = getattr(A, "_db_sync_pipeline_deal", None)
    if sync is None:
        print("\n  _db_sync_pipeline_deal is not available - nothing copied.")
        return 1
    copied, failed = 0, []
    for did in only_json:
        try:
            sync(j[did])
            copied += 1
        except Exception as exc:
            failed.append((did, str(exc)[:50]))
    print("\ncopied %d deal(s) into the database." % copied)
    for did, err in failed[:5]:
        print("   FAILED %-20s %s" % (did, err))
    return 0


if __name__ == "__main__":
    sys.exit(main())
