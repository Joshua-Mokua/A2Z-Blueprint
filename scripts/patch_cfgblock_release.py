#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stop lms_config.json travelling in a release. DRY RUN by default.

data/lms_config.json holds the BANK'S OWN committee membership - who chairs
which committee, who sits on it, who may vote. It is tracked on alex-dev, and
the release builder does not block it, so a release can carry OUR copy over
THEIRS and silently unstaff every committee.

That is not hypothetical. A release copy with 5 of 21 committees staffed was
sitting on two branches, and every merge would have handed it back. It is also
why `del data\\lms_config.json` has been necessary before every build - the file
is tracked on one branch and ignored on the other, and it keeps colliding.

users.json and the staff register are already blocked for exactly this reason.
The committee config belongs in the same list: it is the bank's data, not ours,
and no release should ever write it.

    python scripts\\patch_cfgblock_release.py
    python scripts\\patch_cfgblock_release.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BACKUP = BUILDER + ".pre_cfgblock"

OLD = '''    DATA_BLOCK = ("data/branch_logs.json", "data/pipeline_deals.json",
                  "data/branch_days.json", "data/daily_log_exceptions.json",
                  "data/users.json", "data/staff_register.xlsx")'''

NEW = '''    # lms_config.json is THE BANK'S OWN committee membership - who chairs
    # each committee, who sits on it, who may vote. It is tracked on alex-dev
    # and was never blocked, so a release could carry OUR copy over THEIRS and
    # unstaff every committee at once. A release branch with 5 of 21 staffed
    # was sitting on two branches when this was found.
    #
    # It is also why `del data\\lms_config.json` was needed before every build:
    # tracked on one branch, ignored on the other, colliding every time.
    #
    # users.json and the register are blocked for the same reason. This is the
    # bank's data, not ours, and no release should write it.
    DATA_BLOCK = ("data/branch_logs.json", "data/pipeline_deals.json",
                  "data/branch_days.json", "data/daily_log_exceptions.json",
                  "data/users.json", "data/staff_register.xlsx",
                  "data/lms_config.json")'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    s = open(BUILDER, encoding="utf-8").read()

    if '"data/lms_config.json")' in s:
        print("ABORT: already blocked.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the block list matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  lms_config.json can no longer travel in a release")

    for keep in ("data/users.json", "data/staff_register.xlsx",
                 "data/pipeline_deals.json"):
        if keep not in s:
            print("ABORT: %s fell out of the block list." % keep)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the builder would not parse - line %s: %s"
              % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: the other blocked files are still blocked")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BACKUP)
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s   (backup: %s)" % (BUILDER, os.path.basename(BACKUP)))
    print("\nThe bank keeps its own committee membership across releases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
