#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
First-cut activity sets per Head Office unit. A STARTING POINT, not an answer.

Pilot request (2026-08-10): "each department has unique set of activities, and
the one that will cut across currently is the referral ... enable the admin to
select from a list of all units and create the unique listing ... if we can look
at the various roles within each unit we can come up with a first cut that the
admin can build on."

So this is drawn from the roles actually in each unit on the live roster - not
invented - and written into branch_log_config.activity_sets for the admin panel
to edit. Every unit below is a proposal the bank should correct.

RULINGS HONOURED
    the daily target stays the SAME for everyone; only WEIGHTS vary
    Head Office units keep NOTHING from the branch base except the REFERRAL
    Branches are unchanged - the branch set is already right

WHY NEW ACTIVITIES ARE PROPOSED, NOT CREATED. Most Head Office work has no
matching field today: an Internal Auditor has no "Audits Completed", an FX
Trader has no "Deals Executed". This script writes sets from EXISTING fields
only, and PRINTS the new activities each unit needs so the admin can create
them deliberately. Inventing fields and weights here would bake guesses into
everyone's index.

THE ORDER MATTERS. Do not switch a unit off the branch base before its set
exists - its people would log nothing and their index would read zero, which
looks identical to having done no work.

    python scripts\\seed_unit_activities.py            # show the proposal
    python scripts\\seed_unit_activities.py --apply
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

# Existing field keys that plausibly apply, per unit, from the roles actually
# present. Deliberately sparse: a short honest set beats a long invented one.
PROPOSED = {
    "Director Operations & Technology": [
        "customer_visits", "transactions_count", "complaints_resolved",
        "complaints_received", "digital_txns", "teller_errors",
    ],
    "Director, Corporate Banking Kenya & EAC": [
        "new_leads", "deposits_mobilised", "loans_disbursed",
        "cross_sell_success", "accounts_opened",
    ],
    "Head of Consumer": [
        "new_leads", "accounts_opened", "dfs_registrations",
        "cards_issued", "bancassurance_sold", "cross_sell_success",
    ],
    "Director Consumer & Commercial Banking (CCB)": [
        "new_leads", "deposits_mobilised", "loans_disbursed", "cross_sell_success",
    ],
    "Director, Credit Risk Management- Kenya & EAC": [
        "loans_disbursed",
    ],
    "Director, Treasury & FICC, EAC": [
        "deposits_mobilised", "new_leads",
    ],
    "Chief Finance Officer": [],
    "Director, Internal Control": [],
    "Director, Internal Audit": [],
    "Country Risk Manager, Kenya & EAC": [],
    "Director Compliance- CESA 1": [],
    "Director, Legal Services & Company Secretary": [],
    "Ag. Head Human Resources & Senior HR Business": [],
    "Corporate Communications Manager": [],
    "Business Manager": [],
    "Personal Assistant": [],
}

# Activities these units genuinely need that DO NOT EXIST yet. Printed for the
# admin to create with weights the bank decides - not written by this script.
NEEDED = {
    "Director Operations & Technology": [
        "Calls handled", "Tickets resolved", "Payments processed",
        "Reconciliation items cleared", "SLA breaches",
    ],
    "Chief Finance Officer": [
        "Reports delivered", "Reconciliations completed", "Queries closed",
    ],
    "Director, Internal Control": [
        "Controls tested", "Exceptions raised", "Exceptions closed",
    ],
    "Director, Internal Audit": [
        "Audit engagements progressed", "Findings raised", "Findings closed",
    ],
    "Director, Credit Risk Management- Kenya & EAC": [
        "Applications appraised", "Turnaround within SLA", "Securities perfected",
    ],
    "Country Risk Manager, Kenya & EAC": [
        "Risk events logged", "Assessments completed",
    ],
    "Director Compliance- CESA 1": [
        "Alerts reviewed", "KYC reviews completed", "STRs filed",
    ],
    "Director, Legal Services & Company Secretary": [
        "Contracts reviewed", "Matters progressed",
    ],
    "Ag. Head Human Resources & Senior HR Business": [
        "Positions filled", "Cases closed", "Training sessions delivered",
    ],
    "Corporate Communications Manager": [
        "Publications issued", "Engagements run",
    ],
    "Director, Treasury & FICC, EAC": [
        "Deals executed", "Client quotes given",
    ],
}


def main():
    apply = "--apply" in sys.argv
    try:
        from utils.branch_log import load_log_config, fields_schema, COMMON_KEYS
        from utils.org_validator import unit_for_role
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    known = {f["key"] for f in fields_schema()}
    bad = {u: [k for k in ks if k not in known] for u, ks in PROPOSED.items()}
    bad = {u: v for u, v in bad.items() if v}
    if bad:
        print("ABORT: proposed sets reference fields that do not exist:")
        for u, v in bad.items():
            print("   %-46s %s" % (u[:46], ", ".join(v)))
        print("Fix the key names in this script - a set pointing at a missing")
        print("field would silently give that unit fewer activities than intended.")
        return 1

    print("=" * 74)
    print("FIRST-CUT ACTIVITY SETS - Head Office")
    print("=" * 74)
    print("Every unit also gets: %s" % ", ".join(COMMON_KEYS))
    print("")
    for u in sorted(PROPOSED):
        ks = PROPOSED[u]
        print("%s" % u[:70])
        if ks:
            print("   existing : %s" % ", ".join(ks))
        else:
            print("   existing : (none apply)")
        need = NEEDED.get(u) or []
        if need:
            print("   NEEDS NEW: %s" % "; ".join(need))
        print("")

    total_new = sum(len(v) for v in NEEDED.values())
    print("=" * 74)
    print("%d units proposed · %d NEW activities the admin must create"
          % (len(PROPOSED), total_new))
    print("=" * 74)
    print("The new activities are NOT written by this script. Their weights")
    print("decide people's index, and a guessed weight is worse than an absent")
    print("one - it looks authoritative and nobody questions it.")
    print("")
    print("Units with an empty set keep the branch base until the admin defines")
    print("theirs. Switching them off it first would show their people zero.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    cfg = load_log_config() or {}
    existing = cfg.get("activity_sets") or {}
    # Only write units that HAVE a set. An empty list would switch that unit
    # off the branch base with nothing to replace it.
    written = {u: ks for u, ks in PROPOSED.items() if ks}
    for u, ks in written.items():
        existing[u] = ks
    cfg["activity_sets"] = existing

    path = os.path.join("data", "branch_log_config.json")
    backup = path + ".pre_unitsets"
    if os.path.isfile(path):
        import shutil
        shutil.copy2(path, backup)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, path)
    print("\nwrote %d unit sets to %s (backup: %s)"
          % (len(written), path, os.path.basename(backup)))
    print("Units with no existing fields were LEFT OUT deliberately - they keep")
    print("the branch base until their activities exist.")
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
