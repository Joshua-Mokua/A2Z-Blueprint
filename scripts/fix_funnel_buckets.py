#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Make the funnel show the stages the flows actually use. DRY RUN by default.

FROM THE BANK (2026-09-04): "there are deals in unit review heading to credit
but the funnel does not capture that."

THE FUNNEL MATCHES ON EXACT STAGE NAMES. Each bucket lists the stages it
shows, and a deal appears under a bucket only if its stage string is one of
them. The lists went stale: the flows were renamed and the buckets were not.

    bucket "Unit Review" looks for   Branch Credit Committee
                                     Department Analyst
                                     Department Business Committee

    the flows actually use           Branch Credit Committee Review
                                     Department Credit Analysis
                                     Department Credit Committee Review

Not one of them matches, so every deal at those stages is invisible - the
funnel shows "nothing here" while the deals are plainly there. Eighteen stages
across the catalogue are in this state.

    python scripts\fix_funnel_buckets.py
    python scripts\fix_funnel_buckets.py --apply

WHAT IT DOES: adds the real stage names to the bucket that already means that
part of the journey. Nothing is renamed, nothing is removed, and the old names
stay - a deal still sitting on an old name keeps showing where it did.

WHAT IT DOES NOT TOUCH: Closed Won and Closed Lost belong in no bucket on
purpose - a closed deal has left the funnel. And the early sales stages (Lead,
Contacted, Qualified, Proposal, Negotiation) are left alone: they were removed
from the flows in August and where they still appear it is old data, not a
journey anybody is running. Say so if they should be shown.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "pipeline_settings.json")

# THE FAMILIES DO NOT SHARE A CHAIN. Lending products run
#     Initiation | Documentation | Unit Review | Credit Analysis |
#     Credit Administration | TROPS
# while deposits and insurance run
#     Initiation | Documentation | Approval | Opening
# so a stage has to be added to the bucket that means that part of ITS OWN
# journey. "Account Openned" is an OPENING stage for a current account, not a
# documentation one, and putting it under Documentation would show a completed
# account as still gathering papers.
#
# (family, bucket label) -> stage names to make sure it matches
ADD = {
    ("asset", "Unit Review"): [
        "Branch Credit Committee Review",
        "Department Credit Analysis",
        "Department Credit Committee",
        "Department Credit Committee Review",
    ],
    ("asset", "Credit Administration"): [
        "Credit Administration",
        # A typo in one product's flow. Matching it makes that product's deals
        # visible; correcting the flow itself is a separate, better fix.
        "Credit Administarion",
    ],
    ("asset", "TROPS"): [
        "Trops",
    ],
    # Current Account and Fixed Deposit finish at Opening, not Documentation.
    ("liability", "Opening"): [
        "Account Openned",
        "Fixed Deposit Openned",
    ],
}

# Deliberately not added - see the docstring.
LEAVE = ("Closed Won", "Closed Lost", "Lead", "Contacted", "Qualified",
         "Proposal", "Negotiation", "Offer / Proposal",
         "Lead/Cutomer Instructions")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    sb = cfg.get("stage_buckets") or {}
    flows = cfg.get("product_flows") or {}
    if not sb:
        print("ABORT: no stage_buckets configured - nothing to repair.")
        return 1

    used = {}
    for prod, e in flows.items():
        for st in (e.get("stages") or []):
            n = str(st.get("stage", "")).strip()
            if n:
                used.setdefault(n, set()).add(prod)

    matched = set()
    for buckets in sb.values():
        for b in buckets:
            for st in (b.get("steps") or []):
                matched.add(str(st).strip().lower())

    invisible = sorted(n for n in used if n.strip().lower() not in matched)

    print("=" * 82)
    print("STAGES THE FUNNEL CANNOT SHOW")
    print("=" * 82)
    print("  stage-bucket families  %s" % ", ".join(sb))
    print("  stages in use          %d" % len(used))
    print("  INVISIBLE              %d\n" % len(invisible))
    for n in invisible:
        why = "  (left alone on purpose)" if n in LEAVE else ""
        print("     %-40s %2d product(s)%s" % (n[:40], len(used[n]), why))

    changes = []
    for fam, buckets in sb.items():
        for b in buckets:
            label = str(b.get("label") or b.get("key") or "")
            want = ADD.get((fam, label))
            if not want:
                continue
            have = {str(x).strip().lower() for x in (b.get("steps") or [])}
            new = [w for w in want
                   if w.strip().lower() not in have and w in used]
            if new:
                changes.append((fam, label, b, new))

    if not changes:
        print("\n  Every bucket already matches the stages in use.")
        return 0

    print("\n" + "-" * 82)
    print("WHAT WOULD BE ADDED")
    print("-" * 82)
    for fam, label, _b, new in changes:
        print("  %-10s %-24s + %s" % (fam, label, ", ".join(new)))

    still = [n for n in invisible if n not in LEAVE
             and not any(n in new for _f, _l, _b, new in changes)]
    if still:
        print("\n  STILL INVISIBLE AFTER THIS - no bucket obviously means them:")
        for n in still:
            print("     %-40s %d product(s)" % (n[:40], len(used[n])))
        print("  Say which bucket each belongs in and I will add it.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_buckets_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    for _fam, _label, b, new in changes:
        b["steps"] = list(b.get("steps") or []) + new
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nwritten.  (backup: %s)" % os.path.basename(bak))
    print("\nRESTART UVICORN and hard-refresh. No rebuild - the buckets are")
    print("read at run time. Deals at Unit Review, Credit Analysis, Credit")
    print("Administration and TROPS should now appear where they are.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
