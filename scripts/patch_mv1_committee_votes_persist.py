#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
MV1 - a committee vote survives the database.

FOUND WHILE CHASING A 409 (2026-08-14). MD1 taught the database mapping to
carry branch, committee_records and twenty other fields. committee_VOTES did
not exist when it was written - VT1 introduced it the following day, and nobody
came back to the list.

So each member's vote was written to JSON by update_deal and NEVER REACHED
POSTGRES. Deals are read DB-first. The vote was gone on the next read.

EVERY CONSEQUENCE LOOKS LIKE A DIFFERENT BUG:

    quorum never accumulates          each vote is the "first" one
    the journey shows no votes        it reads a deal with none
    the queue cannot say "you voted"  same
    a member is invited to vote again the record of their vote is absent

One missing line, four symptoms, and a morning spent treating them separately.

The lesson is narrow and worth keeping: WHEN A NEW FIELD IS ADDED TO A DEAL,
the database mapping is not optional plumbing - it is the difference between a
field existing and a field appearing to exist. scripts/test_deal_roundtrip.py
exists to catch exactly this, and would have, had it been re-run after VT1.

No schema change - it goes into the existing metadata JSONB.

Verified: py_compile clean, and the round trip carries it both ways.

Usage (from project root, .venv active):
    python scripts\\patch_mv1_committee_votes_persist.py            # dry run
    python scripts\\patch_mv1_committee_votes_persist.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_mv1"

WRITE_OLD = '                "committee_records":   deal.get("committee_records"),'

WRITE_NEW = '''                "committee_records":   deal.get("committee_records"),
                # ---- THE VOTES THEMSELVES (2026-08-14) --------------------
                # MD1 carried committee_records; committee_VOTES did not exist
                # yet. So each member's vote was written to JSON and never
                # reached Postgres, and since deals are read DB-first it was
                # gone on the next read - which is why quorum never
                # accumulated and no vote ever showed in the journey.
                "committee_votes":     deal.get("committee_votes"),'''

# MD1 v2 writes this list with a different indent from MD1 v1, so the anchor
# is taken from the shortest distinctive run rather than a whole line.
READ_OLD = '"branch", "segment", "committee_records",'
READ_NEW = '"branch", "segment", "committee_records", "committee_votes",'



def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if '"committee_votes":     deal.get' in s:
        print("ABORT: MV1 looks applied.")
        return 1
    if s.count(WRITE_OLD) != 1:
        print("ABORT: the write anchor matched %d times." % s.count(WRITE_OLD))
        print("       MD1 must be applied first.")
        return 1
    if s.count(READ_OLD) != 1:
        print("ABORT: the read anchor matched %d times." % s.count(READ_OLD))
        return 1

    s = s.replace(WRITE_OLD, WRITE_NEW, 1).replace(READ_OLD, READ_NEW, 1)
    print("  ok  committee_votes travels to the database and back")

    # BOTH DIRECTIONS, or the field is still lost.
    i = s.index("def _db_sync_pipeline_deal")
    j = s.index("\ndef ", i + 10)
    k = s.index("def _normalize_db_deal_row")
    l = s.index("\ndef ", k + 10)
    if '"committee_votes"' not in s[i:j]:
        print("ABORT: votes are still not written.")
        return 1
    if '"committee_votes"' not in s[k:l]:
        print("ABORT: votes are written but never read back, which loses them")
        print("       just as completely.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: both directions, and the result parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)
    print("")
    print("Restart uvicorn. Votes cast BEFORE this fix were never stored, so")
    print("they are gone - the affected cases start from no votes, which is")
    print("also why a member may be asked to vote again on one of them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
