#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
JR1 - the case journey records the decisions that change who controls a deal.

RULING (2026-08-12): "why is the manager validation not adding to the case
journey? We had defined that any touch point of the case has to be recorded -
could it be that the journey is not capturing everything?"

It was not. The journey carried creation, stage changes, committee outcomes,
appeals, affordability and SLA. Three things left NO trace at all:

    MANAGER VALIDATION - the gate that lets a deal move
    REFERRAL           - the deal changing hands
    CANCELLATION       - a request to stop, and the answer to it

A case journey missing those cannot answer "who let this through", which is the
first question anybody asks of a credit file afterwards - and the reason the
journey exists rather than being a nice-to-have.

NOTHING NEW IS RECORDED. Every field these events read was already being
written: validated_by_name and validated_by_role by the validate endpoint, the
referral fields by the referral flow, the cancel fields by the cancellation
queue. They were simply never read back. So this is complete for deals that
already exist, not only for new ones.

TWO CHOICES WORTH STATING:

  A DECLINED REFERRAL IS STILL RECORDED. Leaving it out would make a deal look
  as though it had never moved, when somebody was asked and said no.

  REQUEST AND APPROVAL ARE SEPARATE MOMENTS. The gap between them is often
  exactly what somebody is asking about.

Verified: py_compile clean, and a deal carrying all three renders

    deal_created        Acme - Personal Loan
    manager_validated   Dennis Ojiambo (Branch Manager)
    referral_accepted   Edward M to Nancy O
    cancel_requested

Usage (from project root, .venv active):
    python scripts\\patch_jr1_journey_touchpoints.py            # dry run
    python scripts\\patch_jr1_journey_touchpoints.py --apply
"""
import os
import shutil
import sys

JOURNEY = os.path.join("utils", "api_lms_journey.py")
BACKUP_SUFFIX = ".pre_jr1"

ANCHOR = "    return events\n\n\n# \u2500\u2500 public entry point"

EVENTS = r'''    # ── TOUCH POINTS THAT WERE NOT BEING RECORDED (pilot, 2026-08-12) ────────
    # "We had defined that any touch point of the case has to be recorded -
    # could it be that the journey is not capturing everything?"
    #
    # It was not. The journey carried creation, stage changes, committee
    # outcomes, appeals, affordability and SLA - but three decisions that
    # CHANGE WHO CONTROLS THE DEAL left no trace at all:
    #
    #     MANAGER VALIDATION - the gate that lets a deal move at all
    #     REFERRAL           - the deal changing hands
    #     CANCELLATION       - a request to stop, and the answer to it
    #
    # A case journey missing those cannot answer "who let this through", which
    # is the first question anybody asks of a credit file after the fact.

    # Manager validation. The fields are already written by the validate
    # endpoint (Item 5) - nothing new is recorded, it was simply never read.
    if deal.get("manager_validated"):
        who = str(deal.get("validated_by_name", "") or "")
        role = str(deal.get("validated_by_role", "") or "")
        events.append({
            "event": "manager_validated",
            "by": str(deal.get("validated_by_code", "") or ""),
            "by_name": who or None,
            "at": _iso(deal.get("validated_at")),
            "note": ("Validated by %s%s" % (who or "a manager",
                                            " (%s)" % role if role else ""))
                    + " — the deal may now progress",
        })

    # Referral. Recorded whether or not it was accepted: a declined referral is
    # part of the history, and leaving it out would make a deal look as though
    # it had never moved.
    rstatus = str(deal.get("referral_status", "") or "").strip().lower()
    if rstatus:
        frm = str(deal.get("referred_by_name", "") or "")
        to = str(deal.get("referred_to_name", "") or "")
        events.append({
            "event": "referral_%s" % rstatus,
            "by": str(deal.get("referred_by", "") or ""),
            "by_name": frm or None,
            "at": _iso(deal.get("referred_at")),
            "note": ("Referred%s%s — %s"
                     % (" by %s" % frm if frm else "",
                        " to %s" % to if to else "", rstatus)),
        })

    # Cancellation, requested and answered as separate moments - the gap
    # between them is often the thing somebody is asking about.
    if deal.get("cancel_requested"):
        events.append({
            "event": "cancel_requested",
            "by": str(deal.get("cancel_requested_by", "") or ""),
            "by_name": deal.get("cancel_requested_by_name") or None,
            "at": _iso(deal.get("cancel_requested_at")),
            "note": "Cancellation requested"
                    + (" — %s" % deal.get("cancel_request_reason")
                       if deal.get("cancel_request_reason") else ""),
        })
    if deal.get("cancel_approved"):
        events.append({
            "event": "cancel_approved",
            "by": str(deal.get("cancel_approved_by", "") or ""),
            "by_name": deal.get("cancel_approved_by_name") or None,
            "at": _iso(deal.get("cancel_approved_at")),
            "note": "Cancellation approved",
        })

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(JOURNEY):
        print("ABORT: %s not found." % JOURNEY)
        return 1

    src = open(JOURNEY, encoding="utf-8").read()
    if "TOUCH POINTS THAT WERE NOT BEING RECORDED" in src:
        print("ABORT: JR1 looks applied.")
        return 1
    if src.count(ANCHOR) != 1:
        print("ABORT: the event-builder anchor matched %d times." % src.count(ANCHOR))
        return 1

    src = src.replace(ANCHOR, EVENTS + ANCHOR, 1)
    print("  ok  validation, referral and cancellation events")

    for label, needle in (("manager validation", "manager_validated"),
                          ("referral", "referral_%s"),
                          ("cancellation", "cancel_requested")):
        if needle not in EVENTS:
            print("ABORT: %s is still not recorded." % label)
            return 1
    if "if rstatus:" not in EVENTS:
        print("ABORT: only some referral outcomes are recorded - a declined")
        print("       referral would vanish from the history.")
        return 1
    print("  ok  post-checks: all three, including declined referrals")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(JOURNEY, JOURNEY + BACKUP_SUFFIX)
    open(JOURNEY, "w", encoding="utf-8", newline="").write(src)
    print("APPLIED %s" % JOURNEY)

    import py_compile
    try:
        py_compile.compile(JOURNEY, doraise=True)
        print("  ok  api_lms_journey.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Restart uvicorn and open any validated deal's Case Journey - the")
    print("validation appears with who did it and when. Existing deals show it")
    print("too: those fields were always written, never read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
