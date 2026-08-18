#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
LK1 - the branch keeps its case while its own committee holds it.

FROM THE PILOT (2026-08-18): a new case at a branch showed "Locked - with
Credit" the moment its documents were uploaded and submitted.

RULING: "what did we solution for, if the branch is not able to vote and
recommend before it even flows to the department and not even credit yet? I
thought we were clear that after the documents are gathered, that Submit is in
fact Submit to the Branch Credit Committee."

THE ROUTING WAS RIGHT AND IS RIGHT. Measured: Documentation -> Branch Credit
Committee Review. Nothing about that changed. THE LOCK WAS THE STALE PART, and
it predates every piece of the committee work.

Its whole test was "does this deal have an lms_application_id?". Submitting
creates one, because the deal and the loan application are ONE OBJECT the whole
way through. When that test was written, submitting MEANT going to credit - so
the lock, and the words "with Credit", were both true.

They are not true now. Three things happen at submission and only one was
wrong: the case correctly goes to the branch committee, the application
correctly gets created, and the lock - built for a flow where those meant "gone
to credit" - fired THREE STAGES EARLY with the wrong holder named on it.

A case at a BRANCH COMMITTEE STAGE HAS NOT LEFT THE BRANCH. Their own committee
holds it, their own people vote on it, and if that committee asks for a document
the branch should be able to attach it - not go through a rework loop to unlock
their own case.

The lock now falls when the case moves PAST the branch: to the department, to
credit, and beyond. Measured:

    Documentation                       locked (only once submitted)
    Branch Credit Committee Review      the branch can still edit
    Department Credit Analysis          locked
    Department Credit Committee Review  locked
    Credit Analysis                     locked
    Trops                               locked
    no application at all               not locked

The reopen path is untouched: a case returned for rework, or with an
information request outstanding, still unlocks wherever it sits.

Verified: py_compile clean, every stage above measured.

Usage (from project root, .venv active):
    python scripts\\patch_lk1_branch_keeps_its_case.py            # dry run
    python scripts\\patch_lk1_branch_keeps_its_case.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_lk1"

OLD = '''def _deal_locked(deal: dict) -> bool:
    return _deal_submitted_to_credit(deal) and not _linked_app_reopens_origination(deal)'''

BLOCK = r'''def _deal_locked(deal: dict) -> bool:
    """Is the branch locked out of editing this deal?

    RULING (2026-08-18): "what did we solution for, if the branch is not able
    to vote and recommend before it even flows to the department and not even
    credit yet? I thought we were clear that after the documents are gathered,
    that Submit is in fact Submit to the Branch Credit Committee."

    The routing was right and IS right - submitting sends the case to the
    branch's own committee. THE LOCK WAS THE STALE PART, and it predates all of
    that work.

    Its whole test was "does this deal have an lms_application_id?". Submitting
    creates one, because the deal and the loan application are one object the
    whole way. When that test was written, submitting MEANT going to credit, so
    the lock and the words "with Credit" were both true.

    They are not true now. A case at a BRANCH COMMITTEE STAGE has not left the
    branch: their own committee holds it, their own people vote on it, and if
    that committee asks for a document the branch should be able to attach it
    without a rework loop to unlock their own case.

    So: the branch keeps the case while their committee has it. The lock falls
    when the case moves past the branch - to the department, to credit, and
    beyond - which is when it has genuinely left them.
    """
    if not _deal_submitted_to_credit(deal):
        return False
    if _linked_app_reopens_origination(deal):
        return False
    stage = str(deal.get("stage", "") or "").lower()
    if "branch" in stage and "committee" in stage:
        return False
    return True

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "the branch keeps the case while their committee has it" in s or \
       "RULING (2026-08-18)" in s and "_deal_locked" in s and "branch" in s.lower() \
       and "committee\" in stage" in s:
        print("ABORT: LK1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the lock test matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, BLOCK.rstrip(), 1)
    print("  ok  the branch keeps its case while its own committee holds it")

    if "_linked_app_reopens_origination" not in BLOCK:
        print("ABORT: the reopen path is gone - a case returned for rework")
        print("       would stay locked and the branch could not fix it.")
        return 1
    if "_deal_submitted_to_credit" not in BLOCK:
        print("ABORT: an unsubmitted deal would lock.")
        return 1
    if '"branch" in stage' not in BLOCK:
        print("ABORT: the branch committee stage is not exempted, which is the")
        print("       whole point of this patch.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: reopen intact, unsubmitted free, branch exempt")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. A branch keeps its case until it leaves the branch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
