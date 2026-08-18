#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BV1 - one vote per member on the department and business committees, and a
      committee can close its own sitting.

BOTH FOUND 2026-08-18, rehearsing the Business Credit Committee before the
Managing Director was asked to sit on it. Neither would have been found by
using the screen.

1. A MEMBER COULD VOTE TWICE, AND THE SECOND SILENTLY REPLACED THE FIRST.

   The vote list removed the member's previous entry and re-added it. No
   refusal, no record that anybody had changed their mind. The branch committee
   has required one vote per member since VF1; the department and business
   committees never did.

   Nobody noticed because THE PANEL HIDES THE BUTTON after voting - so only
   somebody calling the endpoint directly would find it, which is what a
   rehearsal does and a walkthrough does not.

   A vote quietly overwritten is worse than one refused: the record then says
   the committee agreed, when a member may have been persuaded - or pressed -
   to vote again. An administrator can still change one, and it is logged.

2. THE CHAIR COULD NOT CLOSE THEIR OWN COMMITTEE.

   Closing was restricted to a manager or the ASSIGNED ANALYST. That is right
   for a department committee, which an analyst convenes about their own case.

   It is wrong for the business committee, which is chaired by the MD and has
   NO assigned analyst - the case was referred to it. Under the old rule the MD
   could sit, hear the case and vote, and then be refused permission to record
   what the committee had decided. In front of the room.

   A member of the committee that just sat may now close it. Nobody else.

Measured after the fix, driving the real roster:

    all 7 members could vote
    a second vote is refused
    a member cannot vote in another member's name
    a supported case goes back to credit risk, marked approved by the committee
    an opposed case comes back too, marked not approved
    the committee sets no conditions - those are the analyst's

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_bv1_committee_vote_integrity.py            # dry run
    python scripts\\patch_bv1_committee_vote_integrity.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_bv1"

VOTE_ANCHOR = '    votes = [v for v in (app.get("dcc_votes", []) or []) if v.get("member_id") != member_id]'

CLOSE_OLD = '''    if not (is_manager(user) or (caller and caller == analyst_code)):
        raise HTTPException(status_code=403,
                            detail="Only a manager or the assigned analyst can close the DCC.")'''

DCC_ANCHOR = "    dcc = _dcc_for_app(app)\n"

VOTE_BLOCK = r'''    # ── ONE VOTE PER MEMBER, AND IT STANDS ──────────────────────────────────
    # FOUND 2026-08-18, rehearsing before the MD sat on this committee. The
    # line below REMOVES the member's previous vote and the next re-adds it -
    # so a second vote silently replaced the first, with no record that a
    # member had changed their mind and no refusal.
    #
    # The branch committee has required one vote per member since VF1. The
    # department and business committees never did, and nobody noticed because
    # the panel hides the button after voting - so only somebody calling the
    # endpoint directly would find it. Which is what a rehearsal does.
    #
    # A vote quietly overwritten is worse than one refused: the record then
    # says the committee agreed, when a member may have been persuaded - or
    # pressed - to vote again.
    if (any(str(v.get("member_id")) == str(member_id)
            for v in (app.get("dcc_votes", []) or []))
            and not user.get("is_admin")):
        raise HTTPException(
            status_code=409,
            detail="You have already voted on this case. A vote stands once "
                   "cast - ask an administrator if it must be changed.")
'''

CLOSE_BLOCK = r'''    # ── A COMMITTEE CAN CLOSE ITS OWN SITTING ───────────────────────────────
    # FOUND 2026-08-18, rehearsing the Business Credit Committee. Closing was
    # restricted to a manager or the ASSIGNED ANALYST. That is right for a
    # department committee, which an analyst convenes about their own case.
    #
    # It is wrong for the business committee. That one is chaired by the
    # Managing Director and has NO assigned analyst - the case was referred to
    # it. Under the old rule the MD could sit, hear the case and vote, and then
    # not be allowed to record what the committee had decided.
    #
    # A member of the committee that just sat may close it. Nobody else.
    _closer = str(user.get("staff_code", "") or "").strip()
    _closer_name = str(user.get("full_name", "") or "").strip().lower()
    _on_committee = any(
        (_closer and (str(m.get("staff_code", "")).strip() == _closer
                      or str(m.get("id") or m.get("member_id") or "").strip() == _closer))
        or (_closer_name and str(m.get("name", "")).strip().lower() == _closer_name)
        for m in (dcc.get("members") or []) if isinstance(m, dict))
    if not (_on_committee or is_manager(user)
            or (caller and caller == analyst_code)):
        raise HTTPException(
            status_code=403,
            detail="Only a member of this committee, its analyst, or a "
                   "manager can record its decision.")
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "ONE VOTE PER MEMBER, AND IT STANDS" in s:
        print("ABORT: BV1 looks applied.")
        return 1
    if "_dcc_for_app" not in s:
        print("ABORT: DR2 must be applied first.")
        return 1
    if s.count(VOTE_ANCHOR) != 1 or s.count(CLOSE_OLD) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (s.count(VOTE_ANCHOR), s.count(CLOSE_OLD)))
        return 1

    s = s.replace(VOTE_ANCHOR, VOTE_BLOCK + VOTE_ANCHOR, 1)
    # The close check reads `dcc`, so it must sit AFTER dcc is resolved - not
    # where the old gate stood. Placing it by line order rather than by the old
    # gate's position is the difference between working and a NameError the
    # first time somebody closes a sitting.
    s = s.replace(CLOSE_OLD, "", 1)
    i = s.index("def lms_dcc_resolve")
    k = s.index(DCC_ANCHOR, i) + len(DCC_ANCHOR)
    s = s[:k] + CLOSE_BLOCK + s[k:]
    print("  ok  one vote per member; a committee closes its own sitting")

    if "409" not in VOTE_BLOCK:
        print("ABORT: a second vote would not be refused.")
        return 1
    if "is_admin" not in VOTE_BLOCK:
        print("ABORT: an administrator could not correct a vote, which is a")
        print("       real administrative act.")
        return 1
    if "_on_committee" not in CLOSE_BLOCK or "is_manager" not in CLOSE_BLOCK:
        print("ABORT: the close gate is incomplete.")
        return 1
    # The check must sit after dcc is resolved, or it raises on first use.
    body_ = s[s.index("def lms_dcc_resolve"):]
    body_ = body_[:body_.index("\n@router.")]
    if body_.index("_on_committee = any") < body_.index("dcc = _dcc_for_app"):
        print("ABORT: the close check reads `dcc` before it is resolved - it")
        print("       would raise the first time somebody closed a sitting.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: refused, admin allowed, ordered correctly")

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
    print("\nRESTART UVICORN, then:  python scripts\\rehearse_bcc.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
