#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Give the unassigned deals a branch, from where they were validated. DRY RUN.

FROM THE BANK (2026-09-01): "on the unassigned, check the branch where it was
validated in to enforce the branch."

Every deal carries validated_by_code - the manager who validated it. A manager
works in one branch, and the register says which. That is a firmer answer than
the owner's posting, because a deal can be raised by somebody covering and
validated by the branch that actually owns it.

    python scripts\backfill_branch_from_validator.py
    python scripts\backfill_branch_from_validator.py --apply

ORDER OF EVIDENCE, best first:

    1. the branch already on the deal        - left alone, never overwritten
    2. the VALIDATOR's branch                - the bank's instruction
    3. the owner's branch from the register  - where it was never validated

A DEAL WITH NEITHER IS LEFT AS IT IS AND REPORTED. Guessing a branch puts a
case in front of the wrong committee, which is worse than an unassigned deal
somebody can see and fix.

NOTHING ALREADY ASSIGNED IS TOUCHED. This only fills blanks.
"""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())


def _digits(v):
    m = re.match(r"^([A-Za-z]*)0*(\d+)$", str(v or "").strip())
    return ("%s%s" % (m.group(1).upper(), m.group(2))) if m else ""


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    try:
        from utils.api_pipeline_scope import get_staff_roster
        roster = get_staff_roster()
    except Exception as exc:
        print("ABORT: cannot read the staff register: %s" % str(exc)[:60])
        return 1

    branch_of = {}
    for _i, r in roster.iterrows():
        code = str(r.get("Staff Code") or "").strip()
        br = str(r.get("Branch") or r.get("Unit") or "").strip()
        if code and br:
            branch_of[_digits(code)] = br

    pm = PipelineManager()
    deals = pm.deals or []

    have, from_validator, from_owner, stuck = 0, [], [], []
    for d in deals:
        if str(d.get("branch") or "").strip():
            have += 1
            continue
        vcode = _digits(d.get("validated_by_code"))
        ocode = _digits(d.get("staff_code"))
        if vcode and branch_of.get(vcode):
            from_validator.append((d, branch_of[vcode]))
        elif ocode and branch_of.get(ocode):
            from_owner.append((d, branch_of[ocode]))
        else:
            stuck.append(d)

    print("=" * 80)
    print("GIVE THE UNASSIGNED DEALS A BRANCH")
    print("=" * 80)
    print("  deals                     %d" % len(deals))
    print("  already have a branch     %d  (never touched)" % have)
    print("  from the VALIDATOR        %d" % len(from_validator))
    print("  from the owner            %d  (never validated)" % len(from_owner))
    print("  cannot be placed          %d" % len(stuck))

    if from_validator:
        print("\n  FROM THE VALIDATOR - the bank's instruction")
        for d, br in from_validator[:8]:
            print("     %-10s %-28s -> %s" % (str(d.get("id"))[:10],
                                              str(d.get("client_name"))[:28], br))
        if len(from_validator) > 8:
            print("     ... and %d more" % (len(from_validator) - 8))
    if from_owner:
        print("\n  FROM THE OWNER - these were never validated, so there is no")
        print("  validator to ask")
        for d, br in from_owner[:5]:
            print("     %-10s %-28s -> %s" % (str(d.get("id"))[:10],
                                              str(d.get("client_name"))[:28], br))
        if len(from_owner) > 5:
            print("     ... and %d more" % (len(from_owner) - 5))
    if stuck:
        print("\n  LEFT ALONE - neither the validator nor the owner is in the")
        print("  register with a branch. Guessing would put a case before the")
        print("  wrong committee, which is worse than an unassigned deal")
        print("  somebody can see:")
        for d in stuck[:6]:
            print("     %-10s %-28s owner=%s validator=%s"
                  % (str(d.get("id"))[:10], str(d.get("client_name"))[:28],
                     d.get("staff_code"), d.get("validated_by_code") or "-"))
        if len(stuck) > 6:
            print("     ... and %d more" % (len(stuck) - 6))

    todo = from_validator + from_owner
    if not todo:
        print("\n  Nothing to fill.")
        return 0
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    stamp = datetime.now().strftime("%H%M%S")
    for d, br in todo:
        d["branch"] = br
        d["branch_source"] = ("validator" if any(d is x for x, _b in from_validator)
                              else "owner register")
        d["branch_backfilled_at"] = stamp
    pm._save_deals()
    print("\nfilled %d deal(s)." % len(todo))

    synced = 0
    try:
        from utils.api import _db_sync_pipeline_deal as _sync
        for d, _b in todo:
            try:
                _sync(d)
                synced += 1
            except Exception:
                pass
        print("synced %d to the database." % synced)
    except Exception as exc:
        print("*** could not sync to the database: %s" % str(exc)[:44])
        print("    The JSON is filled but Postgres is not, so a DB-first read")
        print("    will still show them unassigned. Fix before the team looks.")
        return 1

    print("\nRESTART UVICORN, then:  python scripts\\audit_200.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
