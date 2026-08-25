#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CN2 - the tab reads "Credit Committee"; the panel inside says which one.

FROM THE PILOT (2026-08-25), on one screen at one moment:

    header badge   Department Credit Committee Review
    tab            Branch Credit Committee
    panel inside   B1 - Consumer Banking Credit Committee

Three names for one thing. An officer voting on that case has to work out
whether they are three stages or one, and the answer is that they are one.

THE TAB IS FIXED AND THE COMMITTEE IS NOT. A case may sit before B1 Consumer,
B2 Commercial, B3 CIB, B4, or a branch committee - so a hardcoded "Branch
Credit Committee" is wrong for every case that is not at a branch, which on
this screen it plainly was not.

    tab     "Credit Committee"      - true wherever the case is
    panel   "B1 - Consumer Banking Credit Committee"  - already correct

The specific name belongs where the vote is cast, next to the voting rule and
the bench. That is where somebody needs to know exactly which committee they
are answering to, and it is already there.

NOTHING ELSE MOVES. The panel, the badge and the journey are untouched - only
the tab label, which was the one piece of text that could not be right.

Usage (from project root, .venv active):
    python scripts\patch_cn2_committee_tab_name.py            # dry run
    python scripts\patch_cn2_committee_tab_name.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")

OLD = "{ id: 'committee', label: 'Branch Credit Committee', color: '#EF6C00',"
NEW = ("{ id: 'committee', label: 'Credit Committee', color: '#EF6C00',"
       "  /* not 'Branch': a case may sit before B1 Consumer, B2 Commercial,"
       " B3 CIB, B4 or a branch committee, and the panel inside names which. */")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "label: 'Credit Committee'" in s:
        print("ABORT: CN2 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the tab label matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  the tab reads Credit Committee")

    # The specific name must SURVIVE inside the panel - moving the generic
    # label up only helps if the precise one is still shown where the vote is
    # cast.
    if "committee_name" not in s and "gate.name" not in s and "c.name" not in s:
        print("ABORT: the panel no longer shows which committee. A generic tab")
        print("       is only an improvement if the specific name is still")
        print("       next to the vote.")
        return 1
    if s.count("{ id: 'committee'") != 1:
        print("ABORT: there is more than one committee tab.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("ABORT: braces unbalanced.")
        return 1
    print("  ok  post-checks: one tab, the panel still names the committee")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cn2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
