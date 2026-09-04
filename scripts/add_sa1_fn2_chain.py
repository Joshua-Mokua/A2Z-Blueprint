#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Put SA1 and FN2 in the chain. DRY RUN by default.

    SA1  a SINGLE_APPROVER voting rule - one YES approves, with any dissent
         still recorded and named. Opt-in per committee; nothing changes until
         somebody sets it.

    FN2  a deal that reached credit and did not advance in the funnel now says
         WHY. The advance was failing in three ways behind `except: pass`, so
         a case could sit at credit while the funnel showed it at the branch.

Both edit backend files UI2 does not carry, so they can sit anywhere. They go
after RC2 with the other September work.

    python scripts\add_sa1_fn2_chain.py
    python scripts\add_sa1_fn2_chain.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
AFTER = '"patch_rc2_referral_carries_client_type",'
NEW = ["patch_sa1_single_approver", "patch_fn2_funnel_follows_credit"]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    missing = [p for p in NEW
               if not os.path.isfile(os.path.join("scripts", "%s.py" % p))]
    if missing:
        print("ABORT: not on disk: %s" % ", ".join(missing))
        return 1

    s = open(BUILDER, encoding="utf-8").read()
    todo = [p for p in NEW if '"%s"' % p not in s]
    for p in NEW:
        print("  %-42s %s" % (p, "already in" if p not in todo else "to add"))
    if not todo:
        print("\n  Both are already in the chain.")
        return 0
    if s.count(AFTER) != 1:
        print("ABORT: the anchor matched %d times." % s.count(AFTER))
        return 1

    s = s.replace(AFTER, AFTER + "".join('\n    "%s",' % p for p in todo), 1)
    print("\n  ok  %d added after RC2" % len(todo))

    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s" % exc.lineno)
        return 1
    # Both edit utils/api.py, and FN2's anchor is a comment SA1 does not touch -
    # but order still matters if that ever changes, so pin it.
    if "patch_sa1_single_approver" in s and "patch_fn2_funnel_follows_credit" in s:
        if s.index('"patch_sa1_single_approver"') > s.index('"patch_fn2_funnel_follows_credit"'):
            print("ABORT: FN2 would run before SA1. Both edit utils/api.py and")
            print("       the order should be the one they were written in.")
            return 1
    print("  ok  post-checks: SA1 before FN2")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0
    shutil.copy2(BUILDER, BUILDER + ".pre_sa1fn2")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nCOMMIT THE BUILDER - the last chain edit was applied but never")
    print("committed, so the build did not see it:")
    print("   git add scripts/build_alex_release.py && git commit -m \\")
    print("       \"chore(release): SA1 and FN2 enter the chain\" && git push origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
