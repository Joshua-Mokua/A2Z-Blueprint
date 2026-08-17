#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Remove the second _updates assignment that discards the referral.

WHY NOTHING REACHED THE COMMITTEE. Two patches edited the same function on
different days and each introduced its own `_updates = {...}`:

    _updates = {"committee_readiness": readiness}     <- RD1's, set first
    if decision == "ready":
        _updates.update({"status": "referred_to_committee", ...})

    _updates = {"committee_readiness": readiness}     <- RB1's, REASSIGNS
    if decision == "rework":
        _updates.update({"status": "returned", ...})

    lam.update(app_id, _updates)

The second line throws away everything the first block set. So recommending a
case recorded the readiness state, built the referral, and then discarded it
one line later - which is exactly what "it moved but the committee page is
blank" looks like. The rework path was unaffected, because its updates came
after the reassignment.

Neither patch was wrong on its own. The anchor RD1 chose sat above RB1's
assignment rather than below it, and no post-check asked whether `_updates`
was assigned twice.

This removes the SECOND assignment, leaving one dict that both branches add to.

    python scripts\\fix_readiness_overwrite.py
    python scripts\\fix_readiness_overwrite.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP = ROUTES + ".pre_overwritefix"

ASSIGN = '    _updates = {"committee_readiness": readiness}'


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1
    s = open(ROUTES, encoding="utf-8").read()

    i = s.find("def lms_committee_readiness")
    if i < 0:
        print("ABORT: lms_committee_readiness is not in this file.")
        return 1
    j = s.find("\n@router.", i)
    if j < 0:
        j = len(s)
    seg = s[i:j]

    n = seg.count(ASSIGN)
    print("  _updates assignments in the function: %d" % n)
    if n == 1:
        print("\n  Only one. Nothing to remove - the referral is not being")
        print("  discarded here, so a case not reaching the committee has")
        print("  another cause.")
        return 0
    if n != 2:
        print("\nABORT: expected two, found %d. Not repairing blind." % n)
        return 1

    first = seg.index(ASSIGN)
    second = seg.index(ASSIGN, first + len(ASSIGN))
    # Which one comes before the "ready" branch? That is the one to keep.
    ready_at = seg.find('if decision == "ready":')
    if not (first < ready_at < second):
        print("ABORT: the assignments do not sit where expected - the first")
        print("       should precede the ready branch and the second follow it.")
        return 1

    new_seg = seg[:second] + seg[second + len(ASSIGN):].lstrip("\n")
    new_seg = new_seg.replace("\n\n\n", "\n\n")
    if new_seg.count(ASSIGN) != 1:
        print("ABORT: after removal there are %d assignments." % new_seg.count(ASSIGN))
        return 1
    # Both branches must still add to it.
    if 'if decision == "ready":' not in new_seg or 'if decision == "rework":' not in new_seg:
        print("ABORT: one of the two branches was lost.")
        return 1

    out = s[:i] + new_seg + s[j:]
    import ast
    try:
        ast.parse(out)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  one _updates dict, both branches add to it, and it parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(ROUTES, BACKUP)
    open(ROUTES, "w", encoding="utf-8", newline="").write(out)
    print("APPLIED %s   (backup: %s)" % (ROUTES, os.path.basename(BACKUP)))
    print("\nRestart uvicorn. Recommending a case now sends it to the committee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
