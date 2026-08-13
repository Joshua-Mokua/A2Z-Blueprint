#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
MD1 - a deal stops losing half of itself on the way to the database.

FOUND BY THE ROUND-TRIP TEST (2026-08-13). Of 39 fields written to a deal, NINE
did not survive a trip through Postgres and back:

    branch, committee_records, documents_required_at_stage, application_id,
    cancel_requested, referred_to_name, warehouse_prospect_id,
    created_at, updated_at

pipeline_deals has 21 real columns and a `metadata` JSONB. metadata reads like a
catch-all and is NOT one - it is a hand-listed set of thirteen fields. Anything
not named there never reached the database, and since deals are read DB-FIRST,
it came back empty on the next read.

WHY THIS MATTERS MORE THAN IT SOUNDS.

  BRANCH decides everything about committee routing. Measured:

      branch-originated?   with branch: True     without: False

  A deal that loses `branch` is not branch-originated, so no branch committee
  is substituted into its journey and THE CASE NEVER REACHES A COMMITTEE. That
  is very likely why the branch managers were gathered and nothing moved -
  underneath the missing committees, the deals had lost the field that routes
  them. The reconciler had already shown it in the wild:
  `SCN0001 branch json='Head Office' db='None'`.

  COMMITTEE_RECORDS is the decision itself. A committee could record its
  recommendation and find it gone the next morning.

  MANAGER_VALIDATED, the cancellation flags and the referral fields go the same
  way - each one a screen that renders a blank where a decision used to be.

THE FIX IS BOTH DIRECTIONS. Writing a field into metadata and never reading it
back loses it exactly as completely as never writing it. So the write side
carries them and the read side lifts them out.

BOOLEANS USE `is not None`, not truthiness. manager_validated=False and
cancel_requested=False are meaningful answers; treating them as absent would
leave a caller unable to tell "no" from "unknown".

NO SCHEMA CHANGE. Everything goes into the existing metadata JSONB, so this
applies to a running database with no migration.

Verified: py_compile clean, and the round-trip test goes from 9 fields lost to
0. Run it yourself after applying:

    python scripts\\test_deal_roundtrip.py --write

Usage (from project root, .venv active):
    python scripts\\patch_md1_deal_field_mapping.py            # dry run
    python scripts\\patch_md1_deal_field_mapping.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_md1"

W_OLD = '                "lms_application_id":   deal.get("lms_application_id"),'
W_NEW = '''                "lms_application_id":   deal.get("lms_application_id"),
                # ── FIELDS THAT WERE BEING SILENTLY DROPPED (2026-08-13) ────
                # metadata is a HAND-LISTED set, not a catch-all: anything not
                # named here never reached Postgres. Since deals are read
                # DB-first, these came back EMPTY on the next read.
                #
                # BRANCH IS THE WORST OF THEM. Without it a deal is not
                # branch-originated, so no branch committee is substituted into
                # its journey and the case NEVER REACHES A COMMITTEE - very
                # likely why the branch managers were gathered and nothing
                # moved. Underneath the missing committees, the deals had lost
                # the field that routes them.
                #
                # COMMITTEE_RECORDS is the decision itself. A committee could
                # record a recommendation and find it gone the next morning.
                "branch":              deal.get("branch"),
                "segment":             deal.get("segment"),
                "committee_records":   deal.get("committee_records"),
                "documents_required_at_stage": deal.get("documents_required_at_stage"),
                "documents_provided":  deal.get("documents_provided"),
                "document_files":      deal.get("document_files"),
                "application_id":      deal.get("application_id"),
                "manager_validated":   deal.get("manager_validated"),
                "validated_by_name":   deal.get("validated_by_name"),
                "validated_by_code":   deal.get("validated_by_code"),
                "validated_by_role":   deal.get("validated_by_role"),
                "validated_at":        deal.get("validated_at"),
                "cancel_requested":    deal.get("cancel_requested"),
                "cancel_approved":     deal.get("cancel_approved"),
                "cancel_requested_at": deal.get("cancel_requested_at"),
                "cancel_request_reason": deal.get("cancel_request_reason"),
                "referral_status":     deal.get("referral_status"),
                "referred_by_name":    deal.get("referred_by_name"),
                "referred_to_name":    deal.get("referred_to_name"),
                "referred_by_code":    deal.get("referred_by_code"),
                "referred_to_code":    deal.get("referred_to_code"),
                "referred_at":         deal.get("referred_at"),
                "created_at":          deal.get("created_at"),
                "updated_at":          deal.get("updated_at"),'''

R_OLD = '''        for _k in ("origin", "origin_party_code", "origin_party_name",
                   "event_id", "mou_id", "channel_id", "warehouse_prospect_id"):
            if not r.get(_k) and md.get(_k):
                r[_k] = md.get(_k)'''
R_NEW = '''        for _k in ("origin", "origin_party_code", "origin_party_name",
                   "event_id", "mou_id", "channel_id", "warehouse_prospect_id",
                   # ── LIFTED BACK OUT (2026-08-13) ────────────────────────
                   # The other half of the same fix. Writing a field into
                   # metadata and never reading it back loses it just as
                   # completely as never writing it at all.
                   "branch", "segment", "committee_records",
                   "documents_required_at_stage", "documents_provided",
                   "document_files", "application_id",
                   "validated_by_name", "validated_by_code",
                   "validated_by_role", "validated_at",
                   "cancel_requested_at", "cancel_request_reason",
                   "referral_status", "referred_by_name", "referred_to_name",
                   "referred_by_code", "referred_to_code", "referred_at",
                   "created_at", "updated_at"):
            if not r.get(_k) and md.get(_k):
                r[_k] = md.get(_k)
        # BOOLEANS NEED `is not None`, not truthiness. manager_validated=False
        # and cancel_requested=False are meaningful answers; treating them as
        # absent would leave the caller unable to tell "no" from "unknown".
        for _k in ("manager_validated", "cancel_requested", "cancel_approved"):
            if r.get(_k) is None and md.get(_k) is not None:
                r[_k] = md.get(_k)'''



def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "FIELDS THAT WERE BEING SILENTLY DROPPED" in s:
        print("ABORT: MD1 looks applied.")
        return 1
    if s.count(W_OLD) != 1:
        print("ABORT: the metadata write block matched %d times." % s.count(W_OLD))
        return 1
    if s.count(R_OLD) != 1:
        print("ABORT: the metadata read block matched %d times." % s.count(R_OLD))
        return 1

    s = s.replace(W_OLD, W_NEW, 1).replace(R_OLD, R_NEW, 1)
    print("  ok  fields carried into metadata and lifted back out")

    # Both halves, or the field is still lost.
    for f in ("branch", "committee_records", "created_at", "manager_validated"):
        if ('"%s"' % f) not in W_NEW:
            print("ABORT: %r is not written - it would still be lost." % f)
            return 1
        if ('"%s"' % f) not in R_NEW:
            print("ABORT: %r is written but never read back, which loses it" % f)
            print("       just as completely.")
            return 1
    # Booleans must not be tested for truthiness.
    if "is not None" not in R_NEW:
        print("ABORT: a False boolean would be treated as absent, so 'no' and")
        print("       'unknown' become the same answer.")
        return 1
    print("  ok  post-checks: both directions, booleans distinguish False")

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
    print("Restart uvicorn, then prove it:")
    print("  python scripts\\test_deal_roundtrip.py --write")
    print("It should report 0 fields missing. Existing rows keep whatever they")
    print("already lost - this stops the leak, it does not refill them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
