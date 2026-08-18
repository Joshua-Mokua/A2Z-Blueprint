#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
What votes does the server actually see on this case? READ ONLY.

A 409 on voting means the server found a vote already recorded under your key.
Rather than reason about why, this shows what is there - in BOTH stores, since
they can disagree, and the endpoint reads only one of them.

    python scripts\\diag_case_votes.py --deal SIMBCC_FORTIS_01
    python scripts\\diag_case_votes.py --deal SIMBCC_FORTIS_01 --clear
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())


def show(label, deal):
    if deal is None:
        print("  %-10s (not found)" % label)
        return
    cv = deal.get("committee_votes") or {}
    cr = deal.get("committee_records") or {}
    print("  %-10s stage=%r" % (label, deal.get("stage")))
    if not cv:
        print("             committee_votes: none")
    for code, cast in cv.items():
        print("             %s — %d vote(s)" % (code, len(cast or {})))
        for who, v in (cast or {}).items():
            print("                key=%-12r %-24s %-8s %s"
                  % (who, str(v.get("name"))[:24], v.get("vote"),
                     str(v.get("at"))[:16]))
    for code, rec in cr.items():
        print("             RECORD %s -> %s" % (code, rec.get("outcome")))


def main():
    did = ""
    if "--deal" in sys.argv:
        i = sys.argv.index("--deal")
        if i + 1 < len(sys.argv):
            did = sys.argv[i + 1].strip()
    if not did:
        print("ABORT: --deal <id> is required.")
        return 1
    clear = "--clear" in sys.argv

    from utils.core import PipelineManager
    import utils.api as A

    pm = PipelineManager()
    j = next((d for d in pm.deals if str(d.get("id")) == did), None)

    print("=" * 74)
    print("VOTES ON %s" % did)
    print("=" * 74)
    show("JSON", j)

    dbd = None
    if A._db_available():
        try:
            from utils.db import db as _db
            row = _db.fetch_one("SELECT * FROM pipeline_deals WHERE id = %s", (did,))
            dbd = A._normalize_db_deal_row(A._serialize(row)) if row else None
        except Exception as exc:
            print("  DB unreadable: %s" % str(exc)[:60])
    show("DATABASE", dbd)

    print("")
    print("  THE ENDPOINT READS whichever _deal_for_docs returns - DB first")
    print("  when Postgres is answering. If the two above disagree, that is")
    print("  the 409: a vote you cannot see in one store, refusing you in the")
    print("  other.")

    if not clear:
        print("")
        print("  --clear removes every vote on this case, from BOTH stores, so")
        print("  it can be voted on again from scratch. Test data only.")
        return 0

    if j is not None:
        j.pop("committee_votes", None)
        j.pop("committee_records", None)
        pm._save_deals()
        print("\n  cleared in JSON")
    if dbd is not None:
        try:
            dbd.pop("committee_votes", None)
            dbd.pop("committee_records", None)
            A._db_sync_pipeline_deal(dbd)
            print("  cleared in the database")
        except Exception as exc:
            print("  could not clear the database: %s" % str(exc)[:60])
    print("\n  %s can now be voted on from scratch." % did)
    return 0


if __name__ == "__main__":
    sys.exit(main())
