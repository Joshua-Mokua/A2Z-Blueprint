#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
VS1 - a vote reaches the database, so the rest of the system can see it.

THE PILOT VOTED, THE VOTE "WENT THROUGH", AND NOTHING CHANGED (2026-08-14).
The journey stayed at two events, the queue still said "Review", and quorum
never accumulated.

The vote endpoint calls PipelineManager.update_deal, which writes the JSON
store AND NOTHING ELSE. Deals are read DB-first. So the vote was recorded in a
store nothing reads and every screen that looked afterwards saw a case with no
votes on it.

MV1 taught the mapping to CARRY committee_votes. It did not make anything CALL
that mapping after a vote - and a field the mapping knows about is not
persisted until something asks it to be. Two fixes that each looked complete,
with the join between them missing.

The whole deal is synced, not the votes alone, so a stage set by an automatic
advance travels in the same write.

BEST EFFORT. If the sync fails the vote still stands in JSON and a warning is
logged - a recorded decision must not be lost because the copy failed.

Measured with the full stack:

    journey   committee_vote  BCC_BRN002 - Member Two recommended (CSM)
    queue     you_voted=True  your_vote=YES

THE LESSON, and it is the third time this shape has cost a morning: WRITING TO
ONE STORE IS NOT WRITING. Anything that changes a deal must go through the
path that reaches Postgres, because that is what every reader uses.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_vs1_vote_syncs_to_db.py            # dry run
    python scripts\\patch_vs1_vote_syncs_to_db.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_vs1"

ANCHOR = '    _audit("API_COMMITTEE_VOTE", user,'

BLOCK = r'''    # ── AND INTO THE DATABASE, OR THE VOTE DID NOT HAPPEN ───────────────────
    # update_deal writes the JSON store and NOTHING ELSE. Deals are read
    # DB-first, so a vote recorded here was invisible to every screen that
    # looked afterwards: the journey showed nothing, the queue still said
    # "Review", and quorum never accumulated.
    #
    # MV1 taught the mapping to CARRY committee_votes; it did not make anything
    # CALL that mapping after a vote. A field the mapping knows about is not
    # persisted until something asks it to persist.
    #
    # Sync the whole deal, not the votes alone, so the stage set by an
    # automatic advance travels in the same write.
    try:
        if _db_available():
            _fresh = _pm.get_deal(deal_id)
            if _fresh:
                _db_sync_pipeline_deal(_fresh)
    except Exception as _exc:
        logger.warning("vote recorded in JSON but not synced to the database "
                       "for %s: %s", deal_id, _exc)

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "AND INTO THE DATABASE, OR THE VOTE DID NOT HAPPEN" in s:
        print("ABORT: VS1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the vote audit line matched %d times." % s.count(ANCHOR))
        print("       VT1 must be applied first.")
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  a vote is written to the database as well as JSON")

    if "_db_sync_pipeline_deal" not in BLOCK:
        print("ABORT: nothing calls the mapping, so the vote still would not")
        print("       reach Postgres.")
        return 1
    if "except Exception" not in BLOCK:
        print("ABORT: a failed sync would lose the vote entirely - it must")
        print("       stand in JSON and warn.")
        return 1
    if "get_deal(deal_id)" not in BLOCK:
        print("ABORT: syncing a stale copy would drop the stage an automatic")
        print("       advance had just set.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: syncs a fresh copy, fails safe, parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)
    print("\nRestart uvicorn. A vote now appears in the journey and the queue.")
    print("Votes cast before this are in JSON only - clear those cases with")
    print("  python scripts\\diag_case_votes.py --deal <id> --clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
