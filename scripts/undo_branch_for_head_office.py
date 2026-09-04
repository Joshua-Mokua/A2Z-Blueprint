#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Take back the branch the backfill gave a HEAD OFFICE deal. DRY RUN by default.

FROM THE BANK (2026-09-04): "the department credit analyst says the cases she
is approving are going back to the branch, while we said they should progress
to the department credit committee."

WHAT HAPPENED, AND IT IS MINE. backfill_branch_from_validator.py gave 113
branchless deals a branch, taken from the validator or the owner. That fixed
the unassigned list and unblocked branch validation, which is what was asked
for.

A BRANCH FIELD ALSO DECIDES ROUTING, and nobody said so:

    _deal_is_branch_originated(deal) == the deal has a branch, or an owner at
                                       one
    the advance path SKIPS the Branch Credit Committee for a deal that is not
    branch-originated

Before the backfill those deals had no branch, so the branch committee was
skipped and they went straight to the department committee - the behaviour the
bank describes as working. Afterwards they have one, so they route through the
branch committee first.

    python scripts\undo_branch_for_head_office.py
    python scripts\undo_branch_for_head_office.py --apply

WHAT THIS TAKES BACK: only the branch the BACKFILL wrote, and only where it
wrote "Head Office" or an equivalent - a deal owned from head office is not a
branch deal, and giving it one sent it to a committee that does not serve it.

WHAT IT LEAVES: every branch the backfill wrote that names a REAL branch -
Kisumu, Kisii, Nyeri. Those deals belong to those branches, they route through
those branch committees correctly, and taking their branch away would
re-break validation for the people who just got it.

IT ONLY TOUCHES WHAT THE BACKFILL WROTE. Each deal it filled carries
branch_backfilled_at; a branch somebody entered by hand is never removed.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

# Head office is not a branch, whatever the register calls it.
NOT_A_BRANCH = ("head office", "headoffice", "ho", "hq", "head-office")


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    pm = PipelineManager()
    deals = pm.deals or []

    filled = [d for d in deals if d.get("branch_backfilled_at")]
    ho = [d for d in filled
          if str(d.get("branch", "") or "").strip().lower() in NOT_A_BRANCH]
    real = [d for d in filled if d not in ho]

    print("=" * 80)
    print("BRANCHES THE BACKFILL WROTE")
    print("=" * 80)
    print("  deals it filled           %d" % len(filled))
    print("  a REAL branch             %d  (left alone)" % len(real))
    print("  head office               %d  (to take back)" % len(ho))

    if real:
        from collections import Counter
        c = Counter(str(d.get("branch")) for d in real)
        print("\n  LEFT ALONE - these belong where they are, and their branch")
        print("  is what lets that branch's managers validate them:")
        for b, n in c.most_common(8):
            print("     %-28s %d" % (b[:28], n))

    if not ho:
        print("\n  Nothing to take back. The routing change is not head office")
        print("  deals - send me a deal id that went the wrong way.")
        return 0

    print("\n  TO TAKE BACK - a head-office deal is not a branch deal, and a")
    print("  branch it never had sends it to a committee that does not serve")
    print("  it:")
    for d in ho[:12]:
        print("     %-10s %-30s owner=%s"
              % (str(d.get("id"))[:10], str(d.get("client_name"))[:30],
                 d.get("staff_code")))
    if len(ho) > 12:
        print("     ... and %d more" % (len(ho) - 12))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        print("\n  AFTER THIS, those deals skip the branch committee again and")
        print("  go to the department committee, as they did before.")
        return 0

    for d in ho:
        d["branch"] = ""
        d["branch_removed_reason"] = ("head office is not a branch; the "
                                      "backfill's value sent this to a branch "
                                      "committee that does not serve it")
    pm._save_deals()
    print("\ntook back %d branch(es)." % len(ho))

    try:
        from utils.api import _db_sync_pipeline_deal as _sync
        n = 0
        for d in ho:
            try:
                _sync(d)
                n += 1
            except Exception:
                pass
        print("synced %d to the database." % n)
    except Exception as exc:
        print("*** could not sync to the database: %s" % str(exc)[:44])
        print("    The JSON is changed but Postgres is not - a DB-first read")
        print("    will still route them to the branch. Fix before the team")
        print("    works these cases.")
        return 1

    print("\nRESTART UVICORN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
