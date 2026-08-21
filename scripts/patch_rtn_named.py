#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Name RTN as held back. One line, because the build refuses without it.

    *** 1 patcher(s) exist but are NOT in the release chain:
          patch_rtn_return_home
    ABORT: refusing to build a release that silently omits work.

RTN edits the release builder, so it can never be replayed onto the pilot - the
same reason WHS and NFR are excluded. NFR was applied before RTN existed, and a
patcher cannot be applied twice, so the name has to be added on its own.

    python scripts\patch_rtn_named.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")

OLD = '''    "patch_nfr_six",'''
NEW = '''    "patch_nfr_six",
    # RTN edits the builder too: a failed build now discards the partial
    # replay and returns you to the branch you started from. It cannot be
    # replayed onto the pilot for the same reason as WHS and NFR - it IS the
    # tool doing the replaying.
    "patch_rtn_return_home",'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    s = open(BUILDER, encoding="utf-8").read()
    if '"patch_rtn_return_home"' in s:
        print("ABORT: already named.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: anchor matched %d times." % s.count(OLD))
        return 1
    s = s.replace(OLD, NEW, 1)
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s" % exc.lineno)
        return 1
    print("  ok  RTN is named as deliberately held back")
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0
    shutil.copy2(BUILDER, BUILDER + ".pre_rtnname")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
