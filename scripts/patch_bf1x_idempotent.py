#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BF1X - BF1 checks each file separately, because they are in different states.

The build failed with

    FAILED patch_bf1_branch_is_required
    ABORT: the branch validation matched 0 times.

BF1 EDITS TWO FILES, AND ON THE PILOT THEY ARE NO LONGER IN THE SAME STATE:

    AdminConfig.tsx      UI2 CARRIES IT. UI2 replays its own copy - captured
                         before BF1 existed - so the branch toggle is REMOVED
                         and BF1 must put it back.

    PipelineCreate.tsx   UI2 does NOT carry it. Alex merged the release that
                         added BF1, so it is ALREADY THERE and its anchor is
                         gone.

BF1 asked one question - "is the toggle in AdminConfig?" - and got "no", so it
proceeded to the second file and found nothing to anchor on. One file needed
the patch and the other did not, and the patcher could only believe one thing.

This is the third time whole-file and anchored patches have collided. EV1 had
it, UI2's TreasuryRateDesk had it, and now BF1.

THE RULE: a patcher that edits more than one file must ask ITS OWN QUESTION OF
EACH ONE, and skip the files that already carry its work.

Usage (from project root, .venv active):
    python scripts\patch_bf1x_idempotent.py            # dry run
    python scripts\patch_bf1x_idempotent.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("scripts", "patch_bf1_branch_is_required.py")

OLD = '''    a = open(ADMIN, encoding="utf-8").read()
    c = open(CREATE, encoding="utf-8").read()
    if "'branch', label: 'Originating branch'" in a:
        print("ABORT: BF1 looks applied.")
        return 1
    for nm, src, anchor in (("the admin field list", a, ADMIN_OLD),
                            ("the branch validation", c, CREATE_OLD),
                            ("the payload", c, SEND_OLD)):
        if src.count(anchor) != 1:
            print("ABORT: %s matched %d times." % (nm, src.count(anchor)))
            return 1'''

NEW = '''    a = open(ADMIN, encoding="utf-8").read()
    c = open(CREATE, encoding="utf-8").read()

    # ── EACH FILE IS ASKED ITS OWN QUESTION ─────────────────────────────────
    # These two files are NOT in the same state on the pilot. UI2 carries
    # AdminConfig.tsx and replays a copy captured before BF1 existed, so the
    # toggle is removed and must be put back. UI2 does NOT carry
    # PipelineCreate.tsx, so once the pilot has merged BF1 the change is
    # already there and its anchor is gone.
    #
    # Asking one question of both meant one answer had to be wrong. The build
    # stopped at "the branch validation matched 0 times".
    admin_done = "'branch', label: 'Originating branch'" in a
    create_done = "requiredFields.includes('branch')" in c
    if admin_done and create_done:
        print("ABORT: BF1 looks applied to both files.")
        return 1

    if not admin_done and a.count(ADMIN_OLD) != 1:
        print("ABORT: the admin field list matched %d times." % a.count(ADMIN_OLD))
        return 1
    if not create_done:
        for nm, anchor in (("the branch validation", CREATE_OLD),
                           ("the payload", SEND_OLD)):
            if c.count(anchor) != 1:
                print("ABORT: %s matched %d times." % (nm, c.count(anchor)))
                return 1'''

OLD_APPLY = '''    a = a.replace(ADMIN_OLD, ADMIN_NEW, 1)
    c = c.replace(CREATE_OLD, CREATE_NEW, 1).replace(SEND_OLD, SEND_NEW, 1)
    print("  ok  the admin offers branch; the form asks everybody")'''

NEW_APPLY = '''    if not admin_done:
        a = a.replace(ADMIN_OLD, ADMIN_NEW, 1)
        print("  ok  the admin offers a branch toggle")
    else:
        print("  ok  the admin already offers it - left alone")
    if not create_done:
        c = c.replace(CREATE_OLD, CREATE_NEW, 1).replace(SEND_OLD, SEND_NEW, 1)
        print("  ok  the form asks everybody")
    else:
        print("  ok  the form already asks everybody - left alone")'''

OLD_POST = '''    if "creatorIsHeadOffice && originatingBranch" in c:
        print("ABORT: the payload still withholds the branch from a branch")
        print("       officer, which is the whole fault.")
        return 1
    if "requiredFields.includes('branch')" not in c:'''

NEW_POST = '''    if not create_done and "creatorIsHeadOffice && originatingBranch" in c:
        print("ABORT: the payload still withholds the branch from a branch")
        print("       officer, which is the whole fault.")
        return 1
    if "requiredFields.includes('branch')" not in c:'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1
    s = open(MOD, encoding="utf-8").read()
    if "EACH FILE IS ASKED ITS OWN QUESTION" in s:
        print("ABORT: BF1X looks applied.")
        return 1
    for nm, anchor in (("the guard block", OLD), ("the apply block", OLD_APPLY),
                       ("the post-check", OLD_POST)):
        if s.count(anchor) != 1:
            print("ABORT: %s matched %d times." % (nm, s.count(anchor)))
            return 1

    s = (s.replace(OLD, NEW, 1).replace(OLD_APPLY, NEW_APPLY, 1)
          .replace(OLD_POST, NEW_POST, 1))
    print("  ok  BF1 asks each file its own question")

    if "admin_done" not in NEW or "create_done" not in NEW:
        print("ABORT: the two files are still judged together.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: each file judged separately")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0
    shutil.copy2(MOD, MOD + ".pre_bf1x")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
