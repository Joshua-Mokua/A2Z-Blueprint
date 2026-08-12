#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Turn on the Department Analyst and DCC layer. DRY RUN by default.

THIS IS THE BLOCKER BETWEEN A CASE AND THE CREDIT ANALYST. Both
can_submit_to_dcc and can_hand_to_credit_analyst require
department_analyst.enabled. With it off, an analyst cannot send a case to the
Department Credit Committee and nobody can hand it on - and neither button
appears, so it reads as a permission fault rather than a setting.

A CORRECTION TO WHAT THE AUDIT SAID. It reported "not configured". The truth is
narrower and more useful: the block EXISTS, complete, in the code defaults -
disabled. The audit read lms_config.json directly rather than through
get_credit_workflow_config(), which falls back to those defaults, so it
described a missing section that was really a switch set to off. Fixed there
too.

WHAT TURNING IT ON ACTUALLY DOES, so this is not a blind flip:

    ROUTES THE CASE to a segment Department Analyst on reaching the Department
    Credit Committee Review stage, then to the Credit Analyst at Credit
    Analysis.

    REQUIRES A CALL-BACK MEMO and a PEP check before the case can go to the
    DCC. That is required_attachments in the config - the same Call Back Memo
    the pilot asked Catherine to attach.

    THE DEPARTMENT ANALYST CANNOT DECIDE (can_decide: False). They confirm
    completeness and voice support; the DCC advises and the Credit Analyst
    decides. Enabling this adds a step, it does not move the decision.

    AUTO STAGE TRAVEL on real actions.

THE DCC IS ENABLED WITH IT, because half the path is worse than neither: an
analyst able to submit to a committee that is switched off would have the case
stop between the two.

ITS ROSTER STARTS EMPTY, and that is called out rather than filled - the DCC is
a distinct body from the branch committees and its membership is the bank's to
name, not a script's to guess.

    python scripts\\enable_department_analyst.py
    python scripts\\enable_department_analyst.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

CFG = os.path.join("data", "lms_config.json")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1

    # Read through the accessor, so what is reported is what the code SEES -
    # file plus defaults - not just what the file happens to carry.
    try:
        from utils.api_lms_mutations import get_credit_workflow_config
        effective = get_credit_workflow_config() or {}
    except Exception as exc:
        print("ABORT: could not read the credit workflow config: %s" % exc)
        return 1

    cfg = json.load(open(CFG, encoding="utf-8")) or {}
    cw = cfg.get("credit_workflow")
    if not isinstance(cw, dict):
        cw = {}

    da_eff = effective.get("department_analyst") or {}
    dcc_eff = effective.get("dcc") or {}

    print("=" * 74)
    print("DEPARTMENT ANALYST + DCC LAYER")
    print("=" * 74)
    print("  department_analyst.enabled   %s" % da_eff.get("enabled"))
    print("  dcc.enabled                  %s" % dcc_eff.get("enabled"))
    print("  in the FILE                  %s"
          % ("yes" if "department_analyst" in cw else "no - running on code defaults"))

    if da_eff.get("enabled") and dcc_eff.get("enabled"):
        print("\n  Both already on. Nothing to do.")
        return 0

    print("\n  TURNING ON:")
    print("     the case routes to a segment Department Analyst at")
    print("       %r," % da_eff.get("handoff_stage"))
    print("       then to the Credit Analyst at %r"
          % da_eff.get("credit_analyst_handoff_stage"))
    print("     segment roles: %s" % ", ".join(
        "%s -> %s" % (k, v) for k, v in
        (da_eff.get("segment_roles") or {}).items()))
    req = da_eff.get("required_attachments") or []
    if req:
        print("     REQUIRED BEFORE THE DCC: %s" % ", ".join(req))
    if (da_eff.get("compliance_confirmation") or {}).get("pep_check"):
        print("     a PEP check must be confirmed")
    print("     the Department Analyst CANNOT decide - they confirm")
    print("       completeness and support; the Credit Analyst decides")

    roster = dcc_eff.get("members") or []
    print("\n  DCC roster: %d member(s)" % len(roster))
    if not roster:
        print("     *** EMPTY. The DCC is a distinct body from the branch")
        print("         committees and its membership is the bank's to name.")
        print("         A case reaching an empty DCC will stop there, exactly")
        print("         as an empty branch committee would - name the members")
        print("         in admin before routing a product through it.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(CFG, CFG + ".pre_da")
    # Write the FULL effective block, not just the flag - so the file carries
    # what is actually in force and an admin can read it, rather than a lone
    # switch over invisible defaults.
    da = dict(da_eff)
    da["enabled"] = True
    dcc = dict(dcc_eff)
    dcc["enabled"] = True
    cw["department_analyst"] = da
    cw["dcc"] = dcc
    cfg["credit_workflow"] = cw
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, CFG)

    print("\nenabled (backup: %s)" % os.path.basename(CFG + ".pre_da"))
    print("Restart uvicorn, then:")
    print("  python scripts\\audit_committee_path.py")
    print("")
    print("Catherine should now see 'Submit to DCC' on an assigned case in her")
    print("segment, once the Call-Back Memo is attached.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
