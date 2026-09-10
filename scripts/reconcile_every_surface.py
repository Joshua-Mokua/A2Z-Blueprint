#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Every screen's numbers, side by side, with the reason each differs.

Five surfaces count the same work and none of them counts it the same way:

    the funnel            deals, by STAGE, from the DATABASE
    Sales Pro             deals, by STAGE, scoped to the caller
    credit analytics      cases, by STATUS, from JSON
    the credit workbench  cases, by STATUS, filtered to committee-recommended
    credit admin          its own cases, separate again

When they disagree, somebody has to explain it to senior management. This puts
them in one place and says why.

    python scripts/reconcile_every_surface.py

Read only.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())


def main():
    from utils.core import PipelineManager
    import utils.api as A

    jd = PipelineManager().deals or []
    print("=" * 96)
    print("WHAT EACH SURFACE COUNTS")
    print("=" * 96)

    # 1. Deals, in each store.
    dbmap = {}
    try:
        from utils.db import db
        with db.connection() as c:
            cur = c.cursor()
            cur.execute("SELECT id, stage FROM pipeline_deals")
            dbmap = {str(r[0]): str(r[1] or "") for r in cur.fetchall()}
    except Exception as exc:
        print("  (no database read: %s)" % str(exc)[:50])

    print("\n  DEALS")
    print("     in JSON            %d" % len(jd))
    print("     in the database    %d" % len(dbmap))
    jstage = Counter(str(d.get("stage") or "(none)") for d in jd)
    dstage = Counter(v or "(none)" for v in dbmap.values())
    drift = [s for s in set(jstage) | set(dstage)
             if jstage.get(s, 0) != dstage.get(s, 0)]
    if drift:
        print("     THEY DISAGREE on %d stage(s):" % len(drift))
        for s in sorted(drift):
            print("        %-40s json=%-4d db=%-4d"
                  % (s[:40], jstage.get(s, 0), dstage.get(s, 0)))
        print("        The funnel reads the database column.")
    else:
        print("     the two stores agree")

    # 2. Cases.
    try:
        from utils.api_lms_routes import _lam
        apps = getattr(_lam(), "apps", []) or []
    except Exception as exc:
        print("\n  (no cases: %s)" % str(exc)[:50])
        apps = []
    st = Counter(str(a.get("status") or "(none)").lower() for a in apps)
    print("\n  CASES  %d" % len(apps))
    for k, n in st.most_common():
        print("     %-40s %d" % (k[:40], n))

    # 3. What credit analytics can show.
    try:
        s = open(os.path.join("utils", "api_lms_routes.py"),
                 encoding="utf-8").read()
        i = s.index("STAGE_ORDER = [")
        block = s[i:s.index("]", i)]
        import re
        known = set(re.findall(r'"([a-z_]+)"', block))
        unmapped = {k: n for k, n in st.items() if k not in known and k != "(none)"}
        print("\n  CREDIT ANALYTICS")
        print("     statuses it knows   %d" % len(known))
        if unmapped:
            print("     CASES IT CANNOT PLACE: %d" % sum(unmapped.values()))
            for k, n in sorted(unmapped.items(), key=lambda x: -x[1]):
                print("        %-40s %d" % (k[:40], n))
            print("     These show as Other / unmapped.")
        else:
            print("     every status in use has a bucket")
    except Exception as exc:
        print("\n  (could not read the analytics map: %s)" % str(exc)[:50])

    # 4. The credit risk workbench.
    ready = [a for a in apps
             if str(a.get("status") or "").lower()
             in ("committee_recommended", "committee_approved")]
    print("\n  CREDIT RISK WORKBENCH  %d" % len(ready))

    # 5. The funnel at Credit Analysis.
    at_ca_db = sum(1 for v in dbmap.values() if v == "Credit Analysis")
    at_ca_js = sum(1 for d in jd if str(d.get("stage") or "") == "Credit Analysis")
    print("\n  FUNNEL at Credit Analysis")
    print("     database  %d      <- what the screen shows" % at_ca_db)
    print("     json      %d" % at_ca_js)

    print("\n" + "=" * 96)
    print("DO THEY AGREE?")
    print("=" * 96)
    print("  workbench %d   funnel %d" % (len(ready), at_ca_db))
    if len(ready) == at_ca_db:
        print("\n  Yes.")
    else:
        print("\n  No. Every case a department committee recommended should be")
        print("  on the workbench, and its deal should be at Credit Analysis.")
        ids = {str(a.get("pipeline_deal_id") or "") for a in ready}
        ca = {k for k, v in dbmap.items() if v == "Credit Analysis"}
        only_wb = [i for i in ids if i and i not in ca]
        only_fn = [i for i in ca if i not in ids]
        if only_wb:
            print("\n  recommended, deal NOT at Credit Analysis: %s"
                  % ", ".join(sorted(only_wb)[:12]))
            print("     align_deals_both_ways.py")
        if only_fn:
            print("\n  deal at Credit Analysis, case NOT recommended: %s"
                  % ", ".join(sorted(only_fn)[:12]))
            print("     which_committees_approved.py - if a department")
            print("     committee did approve these, the case was never marked")
            print("     and mark_already_approved_cases.py is the fix.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
