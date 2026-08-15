#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Put every chair on their own committee's roster. DRY RUN by default.

THE ELDORET FAULT (2026-08-14, found 2026-08-15). Eldoret's committee was
correctly created, correctly routed and correctly staffed with three members -
and the chair, Ludy Chebet Mining, was not one of them. She sat in chaired_by
and nowhere else.

That matters twice over:

  HER VOTE IS MANDATORY. The chair rule requires it before a committee can
  decide, so the committee could reach quorum and still never complete. The
  case would sit at "awaiting the chair" for ever.

  MEMBERSHIP IS MATCHED BY STAFF CODE. A chair named only in chaired_by is
  matched by NAME - fragile where two people share one, and useless where the
  login's full name is spelled differently.

Managers gathered at that branch on two separate days and could not finish a
single case.

The seeder wrote members and the chair as separate things and never joined
them. It has been fixed; this repairs the committees it already built, which a
re-seed will not touch because they already have members.

    python scripts\\seat_the_chairs.py
    python scripts\\seat_the_chairs.py --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

CFG = os.path.join("data", "lms_config.json")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(CFG):
        print("ABORT: %s not found." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    cw = cfg.get("credit_workflow") or {}
    pal = cw.get("committee_palette") or []

    # The register, so a chair can be seated with a real staff code.
    people = {}
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        for _i, r in df.iterrows():
            nm = str(r.get("Staff Name") or "").strip()
            if nm:
                people[nm.lower()] = {
                    "code": str(r.get("Staff Code") or "").strip(),
                    "name": nm,
                    "role": str(r.get("Role") or "").strip()}
    except Exception as exc:
        print("  note: staff register unreadable (%s)" % str(exc)[:40])

    fix, already, unknown = [], [], []
    for c in pal:
        chair = str(c.get("chaired_by", "") or "").strip()
        if not chair:
            continue
        mem = [m for m in (c.get("members") or []) if isinstance(m, dict)]
        code = str(c.get("chair_staff_code", "") or "").strip()
        seated = any(
            (code and str(m.get("staff_code", "")).strip() == code)
            or str(m.get("name", "")).strip().lower() == chair.lower()
            for m in mem)
        if seated:
            already.append(c.get("code"))
            continue
        who = people.get(chair.lower())
        if not who and code:
            who = {"code": code, "name": chair, "role": ""}
        if not who:
            unknown.append((c.get("code"), chair))
            continue
        fix.append((c, who, len(mem)))

    print("=" * 78)
    print("CHAIRS AND THEIR OWN COMMITTEES")
    print("=" * 78)
    print("  already seated      %d" % len(already))
    print("  TO SEAT             %d" % len(fix))
    print("  cannot identify     %d" % len(unknown))

    if fix:
        print("\n  These chairs will be added to their own roster:\n")
        for c, who, n in fix:
            print("     %-12s %-18s %-26s %s"
                  % (c.get("code"), str(c.get("branch") or "")[:18],
                     who["name"][:26], who["code"] or "no code"))
    if unknown:
        print("\n  *** These chairs are not in the register, so they cannot be")
        print("      seated with a staff code. Their mandatory vote will be")
        print("      matched by NAME only, which is fragile:\n")
        for code, chair in unknown:
            print("     %-12s %s" % (code, chair))

    if not fix:
        print("\n  Nothing to do - every identifiable chair already sits on their")
        print("  own committee.")
        return 0

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for c, who, _n in fix:
        mem = list(c.get("members") or [])
        mem.insert(0, {"staff_code": who["code"], "name": who["name"],
                       "role": who["role"] or "Chair",
                       "id": who["code"] or who["name"],
                       "member_id": who["code"] or who["name"]})
        c["members"] = mem
        if who["code"]:
            c["chair_staff_code"] = who["code"]

    cw["committee_palette"] = pal
    cfg["credit_workflow"] = cw
    bak = CFG + ".pre_chairs_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nseated %d chair(s).  (backup: %s)" % (len(fix), os.path.basename(bak)))
    print("The config is read per request - no restart needed.")
    print("\nCheck with:  python scripts\\walkthrough_branch.py --branch Eldoret")
    return 0


if __name__ == "__main__":
    sys.exit(main())
