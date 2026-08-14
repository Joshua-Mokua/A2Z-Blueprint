#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Switch on the Department Credit Committee and give it members. DRY RUN default.

The committee tab reports "not switched on for this bank" because
credit_workflow.dcc.enabled is false and its member list is empty. That is
config, not code: the palette's B1/B2/B3 committees are the PIPELINE gates,
while credit_workflow.dcc is the LMS-side roster the voting panel reads. Two
places, and only one of them was populated.

MEMBERS ARE TAKEN FROM THE PALETTE, so the same people sit on the same
committee on both sides of the system. Without that, a bank could name a
committee twice and have it disagree with itself.

    python scripts\\enable_dcc.py
    python scripts\\enable_dcc.py --apply
    python scripts\\enable_dcc.py --apply --from B2      # Commercial roster
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "lms_config.json")


def main():
    apply = "--apply" in sys.argv
    src_code = "B1"
    if "--from" in sys.argv:
        i = sys.argv.index("--from")
        if i + 1 < len(sys.argv):
            src_code = sys.argv[i + 1].strip()

    if not os.path.isfile(CFG):
        print("ABORT: %s not found." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    cw = cfg.get("credit_workflow")
    if not isinstance(cw, dict):
        print("ABORT: credit_workflow is missing from the config.")
        return 1

    pal = cw.get("committee_palette") or []
    src = next((c for c in pal if str(c.get("code")) == src_code), None)
    if not src:
        print("ABORT: no committee %r in the palette." % src_code)
        print("       Available: %s"
              % ", ".join(str(c.get("code")) for c in pal[:10]))
        return 1

    members = [m for m in (src.get("members") or []) if isinstance(m, dict)]
    if not members:
        print("ABORT: %s has no members, so the committee could not sit."
              % src_code)
        print("       Name them in Administration > Credit Committees first.")
        return 1

    dcc = dict(cw.get("dcc") or {})
    print("=" * 74)
    print("DEPARTMENT CREDIT COMMITTEE")
    print("=" * 74)
    print("  source committee   %s — %s" % (src_code, src.get("name")))
    print("  currently enabled  %s" % bool(dcc.get("enabled")))
    print("  currently members  %d" % len(dcc.get("members") or []))
    print("")
    print("  WILL BECOME")
    print("    enabled          True")
    print("    name             %s" % (src.get("name") or "Department Credit Committee"))
    print("    members          %d" % len(members))
    for m in members:
        print("       %-10s %-28s %s"
              % (m.get("staff_code"), str(m.get("name"))[:28], m.get("role") or ""))
    if src.get("chaired_by"):
        print("    chair            %s" % src.get("chaired_by"))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    dcc.update({
        "enabled": True,
        "name": src.get("name") or "Department Credit Committee",
        "members": members,
        "chaired_by": src.get("chaired_by", ""),
        "voting_rule": src.get("voting_rule", "SIMPLE_MAJORITY"),
        "min_quorum_count": src.get("min_quorum_count"),
        "source_committee": src_code,
    })
    cw["dcc"] = dcc
    cfg["credit_workflow"] = cw

    bak = CFG + ".pre_dcc_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nenabled, with %d member(s).  (backup: %s)"
          % (len(members), os.path.basename(bak)))
    print("RESTART UVICORN - the config is read at request time, but a stale")
    print("process will keep serving the old roster to anybody already signed in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
