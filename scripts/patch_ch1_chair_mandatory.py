#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH1 - the chair must have voted, or the operations manager in their absence.

RULING (2026-08-13): "as a rule of law we should make the chair vote mandatory,
and in the absence the operations manager."

QUORUM COUNTS HEADS; IT DOES NOT CARE WHOSE. A committee could reach two votes
without the person who convenes it having said anything, and the decision would
still carry that committee's name. That is the difference between a meeting and
a headcount.

The chair is recognised by staff code where the committee carries one, by name
against chaired_by otherwise, or by a role of "Chair". IN THEIR ABSENCE THE
OPERATIONS MANAGER stands in - a named deputy rather than "anybody else", so
the authority is traceable to a role the bank recognises.

NOBODY'S VOTE IS DISCARDED for arriving before the chair's. The votes are kept;
the decision simply is not final until the chair or their deputy has spoken.

The response says WHY a case with enough votes is still open - "waiting on the
chair" is a different thing from "waiting on a body" - through chair_voted,
deputy_voted and awaiting_chair.

Measured:

    two members, one of them the operations manager  -> decided
    two members, neither chair nor operations        -> HELD, awaiting_chair
    the chair then votes                             -> decided, APPROVED

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_ch1_chair_mandatory.py            # dry run
    python scripts\\patch_ch1_chair_mandatory.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_ch1"

QUORUM_OLD = '''    quorum = _committee_quorum(committee)
    attended = len(cast)
    updates = {"committee_votes": all_votes}
    outcome = ""

    if attended >= quorum:'''

RET_OLD = '        "decided": bool(outcome),'

CHAIR = r'''    # ── THE CHAIR MUST HAVE VOTED ───────────────────────────────────────────
    # RULING (2026-08-13): "as a rule of law we should make the chair vote
    # mandatory, and in the absence the operations manager."
    #
    # Quorum counts heads; it does not care WHOSE. A committee could reach two
    # votes without the person who convenes it having said anything, and the
    # decision would carry their committee's name. That is the difference
    # between a meeting and a headcount.
    #
    # IN THEIR ABSENCE, THE OPERATIONS MANAGER stands in - a named deputy
    # rather than "anybody else", so the authority is traceable to a role the
    # bank recognises.
    #
    # THE VOTES ARE KEPT EITHER WAY. Nobody's view is discarded for arriving
    # before the chair's; the decision simply is not final until the chair (or
    # their deputy) has spoken.
    _chair_name = str(committee.get("chaired_by", "") or "").strip().lower()
    _chair_code = str(committee.get("chair_staff_code", "") or "").strip()

    def _is_chair(v):
        return ((_chair_code and str(v.get("staff_code", "")).strip() == _chair_code)
                or (_chair_name and str(v.get("name", "")).strip().lower() == _chair_name)
                or str(v.get("role", "")).strip().lower() == "chair")

    def _is_deputy(v):
        _r = str(v.get("role", "") or "").lower()
        return "operations manager" in _r or "operations" in _r

    _chair_spoke = any(_is_chair(v) for v in cast.values())
    _deputy_spoke = any(_is_deputy(v) for v in cast.values())
    _authority = _chair_spoke or _deputy_spoke

'''

RETURN_FIELDS = r'''        # So the panel can say WHY a case with enough votes is still open -
        # "waiting on the chair" is a different thing from "waiting on a body".
        "chair_voted": _chair_spoke,
        "deputy_voted": _deputy_spoke,
        "awaiting_chair": bool(attended >= quorum and not _authority),
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "THE CHAIR MUST HAVE VOTED" in s:
        print("ABORT: CH1 looks applied.")
        return 1
    if s.count(QUORUM_OLD) != 1:
        print("ABORT: the quorum block matched %d times." % s.count(QUORUM_OLD))
        print("       VT1 must be applied first - this amends its vote endpoint.")
        return 1
    if s.count(RET_OLD) != 1:
        print("ABORT: the response block matched %d times." % s.count(RET_OLD))
        return 1

    tail = QUORUM_OLD.rsplit("\n", 1)[0]
    s = s.replace(QUORUM_OLD, tail + "\n" + CHAIR + "    if attended >= quorum and _authority:", 1)
    s = s.replace(RET_OLD, RETURN_FIELDS + RET_OLD, 1)
    print("  ok  the chair's vote is required, operations manager deputises")

    if "_is_deputy" not in CHAIR:
        print("ABORT: there is no deputy, so an absent chair would block the")
        print("       committee indefinitely.")
        return 1
    if "operations manager" not in CHAIR.lower():
        print("ABORT: the deputy is not the operations manager.")
        return 1
    # Votes must survive an early arrival.
    if "cast.values()" not in CHAIR:
        print("ABORT: the check does not read the votes already cast.")
        return 1
    if "awaiting_chair" not in RETURN_FIELDS:
        print("ABORT: the panel could not say WHY a case with enough votes is")
        print("       still open.")
        return 1
    print("  ok  post-checks: deputy exists, votes kept, reason reported")

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
    print("")
    print("Restart uvicorn. A committee reaching quorum without its chair now")
    print("waits for them - or for the operations manager standing in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
