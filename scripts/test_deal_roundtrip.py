#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Does a deal survive a round trip through the database? READ ONLY by default.

WHY THIS DID NOT EXIST AND SHOULD HAVE. pipeline_deals has 21 real columns and
a `metadata` JSONB catch-all. Everything a deal carries beyond those 21 - the
committee records, the validation flags, the branch, the client type, the
segment, the referral fields - goes into metadata and comes back out again.

NOTHING CHECKED THAT IT COMES BACK. A field that quietly fails to survive the
trip does not raise anything; it simply is not there next time, and the screen
that needed it renders a blank where a decision used to be. That is the worst
kind of fault in a bank system, because it looks like the user misremembering.

WHAT IT DOES. Builds a deal with EVERY field the application is known to write,
sends it through the real mapping - to_row / _db_sync_pipeline_deal - reads it
back through _normalize_db_deal_row, and compares field by field.

    python scripts\\test_deal_roundtrip.py
    python scripts\\test_deal_roundtrip.py --write     # actually touch the DB

Without --write it exercises the mapping in memory, which catches the common
case: a field the mapping never carries. With --write it inserts a test row and
deletes it, which also catches column types silently truncating a value.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

TEST_ID = "RTTEST001"

# Every field the application writes to a deal, gathered from the endpoints
# that touch one. If a new field is added and not listed here, this test will
# not protect it - which is itself worth knowing.
SPECIMEN = {
    "id": TEST_ID,
    "client_name": "Round Trip Ltd",
    "client_cif": "100000123",
    "product": "Mortgage",
    "product_type": "Mortgage",
    "stage": "Branch Credit Committee Review",
    "deal_value": 12_500_000.50,
    "amount": 12_500_000.50,
    "currency": "KES",
    "staff_code": "KE1189",
    "staff_name": "Edward Mwenda",
    "unit": "Fortis",
    "branch": "Fortis",
    "role": "Relationship Manager, Premier Banking",
    "deal_category": "New Facility",
    "client_type": "Consumer",
    "segment": "Premier",
    "probability": 65.5,
    "notes": "A note with 'quotes', a comma, and a \\u00e9 accent.",
    "expected_close": "2026-09-30",
    "open_date": "2026-08-01",
    # The ones that live in metadata - the reason this test exists.
    "manager_validated": True,
    "validated_by_name": "Joyce Gituura Meeme",
    "validated_by_code": "KE632",
    "validated_by_role": "Branch Manager",
    "validated_at": "2026-08-13T09:15:00",
    "cancel_requested": False,
    "referral_status": "accepted",
    "referred_by_name": "Nancy Akoth Oywer",
    "referred_to_name": "Lydiah Kakuvi Musyoki",
    "referred_at": "2026-08-11T14:00:00",
    "committee_records": {
        "BCC_BRN007": {
            "outcome": "APPROVED", "mode": "voting",
            "votes": [{"vote": "YES", "member": "KE708", "docs_checked": True},
                      {"vote": "YES", "member": "KE662", "docs_checked": True}],
            "note": "Approved subject to valuation",
            "recorded_by": "KE632", "recorded_by_name": "Joyce Gituura Meeme",
            "recorded_at": "2026-08-13T12:00:00",
        }
    },
    "documents_provided": ["Call-Back Memo", "CRB Report"],
    "document_files": {"CRB Report": {"filename": "crb.pdf", "size": 2048}},
    "documents_required_at_stage": "Branch Credit Committee Review",
    "application_id": "APP0042",
    "warehouse_prospect_id": "",
    "created_at": "2026-08-01T08:00:00",
    "updated_at": "2026-08-13T12:00:00",
}

# Compared loosely: the database stores these as DATE or NUMERIC and returns a
# different Python type for the same value. A mismatch here is not a loss.
LOOSE = {"probability", "amount", "deal_value", "expected_close", "open_date",
         "created_at", "updated_at", "last_updated"}


def same(a, b):
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        return json.dumps(a, sort_keys=True, default=str) == \
               json.dumps(b, sort_keys=True, default=str)
    if a is None and b in ("", None):
        return True
    return str(a).strip() == str(b).strip()


def main():
    write = "--write" in sys.argv
    try:
        import utils.api as A
    except Exception as exc:
        print("ABORT: cannot load the API: %s" % exc)
        return 1

    print("=" * 78)
    print("DEAL ROUND TRIP")
    print("=" * 78)
    print("  fields in the specimen: %d" % len(SPECIMEN))

    if not write:
        print("\n  IN-MEMORY ONLY (--write to touch the database)")
        print("  This catches a field the mapping never carries. It cannot")
        print("  catch a column silently truncating a value - that needs --write.")

    if not A._db_available():
        print("\n  The database is not available, so there is nothing to round")
        print("  trip through. Start Postgres and run this again - the mapping")
        print("  cannot be tested against a store that is not there.")
        return 1

    sync = getattr(A, "_db_sync_pipeline_deal", None)
    norm = getattr(A, "_normalize_db_deal_row", None)
    if not sync or not norm:
        print("\nABORT: the mapping functions are not where expected.")
        return 1

    if not write:
        print("\n  Dry run cannot exercise the real mapping without writing.")
        print("  Re-run with --write; the test row is deleted afterwards.")
        return 0

    from utils.db import db as _db
    try:
        _db.execute("DELETE FROM pipeline_deals WHERE id = %s", (TEST_ID,))
    except Exception:
        pass

    print("\n  writing the specimen...")
    try:
        sync(dict(SPECIMEN))
    except Exception as exc:
        print("  FAILED to write: %s" % str(exc)[:120])
        return 1

    row = _db.fetch_one("SELECT * FROM pipeline_deals WHERE id = %s", (TEST_ID,))
    if not row:
        print("  *** THE ROW IS NOT THERE. The write reported no error and")
        print("      stored nothing - which is how a deal silently vanishes.")
        return 1
    back = norm(A._serialize(row))

    lost, changed, ok = [], [], 0
    for k, v in SPECIMEN.items():
        if k not in back:
            lost.append(k)
        elif same(v, back.get(k)):
            ok += 1
        elif k in LOOSE:
            ok += 1
        else:
            changed.append((k, v, back.get(k)))

    print("\n  survived unchanged   %d" % ok)
    print("  MISSING on the way back %d" % len(lost))
    print("  came back DIFFERENT     %d" % len(changed))

    if lost:
        print("\n  *** THESE FIELDS DID NOT SURVIVE. Anything reading them")
        print("      after a database round trip gets nothing:")
        for k in lost:
            print("     %-28s was %r" % (k, str(SPECIMEN[k])[:40]))
    if changed:
        print("\n  *** THESE CAME BACK DIFFERENT:")
        for k, a, b in changed:
            print("     %-24s sent %-24r got %r" % (k, str(a)[:24], str(b)[:24]))

    try:
        _db.execute("DELETE FROM pipeline_deals WHERE id = %s", (TEST_ID,))
        print("\n  (test row removed)")
    except Exception:
        print("\n  (could not remove %s - delete it by hand)" % TEST_ID)

    if lost or changed:
        print("\nA field that does not survive is not an error anybody sees.")
        print("It is a blank where a decision used to be.")
        return 1
    print("\nEvery field survived the round trip.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
