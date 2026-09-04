#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Add the 4 September fixes to the release chain. DRY RUN by default.

    CF1  an untargeted stage is named, not silently dropped
         The admin ticked documents and was told "every flow needs a closing
         stage" while looking straight at Closed Won and Closed Lost. The form
         was filtering out any stage with a blank target before sending, and
         closing stages are the likeliest to be blank.

    SC3  the deal's owner is recognised however their code is padded
         canEditDocs compared staff codes as strings, so "KE0539" was not
         "KE539" and the owner of a deal was refused every upload control. A
         credit analyst returned a case asking for documents the owner could
         not attach. Third place this padding has bitten.

    BV2  a manager at a branch may validate that branch's deals
         Validation followed the cascade, so a Customer Service Manager
         covering for an absent Branch Manager could validate the tellers and
         not the relationship officers. Opened up per the bank's ruling.

ORDER: CF1 and SC3 edit files UI2 carries, so they follow it. BV2 is backend
and independent.

    python scripts\add_sept4_fixes_chain.py
    python scripts\add_sept4_fixes_chain.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
AFTER = '"patch_bf3_branch_field_is_shown",'
NEW = ["patch_bv2_branch_manager_validates_branch",
       "patch_cf1_no_silent_stage_drop",
       "patch_sc3_deal_owner_digits"]


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
    print("=" * 70)
    for p in NEW:
        print("  %-46s %s" % (p, "already in" if p not in todo else "to add"))
    if not todo:
        print("\n  All three are already in the chain.")
        return 0
    if s.count(AFTER) != 1:
        print("ABORT: BF3 appears %d times - cannot place these after it."
              % s.count(AFTER))
        return 1

    s = s.replace(AFTER, AFTER + "".join('\n    "%s",' % p for p in todo), 1)
    print("\n  ok  %d added after BF3" % len(todo))

    i_ui2 = s.index('"patch_ui2_credit_frontend"')
    for p in ("patch_cf1_no_silent_stage_drop", "patch_sc3_deal_owner_digits"):
        if s.index('"%s"' % p) < i_ui2:
            print("ABORT: %s would run before UI2, which carries the file it" % p)
            print("       edits and would overwrite it.")
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s" % exc.lineno)
        return 1
    print("  ok  post-checks: the frontend ones follow UI2")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0
    shutil.copy2(BUILDER, BUILDER + ".pre_sept4")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
