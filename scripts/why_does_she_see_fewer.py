#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Why a department analyst sees fewer deals at a stage than exist there.

Eleven consumer deals are at Credit Analysis. Catherine's funnel shows four.
Her scope is her Department: she sees every deal whose owner is in the same
Department string as her, exactly. So the seven she cannot see are owned by
people whose register Department differs from hers - "Consumer" against
"Consumer Banking", or blank.

    python scripts/why_does_she_see_fewer.py --user KE1300 --stage "Credit Analysis"

Read only. It names the owners and their Department strings, so the register
can be corrected rather than guessed at.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())


def main():
    who = stage = ""
    for flag in ("--user", "--stage"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--user":
                    who = sys.argv[i + 1].strip()
                else:
                    stage = sys.argv[i + 1].strip()
    if not who or not stage:
        print('--user KE1300 --stage "Credit Analysis"')
        return 1

    from utils.core import UserManager, PipelineManager
    from utils.api_pipeline_scope import get_staff_roster, get_visible_staff_codes

    users = UserManager().users or {}
    u = next((dict(r, username=l) for l, r in users.items()
              if str(r.get("staff_code", "")).strip().lower() == who.lower()), None)
    if not u:
        print("Nobody has staff code %r." % who)
        return 1

    df = get_staff_roster()
    dept_col = "Department" if "Department" in df.columns else None
    info = {}
    for _i, r in df.iterrows():
        c = str(r.get("Staff Code") or "").strip()
        if c:
            info[c] = {"name": str(r.get("Staff Name") or "").strip(),
                       "dept": str(r.get(dept_col) or "").strip() if dept_col else "",
                       "unit": str(r.get("Unit") or "").strip()}
    mine = info.get(str(u.get("staff_code", "")).strip(), {})
    my_dept = mine.get("dept", "")

    vis = set(get_visible_staff_codes(u) or [])
    deals = [d for d in (PipelineManager().deals or [])
             if str(d.get("stage") or "") == stage]

    print("=" * 92)
    print("WHY %s SEES FEWER AT %s" % (u.get("full_name") or who, stage))
    print("=" * 92)
    print("  her Department   %r" % my_dept)
    print("  her Unit         %r" % mine.get("unit", ""))
    print("  cascade covers   %d staff" % len(vis))
    print("  deals at stage   %d" % len(deals))
    seen = [d for d in deals if str(d.get("staff_code") or "").strip() in vis]
    print("  she can see      %d\n" % len(seen))

    print("  %-9s %-26s %-9s %-22s %-20s %s"
          % ("DEAL", "CLIENT", "OWNER", "OWNER'S DEPARTMENT", "UNIT", "SEES?"))
    depts = Counter()
    for d in deals:
        oc = str(d.get("staff_code") or "").strip()
        oi = info.get(oc, {})
        od = oi.get("dept", "") or "(not in register)"
        depts[od] += 1
        ok = oc in vis
        print("  %-9s %-26s %-9s %-22s %-20s %s"
              % (str(d.get("id"))[:9], str(d.get("client_name"))[:26], oc,
                 od[:22], (oi.get("unit") or "-")[:20], "yes" if ok else "NO"))

    print("\n  owners' departments at this stage:")
    for k, n in depts.most_common():
        mark = "  <-- matches hers" if k == my_dept else ""
        print("     %-30s %d%s" % (k[:30], n, mark))

    print("\n" + "=" * 92)
    print("  The department rule is an EXACT string match. 'Consumer' and")
    print("  'Consumer Banking' are two departments to this code. Every owner")
    print("  she cannot see is under a different string, or none.")
    print("")
    print("  The fix is the register: one spelling for the department, on")
    print("  every consumer officer. That is a data correction, not code.")
    return 1 if len(seen) < len(deals) else 0


if __name__ == "__main__":
    sys.exit(main())
