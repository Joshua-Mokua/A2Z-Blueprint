#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DM1 - a credit decision moves the case.

RULING (2026-08-15). A decision recorded a verdict and the case sat where it
was, waiting for somebody to find a separate button. That is the committee
fault one gate further on: the state changed and the case did not move.

APPROVED goes to credit admin, carrying its conditions so they can be ticked
there. Nobody re-submits what has just been approved.

DECLINED GOES BACK TO THE OWNER, NOT TO CLOSED LOST. The ruling is explicit:
"it should go back to the owner who is to click on appeal or accept the
decision - if they accept it closes as lost."

So a decline is a question put to the person who raised the case, not the end
of it. Closing it here would take that choice away, and an appeal would then
have to reopen a closed deal.

TWO THINGS THIS PATCH ALMOST GOT WRONG, both worth recording:

  `logger` does not exist in this module. Calling it inside an except would
  raise a NameError FROM THE HANDLER and lose the decision - which is how a
  swallowed NameError hid here for two years. The audit trail is what this
  module has.

  `_dt` is imported LOCALLY inside two other functions in this file, meaning
  different things in each - the module in one, the class in the other. This
  function has neither, so `_dt.now()` raised a NameError that my own except
  swallowed: the decision recorded, the case did not move, and nothing said
  why. Caught only by driving the endpoint and looking at the status.

Measured:

    approve   status=credit_admin  awaiting_credit_admin  2 conditions carried
    decline   status=declined      back to the owner      appeal window open

Verified: py_compile clean, the LMS router loads its 52 routes.

Usage (from project root, .venv active):
    python scripts\\patch_dm1_decision_moves_case.py            # dry run
    python scripts\\patch_dm1_decision_moves_case.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_dm1"

ANCHOR = "    updated = lam.get(app_id)"

BLOCK = r'''    # ── A DECISION MOVES THE CASE ───────────────────────────────────────────
    # RULING (2026-08-15). Until now a decision recorded a verdict and the case
    # sat where it was, waiting for somebody to find a separate button. That is
    # the same fault the committee had, one gate further on: the state changed
    # and the case did not move.
    #
    # APPROVED goes to credit admin, carrying its conditions so they can be
    # ticked there. Nobody re-submits what has just been approved.
    #
    # DECLINED GOES BACK TO THE OWNER, NOT TO CLOSED LOST. The ruling is
    # explicit: "it should probably go back to the owner who is to click on
    # appeal or accept the decision - if they accept it closes as lost."
    #
    # So a decline is not the end of the case; it is a question put to the
    # person who raised it. Closing it here would take that choice away, and
    # an appeal would then have to reopen a closed deal.
    # `datetime`, NOT `_dt`. _dt is imported locally inside two other
    # functions here and means different things in each - the module in one,
    # the class in the other. This function has neither, so datetime.now() raised a
    # NameError that my own except swallowed: the decision recorded, the case
    # did not move, and nothing said why. Exactly the shape of the two-year
    # NameError this codebase already carried once.
    try:
        if verdict_normalized == "approved":
            _conds = list(getattr(payload, "conditions", None) or [])
            lam.update(app_id, {
                "status": "credit_admin",
                "awaiting_credit_admin": True,
                "approved_at": datetime.now().isoformat(timespec="seconds"),
                "approved_by_name": str(user.get("full_name", "") or ""),
                "decision_conditions": _conds,
            })
            audit_log("LMS_APPROVED_TO_CREDIT_ADMIN",
                      str(user.get("username", "") or ""),
                      "%s|%d condition(s)" % (app_id, len(_conds)))
        elif verdict_normalized == "declined":
            lam.update(app_id, {
                "status": "declined",
                "awaiting_owner_response": True,
                "declined_at": datetime.now().isoformat(timespec="seconds"),
                "declined_by_name": str(user.get("full_name", "") or ""),
                "decline_reason": str(getattr(payload, "reason", "") or ""),
                # The owner chooses: appeal, or accept and close as lost.
                "appeal_window_open": True,
            })
            audit_log("LMS_DECLINED_TO_OWNER",
                      str(user.get("username", "") or ""), app_id)
    except Exception as _exc:
        # THIS MODULE HAS NO LOGGER. Calling one inside an except would raise a
        # NameError from the handler and lose the decision entirely - which is
        # exactly how a silent `except: pass` hid a NameError here for two
        # years. The audit trail is what this module has, so use it.
        try:
            audit_log("LMS_DECISION_MOVE_FAILED",
                      str(user.get("username", "") or ""),
                      "%s|%s: %s" % (app_id, type(_exc).__name__, str(_exc)[:80]))
        except Exception:
            pass

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "A DECISION MOVES THE CASE" in s:
        print("ABORT: DM1 looks applied.")
        return 1
    i = s.find("def lms_application_decision")
    if i < 0:
        print("ABORT: the decision endpoint is not in this file.")
        return 1
    j = s.find("\n@router.", i)
    seg = s[i:j if j > 0 else len(s)]
    if seg.count(ANCHOR) != 1:
        print("ABORT: the anchor matched %d times in the decision endpoint."
              % seg.count(ANCHOR))
        return 1
    s = s[:i] + seg.replace(ANCHOR, BLOCK + ANCHOR, 1) + (s[j:] if j > 0 else "")
    print("  ok  approved goes to credit admin, declined goes to the owner")

    if "_dt.now()" in BLOCK:
        print("ABORT: _dt is a LOCAL import in other functions here and does")
        print("       not exist in this one - it would raise a NameError that")
        print("       the except would swallow.")
        return 1
    if "logger." in BLOCK:
        print("ABORT: this module has no logger; calling one inside the except")
        print("       would raise from the handler and lose the decision.")
        return 1
    if "Closed Lost" in BLOCK or "closed_lost" in BLOCK:
        print("ABORT: a decline must NOT close the case - the owner chooses")
        print("       whether to appeal or accept.")
        return 1
    if "awaiting_owner_response" not in BLOCK:
        print("ABORT: a declined case would not reach the owner.")
        return 1
    if "decision_conditions" not in BLOCK:
        print("ABORT: the conditions would not travel to credit admin, so")
        print("       there would be nothing to tick there.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: right clock, no logger, decline stays open")

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
    print("\nRestart uvicorn. An approval reaches credit admin with its")
    print("conditions; a decline reaches the owner with the appeal open.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
