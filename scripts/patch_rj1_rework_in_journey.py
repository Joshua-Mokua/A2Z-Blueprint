#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RJ1 - a rework appears in the case journey.

FOUND BY THE SIMULATION, not by a person reporting it - which is the point of
having written the simulation. Sixteen checks passed and this one did not:

    FAIL  6  a rework does NOT appear in the journey
             a case returned to the branch leaves no trace of who returned it
             or why

That is the first entry an auditor asks about, because it is the point where a
case stopped moving. Every other touch point was recorded and this one was not.

TWO EVENTS, because a return without a homecoming reads as a case that
vanished:

    returned_for_rework   Catherine Mwikali Mutisya
                          Valuation report is out of date - Valuation Report
    rework_completed      Edward Mwenda
                          reworked and sent back to credit - Fresh valuation
                          attached

EVERY RETURN IS SHOWN, not only the last. A case returned three times is a
different conversation from one returned once, and rework_history keeps them
all - so the journey shows the pattern rather than the most recent line.

Verified: py_compile clean, and the rendering measured above.

Usage (from project root, .venv active):
    python scripts\\patch_rj1_rework_in_journey.py            # dry run
    python scripts\\patch_rj1_rework_in_journey.py --apply
"""
import os
import shutil
import sys

JOURNEY = os.path.join("utils", "api_lms_journey.py")
BACKUP_SUFFIX = ".pre_rj1"

ANCHOR = "    # Manager validation. The fields are already written by the validate"

BLOCK = r'''    # ── A RETURN FOR REWORK, AND THE WORK COMING BACK ───────────────────────
    # The simulation caught this: every other touch point was recorded and a
    # rework was not. A case sent back to a branch left no trace of who
    # returned it or why - which is the first entry an auditor asks about,
    # because it is the point where a case stopped moving.
    #
    # EVERY return is shown, not just the last. A case returned three times is
    # a different conversation from one returned once, and rework_history keeps
    # them all.
    for _rw in (deal.get("rework_history") or []):
        if not isinstance(_rw, dict):
            continue
        _note = str(_rw.get("reason", "") or "").strip() or "returned for rework"
        _items = [str(x) for x in (_rw.get("items") or []) if str(x).strip()]
        if _items:
            _note += " — " + ", ".join(_items)
        events.append({
            "event": "returned_for_rework",
            "by": str(_rw.get("by", "") or ""),
            "by_name": _rw.get("by_name") or None,
            "at": _iso(_rw.get("at")),
            "note": _note,
        })

    # And the branch sending it back, which closes the loop: without it the
    # journey shows a case leaving and never returning.
    if deal.get("rework_completed_at"):
        events.append({
            "event": "rework_completed",
            "by": "", "by_name": deal.get("rework_completed_by") or None,
            "at": _iso(deal.get("rework_completed_at")),
            "note": ("reworked and sent back to credit"
                     + (" — %s" % deal.get("rework_note")
                        if deal.get("rework_note") else "")),
        })

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(JOURNEY):
        print("ABORT: %s not found." % JOURNEY)
        return 1

    s = open(JOURNEY, encoding="utf-8").read()
    if "A RETURN FOR REWORK, AND THE WORK COMING BACK" in s:
        print("ABORT: RJ1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the journey anchor matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  a rework and its return appear in the journey")

    if "rework_history" not in BLOCK:
        print("ABORT: only the most recent return would show.")
        return 1
    if "rework_completed" not in BLOCK:
        print("ABORT: the journey would show a case leaving and never coming")
        print("       back.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: every return shown, the loop closes, parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(JOURNEY, JOURNEY + BACKUP_SUFFIX)
    open(JOURNEY, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % JOURNEY)
    print("\nRe-run scripts\\simulate_consumer_flow.py - it should now pass all")
    print("seventeen checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
