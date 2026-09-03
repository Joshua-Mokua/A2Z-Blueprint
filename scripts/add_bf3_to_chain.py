#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Put BF3 in the chain, immediately after BF2. DRY RUN by default.

BF1 made the branch required. BF2 exempted the referral. BF3 SHOWS the field to
the officer who has to fill it - it was wrapped in `creatorIsHeadOffice`, so a
branch officer was asked for a branch they could not see.

The three must run in that order: BF2 reorders the block BF1 adds, and BF3
edits the render condition beside it. All three come after UI2, which carries
the file.

    python scripts\add_bf3_to_chain.py
    python scripts\add_bf3_to_chain.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
AFTER = '"patch_bf2_refer_needs_no_branch",'
BF3 = "patch_bf3_branch_field_is_shown"


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    if not os.path.isfile(os.path.join("scripts", "%s.py" % BF3)):
        print("ABORT: %s.py is not on disk." % BF3)
        return 1
    s = open(BUILDER, encoding="utf-8").read()
    if '"%s"' % BF3 in s:
        print("ABORT: BF3 is already in the chain.")
        return 1
    if s.count(AFTER) != 1:
        print("ABORT: BF2 appears %d times - BF3 must follow it." % s.count(AFTER))
        return 1

    s = s.replace(AFTER, AFTER + '\n    "%s",' % BF3, 1)
    print("  ok  BF3 added directly after BF2")

    for earlier in ("patch_ui2_credit_frontend", "patch_bf1_branch_is_required",
                    "patch_bf2_refer_needs_no_branch"):
        if s.index('"%s"' % earlier) > s.index('"%s"' % BF3):
            print("ABORT: BF3 would run before %s, which it depends on." % earlier)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s" % exc.lineno)
        return 1
    print("  ok  post-checks: after UI2, BF1 and BF2")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0
    shutil.copy2(BUILDER, BUILDER + ".pre_bf3chain")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
