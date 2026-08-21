#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SELFX - a patcher that edits the builder excludes itself. No more naming them.

THE REGRESS, three times in one hour:

    WHS edits the builder  ->  build refuses, WHS is unplaced
    NFR names WHS          ->  build refuses, NFR is unplaced
    NFR names itself       ->  RTN arrives, build refuses, RTN is unplaced
    RTN_NAMED names RTN    ->  build refuses, RTN_NAMED is unplaced

Every one of those is the same fact: A PATCHER THAT EDITS THE RELEASE BUILDER
CAN NEVER BE REPLAYED ONTO THE PILOT, because the pilot has no release builder -
it is the tool that does the replaying, and it lives on the developer's box.

Naming them one at a time is a list that grows forever and refuses a build each
time somebody forgets. The rule is what should be written down, not the names.

WHAT THIS CHANGES: the unplaced check reads each patcher and skips any that
writes to build_alex_release.py. That is a fact about the file, not a judgement
somebody has to remember.

    on_disk - CHAIN - NOT_FOR_RELEASE - {patchers that edit the builder}

THE EXPLICIT LIST STAYS. The warehouse patchers are held back for a REASON -
"not until it is well built" - and a reason belongs in writing where somebody
can disagree with it. Only the mechanical case is automatic.

AND IT EXCLUDES ITSELF, because it edits the builder. That is the point.

Usage (from project root, .venv active):
    python scripts\patch_selfx_builder_patchers.py            # dry run
    python scripts\patch_selfx_builder_patchers.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")

OLD = '''    unlisted = sorted(on_disk - set(CHAIN) - NOT_FOR_RELEASE)'''

NEW = '''    # ── A PATCHER THAT EDITS THIS FILE EXCLUDES ITSELF ──────────────────────
    # WHS, NFR, RTN and RTN_NAMED each refused a build by existing, and each
    # was fixed by naming the previous one - a regress that ends only when the
    # RULE is written down instead of the names.
    #
    # A patcher that writes to build_alex_release.py cannot be replayed onto
    # the pilot: the pilot has no release builder. That is a fact about the
    # file, not a judgement anybody should have to remember.
    #
    # The explicit NOT_FOR_RELEASE list stays for the warehouse and anything
    # else held back for a REASON - a reason belongs in writing where somebody
    # can disagree with it. Only the mechanical case is automatic.
    _edits_builder = set()
    for _f in glob.glob(os.path.join("scripts", "patch_*.py")):
        try:
            _src = open(_f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if "build_alex_release" in _src:
            _edits_builder.add(os.path.splitext(os.path.basename(_f))[0])
    if _edits_builder:
        print("  %d patcher(s) edit the release builder and cannot reach the"
              % len(_edits_builder))
        print("  pilot - excluded automatically:")
        for _b in sorted(_edits_builder):
            print("     %s" % _b)
        print("")

    unlisted = sorted(on_disk - set(CHAIN) - NOT_FOR_RELEASE - _edits_builder)'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1

    s = open(BUILDER, encoding="utf-8").read()
    if "A PATCHER THAT EDITS THIS FILE EXCLUDES ITSELF" in s:
        print("ABORT: SELFX looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the unplaced check matched %d times." % s.count(OLD))
        return 1
    if "import glob" not in s:
        print("ABORT: glob is not imported in the builder.")
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  a patcher that edits the builder is excluded by rule")

    if "NOT_FOR_RELEASE" not in NEW:
        print("ABORT: the explicit list would be discarded. Things held back")
        print("       for a REASON must stay named, so somebody can disagree.")
        return 1
    if "_edits_builder" not in NEW.split("unlisted =")[1]:
        print("ABORT: the automatic set is computed but not subtracted.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: the explicit list survives, the set is used")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BUILDER + ".pre_selfx")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nThe regress is over. A patcher that edits the builder - including")
    print("this one - no longer needs to be named.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
