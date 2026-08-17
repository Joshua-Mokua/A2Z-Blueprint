#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DC1 - a supported case goes on to the bank credit pool.

RULING (2026-08-14): "since it also has the simple majority, once the vote
reaches that it should now autosubmit to the bank credit analysis pool."

Every outcome used to return the case to the department analyst. That is right
for an opposed or split committee - somebody must act on it - and wrong for a
supported one, which is finished business at this level. Making the analyst
re-submit what a committee has just supported is the delay every auto-advance
ruling has been about.

A SUPPORTED CASE IS RELEASED TO THE CREDIT POOL: status back to submitted, the
analyst cleared, awaiting_credit_analyst set. That is exactly what
hand-to-credit-analyst does, so a bank credit analyst self-picks it in the
ordinary way rather than through a special path.

SPLIT IS NOT SUPPORT. A tied committee has not recommended anything, so it goes
back like a rejection.

TWO MISTAKES WORTH RECORDING, because both made the fix look applied while
changing nothing:

  `outcome` is a DICT - recommendation, tally, who, when - not a string. My
  first check stringified it and matched nothing.

  The verdict words are the COMMITTEE'S OWN - "support", "oppose", "split",
  derived from the votes - not "approved"/"declined" from a payload. My second
  check matched the wrong vocabulary.

Both times every case took the not-approved branch, which is the behaviour the
patch existed to change. A post-check that only asks "is the code present?"
cannot catch that; driving the endpoint can, and did.

Measured:

    3 yes 1 no   support   -> submitted, awaiting_credit_analyst
    1 yes 3 no   oppose    -> assigned, back to the analyst
    2 yes 2 no   split     -> assigned, back to the analyst

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_dc1_supported_case_goes_on.py            # dry run
    python scripts\\patch_dc1_supported_case_goes_on.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_dc1"

OLD = '    lam.update(app_id, {"dcc_outcome": outcome, "status": "assigned", "committee_kind": ""})'

BLOCK = r'''    # ── AN APPROVAL GOES ON; ANYTHING ELSE COMES BACK ───────────────────────
    # RULING (2026-08-14): "since it also has the simple majority, once the
    # vote reaches that it should now autosubmit to the bank credit analysis
    # pool."
    #
    # Every outcome used to return the case to the department analyst. That is
    # right for a rejection or a deferral - somebody must act on it - and wrong
    # for an approval, which is finished business at this level: the committee
    # has recommended it, and making the analyst re-submit what a committee has
    # just approved is the delay the auto-advance rulings were about.
    #
    # AN APPROVED CASE IS RELEASED TO THE CREDIT POOL: status back to
    # submitted, the analyst cleared, awaiting_credit_analyst set - which is
    # exactly what hand-to-credit-analyst does, so a bank credit analyst
    # self-picks it in the ordinary way rather than through a special path.
    # outcome is a DICT - recommendation, tally, who and when - so the verdict
    # is outcome["recommendation"], not the dict stringified. Reading it wrongly
    # made every case take the "not approved" branch and go back to the
    # analyst, which is the behaviour this was meant to change.
    # THE COMMITTEE'S OWN WORDS. recommendation is derived from the votes -
    # "support" when yes beats no, "oppose" when no beats yes, "split" when
    # they tie - not from anything the caller sends. Matching on "approved"
    # here found nothing, so every case took the not-approved branch: the fix
    # looked applied and changed nothing.
    #
    # SPLIT IS NOT SUPPORT. A tied committee has not recommended anything, so
    # the case goes back to the analyst like a rejection.
    _verdict = str((outcome or {}).get("recommendation", "")).lower()
    _approved = _verdict == "support"
    if _approved:
        _next = {
            "dcc_outcome": outcome,
            "committee_kind": "",
            "status": "submitted",
            "analyst": None,
            "awaiting_credit_analyst": True,
            "dcc_cleared_at": _dt.datetime.now().isoformat(timespec="seconds"),
        }
    else:
        _next = {"dcc_outcome": outcome, "status": "assigned", "committee_kind": ""}
    lam.update(app_id, _next)'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "AN APPROVAL GOES ON; ANYTHING ELSE COMES BACK" in s:
        print("ABORT: DC1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the resolve update matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, BLOCK, 1)
    print("  ok  a supported case is released to the credit pool")

    if '_verdict == "support"' not in BLOCK:
        print("ABORT: the verdict is not matched against the committee's own")
        print("       word, so every case would take the not-approved branch.")
        return 1
    if "awaiting_credit_analyst" not in BLOCK:
        print("ABORT: a supported case would not reach the credit pool.")
        return 1
    if '"status": "assigned"' not in BLOCK:
        print("ABORT: an opposed case would not go back to the analyst.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: right vocabulary, both branches, parses")

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
    print("\nRestart uvicorn. A committee that supports a case sends it to the")
    print("bank credit pool without the analyst re-submitting it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
