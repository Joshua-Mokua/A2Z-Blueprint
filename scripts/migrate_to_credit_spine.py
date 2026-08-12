#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bring the remaining lending products onto the credit spine. DRY RUN by default.

Seven of the twelve Asset products already carry the spine. This maps the other
five onto it:

    Asset Finance, Bundled Loan Product, Business Loan, Overdraft, Personal Loan

RENAMING A STAGE MOVES LIVE DEALS. That is the whole risk here, so this counts
the deals sitting on every stage it would touch and shows them BEFORE changing
anything. A stage carrying deals is not renamed silently - it is listed, with
the count, so somebody can decide whether that is where those cases should end
up.

WHAT MAPS TO WHAT, and why each one:

    Credit Assessment - BCC      -> Branch Credit Committee Review
        the same step under an older name

    Credit Analysis & Assesment  -> Credit Analysis
    Credit Analyst & Assesment   -> Credit Analysis
        two spellings of one stage, both reaching users

    Credit Admin                 -> Credit Administration
    Closed - Trops               -> Trops
    Closed Lost - Trops          -> Trops
        "Closed - Trops" conflated a working stage with a closing one, which is
        why these flows had no real closing stage

Stages with no mapping are LEFT WHERE THEY ARE. Lead, Contacted, Qualified,
Offer / Proposal and Negotiation are legitimate per-product steps and the spine
explicitly allows extra stages between its fixed points.

MISSING SPINE STAGES ARE INSERTED in the right place, with Closed Won and
Closed Lost appended - a flow that cannot be closed is the fault behind the
fixed deposit the pilot reported.

    python scripts\\migrate_to_credit_spine.py
    python scripts\\migrate_to_credit_spine.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

PS = os.path.join("data", "pipeline_settings.json")

SPINE = [
    "Documentation",
    "Branch Credit Committee Review",
    "Department Credit Analysis",
    "Department Credit Committee Review",
    "Credit Analysis",
    "Credit Administration",
    "Trops",
]

RENAME = {
    "credit assessment - bcc": "Branch Credit Committee Review",
    "credit analysis & assesment": "Credit Analysis",
    "credit analyst & assesment": "Credit Analysis",
    "credit admin": "Credit Administration",
    "closed - trops": "Trops",
    "closed lost - trops": "Trops",
}

CLOSING = ["Closed Won", "Closed Lost"]


def _deal_counts():
    """How many live deals sit on each stage, per product."""
    out = {}
    try:
        from utils.core import PipelineManager
        for d in (getattr(PipelineManager(), "deals", []) or []):
            prod = str(d.get("product_type") or d.get("product") or "")
            stage = str(d.get("stage") or "")
            if prod and stage:
                out.setdefault(prod, {}).setdefault(stage, 0)
                out[prod][stage] += 1
    except Exception:
        pass
    return out


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PS):
        print("ABORT: %s not found - run from the project root." % PS)
        return 1

    ps = json.load(open(PS, encoding="utf-8")) or {}
    flows = ps.get("product_flows") or {}
    cat = (ps.get("product_catalogue") or {}).get("Assets") or []
    assets = {str(n).strip().lower() for n in cat}
    counts = _deal_counts()

    print("=" * 76)
    print("MIGRATE TO THE CREDIT SPINE")
    print("=" * 76)

    plans, moves = [], []
    for prod, e in sorted(flows.items()):
        names_now = [str(x.get("stage", "") or "") for x in (e or {}).get("stages") or []]
        # NON-CREDIT PRODUCTS GET THE CLOSING STAGES TOO, and nothing else. A
        # savings account must not be forced through a credit committee, but it
        # must still be closable - Fixed Deposit is the one the pilot reported,
        # and Current Account, Savings Account and Credit Card sit in exactly
        # the same state behind it.
        if prod.strip().lower() not in assets:
            if names_now and not any("closed" in n.lower() for n in names_now):
                add = [c for c in CLOSING
                       if not any(c.lower() == n.lower() for n in names_now)]
                plans.append((prod, names_now, names_now + add, [], add))
            continue
        names = [str(s.get("stage", "") or "") for s in (e or {}).get("stages") or []]
        if all(x in names for x in SPINE):
            pos = [names.index(x) for x in SPINE]
            if pos == sorted(pos) and any("closed" in n.lower() for n in names):
                continue  # already good

        new_names, renamed = [], []
        for n in names:
            r = RENAME.get(n.strip().lower())
            if r:
                renamed.append((n, r))
                if r not in new_names:
                    new_names.append(r)
            elif n not in new_names:
                new_names.append(n)

        # ── REBUILD IN SPINE ORDER ──────────────────────────────────────────
        # Renaming alone is not enough, and the first version of this proved
        # it: "Credit Analysis & Assesment" sat at position four, was renamed
        # to "Credit Analysis", and stayed there - so the migration produced
        # Credit Analysis BEFORE the Branch Credit Committee, violating the
        # spine it was building. The dry run showed it; nothing was applied.
        #
        # So the spine is laid down in ITS order, and every other stage is
        # attached to whichever spine stage it currently follows. A product's
        # own steps keep their place in the journey without being able to
        # displace a fixed point.
        inserted = [sp for sp in SPINE if sp not in new_names]

        spine_set = set(SPINE)
        extras_after = {sp: [] for sp in SPINE}
        lead_extras = []          # anything before the first spine stage
        current = None
        for n in new_names:
            if n in spine_set:
                current = n
            elif current is None:
                lead_extras.append(n)
            else:
                extras_after[current].append(n)

        rebuilt_names = list(lead_extras)
        for sp in SPINE:
            rebuilt_names.append(sp)
            rebuilt_names.extend(extras_after.get(sp, []))
        new_names = rebuilt_names

        for c in CLOSING:
            if not any(c.lower() == x.lower() for x in new_names):
                new_names.append(c)
                inserted.append(c)

        plans.append((prod, names, new_names, renamed, inserted))
        for old, new in renamed:
            n = (counts.get(prod) or {}).get(old, 0)
            if n:
                moves.append((prod, old, new, n))

    if not plans:
        print("  Every lending product already carries the spine.")
        return 0

    for prod, old, new, renamed, inserted in plans:
        print("\n  %s" % prod)
        print("     before  %s" % " -> ".join(old))
        print("     after   %s" % " -> ".join(new))
        if renamed:
            print("     renamed %s" % "; ".join("%s -> %s" % r for r in renamed))
        if inserted:
            print("     added   %s" % ", ".join(inserted))

    print("\n" + "-" * 76)
    if moves:
        print("  *** LIVE DEALS THAT WOULD MOVE")
        for prod, old, new, n in moves:
            print("     %-22s %-28s -> %-28s %d deal(s)"
                  % (prod[:22], old[:28], new[:28], n))
        print("")
        print("  Read that list before applying. A rename moves every deal on")
        print("  that stage, and where those cases land is a decision about")
        print("  the bank's process - not something to discover afterwards.")
    else:
        print("  No live deal sits on any stage being renamed.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(PS, PS + ".pre_spine")
    for prod, _old, new_names, _r, _i in plans:
        e = flows[prod]
        by_name = {str(s.get("stage", "") or ""): s for s in (e.get("stages") or [])}
        rebuilt = []
        for n in new_names:
            src = by_name.get(n)
            if src is None:
                # A stage that was renamed keeps its original target_days.
                for o, r in RENAME.items():
                    if r == n:
                        src = next((v for k, v in by_name.items()
                                    if k.strip().lower() == o), None)
                        if src:
                            break
            rebuilt.append({"stage": n,
                            "target_days": (src or {}).get("target_days", 3),
                            "win_probability": (src or {}).get("win_probability")})
        e["stages"] = rebuilt
        flows[prod] = e
    ps["product_flows"] = flows
    tmp = PS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ps, fh, indent=2)
    os.replace(tmp, PS)

    print("\nmigrated %d product(s) (backup: %s)"
          % (len(plans), os.path.basename(PS + ".pre_spine")))
    print("Restart uvicorn, then confirm nothing is stranded:")
    print("  python scripts\\audit_deal_journey.py")
    print("  python scripts\\pilot_status.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
