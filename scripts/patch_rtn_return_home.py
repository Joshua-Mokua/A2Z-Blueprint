#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RTN - a failed build puts you back on the branch you started from.

FOUND 2026-08-21, after the third time in a row: a build fails, and the next
commit lands on the half-built release branch instead of main. The developer
does not notice, because `git commit` says nothing about which branch it is on.

THE BUILDER ALREADY TRIES to return home - it calls

    sh("git", "checkout", "-q", here, check=False)
    sh("git", "branch", "-D", branch, check=False)

But a failed replay leaves MODIFIED FILES in the tree. Git refuses to switch
branches over them, the checkout fails, and `check=False` means nobody is told.
The branch delete then fails too, because you cannot delete the branch you are
standing on - also silently.

So the cleanup reports success by saying nothing, and leaves the developer in
exactly the state it was written to prevent.

WHAT THIS CHANGES: the partial replay is DISCARDED before returning home.

    git reset --hard      throw away the half-applied patches
    git checkout          now succeeds
    git branch -D         now succeeds

Discarding is right: the branch is being deleted anyway, and a half-replayed
tree is worth nothing. The commits on the original branch are untouched -
`reset --hard` here only clears the working tree of the release branch.

AND IT SAYS WHERE YOU ARE. Every exit now prints the branch, so a failed build
cannot quietly leave you somewhere else.

Usage (from project root, .venv active):
    python scripts\patch_rtn_return_home.py            # dry run
    python scripts\patch_rtn_return_home.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BACKUP_SUFFIX = ".pre_rtn"

OLD = '''            sh("git", "checkout", "-q", here, check=False)
            sh("git", "branch", "-D", branch, check=False)
            return 1'''

NEW = '''            # ── PUT THE DEVELOPER BACK WHERE THEY STARTED ───────────────
            # The half-applied patches must be DISCARDED first. Git refuses to
            # switch branches over modified files, so without this the
            # checkout silently fails, the branch delete silently fails
            # (you cannot delete the branch you are standing on), and the next
            # commit lands on a half-built release branch.
            #
            # That happened three times in a row before anybody noticed.
            #
            # Discarding is correct: this branch is about to be deleted, and a
            # half-replayed tree is worth nothing. Nothing on the ORIGINAL
            # branch is touched.
            sh("git", "reset", "--hard", "-q", check=False)
            sh("git", "checkout", "-q", here, check=False)
            sh("git", "branch", "-D", branch, check=False)
            _now = sh("git", "rev-parse", "--abbrev-ref", "HEAD").strip()
            if _now == here:
                print("\\n  you are back on %s - nothing was left behind." % here)
            else:
                print("\\n  *** COULD NOT RETURN TO %s - you are on %s."
                      % (here, _now))
                print("      Run:  git checkout -f %s" % here)
            return 1'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1

    s = open(BUILDER, encoding="utf-8").read()
    if "PUT THE DEVELOPER BACK WHERE THEY STARTED" in s:
        print("ABORT: RTN looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the cleanup anchor matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  a failed build discards the partial replay and returns home")

    if "reset\", \"--hard\"" not in NEW:
        print("ABORT: the partial replay would survive and block the checkout.")
        return 1
    if "COULD NOT RETURN" not in NEW:
        print("ABORT: a cleanup that fails must SAY SO. Silence is how three")
        print("       commits landed on the wrong branch.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: discards first, reports where you are")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BUILDER + BACKUP_SUFFIX)
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nA failed build now leaves you on the branch you started from.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
