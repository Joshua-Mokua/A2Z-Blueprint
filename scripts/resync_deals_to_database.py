#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Push the JSON store's deals into the database.

The funnel reads the database. The scripts write JSON and sync each deal
separately, and a sync that fails is only a warning in the log - so JSON moves
and the funnel does not.

    python scripts/resync_deals_to_database.py
    python scripts/resync_deals_to_database.py --apply

Read only without --apply. It never deletes; it writes what JSON holds.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    import utils.api as A

    deals = PipelineManager().deals or []
    try:
        from utils.db import db
        with db.connection() as c:
            cur = c.cursor()
            cur.execute("SELECT id, stage FROM pipeline_deals")
            dmap = {str(r[0]): str(r[1] or "") for r in cur.fetchall()}
    except Exception as exc:
        print("Could not read pipeline_deals: %s" % str(exc)[:60])
        return 1

    stale = [d for d in deals
             if str(d.get("id")) not in dmap
             or dmap.get(str(d.get("id"))) != str(d.get("stage") or "")]

    print("=" * 76)
    print("DEALS THE DATABASE HAS NOT CAUGHT UP WITH")
    print("=" * 76)
    print("  deals in JSON     %d" % len(deals))
    print("  in the database   %d" % len(dmap))
    print("  to push           %d\n" % len(stale))
    if not stale:
        print("  The database is current.")
        return 0

    for d in stale[:20]:
        print("  %-10s %-34s db has %s"
              % (str(d.get("id")), str(d.get("stage"))[:34],
                 dmap.get(str(d.get("id")), "(missing)")[:28]))
    if len(stale) > 20:
        print("     ... and %d more" % (len(stale) - 20))

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    ok = fail = 0
    errs = []
    for d in stale:
        try:
            A._db_sync_pipeline_deal(d)
            ok += 1
        except Exception as exc:
            fail += 1
            if len(errs) < 5:
                errs.append((str(d.get("id")), str(exc)[:80]))
    print("\npushed %d, failed %d" % (ok, fail))
    if errs:
        print("\n  The first failures - these are why the funnel was static:")
        for i, e in errs:
            print("     %-10s %s" % (i, e))
        print("\n  Fix the cause. Pushing again will not help until it is fixed.")
        return 1
    print("\nRestart uvicorn and hard-refresh. The funnel should now show what")
    print("the screens have been showing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
