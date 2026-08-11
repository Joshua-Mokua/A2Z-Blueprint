#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed lead generators, so the third channel is testable. DRY RUN by default.

WHAT A LEAD GENERATOR IS (ruling 2026-08-11): "an EXTERNAL party that we recruit
owing to their influence in a particular area. We onboard them - name, company,
when onboarded, area. They generate business leads and are PAID UPON CLOSURE ON
A COMMISSION BASIS."

DISTINCT FROM A PARTNERSHIP, and the difference is not cosmetic: "a partnership
may not specifically be a commission but maybe incentivised - for example a
partnership with Toyota to finance our customers purchasing cars from them."

    LEAD GENERATOR   an individual or firm recruited for local influence.
                     Onboarded, assigned an area, PAID A COMMISSION when a deal
                     they sourced CLOSES. The money is a cost per closed deal.

    PARTNERSHIP      a commercial arrangement with another business, where the
                     value is access to their customers rather than introductions
                     bought by the deal. Often incentivised, rarely commissioned.

So they stay separate channels. This also settles the overlap flagged in CH4:
utils/partner_leads_commissions.py keys leads off a partner_id, but a generator
is not a partner - and merging them would have made "what does a lead cost us"
unanswerable for one of the two.

BECAUSE THEY ARE PAID ON CLOSURE, a generator has NO BUDGET. Each carries a
commission_pct instead. The channel supports ROI, so seeding a fake budget would
produce a fake return the moment the analytics tab opened - and the real spend
figure will be earned commission, once closures exist to compute it from.

OWNER UNITS ARE RESOLVED AT RUNTIME, never hardcoded. The first version named
"Head of Consumer", which stopped being a unit the same morning it was
re-parented under CCB - and the seeder aborted. Anything that hardcodes a unit
name breaks every time the hierarchy moves.

    python scripts\\seed_lead_generators.py
    python scripts\\seed_lead_generators.py --apply
"""
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())

PATH = os.path.join("data", "lead_generators.json")

# (name, company, kind, area, commission %, which unit - by KEYWORD, resolved
# against whatever units exist at runtime)
SEED = [
    ("Daniel Kimathi", "Kimathi Motors Ltd", "Motor dealer", "Nairobi - Industrial Area", 1.5, "consumer"),
    ("Grace Wanjiru", "Wanjiru Properties", "Property agent", "Kiambu", 1.0, "consumer"),
    ("Mombasa Marine Brokers", "Mombasa Marine Brokers Ltd", "Broker", "Mombasa", 0.75, "corporate"),
    ("Peter Otieno", "Lakeside SACCO Link", "SACCO introducer", "Kisumu", 2.0, "commercial"),
    ("Aisha Noor", "Noor Diaspora Advisory", "Diaspora introducer", "Diaspora - Gulf", 2.0, "commercial"),
    ("Rift Agri Aggregators", "Rift Agri Aggregators Ltd", "Agri aggregator", "Nakuru / Eldoret", 1.25, "corporate"),
    ("Campus Reach Kenya", "Campus Reach Kenya", "Campus ambassador", "Nairobi universities", 3.0, "consumer"),
    ("Halima Yusuf", "Yusuf Insurance Agency", "Insurance agency", "Garissa", 1.75, "consumer"),
]

# Keyword -> preferred unit, matched against the units that ACTUALLY exist.
# Keywords must be specific enough to match a BANKING unit. "corporate" alone
# matched "Corporate Communications Manager" - a communications role, not a
# banking one. A loose keyword does not fail; it quietly assigns work to the
# wrong department, which is worse.
KEYWORDS = {
    "consumer": ("head of consumer", "consumer & commercial", "consumer"),
    "commercial": ("consumer & commercial", "commercial banking", "consumer"),
    "corporate": ("corporate banking",),
}
# Units that must never be offered as an owner for a commercial channel, even
# by a fallback - they do not sell.
NEVER = ("communications", "audit", "control", "compliance", "legal",
         "human resources", "personal assistant", "business manager")


def _resolve(units: list, key: str) -> str:
    """Pick a real unit for this keyword, else the first commercial-looking one.

    Never returns a name that does not exist - a generator owned by a unit
    nobody has is invisible to every view.
    """
    low = {u.lower(): u for u in units}
    for want in KEYWORDS.get(key, ()):
        for lu, u in low.items():
            if want in lu:
                return u
    for lu, u in low.items():
        if any(w in lu for w in ("commercial banking", "corporate banking",
                                 "consumer", "retail")):
            return u
    # Last resort: any unit that is not obviously a support function.
    for lu, u in low.items():
        if not any(bad in lu for bad in NEVER):
            return u
    return ""


def main():
    apply = "--apply" in sys.argv
    if os.path.exists(PATH):
        try:
            existing = json.load(open(PATH, encoding="utf-8"))
        except ValueError:
            existing = []
        if existing:
            print("ABORT: %s already has %d records. Seeding would duplicate"
                  % (PATH, len(existing)))
            print("       them; delete the file first if you meant to reseed.")
            return 1

    try:
        from utils.org_validator import md_reporting_roles
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1
    units = sorted(md_reporting_roles() or [])
    if not units:
        print("ABORT: no MD-reporting units found - org_config is not loaded.")
        return 1

    today = date.today()
    records = []
    for i, (name, company, kind, area, rate, want) in enumerate(SEED, start=1):
        owner = _resolve(units, want)
        if not owner:
            print("ABORT: could not resolve any owner unit.")
            return 1
        records.append({
            "id": "LGN%04d" % i,
            "name": name,
            # The generator is a PERSON or a FIRM; company is who they trade as.
            "company": company,
            "partner": company or name,
            "owner_type": "unit",
            "owner": owner,
            "department": owner,
            "branch": "",
            "category_name": kind,
            # The area they were recruited FOR - the whole reason they were
            # recruited is influence somewhere specific.
            "area": area,
            "onboarded_at": (today - timedelta(days=30 * i)).isoformat(),
            "start_date": (today - timedelta(days=30 * i)).isoformat(),
            "end_date": "",
            "status": "Active",
            # PAID ON CLOSURE, so no budget. Spend becomes real commission once
            # deals close; a seeded budget would fabricate a return today.
            "budget_kes": 0.0,
            "spent_kes": 0.0,
            "commission_pct": rate,
            "commission_basis": "on closure",
            "target_leads": 20 * i,
            "target_accounts": 4 * i,
            "target_value_kes": 2_500_000.0 * i,
            "notes": "Seeded for testing.",
            "created_by": "seed",
            "created_at": today.isoformat(),
        })

    print("=" * 76)
    print("LEAD GENERATORS TO SEED")
    print("=" * 76)
    for r in records:
        print("  %-8s %-22s %-26s %-4s%%  %s"
              % (r["id"], r["name"][:22], r["area"][:26],
                 r["commission_pct"], r["owner"][:28]))
    print("\n  %d generators. No budgets - they are paid a COMMISSION ON CLOSURE,"
          % len(records))
    print("  so spend becomes real only when deals close. A seeded budget would")
    print("  have produced a return figure nobody earned.")
    print("\n  owner units resolved against the %d that actually exist." % len(units))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    os.makedirs(os.path.dirname(PATH) or ".", exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
    os.replace(tmp, PATH)
    print("\nwrote %d generators to %s" % (len(records), PATH))
    print("Restart uvicorn. Origin Channels > Lead Generators.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
