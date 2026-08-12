#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AV1 - the deal moves when the manager validates it.

RULING (2026-08-12): "the stage was to move automatically once the manager
validates, but now the owner has to go and move it from Actions to the next
stage."

Validation was unlocking the move and leaving the owner to make it. That is a
second action for a decision already taken - and worse, the deal sits at the
old stage in every queue and report in between, so a branch looks stalled when
it is not.

FOUR CONSTRAINTS, each one a way this could have gone wrong:

    ONE STAGE, FROM THE CONFIGURED FLOW. Not a jump to credit - the same single
    step the owner would have made, so nothing skips a gate.

    ONLY ON APPROVAL. A queried deal goes back to its owner and must not move
    forward; advancing on a query would push onward the very work a manager had
    just sent back.

    NEVER OUT OF A TERMINAL STAGE, AND NEVER INTO ONE. A closed deal stays
    closed - validation must not become a way to reopen it - and auto-advancing
    into Closed Won would declare an outcome nobody decided.

    BEST EFFORT. A failure here leaves the deal validated and unmoved, which is
    exactly where it used to be. Validation must not fail because an advance
    did.

Measured against the real product flows:

    Personal Loan, validated at Initiation     -> Negotiation
    Personal Loan, validated at Documentation  -> Branch Credit Committee Review
    Personal Loan, validated at Closed Won     -> stays

A SEPARATE FINDING WHILE TESTING THIS, and it explains the fixed-deposit case:

    Fixed Deposit    ["Lead/Cutomer Instructions", "Fixed Deposit Openned"]
    Savings Account  ["Lead", "Documentation"]

Neither flow has a CLOSING stage. There is nowhere for the owner to close to,
so those deals cannot be finished at all - which is exactly "the owner is
unable to close". That is CONFIG, not code: Admin > product flow, add Closed
Won / Closed Lost to those flows. No patch should guess what the bank wants a
flow to end with.

(Two spellings in that config reach users: "Cutomer" and "Openned".)

Usage (from project root, .venv active):
    python scripts\\patch_av1_advance_on_validation.py            # dry run
    python scripts\\patch_av1_advance_on_validation.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_av1"

ANCHOR = """    # Persist the validation to the DB read path. The analytics assured value
    # and funnel read deals via _acquire_scoped_deals (DB-first); without this
    # sync, manager_validated would live only in the JSON store and the DB
    # readers would never see it."""

ADVANCE = r'''    # ── ADVANCE ON VALIDATION (pilot, 2026-08-12) ───────────────────────────
    # "The stage was to move automatically once the manager validates, but now
    # the owner has to go and move it from Actions to the next stage."
    #
    # Validation was unlocking the move and leaving the owner to make it. That
    # is a second action for a decision already taken - and worse, the deal
    # sits at the old stage in every queue and report in between, so the branch
    # looks stalled when it is not.
    #
    # ONE STAGE, FROM THE CONFIGURED FLOW. Not a jump to credit: the same
    # single step the owner would have made, so nothing skips a gate.
    #
    # ONLY ON APPROVAL, never on a query - a queried deal goes back to the
    # owner and must not move forward.
    #
    # NEVER OUT OF A TERMINAL STAGE, and never past one. A closed deal stays
    # closed, and validation must not be a way to reopen it.
    #
    # BEST EFFORT: a failure here leaves the deal validated and unmoved, which
    # is exactly where it used to be. Validation must not fail because an
    # advance did.
    if payload.approved:
        try:
            _d = pm.get_deal(deal_id) or {}
            _cur = str(_d.get("stage") or "")
            _flow = _stage_flow_for(_d.get("product_type") or _d.get("product", "")) or []
            if _cur in _flow:
                _i = _flow.index(_cur)
                if _i + 1 < len(_flow):
                    _next = _flow[_i + 1]
                    _terminal = ("closed" in _cur.lower(), "closed" in _next.lower())
                    if not any(_terminal):
                        pm.update_stage(deal_id, _next,
                                        "Advanced on manager validation by %s."
                                        % (user.get("full_name") or user.get("username") or ""),
                                        str(user.get("username", "") or ""))
                        _audit("DEAL_AUTO_ADVANCED", user,
                               "%s: %s -> %s on validation" % (deal_id, _cur, _next))
        except Exception as _exc:
            logger.warning("could not advance %s on validation: %s", deal_id, _exc)

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    api = open(API, encoding="utf-8").read()
    if "ADVANCE ON VALIDATION" in api:
        print("ABORT: AV1 looks applied.")
        return 1
    if api.count(ANCHOR) != 1:
        print("ABORT: the validate anchor matched %d times." % api.count(ANCHOR))
        return 1

    api = api.replace(ANCHOR, ADVANCE + ANCHOR, 1)
    print("  ok  advance on validation")

    if "if payload.approved:" not in ADVANCE:
        print("ABORT: a QUERIED deal would advance - a manager sending work")
        print("       back would push it forward instead.")
        return 1
    if "_i + 1 < len(_flow)" not in ADVANCE:
        print("ABORT: the advance is not limited to one stage.")
        return 1
    if "closed" not in ADVANCE.lower():
        print("ABORT: terminal stages are not guarded - validation could reopen")
        print("       a closed deal, or declare one won.")
        return 1
    if "could not advance" not in ADVANCE:
        print("ABORT: a failed advance would fail the validation with it.")
        return 1
    print("  ok  post-checks: approval only, one stage, terminals guarded")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Restart uvicorn. A manager validating now moves the deal on by one")
    print("stage; the owner no longer repeats the decision.")
    print("")
    print("SEPARATELY, in Admin > product flow: Fixed Deposit and Savings")
    print("Account have NO closing stage, so their deals cannot be closed at")
    print("all. Add Closed Won / Closed Lost to those flows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
