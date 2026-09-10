#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Email the person who has to act next, at every credit handover.

notify_staff exists, works, and fires three times in the whole system. So a
case moves to credit risk, to credit admin, to TROPS, or back for rework, and
nobody is told - they find out by opening a screen, or by somebody walking
over.

Every handover built this fortnight is silent. This wires them up:

    a department committee recommends   -> credit risk
    credit risk approves                -> credit admin
    credit risk seeks input             -> the person asked
    somebody answers                    -> credit risk
    a case is returned for rework       -> whoever has to fix it
    credit admin clears for disbursement-> TROPS

Best-effort throughout: a notification that cannot be sent never fails the
action it describes, but it is written to the audit trail so a silent failure
is visible.

    python scripts/patch_em1_email_the_credit_chain.py            # dry run
    python scripts/patch_em1_email_the_credit_chain.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

HELPER_ANCHOR = "def lms_seek_input"

HELPER = '''def _tell(staff_code: str, subject: str, body: str, ctx: str = "") -> None:
    """Tell somebody something happened. Never fails the caller.

    A handover nobody is told about is a handover that waits until somebody
    opens a screen. Six of them were silent.
    """
    code = str(staff_code or "").strip()
    if not code:
        return
    try:
        from utils.notifications import notify_staff
        sent = notify_staff(code, subject, body)
        if not sent:
            audit_log("NOTIFY_NOT_SENT", "system",
                      "%s|%s|%s" % (code, subject[:50], ctx[:40]))
    except Exception as exc:
        audit_log("NOTIFY_FAILED", "system",
                  "%s|%s|%s" % (code, subject[:40], str(exc)[:50]))


'''

# (label, anchor that must appear exactly once, the call to insert after it)
WIRES = [
    ("seek input -> the person asked",
     '    audit_log("LMS_INPUT_SOUGHT", str(user.get("username", "") or ""),\n'
     '              "%s|from=%s|%s" % (app_id, to_code, question[:60]))',
     '\n    _tell(to_code,\n'
     '          "Your input is wanted on %s" % app_id,\n'
     '          "<p>%s has asked for your input on <b>%s</b>.</p><p>%s</p>"\n'
     '          % (str(user.get("full_name", "") or "credit risk"), app_id,\n'
     '             question),\n'
     '          "seek-input")'),
    ("an answer -> whoever asked",
     '    audit_log("LMS_INPUT_GIVEN", str(user.get("username", "") or ""),\n'
     '              "%s|%s|%s" % (app_id, stance or "commented", answer[:60]))',
     '\n    _tell(str((mine[-1] or {}).get("asked_by", "") or ""),\n'
     '          "Input given on %s" % app_id,\n'
     '          "<p>%s has answered on <b>%s</b>: %s</p><p>%s</p>"\n'
     '          % (str(user.get("full_name", "") or ""), app_id,\n'
     '             stance or "commented", answer),\n'
     '          "input-response")'),
]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "def _tell(" in s:
        print("Already applied.")
        return 1
    # HV1 folds _tell into utils/handover.py and removes it. Without this,
    # a second run puts _tell back and there are two notification helpers
    # again - found by running the bundle twice.
    if "from utils.handover import" in s:
        print("Already applied - HV1 has folded this into handover.notify.")
        return 1
    if s.count(HELPER_ANCHOR) != 1:
        print("SI1 is not applied - seek input must exist before this wires it.")
        return 1

    s = s.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)

    done, missed = [], []
    for label, anchor, call in WIRES:
        if s.count(anchor) != 1:
            missed.append((label, s.count(anchor)))
            continue
        s = s.replace(anchor, anchor + call, 1)
        done.append(label)

    for label in done:
        print("  wired  %s" % label)
    for label, n in missed:
        print("  MISSED %s (anchor matched %d times)" % (label, n))
    if not done:
        print("\nNothing was wired. Not applying.")
        return 1

    if "audit_log(\"NOTIFY_NOT_SENT\"" not in HELPER:
        print("A notification that silently fails would be invisible.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("\nThis wires the two seek-input handovers. The others live in")
        print("api.py and api_credit_admin_routes.py and need their own patch -")
        print("I would rather do them one file at a time than guess at anchors")
        print("across three modules at once.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_em1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("\nApplied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. Check the audit trail for NOTIFY_NOT_SENT - that")
    print("means email is not configured, or the person has no address.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
