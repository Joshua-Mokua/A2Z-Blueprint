#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Add the five pilot-unlock fixes to the release chain. DRY RUN by default.

Found on 2026-08-25 while seating the Consumer and Commercial credit
committees and watching real people try to use them:

    HD2  a Head is a manager however the register punctuates it
         "Head of Sales" matched; "Head, SME" and "Head EFS" did not. Four of
         the eight seated committee members had no Manager Queues at all -
         which is where the committee bench lives.

    CS1  a seated committee member can reach the committee
         Department Review was gated on the role string containing a credit
         word. The eight people the bank seated are business heads. None
         qualified.

    AT1  the segment's analyst may attach papers to the segment's cases
         The Consumer analyst got 403 attaching a CRB report to a consumer
         case because she was not the ASSIGNED analyst on it.

    AT2  credit risk works across every segment
         Credit risk, credit administration and remedial have no segment by
         design, so AT1 could not help them.

    CN2  the tab reads "Credit Committee"
         One screen showed "Department Credit Committee Review", "Branch
         Credit Committee" and "B1 - Consumer Banking Credit Committee" at
         once.

ORDER MATTERS FOR TWO OF THEM. AT2 extends the check AT1 adds and refuses to
apply without it. CS1 must follow UI2, which carries the Sidebar file it edits.
The rest are independent.

    python scripts\add_pilot_unlock_chain.py
    python scripts\add_pilot_unlock_chain.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")

# (patcher, must come after)
NEW = [
    ("patch_hd2_head_is_a_manager", None),
    ("patch_at1_segment_analyst_attaches", None),
    ("patch_at2_credit_risk_across_segments", "patch_at1_segment_analyst_attaches"),
    ("patch_cs1_committee_sidebar", "patch_ui2_credit_frontend"),
    ("patch_cn2_committee_tab_name", "patch_ui2_credit_frontend"),
]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    s = open(BUILDER, encoding="utf-8").read()

    missing = [p for p, _ in NEW
               if not os.path.isfile(os.path.join("scripts", "%s.py" % p))]
    if missing:
        print("ABORT: not on disk: %s" % ", ".join(missing))
        return 1

    already = [p for p, _ in NEW if '"%s"' % p in s or "'%s'" % p in s]
    todo = [(p, a) for p, a in NEW if p not in already]

    print("=" * 76)
    print("THE PILOT-UNLOCK FIXES")
    print("=" * 76)
    for p, after in NEW:
        mark = "already in the chain" if p in already else (
            "-> after %s" % after if after else "-> anywhere")
        print("  %-42s %s" % (p, mark))
    if not todo:
        print("\n  All five are already in the chain.")
        return 0

    # UI2 IS LAST IN THE CHAIN and carries whole frontend files. Anything that
    # EDITS a file UI2 carries must run AFTER it, or UI2 overwrites the edit.
    i_ui2 = s.rfind('"patch_ui2_credit_frontend"')
    if i_ui2 < 0:
        print("ABORT: UI2 is not in the chain - CS1 and CN2 edit files it")
        print("       carries and must follow it.")
        return 1
    line_end = s.index("\n", i_ui2)

    block = "".join('\n    "%s",' % p for p, _ in todo)
    s = s[:line_end] + block + s[line_end:]
    print("\n  ok  %d patcher(s) added after UI2" % len(todo))

    for p, after in todo:
        if not after:
            continue
        if s.index('"%s"' % after) > s.index('"%s"' % p):
            print("ABORT: %s would run before %s, which it depends on."
                  % (p, after))
            return 1
    if s.index('"patch_ui2_credit_frontend"') > s.index('"patch_cs1_committee_sidebar"'):
        print("ABORT: CS1 would run before UI2 and be overwritten by it.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: AT2 after AT1, CS1 and CN2 after UI2")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BUILDER + ".pre_unlock")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nNext:  python scripts\\preflight_build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
