#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Give back the branch that deals lost. DRY RUN by default.

WHY THESE DEALS ARE BROKEN. Until MD1 (2026-08-13) the database write carried
only thirteen named fields, and `branch` was not among them. Deals are read
DB-first, so every deal that went through Postgres came back with no branch.

WHAT THAT COSTS. A deal without a branch is not branch-originated, so
_branch_committee_code_for finds nothing, no branch committee is substituted
into its journey, and the case NEVER REACHES A COMMITTEE. The queue diagnostic
says it plainly:

    out  D2989  Acme Traders  journey [] does not include any of this
                              person's committees

MD1 stopped the leak. It does not refill what already drained, which is what
this does.

WHERE THE VALUE COMES FROM, in order:

    1. THE JSON STORE, if that copy still has it. That is the deal's own
       answer, written before the field was lost.
    2. THE OWNER'S UNIT in the staff register. An RM at Fortis raises Fortis
       deals; this is a sound inference, not a guess.
    3. NOTHING. Reported, not invented - a deal whose owner is not in the
       register has no defensible branch and somebody must say what it is.

CLIENT TYPE IS RESTORED THE SAME WAY, from the JSON copy only. There is no
second source for it, and inferring a customer's segment from who owns the deal
would be inventing a fact about the customer.

    python scripts\\backfill_deal_branch.py
    python scripts\\backfill_deal_branch.py --apply
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv

    try:
        from utils.core import PipelineManager
        import utils.api as A
    except Exception as exc:
        print("ABORT: cannot load the application: %s" % exc)
        return 1

    print("=" * 78)
    print("BRANCH BACKFILL")
    print("=" * 78)

    pm = PipelineManager()
    json_by_id = {str(d.get("id")): d for d in (getattr(pm, "deals", []) or [])}
    print("  JSON store    %d deal(s)" % len(json_by_id))

    if not A._db_available():
        print("  DB            not available")
        print("")
        print("  Nothing to backfill INTO - every screen is reading the JSON")
        print("  store, which still has these values. Start Postgres and run")
        print("  this again.")
        return 0

    from utils.db import db as _db
    rows = _db.fetch_all("SELECT * FROM pipeline_deals", tuple())
    db_deals = [A._normalize_db_deal_row(r) for r in A._serialize(rows)]
    print("  database      %d deal(s)" % len(db_deals))

    # The register, for the owner's unit.
    unit_by_code = {}
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        for _i, r in df.iterrows():
            code = str(r.get("Staff Code") or "").strip()
            _raw_unit = r.get("Unit")
            # A real NaN (pandas float) is truthy in Python, so `or ""` never
            # fires and str(nan) leaks the literal text "nan" as a branch -
            # worse than blank, since it looks resolved but matches nothing.
            unit = "" if pd.isna(_raw_unit) else str(_raw_unit or "").strip()
            if code and unit:
                unit_by_code[code] = unit
    except Exception as exc:
        print("  (register unreadable: %s)" % str(exc)[:50])

    from_json, from_owner, stuck = [], [], []
    for d in db_deals:
        did = str(d.get("id"))
        if str(d.get("branch") or "").strip():
            continue
        j = json_by_id.get(did) or {}
        jb = str(j.get("branch") or "").strip()
        ct = str(j.get("client_type") or "").strip()
        if jb:
            from_json.append((did, jb, ct, d))
            continue
        owner = str(d.get("staff_code") or j.get("staff_code") or "").strip()
        ob = unit_by_code.get(owner, "")
        if ob:
            from_owner.append((did, ob, ct, d))
        else:
            stuck.append((did, owner, str(d.get("client_name") or "")))

    total = len(from_json) + len(from_owner) + len(stuck)
    print("\n  deals with NO branch: %d" % total)
    if not total:
        print("  Nothing to do.")
        return 0

    if from_json:
        print("\n  FROM THE JSON COPY (%d) - the deal's own answer:" % len(from_json))
        for did, b, ct, _d in from_json[:10]:
            print("     %-10s -> %-22s %s" % (did, b, ("client_type " + ct) if ct else ""))
        if len(from_json) > 10:
            print("     ... and %d more" % (len(from_json) - 10))

    if from_owner:
        print("\n  FROM THE OWNER'S UNIT (%d) - inferred, and sound:" % len(from_owner))
        for did, b, _ct, d in from_owner[:10]:
            print("     %-10s -> %-22s owner %s" % (did, b, d.get("staff_code")))
        if len(from_owner) > 10:
            print("     ... and %d more" % (len(from_owner) - 10))

    if stuck:
        print("\n  *** CANNOT BE ANSWERED (%d). No JSON copy, and the owner is" % len(stuck))
        print("      not in the register - so there is no defensible branch:")
        for did, owner, name in stuck[:10]:
            print("     %-10s %-26s owner %r" % (did, name[:26], owner))
        print("")
        print("      These need somebody to say which branch they belong to.")
        print("      Guessing would put a case in front of the wrong committee.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    fixed = 0
    for did, b, ct, d in from_json + from_owner:
        rec = dict(d)
        rec["branch"] = b
        if ct and not str(rec.get("client_type") or "").strip():
            rec["client_type"] = ct
        # Through the application's own write path, so whatever it does about
        # columns and metadata is what every endpoint does.
        try:
            A._db_sync_pipeline_deal(rec)
            fixed += 1
        except Exception as exc:
            print("   FAILED %-10s %s" % (did, str(exc)[:50]))

    print("\nrestored a branch on %d deal(s)." % fixed)
    print("Those cases can now resolve a branch committee. Check one:")
    print("  python scripts\\diag_committee_queue.py --user <a member> --deal <id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
