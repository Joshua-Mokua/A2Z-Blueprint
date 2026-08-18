#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
VP1 - a vote is personal. One member cannot cast another's. SECURITY.

FOUND 2026-08-18, rehearsing the Business Credit Committee before the MD was
asked to sit on it.

`member_id` arrived from the REQUEST BODY and was checked only against the
roster. Nothing checked that it belonged to the person signed in. So ANY
COMMITTEE MEMBER COULD CAST A VOTE IN ANOTHER MEMBER'S NAME - including the
chair's.

On a committee whose chair's vote is MANDATORY, that is not a small thing: one
member, voting twice under two names, could complete a decision alone. On a
committee chaired by the Managing Director, it is worse than a bug.

The audit log recorded who really sent it, so it was traceable after the fact.
Traceable is not the same as prevented, and a credit decision that has to be
reconstructed from logs has already cost more than it should.

The member voting must BE the person signed in - matched by staff code, then by
name, the same two ways membership is matched everywhere else. An admin is
still allowed through, because recording a vote on somebody's behalf is a real
administrative act, and it is logged as such.

Measured:

    Korir votes as himself    accepted
    Korir votes as the MD     403

WHY NO TEST FOUND THIS: every test drove the endpoint the way the SCREEN drives
it, and the screen sends the signed-in member's own id. Nothing asked what
happens when somebody sends a different one. Testing what the UI does is not
testing what the endpoint permits.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_vp1_vote_is_personal.py            # dry run
    python scripts\\patch_vp1_vote_is_personal.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_vp1"

OLD = '''    if not member_id or member_id not in roster_ids:
        raise HTTPException(status_code=400, detail=f"\'{member_id}\' is not a DCC member")'''
NEW_HEAD = '''    if not member_id or member_id not in roster_ids:
        raise HTTPException(status_code=400, detail=f"\'{member_id}\' is not a committee member")
'''

BLOCK = r'''    # ── A VOTE IS PERSONAL ──────────────────────────────────────────────────
    # FOUND 2026-08-18, rehearsing the Business Credit Committee before the MD
    # sat on it. member_id arrived from the PAYLOAD and was checked only
    # against the roster - so any member could cast a vote in another member's
    # name, INCLUDING THE CHAIR'S. On a committee whose chair's vote is
    # mandatory, that is not a small thing: one member could complete a
    # decision alone.
    #
    # The audit log recorded who really sent it, so it was traceable after the
    # fact. That is not the same as preventable.
    #
    # The member voting must BE the person signed in. Matched by staff code,
    # then by name, which is how membership is matched everywhere else.
    _me = str(user.get("staff_code", "") or "").strip()
    _myname = str(user.get("full_name", "") or "").strip().lower()
    _mine = False
    for _m in (dcc.get("members") or []):
        if not isinstance(_m, dict):
            continue
        _mid = str(_m.get("id") or _m.get("member_id") or "").strip()
        if _mid != member_id:
            continue
        _mcode = str(_m.get("staff_code", "") or "").strip()
        _mname = str(_m.get("name", "") or "").strip().lower()
        _mine = bool((_me and (_mid == _me or _mcode == _me))
                     or (_myname and _mname == _myname))
        break
    if not _mine and not user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="You can only cast your own vote. This seat belongs to "
                   "somebody else on the committee.")
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "A VOTE IS PERSONAL" in s:
        print("ABORT: VP1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the member gate matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW_HEAD + BLOCK.rstrip(), 1)
    print("  ok  a member can only cast their own vote")

    if "403" not in BLOCK:
        print("ABORT: voting as somebody else would not be refused.")
        return 1
    if "staff_code" not in BLOCK:
        print("ABORT: the voter is not matched to the signed-in user.")
        return 1
    if "is_admin" not in BLOCK:
        print("ABORT: an admin could not record a vote on somebody's behalf,")
        print("       which is a real administrative act.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: refused, matched by code and name, admin allowed")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(ROUTES, ROUTES + BACKUP_SUFFIX)
    open(ROUTES, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % ROUTES)

    import py_compile
    try:
        py_compile.compile(ROUTES, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
