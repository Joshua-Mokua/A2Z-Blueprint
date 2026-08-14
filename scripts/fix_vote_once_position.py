#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Move the vote-once check to where it belongs. Repairs a misplaced VF1.

WHY THIS EXISTS. VF1's check was anchored on the quorum line, which sits AFTER
`cast[key] = {...}` - the line that records the vote. So it looked for a vote
the code had added two lines above and refused every FIRST vote with a 409.

The corrected VF1 anchors it before the recording, but it will not repair a
file that already has the block: the idempotence check asks "is the marker
present?", and a marker in the wrong place is still present. So it reports
"already a member votes once" and changes nothing.

This finds the block wherever it is, removes it, and puts it back immediately
after the line that READS the existing votes - before this vote joins them.

Safe to run twice: if the check is already in the right place it says so and
stops.

    python scripts\\fix_vote_once_position.py
    python scripts\\fix_vote_once_position.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP = API + ".pre_votefix"

READS = '    cast = dict(all_votes.get(code) or {})'
RECORDS = '    cast[key] = {'
MARK = '# \u2500\u2500 ONE VOTE PER MEMBER, AND IT STANDS'


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1
    s = open(API, encoding="utf-8").read()

    if MARK not in s:
        print("ABORT: the vote-once check is not in this file at all.")
        print("       Apply VF1 first.")
        return 1
    if s.count(READS) != 1 or s.count(RECORDS) != 1:
        print("ABORT: expected one `cast = dict(...)` and one `cast[key] = {`,")
        print("       found %d and %d. Not repairing blind."
              % (s.count(READS), s.count(RECORDS)))
        return 1

    at_mark = s.index(MARK)
    at_reads = s.index(READS)
    at_records = s.index(RECORDS)

    if at_reads < at_mark < at_records:
        print("The check is already between the read and the recording.")
        print("Nothing to do - the 409 has another cause.")
        return 0

    print("  the check sits AFTER the vote is recorded, so every first vote")
    print("  is refused. Moving it.")

    # The block runs from its comment banner to the end of the raise.
    start = s.rindex("\n", 0, at_mark) + 1
    end_marker = 'if _prev.get("at") else "")))'
    if end_marker not in s[start:]:
        print("ABORT: cannot find the end of the block.")
        return 1
    end = s.index(end_marker, start) + len(end_marker)
    block = s[start:end]

    if "cast[key] = {" in block:
        print("ABORT: the block contains the recording line - moving it would")
        print("       take the vote with it.")
        return 1

    # Remove it, then re-insert after the read.
    s2 = s[:start] + s[end:].lstrip("\n")
    if s2.count(READS) != 1:
        print("ABORT: the read line is no longer unique after removal.")
        return 1
    s2 = s2.replace(READS, READS + "\n\n" + block, 1)

    import ast
    try:
        ast.parse(s2)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1

    i = s2.index("def cast_committee_vote")
    j = s2.index("quorum = _committee_quorum", i)
    seg = s2[i:j]
    if seg.index("if key in cast:") > seg.index("cast[key] = {"):
        print("ABORT: the check would still follow the recording.")
        return 1
    print("  ok  the check now runs BEFORE the vote is recorded, and it parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, BACKUP)
    open(API, "w", encoding="utf-8", newline="").write(s2)
    print("APPLIED %s   (backup: %s)" % (API, os.path.basename(BACKUP)))
    print("\nRestart uvicorn. A first vote is accepted; a second from the same")
    print("person is refused.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
