#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
MV1 v2 - committee votes reach Postgres and come back. Re-anchored for MD1 v2.

The original MV1 anchored on a single line of the field list. MD1 v2 lays that
list out differently, so MV1 aborted with "the read anchor matched 0 times" and
the release would have carried every committee fix EXCEPT the one that makes
votes survive a database round trip.

That is the fault MV1 exists to prevent, arriving by a different door: votes
written to JSON only, invisible to every DB-first read, and a committee that
appears not to have voted.

This version anchors on text MD1 v2 actually leaves behind, and REFUSES if
committee_votes is already handled - so it cannot double-add.

Verified: applies to origin/alex-dev after MD1 v2, py_compile clean, and both
the write and the read carry committee_votes afterwards.

Usage (from project root, .venv active):
    python scripts\patch_mv1_committee_votes_persist_v2.py            # dry run
    python scripts\patch_mv1_committee_votes_persist_v2.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_mv1v2"

WRITE_OLD = '''                "committee_records":   deal.get("committee_records"),'''
WRITE_NEW = '''                "committee_records":   deal.get("committee_records"),
                # A VOTE THAT REACHES ONLY JSON DID NOT HAPPEN. Every reader
                # here is DB-first, so a vote written to one store is a
                # committee that appears not to have voted.
                "committee_votes":     deal.get("committee_votes"),'''

READ_OLD = '''        for _k in ("branch", "segment", "committee_records",'''
READ_NEW = '''        for _k in ("branch", "segment", "committee_records", "committee_votes",'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()

    i = s.find("def _db_sync_pipeline_deal")
    j = s.find("\ndef ", i + 10) if i >= 0 else -1
    i2 = s.find("def _normalize_db_deal_row")
    j2 = s.find("\ndef ", i2 + 10) if i2 >= 0 else -1
    if i < 0 or i2 < 0:
        print("ABORT: the sync or normalise function is not in this file.")
        return 1
    already_w = '"committee_votes"' in s[i:j]
    already_r = '"committee_votes"' in s[i2:j2]
    if already_w and already_r:
        print("ABORT: committee_votes already travels both ways.")
        return 1

    if not already_w:
        if s.count(WRITE_OLD) != 1:
            print("ABORT: the write anchor matched %d times." % s.count(WRITE_OLD))
            print("       MD1 v2 must be applied first.")
            return 1
        s = s.replace(WRITE_OLD, WRITE_NEW, 1)
        print("  ok  votes are written to the database")
    if not already_r:
        if s.count(READ_OLD) != 1:
            print("ABORT: the read anchor matched %d times." % s.count(READ_OLD))
            return 1
        s = s.replace(READ_OLD, READ_NEW, 1)
        print("  ok  votes are read back from it")

    # Written but never lifted out loses them just as completely.
    i = s.index("def _db_sync_pipeline_deal"); j = s.index("\ndef ", i + 10)
    i2 = s.index("def _normalize_db_deal_row"); j2 = s.index("\ndef ", i2 + 10)
    if '"committee_votes"' not in s[i:j] or '"committee_votes"' not in s[i2:j2]:
        print("ABORT: committee_votes does not travel BOTH ways.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: written and read back")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
