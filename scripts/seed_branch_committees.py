#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Create one Branch Credit Committee per branch. DRY RUN by default.

PILOT (2026-08-12): "we created the 16 branch committees but the admin is not
able to see them, and thus technically no branch credit committee is set."

WHAT THE DIAGNOSTIC FOUND. The palette holds five committees, none carrying
kind='branch', and no product references a committee gate at all. So whatever
created the 16 did not land in data/lms_config.json - the admin is not failing
to display them, they are not there.

The API already has POST /api/admin/committee-palette/generate-branch which
does exactly this. This is the same logic runnable from the command line, so
you can see what it will do before it does it - and so it works when the
running instance is the thing in question.

IDEMPOTENT: a branch that already has a committee is skipped, so running it
twice creates nothing the second time.

HEAD OFFICE IS EXCLUDED, as in the API version - HO has no branch credit
committee, and creating one would put a gate in a journey nobody chairs.

WHAT IT DOES NOT DO: assign committees to products. A committee that exists is
not a gate anybody passes through; the product's committee_journey decides
that, and it is an admin decision per product rather than something to guess
at. Admin > product flow > "+ Add committee gate" lists them once they exist.

    python scripts\\seed_branch_committees.py
    python scripts\\seed_branch_committees.py --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

CFG = os.path.join("data", "lms_config.json")
ORG = os.path.join("data", "org_config.json")


def main():
    apply = "--apply" in sys.argv
    for p in (CFG, ORG):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    cfg = json.load(open(CFG, encoding="utf-8")) or {}
    cw = cfg.get("credit_workflow")
    if not isinstance(cw, dict):
        cw = {}
    palette = cw.get("committee_palette")
    if not isinstance(palette, list):
        palette = []

    org = json.load(open(ORG, encoding="utf-8")) or {}
    branches = org.get("branches") or []
    if isinstance(branches, dict):
        branches = list(branches.values())

    have = {str(c.get("branch", "")).strip().lower()
            for c in palette if str(c.get("kind", "")).lower() == "branch"}

    print("=" * 76)
    print("BRANCH CREDIT COMMITTEES")
    print("=" * 76)
    print("  palette today        %d committee(s)" % len(palette))
    print("  of which branch      %d" % len(have))
    print("  branches in config   %d" % len(branches))

    # Best-effort chair. A committee with no chair is still usable - somebody
    # will be named later - so a missing BM is not a reason to refuse.
    def _bm(name):
        try:
            from utils.api_pipeline_scope import get_staff_roster
            df = get_staff_roster()
            for _i, r in df.iterrows():
                role = str(r.get("Role") or "").lower()
                if "branch manager" in role and str(r.get("Region") or "").strip().lower() == name.lower():
                    return str(r.get("Staff Name") or "")
        except Exception:
            pass
        return ""

    planned = []
    for b in branches:
        if not isinstance(b, dict):
            continue
        if str(b.get("type", "")).upper() == "HO":
            continue
        name = str(b.get("name", "")).strip()
        if not name or name.lower() in have:
            continue
        code = "BCC_" + str(b.get("code", name)).strip().upper().replace(" ", "_")
        planned.append({
            "code": code,
            "name": "%s Branch Credit Committee" % name,
            "chaired_by": _bm(name),
            "recording_mode": "voting",
            "voting_rule": "SIMPLE_MAJORITY",
            "amount_threshold_kes": 0.0,
            "branch": name,
            # THE FIELD THAT WAS MISSING. Everything filtering for a branch
            # committee looks for this; without it a committee exists and is
            # invisible to every branch journey.
            "kind": "branch",
            "members": [],
        })

    print("\n  TO CREATE           %d" % len(planned))
    for c in planned[:12]:
        print("     %-22s %-44s chair: %s"
              % (c["code"][:22], c["name"][:44], c["chaired_by"] or "(to be named)"))
    if len(planned) > 12:
        print("     ... and %d more" % (len(planned) - 12))

    if not planned:
        print("\n  Nothing to create - every branch already has one.")
        return 0

    print("\n  Members are left empty for the admin to fill. A committee with no")
    print("  members can still be assigned to a product; it cannot yet vote.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(CFG, CFG + ".pre_committees")
    palette.extend(planned)
    cw["committee_palette"] = palette
    cfg["credit_workflow"] = cw
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, CFG)

    print("\ncreated %d branch committee(s) (backup: %s)"
          % (len(planned), os.path.basename(CFG + ".pre_committees")))
    print("Restart uvicorn, then Admin > product flow > '+ Add committee gate'")
    print("to put a branch committee into the products that need one - that is")
    print("the step that turns an existing committee into an actual gate.")
    print("")
    print("Written at %s" % datetime.now().isoformat(timespec="seconds"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
