#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Take a picture of the whole system, so a change can be checked against it.

Run it BEFORE a change and AFTER. Diff the two. Anything that moved and should
not have is visible immediately, rather than three days later when somebody at
a branch reports it.

    python scripts/snapshot_state.py before.json
    ... make the change ...
    python scripts/snapshot_state.py after.json
    python scripts/snapshot_state.py --compare before.json after.json

Read only. It writes only the snapshot file you name.
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())


def take():
    snap = {}
    try:
        from utils.core import PipelineManager
        deals = PipelineManager().deals or []
        snap["deals"] = len(deals)
        snap["by_stage"] = dict(Counter(str(d.get("stage") or "(none)")
                                        for d in deals))
        snap["with_case"] = sum(1 for d in deals
                                if str(d.get("lms_application_id") or "").strip())
        snap["no_branch"] = sum(1 for d in deals
                                if not str(d.get("branch") or "").strip())
        def val(d):
            try:
                return float(d.get("amount_kes") or d.get("deal_value") or 0)
            except (TypeError, ValueError):
                return 0.0
        snap["value"] = round(sum(val(d) for d in deals), 2)
        snap["value_by_stage"] = {k: round(v, 2) for k, v in
                                  Counter({}).items()}
        vbs = {}
        for d in deals:
            vbs[str(d.get("stage") or "(none)")] = \
                vbs.get(str(d.get("stage") or "(none)"), 0.0) + val(d)
        snap["value_by_stage"] = {k: round(v, 2) for k, v in vbs.items()}
    except Exception as exc:
        snap["deals_error"] = str(exc)[:80]

    try:
        from utils.api_lms_routes import _lam
        apps = getattr(_lam(), "apps", []) or []
        snap["cases"] = len(apps)
        snap["by_status"] = dict(Counter(str(a.get("status") or "(none)")
                                         for a in apps))
        snap["unassigned"] = sum(
            1 for a in apps
            if not str(((a.get("analyst") or {}) if isinstance(a.get("analyst"), dict)
                        else {}).get("code", "") or "").strip())
    except Exception as exc:
        snap["cases_error"] = str(exc)[:80]

    try:
        from utils.core import UserManager
        users = [v for v in (UserManager().users or {}).values() if v.get("active")]
        snap["active_staff"] = len(users)
        snap["roles"] = len({str(u.get("role") or "") for u in users})
    except Exception as exc:
        snap["users_error"] = str(exc)[:80]

    try:
        cfg = json.load(open(os.path.join("data", "lms_config.json"),
                             encoding="utf-8"))
        pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []
        snap["committees"] = len(pal)
        snap["seated"] = sum(1 for c in pal
                             if [m for m in (c.get("members") or [])
                                 if isinstance(m, dict)
                                 and str(m.get("staff_code", "")).strip()])
        pv = cfg.get("pool_visibility") or {}
        snap["pool_roles"] = sorted(str(r) for r in (pv.get("roles") or []))
        snap["pool_statuses"] = sorted(str(r) for r in (pv.get("statuses") or []))
        snap["role_statuses"] = {str(k): sorted(str(x) for x in v)
                                 for k, v in (pv.get("role_statuses") or {}).items()}
        lib = cfg.get("condition_library") or {}
        snap["conditions"] = (len(lib.get("pre_approval") or [])
                              + len(lib.get("pre_disbursement") or []))
    except Exception as exc:
        snap["config_error"] = str(exc)[:80]

    try:
        from utils.core import CreditAdminManager
        snap["credit_admin_cases"] = len(getattr(CreditAdminManager(), "cases", []) or [])
    except Exception as exc:
        snap["ca_error"] = str(exc)[:80]

    return snap


def compare(a_path, b_path):
    a = json.load(open(a_path, encoding="utf-8"))
    b = json.load(open(b_path, encoding="utf-8"))
    keys = sorted(set(a) | set(b))
    print("=" * 84)
    print("WHAT MOVED")
    print("=" * 84)
    moved = 0
    for k in keys:
        av, bv = a.get(k), b.get(k)
        if av == bv:
            continue
        moved += 1
        if isinstance(av, dict) and isinstance(bv, dict):
            print("\n  %s" % k)
            for kk in sorted(set(av) | set(bv)):
                if av.get(kk) != bv.get(kk):
                    print("     %-36s %s -> %s"
                          % (str(kk)[:36], av.get(kk), bv.get(kk)))
        else:
            print("  %-24s %s -> %s" % (k, av, bv))
    print("\n" + "=" * 84)
    if not moved:
        print("Nothing moved.")
        print("=" * 84)
        return 0
    print("%d thing(s) moved. Every one should be something you meant." % moved)
    print("=" * 84)
    print("  A count that changed and should not have is the damage, and it is")
    print("  cheaper to see it here than at a branch.")
    return 1


def main():
    if "--compare" in sys.argv:
        i = sys.argv.index("--compare")
        if i + 2 >= len(sys.argv):
            print("--compare before.json after.json")
            return 1
        return compare(sys.argv[i + 1], sys.argv[i + 2])

    out = ""
    for a in sys.argv[1:]:
        if not a.startswith("-"):
            out = a
            break
    snap = take()

    print("=" * 72)
    print("SNAPSHOT")
    print("=" * 72)
    for k in ("deals", "with_case", "no_branch", "cases", "unassigned",
              "credit_admin_cases", "active_staff", "committees", "seated",
              "conditions"):
        if k in snap:
            print("  %-22s %s" % (k, snap[k]))
    if snap.get("by_stage"):
        print("\n  by stage")
        for k, v in sorted(snap["by_stage"].items(), key=lambda x: -x[1]):
            print("     %-40s %d" % (k[:40], v))
    if snap.get("by_status"):
        print("\n  by case status")
        for k, v in sorted(snap["by_status"].items(), key=lambda x: -x[1]):
            print("     %-40s %d" % (k[:40], v))

    if out:
        json.dump(snap, open(out, "w", encoding="utf-8"), indent=2, sort_keys=True)
        print("\nWritten to %s" % out)
        print("Make the change, take another, then:")
        print("   python scripts/snapshot_state.py --compare %s after.json" % out)
    else:
        print("\nName a file to save it: snapshot_state.py before.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
