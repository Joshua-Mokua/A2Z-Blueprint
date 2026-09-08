#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Let an analyst claim a case that has come back from committee.

A case can only be claimed while its status is 'submitted'. That is right for a
new case. It is wrong for one that has been to a committee and come back for
the next desk: it can be SEEN through the pool, cannot be CLAIMED because of
the status, and so cannot be acted on either, because readiness needs the
claimant.

Brian could see LMS00017 and could do nothing with it. All three doors shut on
the same case.

    python scripts/allow_claim_after_committee.py            # dry run
    python scripts/allow_claim_after_committee.py --apply

Adds the statuses a case carries after a committee has finished with it, so the
next analyst can pick it up the same way they pick up a new one.
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_mutations.py")

OLD = "STATUSES_PERMITTING_ASSIGN: Set[str] = {'submitted'}"
NEW = """# A case can be claimed when it is new, and again once a committee has
# finished with it and it needs the next desk. Only 'submitted' was listed, so
# a case back from committee could be seen in the pool but not picked up - and
# readiness needs the claimant, so it could not be acted on at all.
STATUSES_PERMITTING_ASSIGN: Set[str] = {
    'submitted',
    'referred_to_committee',
    'approved',
    'analyst_confirmed',
}"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "once a committee has" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The status set matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if "'submitted'," not in NEW:
        print("A new case could no longer be claimed.")
        return 1
    # Never let a decided-and-finished case be reopened by a claim.
    for bad in ("disbursed", "declined", "closed", "rejected"):
        if bad in NEW:
            print("A %s case could be claimed, which reopens finished work." % bad)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A case back from committee can be claimed by the next analyst.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_claim")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. Brian claims the case from the Pool, then")
    print("Recommend and Return for rework work as normal.")
    print("")
    print("Approve and Decline will still refuse - /decision needs manager")
    print("authority, and by the bank's own design an analyst recommends while")
    print("a committee decides. If the screen is offering him those buttons,")
    print("that is worth a separate look.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
