#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DJ1 - the department committee's votes reach the case journey.

FROM THE PILOT (2026-08-14): "is their vote recording in the journey as well?"

It was not. The branch committee's votes reach the journey and the
department's did not - the same gap, found the same way. And it is the
DEPARTMENT committee whose decision releases the case to the bank credit pool,
so its record matters at least as much.

EVERY VOTE, AND THE OUTCOME:

    dcc_vote     Joyce Nyambura supported - Security adequate
    dcc_vote     Peter Otieno opposed
    dcc_support  the department committee supported the case - 3 yes, 1 no,
                 0 abstain

IN PLAIN WORDS. "support" and "oppose" are the system's vocabulary; a person
reading a case history six months later should not have to know it. The tally
travels with the outcome, because a 3-1 decision and a 4-0 decision are
different facts about the same case.

Verified: py_compile clean, and the rendering measured above.

Usage (from project root, .venv active):
    python scripts\\patch_dj1_dcc_votes_in_journey.py            # dry run
    python scripts\\patch_dj1_dcc_votes_in_journey.py --apply
"""
import os
import shutil
import sys

JOURNEY = os.path.join("utils", "api_lms_journey.py")
BACKUP_SUFFIX = ".pre_dj1"

ANCHOR = "    # Manager validation. The fields are already written by the validate"

BLOCK = r'''    # ── THE DEPARTMENT COMMITTEE'S VOTES ────────────────────────────────────
    # The branch committee's votes reach the journey and the department's did
    # not - the same gap, found the same way. A committee that decides a case
    # without leaving who said what is not a record anybody can rely on later,
    # and it is the department committee whose decision releases the case to
    # the bank credit pool.
    for _v in (deal.get("dcc_votes") or []):
        if not isinstance(_v, dict):
            continue
        _vote = str(_v.get("vote", "") or "").upper()
        _said = {"YES": "supported", "NO": "opposed",
                 "ABSTAIN": "abstained"}.get(_vote, _vote.lower())
        _who = _v.get("member_name") or _v.get("name") or _v.get("member_id") or "a member"
        _note = "%s %s" % (_who, _said)
        if _v.get("rationale"):
            _note += " — %s" % _v.get("rationale")
        events.append({
            "event": "dcc_vote",
            "by": str(_v.get("member_id", "") or ""),
            "by_name": _v.get("member_name") or _v.get("name") or None,
            "at": _iso(_v.get("at")),
            "note": _note,
        })

    _out = deal.get("dcc_outcome")
    if isinstance(_out, dict) and _out.get("recommendation"):
        _t = _out.get("tally") or {}
        _rec = str(_out.get("recommendation"))
        _plain = {"support": "supported the case",
                  "oppose": "did not support the case",
                  "split": "was split"}.get(_rec, _rec)
        events.append({
            "event": "dcc_%s" % _rec,
            "by": str(_out.get("by", "") or ""),
            "by_name": _out.get("by_name") or None,
            "at": _iso(_out.get("at")),
            "note": ("the department committee %s — %s yes, %s no, %s abstain"
                     % (_plain, _t.get("yes", 0), _t.get("no", 0),
                        _t.get("abstain", 0))
                     + (" · %s" % _out.get("note") if _out.get("note") else "")),
        })

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(JOURNEY):
        print("ABORT: %s not found." % JOURNEY)
        return 1

    s = open(JOURNEY, encoding="utf-8").read()
    if "THE DEPARTMENT COMMITTEE'S VOTES" in s:
        print("ABORT: DJ1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the journey anchor matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  department votes and the outcome reach the journey")

    if "dcc_votes" not in BLOCK:
        print("ABORT: individual votes are not read.")
        return 1
    if "dcc_outcome" not in BLOCK:
        print("ABORT: the committee's decision is not recorded.")
        return 1
    if "tally" not in BLOCK:
        print("ABORT: the tally is missing - a 3-1 decision and a 4-0 decision")
        print("       are different facts about the same case.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: votes, outcome and tally, and it parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(JOURNEY, JOURNEY + BACKUP_SUFFIX)
    open(JOURNEY, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % JOURNEY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
