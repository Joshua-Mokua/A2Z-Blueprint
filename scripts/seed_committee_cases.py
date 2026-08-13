#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Put a few cases in front of a real committee member. DRY RUN by default.

WHY. "Add a few cases for Joyce so that I can get comfortable with how that
would work before we push to Alex." Reading that the queue works is not the
same as watching it work with a name you recognise.

It finds a branch committee that HAS members, takes its first member, and
creates cases at that branch sitting at the committee stage - so they appear in
that person's Committee tab and nowhere else.

TEST DATA IS OBVIOUS AND REMOVABLE. Every case is prefixed SIMBCC and named so
nobody mistakes it for real pipeline. Remove them all with --clean.

    python scripts\\seed_committee_cases.py                    # show the plan
    python scripts\\seed_committee_cases.py --apply
    python scripts\\seed_committee_cases.py --clean            # remove them
    python scripts\\seed_committee_cases.py --branch Fortis    # a named branch
    python scripts\\seed_committee_cases.py --member KE96      # a specific person
"""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.getcwd())

PREFIX = "SIMBCC"


def main():
    apply = "--apply" in sys.argv
    clean = "--clean" in sys.argv
    want = ""
    if "--member" in sys.argv:
        i = sys.argv.index("--member")
        if i + 1 < len(sys.argv):
            want = sys.argv[i + 1].strip()
    # NAME THE BRANCH, because "the first committee with members" is whichever
    # happens to sort first and not the one somebody is sitting in front of.
    want_branch = ""
    if "--branch" in sys.argv:
        i = sys.argv.index("--branch")
        if i + 1 < len(sys.argv):
            want_branch = sys.argv[i + 1].strip()

    try:
        from utils.core import PipelineManager
    except Exception as exc:
        print("ABORT: cannot load the pipeline: %s" % exc)
        return 1
    pm = PipelineManager()

    if clean:
        before = len(pm.deals)
        pm.deals[:] = [d for d in pm.deals
                       if not str(d.get("id", "")).startswith(PREFIX)]
        pm._save_deals()
        print("removed %d simulated case(s)." % (before - len(pm.deals)))
        return 0

    try:
        cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    except Exception as exc:
        print("ABORT: cannot read lms_config.json: %s" % exc)
        return 1
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])

    # A committee that can actually sit - members, and a branch to attach to.
    cands = [c for c in pal
             if str(c.get("kind", "")).lower() == "branch"
             and (c.get("members") or []) and c.get("branch")]
    if want_branch:
        named = [c for c in cands
                 if str(c.get("branch", "")).strip().lower() == want_branch.lower()]
        if not named:
            print("ABORT: no branch committee for %r with members." % want_branch)
            print("       Branches that have one: %s"
                  % ", ".join(sorted(str(c.get("branch")) for c in cands)[:10]))
            return 1
        cands = named
    if want:
        cands = [c for c in cands
                 if any(str(m.get("staff_code", "")) == want
                        for m in (c.get("members") or []))] or cands
    if not cands:
        print("ABORT: no branch committee has members.")
        print("       Run scripts\\seed_committee_members.py --apply first.")
        return 1

    cttee = cands[0]
    branch = str(cttee.get("branch"))
    members = cttee.get("members") or []
    member = next((m for m in members if str(m.get("staff_code", "")) == want),
                  members[0])

    print("=" * 74)
    print("SIMULATED COMMITTEE CASES")
    print("=" * 74)
    print("  committee   %s (%s)" % (cttee.get("name"), cttee.get("code")))
    print("  branch      %s" % branch)
    print("  will appear for")
    for m in members:
        print("     %-10s %-28s %s"
              % (m.get("staff_code"), m.get("name"), m.get("role", "")))

    # An owner at that branch. Committee members are usually branch staff, so
    # the RM who owns the deal should be too - otherwise scope, not the
    # committee, decides what is seen.
    owner_code, owner_name = "", ""
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        for _i, r in df.iterrows():
            if str(r.get("Unit") or "").strip().lower() != branch.lower():
                continue
            role = str(r.get("Role") or "").lower()
            if "relationship" in role and "dsa" not in role:
                owner_code = str(r.get("Staff Code") or "")
                owner_name = str(r.get("Staff Name") or "")
                break
    except Exception:
        pass
    if not owner_code:
        owner_code, owner_name = str(member.get("staff_code")), str(member.get("name"))
        print("  (no RM found at %s - the case will be owned by the member)" % branch)
    print("  owner       %s (%s)" % (owner_name, owner_code))

    stage = "Branch Credit Committee Review"
    now = datetime.now()
    # THE BRANCH GOES IN THE ID. Without it, seeding Westlands and then Fortis
    # reuses SIMBCC01..03, the second run reports "already present" and the
    # cases stay attached to the FIRST branch - which reads exactly like the
    # routing sending a Fortis deal to Westlands' committee. It cost an hour
    # chasing a bug that was this line.
    _tag = "".join(ch for ch in branch.upper() if ch.isalnum())[:6]
    plan = [
        ("%s_%s_01" % (PREFIX, _tag), "Mwangi Hardware Ltd", "Business Loan", 3_500_000, "Commercial"),
        ("%s_%s_02" % (PREFIX, _tag), "Achieng Transporters", "Asset Finance", 8_200_000, "Commercial"),
        ("%s_%s_03" % (PREFIX, _tag), "Kimani Family Home", "Mortgage", 12_000_000, "Consumer"),
    ]
    existing = {str(d.get("id")) for d in pm.deals}
    todo = [p for p in plan if p[0] not in existing]

    print("\n  CASES (%d)" % len(todo))
    for did, client, prod, val, ct in todo:
        print("     %-10s %-24s %-16s KES %s" % (did, client, prod, "{:,}".format(val)))
    if not todo:
        print("     already present for %s - nothing to do." % branch)
        print("     (--clean removes every simulated case, on every branch)")
        return 0
    print("\n  Each is manager-validated and sitting at %r, which is what puts" % stage)
    print("  it in front of the committee rather than the owner.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for n, (did, client, prod, val, ct) in enumerate(todo):
        pm.deals.append({
            "id": did, "client_name": client,
            "product": prod, "product_type": prod,
            "deal_value": val, "currency": "KES",
            "staff_code": owner_code, "staff_name": owner_name,
            "branch": branch, "unit": branch,
            "client_type": ct, "segment": "Premier" if ct == "Consumer" else "SME",
            "stage": stage,
            "manager_validated": True,
            "created_at": (now - timedelta(days=6 - n)).isoformat(timespec="seconds"),
            "updated_at": (now - timedelta(days=2 - n if n < 2 else 0)).isoformat(timespec="seconds"),
            "notes": "Simulated for committee walkthrough - safe to delete.",
        })
    pm._save_deals()
    print("\ncreated %d case(s)." % len(todo))
    print("Sign in as %s (%s) and open Manager Queues > Committee."
          % (member.get("name"), member.get("staff_code")))
    print("Remove them afterwards with:  python scripts\\seed_committee_cases.py --clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
