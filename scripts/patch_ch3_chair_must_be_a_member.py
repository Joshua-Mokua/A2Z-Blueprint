#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH3 - a chair who is not on the committee cannot be waited for.

FROM THE BANK (2026-09-04): "Jane still has to recommend at committee level
even after removing her from the committee."

THE CHAIR IS A NAME, NOT A MEMBERSHIP. _is_chair matches a vote against
committee["chaired_by"] - a string - and nothing checks that the person named
is still on the committee:

    _chair_name = str(committee.get("chaired_by", "")).strip().lower()
    def _is_chair(v):
        return ... str(v.get("name", "")).strip().lower() == _chair_name

So removing Jane from members left chaired_by naming her. The decision still
waits for a vote from somebody who is no longer on the committee AND THEREFORE
CANNOT CAST ONE. The case can never close, by any route: not by her voting, not
by the rest voting, not by a deputy, because a deputy only stands in for an
absent chair rather than a departed one.

WHAT THIS CHANGES: if the named chair is not among the committee's members, the
chair requirement does not apply. Quorum still does.

    the chair is a member, has not voted    wait, as now
    the chair is a member and has voted     close, as now
    THE CHAIR IS NOT A MEMBER               the requirement is dropped, and the
                                            reason is logged
    there is no chaired_by at all           the requirement is dropped, as it
                                            already was

WHY DROP IT RATHER THAN REFUSE THE SAVE. Removing somebody from a committee is
a normal thing to do - people leave, move, are replaced. The system should not
deadlock every case in front of that committee until an admin notices they also
have to clear a second field. Failing OPEN here means a committee keeps working
with a stale chair name; failing closed means it stops entirely, which is what
happened.

IT IS LOGGED EVERY TIME, so a committee running without its named chair is
visible rather than quietly permitted.

Usage (from project root, .venv active):
    python scripts\patch_ch3_chair_must_be_a_member.py            # dry run
    python scripts\patch_ch3_chair_must_be_a_member.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''    _chair_required = committee.get("chair_vote_required", True)'''

NEW = '''    # ── A CHAIR WHO IS NOT ON THE COMMITTEE CANNOT BE WAITED FOR ────────────
    # RULING (2026-09-04): "Jane still has to recommend at committee level even
    # after removing her from the committee."
    #
    # chaired_by is a NAME on the committee and nothing tied it to membership.
    # Removing her from members left it naming her, so the decision waited for
    # a vote she could no longer cast - by any route, since a deputy stands in
    # for an ABSENT chair, not a departed one.
    #
    # Failing OPEN is deliberate. Removing somebody from a committee is normal;
    # the system must not deadlock every case in front of it until an admin
    # notices there is a second field to clear.
    _chair_on_committee = True
    if _chair_name:
        _mem_names = {str(_m.get("name", "") or "").strip().lower()
                      for _m in (committee.get("members") or [])
                      if isinstance(_m, dict)}
        _mem_codes = {str(_m.get("staff_code", "") or "").strip()
                      for _m in (committee.get("members") or [])
                      if isinstance(_m, dict)}
        _chair_on_committee = (_chair_name in _mem_names
                               or (_chair_code and _chair_code in _mem_codes))
        if not _chair_on_committee:
            logger.warning(
                "committee %s names %r as chair but they are not a member - "
                "the chair requirement is dropped, or no case before this "
                "committee could ever close",
                committee.get("code"), committee.get("chaired_by"))

    _chair_required = (committee.get("chair_vote_required", True)
                       and _chair_on_committee)'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "A CHAIR WHO IS NOT ON THE COMMITTEE CANNOT BE WAITED FOR" in s:
        print("ABORT: CH3 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the chair-required line matched %d times." % s.count(OLD))
        print("       CV3 must be applied first - it is what introduced it.")
        return 1
    if "_chair_name" not in s:
        print("ABORT: _chair_name is not in scope here.")
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  a chair who is not a member is not waited for")

    if "logger.warning" not in NEW:
        print("ABORT: a committee running without its named chair must be")
        print("       visible, not quietly permitted.")
        return 1
    if "and _chair_on_committee" not in NEW:
        print("ABORT: the membership test is computed but not applied.")
        return 1
    # Quorum must be untouched - this drops WHO, never HOW MANY.
    if "quorum" in NEW.lower():
        print("ABORT: this must not touch quorum.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: logged, applied, quorum untouched")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ch3")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN, then sweep the cases that were stuck behind her:")
    print("   python scripts\\close_waiting_committees.py")
    print("   python scripts\\close_waiting_committees.py --apply")
    print("\nAND TIDY THE CONFIG when there is time - a committee naming a chair")
    print("who is not a member still reads oddly on the admin screen, even")
    print("though it no longer blocks anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
