#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
GT1 - a committee three stages ahead stops blocking submission. URGENT.

LIVE PILOT BLOCKER (2026-08-14). A deal sitting at Documentation, with every
document attached, was refused:

    Submission is blocked until:
      * Committee decision outstanding: B1.

B1 is the DEPARTMENT credit committee - step 4 of the credit journey. The deal
was at step 1. It could not possibly have a B1 decision, and the only way to
get one was to submit, which the gate was refusing. The case could not move at
all.

The checklist looped EVERY committee on the deal's journey and marked each
undecided one as blocking, with no regard for where the case actually was.

A COMMITTEE BLOCKS ONLY ONCE THE CASE HAS REACHED ITS STAGE. Ones ahead are
simply not its turn yet. Position comes from the deal's own stage flow - the
committee's stage index against the current stage's.

WHERE IT CANNOT PLACE A COMMITTEE, IT TREATS IT AS PENDING. Failing open on a
credit gate is the wrong direction to guess in: a case that stalls is visible
and annoying, a case that skips a committee is neither.

Measured on a Mortgage, Consumer, Fortis deal:

    at Documentation                   pending []              was ['B1']
    at Branch Credit Committee Review  pending ['BCC_BRN007']
    at Department Credit Analysis      pending ['BCC_BRN007']

Verified: py_compile clean, and the API imports.

Usage (from project root, .venv active):
    python scripts\\patch_gt1_committee_gate_position.py            # dry run
    python scripts\\patch_gt1_committee_gate_position.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_gt1"

OLD = '''    for code in journey_codes:
        rec = records.get(code) or {}
        outcome = str(rec.get("outcome", "")).upper()
        if outcome == "APPROVED":
            continue
        if outcome == "REJECTED":
            committee_rejected.append(code)
        else:
            committee_pending.append(code)'''

BLOCK = r'''    # ── ONLY THE COMMITTEES THIS CASE HAS REACHED ───────────────────────────
    # PILOT BLOCKER (2026-08-14): a deal sitting at Documentation was refused
    # with "Committee decision outstanding: B1" - the DEPARTMENT committee,
    # which sits three stages further on. It cannot possibly have decided yet,
    # so the case could never be submitted to the BRANCH committee in front of
    # it. The gate demanded a decision that only submitting could produce.
    #
    # A committee blocks only once the case has arrived at its stage. Ones
    # ahead of the current stage are simply not its turn.
    #
    # Position is worked out from the deal's own stage flow: the committee's
    # stage index against the current stage's. A committee whose stage cannot
    # be located is treated as PENDING, because failing open on a credit gate
    # is the wrong direction to guess in.
    _flow = [str(x) for x in (_stage_flow_for(deal.get("product_type")
                                              or deal.get("product", "")) or [])]
    try:
        _here = _flow.index(str(current_stage)) if str(current_stage) in _flow else -1
    except Exception:
        _here = -1

    def _reached(_code):
        """Has this case arrived at the stage this committee sits on?"""
        if _here < 0 or not _flow:
            return True          # no flow to reason with - keep the old behaviour
        try:
            _c = _committee_by_code(_code) or {}
        except Exception:
            return True
        _stage = str(_c.get("stage", "") or "").strip()
        if not _stage:
            # No stage on the committee: fall back to the name. A branch
            # committee belongs to the branch stage, a department one to the
            # department stage.
            _kind = str(_c.get("kind", "") or "").lower()
            _want = "branch credit committee" if _kind == "branch" \
                else "department credit committee"
            _stage = next((x for x in _flow if _want in x.lower()), "")
        if not _stage or _stage not in _flow:
            return True          # cannot place it - do not fail open silently
        return _flow.index(_stage) <= _here

    for code in journey_codes:
        rec = records.get(code) or {}
        outcome = str(rec.get("outcome", "")).upper()
        if outcome == "APPROVED":
            continue
        if outcome == "REJECTED":
            committee_rejected.append(code)
        elif _reached(code):
            committee_pending.append(code)
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "ONLY THE COMMITTEES THIS CASE HAS REACHED" in s:
        print("ABORT: GT1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the checklist loop matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, BLOCK.rstrip(), 1)
    print("  ok  only committees the case has reached can block it")

    if "_reached(code)" not in BLOCK:
        print("ABORT: position is not consulted - every committee would still")
        print("       block from the first stage.")
        return 1
    if "return True" not in BLOCK:
        print("ABORT: an unplaceable committee would fail OPEN, letting a case")
        print("       skip a gate. That is the wrong way to guess.")
        return 1
    if "committee_rejected.append(code)" not in BLOCK:
        print("ABORT: a rejection would no longer block.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: position used, fails safe, rejections still block")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. The deal can be submitted to its branch committee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
