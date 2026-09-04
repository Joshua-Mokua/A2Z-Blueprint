#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Take the backfilled branch off cases that are already past the branch. DRY RUN.

FROM THE BANK (2026-09-04): the department analyst recommends and it
auto-submits to the DEPARTMENT credit committee - that was the behaviour all
morning. Now its members cannot see what she approved, and cases look as though
they have gone back to the branch.

ONE CAUSE, BOTH SYMPTOMS, AND IT IS MINE.

    a case appears in a member's queue when it is at a stage whose JOURNEY
    includes their committee

    _effective_committee_journey drops branch-only committees for a deal that
    is not branch-originated:

        if not _deal_is_branch_originated(deal):
            out = [c for c in out if c not in branch_only]

    _deal_is_branch_originated == the deal has a branch, or an owner at one

backfill_branch_from_validator.py gave 113 branchless deals a branch. It fixed
the unassigned list and unblocked branch validation, which is what was asked
for - and it put the BRANCH COMMITTEE BACK INTO THEIR JOURNEYS. So a case the
department analyst approved now sits with the branch committee, which is why
the department's members see nothing.

    python scripts\undo_backfill_for_cases_past_branch.py
    python scripts\undo_backfill_for_cases_past_branch.py --apply

WHAT IT TOUCHES: only deals the backfill filled (they carry
branch_backfilled_at) AND which are already at a credit-side stage - past the
branch committee. Those are the cases in flight now.

WHAT IT LEAVES: every backfilled deal still at Initiation or Documentation.
Those have not reached a committee, their branch is correct, and it is what
lets that branch's managers validate them - which was the whole point.

IT NEVER TOUCHES A BRANCH SOMEBODY TYPED. Only the backfill's own values.

THIS IS A RETREAT, NOT A DESIGN. The right fix is that a journey should not
send a case back to a committee it has already passed. That is a change worth
making carefully, and not today.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

PAST_BRANCH = (
    "department credit", "credit analysis", "credit administration",
    "credit administarion", "trops", "management credit committee",
    "board credit committee", "legal - security perfection", "offer letter",
    "disbursement",
)


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    pm = PipelineManager()
    deals = pm.deals or []

    filled = [d for d in deals if d.get("branch_backfilled_at")]

    def past_branch(d):
        s = str(d.get("stage", "") or "").strip().lower()
        return bool(s) and any(w in s for w in PAST_BRANCH)

    affected = [d for d in filled if past_branch(d)]
    early = [d for d in filled if not past_branch(d)]

    print("=" * 82)
    print("BACKFILLED DEALS THAT ARE ALREADY PAST THE BRANCH")
    print("=" * 82)
    print("  the backfill filled       %d" % len(filled))
    print("  still early in the flow   %d  (left alone - their branch is right)"
          % len(early))
    print("  PAST THE BRANCH           %d  (the branch goes back off)"
          % len(affected))

    if not affected:
        print("\n  None. The routing problem is not these deals - send me the")
        print("  id of one that went the wrong way and its audit trail.")
        return 0

    print("\n  %-10s %-28s %-30s %s"
          % ("DEAL", "CLIENT", "STAGE", "BRANCH IT WAS GIVEN"))
    for d in affected[:15]:
        print("  %-10s %-28s %-30s %s"
              % (str(d.get("id"))[:10], str(d.get("client_name"))[:28],
                 str(d.get("stage"))[:30], d.get("branch")))
    if len(affected) > 15:
        print("     ... and %d more" % (len(affected) - 15))

    print("\n  AFTER THIS, each of these drops the branch committee from its")
    print("  journey again, and the department committee's members see it.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for d in affected:
        d["branch_before_undo"] = d.get("branch", "")
        d["branch"] = ""
        d["branch_undo_reason"] = (
            "the backfill's branch put the branch committee back into this "
            "case's journey after it had already passed it, hiding it from the "
            "department committee")
    pm._save_deals()
    print("\ntook the branch back off %d deal(s)." % len(affected))
    print("The previous value is kept on each as branch_before_undo, so this")
    print("is reversible when the journey is fixed properly.")

    try:
        from utils.api import _db_sync_pipeline_deal as _sync
        n = 0
        for d in affected:
            try:
                _sync(d)
                n += 1
            except Exception:
                pass
        print("synced %d to the database." % n)
    except Exception as exc:
        print("\n*** COULD NOT SYNC TO THE DATABASE: %s" % str(exc)[:44])
        print("    The files are changed and Postgres is not, so a DB-first")
        print("    read will still route them to the branch and NOTHING WILL")
        print("    HAVE CHANGED for the team. Fix this before telling anybody")
        print("    it is done.")
        return 1

    print("\nRESTART UVICORN, then have a committee member reload.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
