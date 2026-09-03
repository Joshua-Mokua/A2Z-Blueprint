#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Put BF2 in the chain, immediately after BF1. DRY RUN by default.

BF1 is already in the chain and already on the pilot. It moved the branch
requirement from head office to everybody - and put the check ABOVE the
refer-mode early return, so a referral was refused for a branch field the refer
form does not render. The officer saw "Please fix 1 field below" with nothing
marked red.

BF2 moves that check below the return. It MUST follow BF1 in the chain: it
reorders the block BF1 adds, and refuses to apply if BF1 has not run.

    python scripts\add_bf2_to_chain.py
    python scripts\add_bf2_to_chain.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BF1 = '"patch_bf1_branch_is_required",'
BF2 = "patch_bf2_refer_needs_no_branch"


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    if not os.path.isfile(os.path.join("scripts", "%s.py" % BF2)):
        print("ABORT: %s.py is not on disk." % BF2)
        return 1

    s = open(BUILDER, encoding="utf-8").read()
    if '"%s"' % BF2 in s:
        print("ABORT: BF2 is already in the chain.")
        return 1
    if s.count(BF1) != 1:
        print("ABORT: BF1 appears %d times - BF2 must follow it, and I cannot"
              % s.count(BF1))
        print("       tell which one to follow.")
        return 1

    s = s.replace(BF1, BF1 + '\n    "%s",' % BF2, 1)
    print("  ok  BF2 added directly after BF1")

    if s.index('"patch_bf1_branch_is_required"') > s.index('"%s"' % BF2):
        print("ABORT: BF2 would run before BF1, and it reorders what BF1 adds.")
        return 1
    i_ui2 = s.index('"patch_ui2_credit_frontend"')
    if i_ui2 > s.index('"%s"' % BF2):
        print("ABORT: BF2 would run before UI2, which carries the file it")
        print("       edits and would overwrite it.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: after BF1, after UI2")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0
    shutil.copy2(BUILDER, BUILDER + ".pre_bf2chain")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nNext:  python scripts\\preflight_build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
