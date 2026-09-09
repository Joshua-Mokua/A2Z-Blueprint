#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Is main carrying everything the bank is running?

Checks each fix by its marker in the file, on both branches. Run before any
release build: a marker present at the bank and absent here means the release
would replay old code over a live fix.

    python scripts/verify_main_matches_pilot.py
"""
import subprocess
import sys

# label, file, marker
FIXES = [
    ("BV2 branch validation", "utils/api.py", "A MANAGER AT A BRANCH MAY VALIDATE"),
    ("BV3 queue matches", "utils/api.py", "WHAT THE PERSON CAN ACTUALLY VALIDATE"),
    ("BV4 per-deal permission", "utils/api_pipeline_permissions.py", "OWN BRANCH"),
    ("VA1 day view", "utils/api_pipeline_validation.py", "OWNER'S BRANCH"),
    ("CV3 chair optional", "utils/api.py", "chair_vote_required"),
    ("CH3 chair is a member", "utils/api.py", "CANNOT BE WAITED FOR"),
    ("DD1 roster dedup", "utils/api_pipeline_scope.py", "ONE ROW PER STAFF CODE"),
    ("DD2 scope weighted", "utils/api_pipeline_scope.py", "SCOPE_COLS"),
    ("DUP1 helper", "utils/api_pipeline_scope.py", "row_for_staff_code"),
    ("AG1 no manual entry", "utils/api.py", "ENTERING CREDIT IS A SUBMISSION"),
    ("AG2 reads new_stage", "utils/api.py", 'getattr(payload, "new_stage", "")'),
    ("AM1 amend endpoint", "utils/api.py", "amend-value"),
    ("AM2 amend panel", "frontend/web/src/pages/PipelineDealDetail.tsx", "AmendValuePanel"),
    ("DV1 document types", "utils/api.py", "SERVE IT AS WHAT IT IS"),
    ("DV3 document token", "frontend/web/src/lib/api.ts", "openProtectedFile"),
    ("RW1 rework to analyst", "frontend/web/src/pages/PipelineDealDetail.tsx", "resubmitAfterRework"),
    ("TL1 newest first", "frontend/web/src/components/Timeline.tsx", "const ordered"),
    ("CT1 customer type", "frontend/web/src/pages/AdminConfig.tsx", "'client_type', label:"),
    ("LD1 referral at Initiation", "utils/api.py", "Initiation, not Lead"),
    ("RC3 ready moves the deal", "utils/api_lms_routes.py", "READY MEANS THE DEAL MOVES"),
    ("PV2 per-role pool", "utils/api_lms_scope.py", "SOME ROLES ONLY WANT PART"),
    ("DC1 analyst decides", "utils/api_lms_routes.py", "no manager step in that flow"),
    ("CAD1 Head CAD", "utils/api_credit_admin_scope.py", "_re_cad"),
    ("TR1 trops", "utils/api_credit_admin_scope.py", "_re_trops"),
    ("claim after committee", "utils/api_lms_mutations.py", "once a committee has"),
    # Two versions exist and both work: main carries every unknown field,
    # the pilot names three. Either counts.
    ("WL1 palette carry", "utils/api.py",
     ("existing_members", "KEEP WHAT THIS FUNCTION")),
    ("PI1 metric bounds", "utils/branch_log.py", "AN UNLISTED METRIC IS NOT"),
    ("DV2 delegation", "utils/org_validator.py", "_delegated_branches"),
    ("SC3 owner digits", "frontend/web/src/pages/PipelineDealDetail.tsx", "sameStaffCode"),
    ("BF3 branch shown", "frontend/web/src/pages/PipelineCreate.tsx", "SHOWN TO WHOEVER MUST FILL IT"),
]


def on(ref, path, marker):
    # Read as bytes and decode ourselves. On Windows the default codec is
    # cp1252 and a UTF-8 source file kills the read with a decode error.
    r = subprocess.run(["git", "show", "%s:%s" % (ref, path)],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return False
    text = r.stdout.decode("utf-8", "replace")
    # A fix can have more than one accepted marker where two versions exist.
    if isinstance(marker, tuple):
        return any(m in text for m in marker)
    return marker in text


def main():
    subprocess.run(["git", "fetch", "-q", "origin", "alex-dev"],
                   capture_output=True)
    print("=" * 74)
    print("IS MAIN CARRYING WHAT THE BANK IS RUNNING?")
    print("=" * 74)
    print("  %-32s %-10s %s" % ("FIX", "MAIN", "PILOT"))
    behind, ahead = [], []
    for label, path, marker in FIXES:
        m = on("origin/main", path, marker)
        a = on("origin/alex-dev", path, marker)
        flag = ""
        if a and not m:
            behind.append(label)
            flag = "  <-- MISSING FROM MAIN"
        elif m and not a:
            ahead.append(label)
            flag = "  (main only)"
        print("  %-32s %-10s %s%s"
              % (label[:32], "yes" if m else "-", "yes" if a else "-", flag))

    print("\n" + "=" * 74)
    if not behind:
        print("Main carries everything the bank is running.")
        print("=" * 74)
        if ahead:
            print("\n  Main-only (not yet released): %s" % ", ".join(ahead))
        return 0
    print("MAIN IS BEHIND ON %d FIX(ES)" % len(behind))
    print("=" * 74)
    for b in behind:
        print("  %s" % b)
    print("\n  A release built from main would replay old code over these.")
    print("  Run harmonise_main_with_pilot.py first.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
