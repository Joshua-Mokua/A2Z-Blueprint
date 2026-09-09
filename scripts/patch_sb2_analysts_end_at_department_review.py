#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Credit Analysis is credit risk's. The analysts end at Department Review.

The sidebar already hides Department Review from credit risk:

    !(/credit risk|credit admin|remedial|recover/i.test(user?.role)
      && item.label === 'Department Review')

The mirror was never written, so the segment analysts see Credit Analysis as
well as their own screen - two doors to two different jobs, side by side, with
nothing saying which is which. They have been using each other's.

Adds the other half beside it, in the same shape.

    python scripts/patch_sb2_analysts_end_at_department_review.py            # dry run
    python scripts/patch_sb2_analysts_end_at_department_review.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")

OLD = """              && !(/credit risk|credit admin|remedial|recover/i.test(user?.role ?? '')
                   && item.label === 'Department Review'),"""

NEW = """              && !(/credit risk|credit admin|remedial|recover/i.test(user?.role ?? '')
                   && item.label === 'Department Review')
              // And the mirror: Credit Analysis is credit risk's screen. A
              // segment analyst seeing both could not tell which was theirs,
              // and they have been working on each other's.
              && !(!/credit risk/i.test(user?.role ?? '')
                   && item.label === 'Credit Analysis'),"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "And the mirror" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The role filter matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # Department Review must still be there for the analysts.
    if "item.label === 'Department Review'" not in s:
        print("The existing rule was lost.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("Braces unbalanced.")
        return 1
    print("Credit Analysis is shown to credit risk only.")
    print("Department Review keeps the analysts and the committee members.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("\nAn admin who is not credit risk will no longer see Credit")
        print("Analysis in the menu. They can still reach /credit-risk")
        print("directly, and the server decides what they may do there.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_sb2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
