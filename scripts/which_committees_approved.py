#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Which committees actually approved each case, and where its deal stands.

The workbench shows "recommended by X", where X is whichever committee closed
LAST. A branch committee sitting after a department one overwrites the label,
so a case that a department committee recommended can read BCC_BRN014.

This reads the committee RECORDS on the deal, which cannot be overwritten that
way, and puts them beside the case status and the deal stage - the two numbers
that are supposed to agree.

    python scripts/which_committees_approved.py

Read only.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

APPROVING = ("APPROVED", "RECOMMENDED", "SUPPORTED")


def main():
    from utils.core import PipelineManager
    from utils.api_lms_routes import _lam

    apps = {str(a.get("id")): a for a in (getattr(_lam(), "apps", []) or [])}
    deals = PipelineManager().deals or []

    rows = []
    for d in deals:
        app_id = str(d.get("lms_application_id") or "").strip()
        a = apps.get(app_id)
        if not a:
            continue
        recs = d.get("committee_records") or {}
        appr = [c for c, r in recs.items()
                if isinstance(r, dict)
                and str(r.get("outcome", "")).upper() in APPROVING]
        if not appr:
            continue
        dept = [c for c in appr if not str(c).upper().startswith("BCC_BRN")]
        brn = [c for c in appr if str(c).upper().startswith("BCC_BRN")]
        rows.append({
            "case": app_id, "deal": str(d.get("id")),
            "client": str(d.get("client_name") or ""),
            "status": str(a.get("status") or ""),
            "stage": str(d.get("stage") or ""),
            "label": str(a.get("committee_recommended_by") or ""),
            "dept": dept, "brn": brn,
        })

    print("=" * 108)
    print("WHICH COMMITTEES APPROVED, AND WHERE THE DEAL STANDS")
    print("=" * 108)
    print("  cases with an approving committee  %d\n" % len(rows))
    if not rows:
        print("  None.")
        return 0

    print("  %-11s %-24s %-11s %-24s %-22s %s"
          % ("CASE", "CLIENT", "LABEL SAYS", "DEPARTMENT APPROVED", "CASE STATUS", "DEAL STAGE"))
    misleading = 0
    for r in sorted(rows, key=lambda x: x["case"]):
        lab = r["label"] or "-"
        dept = ", ".join(r["dept"]) or "(none)"
        if r["dept"] and lab.upper().startswith("BCC_BRN"):
            misleading += 1
            lab += " *"
        print("  %-11s %-24s %-11s %-24s %-22s %s"
              % (r["case"][:11], r["client"][:24], lab[:11], dept[:24],
                 r["status"][:22], r["stage"][:26]))

    print("\n  * the label names a BRANCH committee although a DEPARTMENT one")
    print("    also approved: %d case(s). The label is the last committee to"
          % misleading)
    print("    close, not the one that matters.")

    # Do the two numbers agree?
    ready = [r for r in rows
             if str(r["status"]).lower() in ("committee_recommended",
                                             "committee_approved")]
    at_ca = [r for r in rows if r["stage"] == "Credit Analysis"]
    print("\n" + "=" * 108)
    print("DO THE TWO SCREENS AGREE?")
    print("=" * 108)
    print("  credit risk's workbench (case status)  %d" % len(ready))
    print("  the funnel at Credit Analysis (stage)  %d" % len(at_ca))
    only_wb = [r["case"] for r in ready if r not in at_ca]
    only_fn = [r["deal"] for r in at_ca if r not in ready]
    if only_wb:
        print("\n  on the workbench, not in the funnel: %s" % ", ".join(only_wb))
        print("     the case moved and the deal did not")
    if only_fn:
        print("\n  in the funnel, not on the workbench: %s" % ", ".join(only_fn))
        print("     the deal moved and the case did not")
    if not only_wb and not only_fn:
        print("\n  They agree.")
    else:
        print("\n  align_deal_stage_to_case.py closes the first kind.")
        print("  The second kind is a deal walked forward by hand.")

    # Department approvals whose case never got marked.
    missed = [r for r in rows
              if r["dept"] and str(r["status"]).lower() not in
              ("committee_recommended", "committee_approved", "credit_admin",
               "disbursed", "declined")]
    if missed:
        print("\n  DEPARTMENT-APPROVED BUT NOT MARKED: %d" % len(missed))
        for r in missed:
            print("     %-11s %-24s dept=%s status=%s"
                  % (r["case"][:11], r["client"][:24],
                     ", ".join(r["dept"]), r["status"]))
        print("     mark_already_approved_cases.py should pick these up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
