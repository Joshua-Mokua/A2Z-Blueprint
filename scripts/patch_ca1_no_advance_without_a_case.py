#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A committee cannot advance a deal that never reached credit.

D0644: a branch committee voted on a deal that had not been submitted. The
approval auto-advanced it from Documentation to Branch Credit Committee
Review - and submission requires Documentation, so the deal can never be
submitted. No application exists and none can be created. The case is stuck
where nothing can reach it.

The auto-advance now only moves a deal that HAS a credit case. A committee can
still record its vote and its outcome on a deal that has not been submitted -
that is the branch discussing a case before it goes up, which is normal - it
just does not push the deal past the point where submission is possible.

    python scripts/patch_ca1_no_advance_without_a_case.py            # dry run
    python scripts/patch_ca1_no_advance_without_a_case.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '        if outcome == "APPROVED":\n            try:'

NEW = '''        # ── NOT WITHOUT A CREDIT CASE ────────────────────────────────────────
        # D0644: a branch committee voted on a deal that had never been
        # submitted. The approval advanced it past Documentation, and
        # submission requires Documentation - so no application could be
        # created and the deal was stranded where nothing could reach it.
        #
        # A committee may still record its vote on an unsubmitted deal. It just
        # does not move the deal, because the deal has not entered credit.
        _has_case = bool(str(deal.get("lms_application_id") or "").strip())
        if outcome == "APPROVED" and not _has_case:
            _audit("API_COMMITTEE_NO_ADVANCE_NO_CASE", user,
                   f"deal={deal_id}|committee={code}|"
                   f"stage={deal.get('stage')!r} - recorded, not advanced")
        if outcome == "APPROVED" and _has_case:
            try:'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "NOT WITHOUT A CREDIT CASE" in s:
        print("Already applied.")
        return 1

    # Only the one inside the committee-vote close, not the submit path.
    i = s.find('if attended >= quorum and _authority:')
    if i < 0:
        print("Could not find the committee close.")
        return 1
    j = s.index("\n    return", i)
    block = s[i:j]
    if block.count(OLD) != 1:
        print("The flow lookup matched %d times inside the committee close."
              % block.count(OLD))
        return 1

    s = s[:i] + block.replace(OLD, NEW, 1) + s[j:]

    if "_has_case" not in NEW:
        print("The case check is missing.")
        return 1
    if "_audit(" not in NEW:
        print("A deal left where it stands must be recorded, or nobody knows.")
        return 1
    # The committee record must still be written - only the move is stopped.
    if "committee_records" not in s[i:i + 3000]:
        print("The committee record is no longer written.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A committee records its vote; it moves a deal only if one has a case.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ca1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nDeals already stranded stay where they are. Put them back with:")
    print("   python scripts/free_stranded_deals.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
