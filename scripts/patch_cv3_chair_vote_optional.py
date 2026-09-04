#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CV3 - a committee can be configured not to require its chair's vote.

FROM THE BANK (2026-09-04): "in consumer everybody has voted, but since Jane is
away nothing has moved. I want to eliminate that rule of chair must vote for
the department."

THE RULE TODAY. A decision closes only when quorum is met AND the chair or a
named deputy has voted:

    _authority = _chair_spoke or _deputy_spoke
    if attended >= quorum and _authority:

It was asked for on 2026-08-13 - "as a rule of law we should make the chair
vote mandatory" - and it is right for a body whose chair carries the authority.
It is wrong when it means a fully-voted committee sits still because one person
is on leave.

WHAT THIS CHANGES: the requirement becomes a per-committee setting.

    chair_vote_required            absent or true  -> as now, the chair or a
                                                      named deputy must vote
                                   false           -> quorum alone decides

THE DEFAULT IS UNCHANGED. Every committee that does not set it keeps the
current behaviour exactly. Nothing moves until somebody turns it off on a
named committee.

QUORUM STILL APPLIES. This removes the requirement that a PARTICULAR person has
voted; it does not remove the requirement that ENOUGH people have. A committee
with chair_vote_required false still waits for its quorum.

AND IT IS RECORDED. When a decision closes without the chair, the committee
record says so - chair_voted stays false and the audit carries
chair_not_required, so a case decided in the chair's absence is visible as
such rather than looking identical to one they attended.

WHY OFFER THIS RATHER THAN JUST NAMING A DEPUTY. Naming a deputy is the better
answer where the bank has one - it keeps a named person accountable for closing
the vote. This is for committees where the bank has decided the chair's
presence is not a condition. Both exist; the bank picks per committee.

Usage (from project root, .venv active):
    python scripts\patch_cv3_chair_vote_optional.py            # dry run
    python scripts\patch_cv3_chair_vote_optional.py --apply

Then, per committee:
    python scripts\set_chair_vote_required.py --committee B1 --off --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''    _chair_spoke = any(_is_chair(v) for v in cast.values())
    _deputy_spoke = any(_is_deputy(v) for v in cast.values())
    _authority = _chair_spoke or _deputy_spoke

    if attended >= quorum and _authority:'''

NEW = '''    _chair_spoke = any(_is_chair(v) for v in cast.values())
    _deputy_spoke = any(_is_deputy(v) for v in cast.values())

    # ── THE CHAIR'S VOTE IS REQUIRED UNLESS THE BANK SAYS OTHERWISE ─────────
    # RULING (2026-09-04): "in consumer everybody has voted, but since Jane is
    # away nothing has moved. I want to eliminate that rule of chair must vote
    # for the department."
    #
    # The requirement (2026-08-13, "make the chair vote mandatory") is right
    # for a body whose chair carries the authority, and wrong when it leaves a
    # fully-voted committee still because one person is on leave.
    #
    # It is now per-committee and DEFAULTS TO REQUIRED - a committee that does
    # not set chair_vote_required behaves exactly as before.
    #
    # QUORUM STILL APPLIES. This drops the requirement that a PARTICULAR person
    # voted, not the requirement that ENOUGH people did.
    _chair_required = committee.get("chair_vote_required", True)
    if isinstance(_chair_required, str):
        _chair_required = _chair_required.strip().lower() not in (
            "false", "no", "0", "off")
    _authority = (_chair_spoke or _deputy_spoke) if _chair_required else True

    if attended >= quorum and _authority:'''

REC_OLD = '''        "chair_voted": _chair_spoke,
        "deputy_voted": _deputy_spoke,'''
REC_NEW = '''        "chair_voted": _chair_spoke,
        "deputy_voted": _deputy_spoke,
        # A case decided without the chair must be VISIBLE as such, not
        # indistinguishable from one they attended.
        "chair_vote_required": bool(committee.get("chair_vote_required", True)),'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "THE CHAIR'S VOTE IS REQUIRED UNLESS THE BANK SAYS OTHERWISE" in s:
        print("ABORT: CV3 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the decision gate matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    if s.count(REC_OLD) == 1:
        s = s.replace(REC_OLD, REC_NEW, 1)
        print("  ok  the record says whether the chair was required")
    print("  ok  the chair's vote is required unless a committee says otherwise")

    # The default MUST be required, or every committee silently loosens.
    if 'get("chair_vote_required", True)' not in NEW:
        print("ABORT: the default is not 'required'. A committee that has not")
        print("       chosen must keep the behaviour it has today.")
        return 1
    # Quorum must survive - this drops WHO, not HOW MANY.
    if "attended >= quorum" not in NEW:
        print("ABORT: quorum would no longer be checked. This removes the")
        print("       requirement that a PARTICULAR person voted, not that")
        print("       enough people did.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: default unchanged, quorum still enforced")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cv3")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nNOTHING HAS CHANGED YET - every committee still requires its")
    print("chair. Turn it off where the bank has decided to:")
    print("   python scripts\\set_chair_vote_required.py --committee B1 --off --apply")
    print("\nRESTART UVICORN after both.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
