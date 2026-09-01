#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Clear the pilot's trial deals, documents and daily log. DRY RUN by default.

RULING (2026-09-01, go-live): "one thing to push to Alex to clear all the deals
the staff input on the pipeline, and the documents, plus the items they had in
the productivity index."

    python scripts\reset_pilot_for_go_live.py
    python scripts\reset_pilot_for_go_live.py --apply --yes-i-have-a-backup

*** THIS IS FOR THE BANK'S DEPLOYMENT, NOT THE DEVELOPMENT BOX. ***

The development box keeps its trial data - it is needed for post-go-live
support and for building the modules still to come. Running this there throws
away the only environment where a reported fault can be reproduced.

The script cannot tell the two machines apart on its own, so it PRINTS WHO IT
IS ABOUT TO WIPE - the bank name, the deal count, the staff count - and refuses
to proceed until somebody has read that and confirmed. A machine is not
identifiable from inside itself; a person looking at the screen is.

WHAT GOES:

    the deals            pipeline_deals.json, pipeline_activities.json
    the credit cases     loan_applications.json
    the documents        data/uploads/credit_docs, data/lms_documents
                         - the actual uploaded files, not only the index
    the productivity     branch_logs.json, branch_log.json  (the daily log
                         entries behind the productivity index)
    the referrals        referrals.json
    the validations      validations.json

WHAT STAYS, and the script aborts rather than touch any of it:

    users.json           every login and password
    lms_config.json      THE COMMITTEES - B1, B2 and their seated members
    org_config.json      branches, regions, hidden modules
    pipeline_settings    product flows and stages
    fx_rates.json        the currency rates
    staff_roster.json    the register
    audit_log.json       the audit trail - see below

THE AUDIT LOG IS KEPT. A bank does not delete its audit trail to tidy up before
go-live, and "we were starting fresh" is not an answer a regulator accepts.

POSTGRES IS CLEARED TOO. Clearing only the files looks like it worked until the
next read repopulates from the database. If the database cannot be reached this
FAILS rather than reporting success.
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

DATA = "data"

TRIAL = [
    ("pipeline_deals.json", "deals staff raised", []),
    ("pipeline.json", "the pipeline index", []),
    ("pipeline_activities.json", "touchpoints against deals", []),
    ("loan_applications.json", "credit cases", []),
    ("branch_logs.json", "daily log - the productivity index", {}),
    ("branch_log.json", "daily log entries", {}),
    ("referrals.json", "referrals raised", []),
    ("validations.json", "validation records", {}),
    ("credit_admin.json", "credit administration records", {}),
]

DOC_DIRS = [
    (os.path.join("data", "uploads", "credit_docs"), "deal documents"),
    (os.path.join("data", "lms_documents"), "credit case documents"),
]

SACRED = (
    "users.json", "org_config.json", "lms_config.json",
    "pipeline_settings.json", "products.json", "kpi_library.json",
    "target_cascade.json", "staff_roster.json", "bank_targets.json",
    "org_hierarchy_config.json", "fx_rates.json", "deals_warehouse.json",
    "audit_log.json",
)

MIRRORS = {"pipeline_deals.json": "pipeline_deals",
           "loan_applications.json": "loan_applications"}


def _count(p):
    try:
        d = json.load(open(p, encoding="utf-8"))
        return len(d) if hasattr(d, "__len__") else "?"
    except Exception:
        return "unreadable"


def main():
    apply = "--apply" in sys.argv
    confirmed = "--yes-i-have-a-backup" in sys.argv

    if not os.path.isdir(DATA):
        print("ABORT: no data/ directory - run from the project root.")
        return 1
    for name, _w, _e in TRIAL:
        if name in SACRED:
            print("ABORT: %s is configuration. That is a bug here." % name)
            return 1

    # ── WHO AM I ABOUT TO WIPE ──────────────────────────────────────────────
    bank = users = "?"
    try:
        cfg = json.load(open(os.path.join(DATA, "org_config.json"),
                             encoding="utf-8"))
        bank = cfg.get("bank_name") or "?"
    except Exception:
        pass
    try:
        users = len(json.load(open(os.path.join(DATA, "users.json"),
                                   encoding="utf-8")) or {})
    except Exception:
        pass

    print("=" * 78)
    print("CLEAR THE PILOT'S TRIAL DATA")
    print("=" * 78)
    print("  *** THIS IS FOR THE BANK'S DEPLOYMENT, NOT THE DEV BOX ***")
    print("")
    print("  YOU ARE ABOUT TO WIPE:")
    print("     bank        %s" % bank)
    print("     logins      %s" % users)
    print("     folder      %s" % os.path.abspath(DATA))
    print("")
    print("  If that is the development machine, STOP. Its trial data is the")
    print("  only place a reported fault can be reproduced after go-live.")

    print("\n  WHAT WOULD GO")
    present, total = [], 0
    for name, what, empty in TRIAL:
        p = os.path.join(DATA, name)
        if not os.path.isfile(p):
            continue
        n = _count(p)
        present.append((name, empty, p))
        if isinstance(n, int):
            total += n
        print("     %-26s %-36s %s" % (name, what, n))

    docs = []
    for d, what in DOC_DIRS:
        if not os.path.isdir(d):
            continue
        files = sum(len(f) for _r, _dd, f in os.walk(d))
        docs.append((d, files))
        print("     %-26s %-36s %d file(s)" % (d, what, files))

    print("\n  WHAT STAYS")
    for name in SACRED:
        if os.path.isfile(os.path.join(DATA, name)):
            print("     %-26s untouched" % name)

    if not present and not docs:
        print("\n  Nothing to clear.")
        return 0

    if not apply:
        print("\nDRY RUN - nothing deleted.")
        print("\n  READ THE BANK NAME ABOVE. If it is the pilot, then:")
        print("     xcopy /Y /I /E data ..\\data_before_go_live\\")
        print("     python scripts\\reset_pilot_for_go_live.py --apply "
              "--yes-i-have-a-backup")
        return 0

    if not confirmed:
        print("\n" + "=" * 78)
        print("STOP - %d RECORDS AND %d DOCUMENT(S) ON %s"
              % (total, sum(n for _d, n in docs), bank))
        print("=" * 78)
        print("  Take your own copy first - the backup this script makes lives")
        print("  on the same machine, which is not a backup strategy:")
        print("     xcopy /Y /I /E data ..\\data_before_go_live\\")
        print("\n  Then:")
        print("     python scripts\\reset_pilot_for_go_live.py --apply "
              "--yes-i-have-a-backup")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(DATA, "_go_live_backup_%s" % stamp)
    os.makedirs(backup, exist_ok=True)
    for name, _e, p in present:
        shutil.copy2(p, os.path.join(backup, name))
    for d, _n in docs:
        dest = os.path.join(backup, os.path.basename(d))
        try:
            shutil.copytree(d, dest, dirs_exist_ok=True)
        except Exception as exc:
            print("  *** could not back up %s: %s" % (d, str(exc)[:40]))
            print("      Refusing to delete what could not be copied.")
            return 1
    print("\n  backed up to %s" % backup)

    for name, empty, p in present:
        json.dump(empty, open(p, "w", encoding="utf-8"), indent=2)
        print("     cleared %s" % name)

    for d, n in docs:
        for root, _dd, files in os.walk(d):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
        print("     cleared %s (%d file(s))" % (d, n))

    print("\n  clearing the mirrored tables ...")
    try:
        from utils.db import Database
        db = Database()
        for name, table in MIRRORS.items():
            if any(n == name for n, _e, _p in present):
                try:
                    db.execute("DELETE FROM %s" % table)
                    print("     emptied %s" % table)
                except Exception as exc:
                    print("     could not empty %s: %s" % (table, str(exc)[:40]))
    except Exception as exc:
        print("     *** THE DATABASE WAS NOT REACHED: %s" % str(exc)[:44])
        print("     The files are cleared but the tables are not, so the next")
        print("     read will put the deals back and this will look as though")
        print("     it did not happen. Fix that BEFORE the team starts.")
        return 1

    print("\n" + "=" * 78)
    print("DONE. THE BACKUP IS AT %s" % backup)
    print("=" * 78)
    print("\n  RESTART UVICORN, then confirm the committees survived - they")
    print("  are the easiest thing to lose in a reset and the hardest to")
    print("  notice missing:")
    print("     python scripts\\diag_committee_sight.py")
    print("     python scripts\\audit_readiness.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
