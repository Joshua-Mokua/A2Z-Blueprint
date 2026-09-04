#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Put RC2 in the chain, after UI2. DRY RUN by default.

RC2 stops the refer endpoint hardcoding client_type = "Existing" - a
relationship status in a customer-type field, which meant every one of the
pilot's 33 unsegmented deals reached no segment analyst.

It edits four files, two of them frontend (PipelineCreate.tsx and
types/pipeline.ts). UI2 carries PipelineCreate.tsx, so RC2 must run after it.

    python scripts\add_rc2_to_chain.py
    python scripts\add_rc2_to_chain.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
AFTER = '"patch_sc3_deal_owner_digits",'
RC2 = "patch_rc2_referral_carries_client_type"


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    if not os.path.isfile(os.path.join("scripts", "%s.py" % RC2)):
        print("ABORT: %s.py is not on disk." % RC2)
        return 1
    s = open(BUILDER, encoding="utf-8").read()
    if '"%s"' % RC2 in s:
        print("ABORT: RC2 is already in the chain.")
        return 1
    if s.count(AFTER) != 1:
        print("ABORT: the anchor matched %d times." % s.count(AFTER))
        return 1

    s = s.replace(AFTER, AFTER + '\n    "%s",' % RC2, 1)
    print("  ok  RC2 added")

    if s.index('"patch_ui2_credit_frontend"') > s.index('"%s"' % RC2):
        print("ABORT: RC2 would run before UI2, which carries a file it edits")
        print("       and would overwrite it.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s" % exc.lineno)
        return 1
    print("  ok  post-checks: after UI2")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0
    shutil.copy2(BUILDER, BUILDER + ".pre_rc2chain")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
