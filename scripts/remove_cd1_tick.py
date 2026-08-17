#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Remove the duplicate tick endpoint. DRY RUN by default.

CD1 added POST /api/lms/applications/{id}/conditions/tick before I had looked
at utils/api_credit_admin_routes.py - which already carries
`conditions/fulfill`, a disbursement gate that Condition Precedent blocks,
collateral, insurance, legal and perfection. Credit admin should tick THERE,
where the rest of the machinery lives.

Two ways to tick a condition is worse than either one alone: the gate watches
one of them, so a case ticked in the wrong place looks satisfied and never
moves. That is the same class of fault as the two deal stores.

WHAT STAYS: the two kinds on the DECISION - pre_approval and
pre_disbursement. Those are the analyst saying at approval time which
conditions are which, and they feed the CALMS classification instead of
somebody re-deciding it later.

    python scripts\\remove_cd1_tick.py
    python scripts\\remove_cd1_tick.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP = ROUTES + ".pre_ticksplit"

START = '@router.post("/applications/{app_id}/conditions/tick")'
END = '@router.post("/applications/{app_id}/hand-to-credit-analyst")'

NOTE = '''# The tick endpoint that stood here is gone. utils/api_credit_admin_routes.py
# already carries `conditions/fulfill` alongside the disbursement gate,
# collateral, insurance and legal - credit admin ticks there. Two ways to tick
# one condition is worse than either: the gate watches one of them, so a case
# ticked in the wrong place looks satisfied and never moves.
#
# The two KINDS on the decision remain - see the approved branch above.


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1
    s = open(ROUTES, encoding="utf-8").read()

    if START not in s:
        print("Nothing to remove - the tick endpoint is not here.")
        return 0
    if s.count(START) != 1 or s.count(END) != 1:
        print("ABORT: anchors matched %d / %d times." % (s.count(START), s.count(END)))
        return 1
    i = s.index(START)
    j = s.index(END, i)
    removed = j - i
    out = s[:i] + NOTE + s[j:]

    # The two kinds must survive.
    for m in ("pre_approval_conditions", "pre_disbursement_conditions"):
        if m not in out:
            print("ABORT: %s would be lost - that is the half worth keeping." % m)
            return 1
    if "conditions/tick" in out:
        print("ABORT: the route is still registered somewhere.")
        return 1
    import ast
    try:
        ast.parse(out)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  removes %d characters; the two condition kinds survive" % removed)

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(ROUTES, BACKUP)
    open(ROUTES, "w", encoding="utf-8", newline="").write(out)
    print("APPLIED %s   (backup: %s)" % (ROUTES, os.path.basename(BACKUP)))
    print("\nCredit admin ticks via POST /api/credit-admin/cases/{id}/conditions/fulfill")
    return 0


if __name__ == "__main__":
    sys.exit(main())
