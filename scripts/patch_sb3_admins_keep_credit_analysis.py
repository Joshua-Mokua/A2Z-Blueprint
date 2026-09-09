#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Admins and the MD keep Credit Analysis in the menu.

SB2 hid Credit Analysis from anyone whose role does not read "credit risk".
The point was to stop the segment analysts using credit risk's screen. It also
hid it from administrators and the MD, who need to see every module - and it
went out that way.

The rule now hides it from the segment analysts only.

    python scripts/patch_sb3_admins_keep_credit_analysis.py            # dry run
    python scripts/patch_sb3_admins_keep_credit_analysis.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")

OLD = """              && !(!/credit risk/i.test(user?.role ?? '')
                   && item.label === 'Credit Analysis'),"""

NEW = """              && !(!/credit risk/i.test(user?.role ?? '')
                   && !isAdmin && !isAdminOrMd
                   && item.label === 'Credit Analysis'),"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "&& !isAdmin && !isAdminOrMd" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The Credit Analysis rule matched %d times." % s.count(OLD))
        print("Apply patch_sb2_analysts_end_at_department_review.py first.")
        return 1

    s = s.replace(OLD, NEW, 1)

    # Both flags must exist in this component or the rule silently fails.
    for name in ("isAdmin", "isAdminOrMd"):
        if name not in s.split("return (")[0]:
            print("%s is not available here - check before applying." % name)
            return 1
    if "item.label === 'Department Review'" not in s:
        print("The Department Review rule was lost.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("Braces unbalanced.")
        return 1
    print("Hidden from the segment analysts only; admins and the MD keep it.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_sb3")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
