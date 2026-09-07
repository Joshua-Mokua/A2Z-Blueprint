#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Put an approved case back in the pool so the next desk can pick it up.

A case stays assigned to the analyst who worked it. Once a committee has
approved it, that assignment is what keeps it out of credit risk's queue - an
assigned case shows under its assignee's My cases and nowhere else.

    python scripts/release_case_to_pool.py
    python scripts/release_case_to_pool.py --app LMS00002 --apply

Read only without --apply.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

# Statuses that mean the segment analyst's part is done.
DONE_WITH_ANALYST = ("approved", "referred_to_committee", "recommended",
                     "ready_for_committee", "committee_approved")


def main():
    apply = "--apply" in sys.argv
    only = ""
    if "--app" in sys.argv:
        i = sys.argv.index("--app")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1].strip()

    from utils.api_lms_routes import _lam
    lam = _lam()
    apps = getattr(lam, "apps", []) or []

    def assignee(a):
        an = a.get("analyst") or {}
        if not isinstance(an, dict):
            return "", ""
        return (str(an.get("code", "") or "").strip(),
                str(an.get("name", "") or "").strip())

    candidates = []
    for a in apps:
        if only and str(a.get("id")) != only:
            continue
        code, name = assignee(a)
        status = str(a.get("status") or "").lower()
        if code and any(w in status for w in DONE_WITH_ANALYST):
            candidates.append((a, code, name, status))

    print("=" * 84)
    print("CASES STILL HELD BY AN ANALYST AFTER THEIR PART IS DONE")
    print("=" * 84)
    print("  credit cases  %d" % len(apps))
    print("  held          %d\n" % len(candidates))

    if not candidates:
        print("  Nothing to release.")
        if only:
            a = next((x for x in apps if str(x.get("id")) == only), None)
            if a:
                code, name = assignee(a)
                print("\n  %s is at %r, assigned to %s."
                      % (only, a.get("status"), name or code or "nobody"))
                print("  It is released only once a committee or the analyst")
                print("  has finished with it.")
        return 0

    print("  %-12s %-28s %-22s %s"
          % ("CASE", "CLIENT", "STATUS", "HELD BY"))
    for a, code, name, status in candidates:
        print("  %-12s %-28s %-22s %s"
              % (str(a.get("id"))[:12], str(a.get("client_name"))[:28],
                 str(a.get("status"))[:22], name or code))

    print("\n  Releasing puts each back in the pool. It does not decide")
    print("  anything, does not change the status, and does not pick the next")
    print("  person - whoever should work it next claims it themselves.")

    if not apply:
        print("\nDry run. Re-run with --apply, or name one with --app.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    n = 0
    for a, code, name, _s in candidates:
        a["analyst_before_release"] = {"code": code, "name": name}
        a["analyst"] = {}
        a["released_at"] = stamp
        a["released_reason"] = ("the analyst's part was done and the "
                                "assignment was keeping it out of the next "
                                "desk's queue")
        n += 1
        print("  released %s from %s" % (a.get("id"), name or code))
    try:
        lam.save()
    except Exception:
        try:
            lam._save()
        except Exception as exc:
            print("\nCould not save: %s" % str(exc)[:60])
            return 1
    print("\nReleased %d. Restart uvicorn." % n)
    print("The previous assignee is kept on each as analyst_before_release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
