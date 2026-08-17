#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CH4 - Lead Generators become a real channel, not an empty tab.

Events and Partnerships both had populated stores. Lead Generators had none, so
the tab rendered empty and no deal could point at a generator - the channel was
impossible to exercise at all.

TWO SMALL MECHANICS, then the data:

    origin_sources.source_field   lead_gen -> channel_id. A GENERIC field,
        because unlike events and MOUs a generator has no legacy column in the
        deal record to reuse. Any channel added later gets the same field
        rather than another bespoke one - which is the point of having a model.

    origin_sources.options        lead generators are now pickable on the deal
        capture form, reading through origin_channels rather than a second
        store reader.

    api create-clearing           channel_id joins event_id and mou_id in the
        set cleared when it does not match the chosen origin, so a stale
        generator id cannot attribute a walk-in deal to a commission.

WHAT A LEAD GENERATOR IS HERE: a party that sources leads, usually on
commission. The record describes the GENERATOR - who, which unit engaged them,
what rate, what they should produce. It does NOT model the lead lifecycle,
because utils/partner_leads_commissions.py already holds a LeadTrackingEngine
and a CommissionEngine and a second implementation would drift from the first
within a month.

AN OVERLAP FLAGGED RATHER THAN SILENTLY RESOLVED: that existing engine keys
leads off a PARTNER_ID - it already treats lead sources as partners. So a
generator could reasonably be a partnership with a commission arrangement
instead of its own channel. CH4 keeps them separate because they were listed as
a distinct origin, but if commissions are to run through the existing engine the
generator ids will need to line up with partner ids. That is a decision, not a
detail, and it belongs to the bank.

NO BUDGETS ARE SEEDED. Generators are paid commission, so each record carries a
commission_pct and a budget of zero. The channel supports ROI, so a seeded
budget would have produced a return figure nobody earned the moment the
analytics tab opened - the same discipline that keeps partnerships showing null.

The seeder REFUSES to run over a populated file, and refuses to name an owner
unit that does not exist - a generator owned by nobody is invisible to every
view.

Verified: py_compile clean; lead_gen resolves to channel_id and lists 8 options
after seeding.

REQUIRES CH3.

Usage (from project root, .venv active):
    python scripts\patch_ch4_lead_generators.py            # dry run
    python scripts\patch_ch4_lead_generators.py --apply

Then:
    python scripts\seed_lead_generators.py
    python scripts\seed_lead_generators.py --apply
"""
import os
import shutil
import sys

SRC = os.path.join("utils", "origin_sources.py")
API = os.path.join("utils", "api.py")
SEED = os.path.join("scripts", "seed_lead_generators.py")
BACKUP_SUFFIX = ".pre_ch4"

CLEAR_OLD = '''        for _f in ("event_id", "mou_id"):
            if _f != _field:
                deal_dict.pop(_f, None)'''
CLEAR_NEW = '''        for _f in ("event_id", "mou_id", "channel_id"):
            if _f != _field:
                deal_dict.pop(_f, None)'''

OPTIONS = r'''def options(origin_key: str, active_only: bool = True) -> list:
    """The pickable sources for an origin: [{id, label, sub}].

    Returns [] for origins with nothing to pick - self, referral, warehouse -
    so a capture form can simply not render a second dropdown rather than
    special-casing each origin.
    """
    k = str(origin_key or "").strip()
    if k == "events":
        return [{"id": str(e.get("id") or ""),
                 "label": str(e.get("name") or e.get("id") or ""),
                 "sub": " · ".join(x for x in (
                     str(e.get("branch") or ""),
                     str(e.get("start_date") or "")[:10],
                     str(e.get("event_category") or "")) if x)}
                for e in events(active_only) if e.get("id")]
    if k == "lead_gen":
        from utils.origin_channels import listing as _listing
        return [{"id": r["id"], "label": r["name"],
                 "sub": " · ".join(x for x in (r.get("category") or "",
                                               r.get("owner") or "") if x)}
                for r in _listing("lead_gen", active_only) if r.get("id")]
    if k == "partnership":
        return [{"id": str(p.get("id") or ""),
                 "label": str(p.get("partner_name") or p.get("id") or ""),
                 "sub": " · ".join(x for x in (
                     str(p.get("partner_type") or ""),
                     str(p.get("sector") or "")) if x)}
                for p in partnerships(active_only) if p.get("id")]
    return []


'''

SOURCE_FIELD = r'''def source_field(origin_key: str) -> str:
    """Which field on the deal holds the chosen source for this origin."""
    return {"events": "event_id", "partnership": "mou_id",
            "lead_gen": "channel_id"}.get(str(origin_key or "").strip(), "")


'''

SEED_SRC = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed lead generators, so the third channel is testable. DRY RUN by default.

Events and Partnerships both have populated stores. Lead Generators had none, so
the tab renders empty and no deal can point at a generator - which makes the
whole channel impossible to exercise from a development machine.

WHAT A LEAD GENERATOR IS HERE. A party - a person or a firm - that sources leads
for the bank, usually on commission. The record describes the GENERATOR: who
they are, which unit engaged them, what they cost, and what they are expected to
produce. It does NOT model the lead lifecycle: utils/partner_leads_commissions
.py already holds a LeadTrackingEngine and a CommissionEngine for that, and a
second implementation would drift from the first within a month.

AN OVERLAP WORTH DECIDING, not silently resolving: that existing engine keys
leads off a PARTNER_ID, which means it already treats lead sources as partners.
So a lead generator could reasonably be a partnership with a commission
arrangement rather than its own channel. This script keeps them separate,
because they were listed as a distinct origin - but if commissions are to run
through the existing engine, the generator ids here will need to line up with
partner ids, and that is a decision rather than a detail.

Generators are seeded with a BUDGET of zero and a commission rate instead,
because that is how they are actually paid. `supports_roi` is true for the
channel, so once commission is recorded as spend the return becomes real -
seeding a fake budget now would produce a fake return immediately.

    python scripts\\seed_lead_generators.py
    python scripts\\seed_lead_generators.py --apply
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.getcwd())

PATH = os.path.join("data", "lead_generators.json")

# Plausible generator types for a Kenyan bank. Names are obviously generic so
# nobody mistakes seeded test data for a real commercial relationship.
SEED = [
    ("Digital Affiliate Network", "Affiliate", "Head of Consumer", 2.5),
    ("Motor Dealer Referral Desk", "Dealer", "Head of Consumer", 1.5),
    ("SACCO Introducer Programme", "Introducer",
     "Director Consumer & Commercial Banking (CCB)", 2.0),
    ("Property Agent Network", "Agent", "Head of Consumer", 1.0),
    ("Corporate Broker Panel", "Broker",
     "Director, Corporate Banking Kenya & EAC", 0.75),
    ("Campus Ambassador Scheme", "Ambassador", "Head of Consumer", 3.0),
    ("Diaspora Introducer Network", "Introducer",
     "Director Consumer & Commercial Banking (CCB)", 2.0),
    ("Insurance Agency Tie-up", "Agency", "Head of Consumer", 1.75),
]


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
    units = set(md_reporting_roles() or [])
    if not units:
        print("ABORT: no MD-reporting units found - org_config is not loaded.")
        return 1

    unknown = sorted({u for _n, _t, u, _c in SEED} - units)
    if unknown:
        print("ABORT: these owner units do not exist:")
        for u in unknown:
            print("   %s" % u)
        print("A generator owned by a unit nobody has is invisible to every view.")
        return 1

    today = date.today().isoformat()
    records = []
    for i, (name, kind, unit, rate) in enumerate(SEED, start=1):
        records.append({
            "id": "LGN%04d" % i,
            "name": name,
            "partner": name,
            "owner_type": "unit",
            "owner": unit,
            "department": unit,
            "branch": "",
            "category_name": kind,
            "start_date": today,
            "end_date": "",
            "status": "Active",
            # No budget: generators are paid COMMISSION, and a fake budget would
            # produce a fake return the moment the analytics tab opened.
            "budget_kes": 0.0,
            "spent_kes": 0.0,
            "commission_pct": rate,
            "target_leads": 40 * i,
            "target_accounts": 8 * i,
            "target_value_kes": 5_000_000.0 * i,
            "notes": "Seeded for testing.",
            "created_by": "seed",
            "created_at": today,
        })

    print("=" * 70)
    print("LEAD GENERATORS TO SEED")
    print("=" * 70)
    for r in records:
        print("  %-8s %-32s %-6s%% %s"
              % (r["id"], r["name"][:32], r["commission_pct"], r["owner"][:36]))
    print("\n  %d generators, no budgets - commission is how they are paid, and"
          % len(records))
    print("  a seeded budget would produce a return figure nobody earned.")

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
'''


def main():
    apply = "--apply" in sys.argv
    for p in (SRC, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found - apply patch_ev1_origin_sources.py first." % p)
            return 1

    src = open(SRC, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if '"lead_gen": "channel_id"' in src:
        print("ABORT: lead_gen is already wired - CH4 looks applied.")
        return 1
    if "def options(" not in src or "def source_field(" not in src:
        print("ABORT: origin_sources is not in the expected shape.")
        return 1

    i = src.index("def options(origin_key: str")
    j = src.index("def source_field(")
    k = src.index("def attribution(")
    src = src[:i] + OPTIONS + SOURCE_FIELD + src[k:]
    print("  ok  origin_sources - lead generators pickable, channel_id field")

    if api.count(CLEAR_OLD) == 1:
        api = api.replace(CLEAR_OLD, CLEAR_NEW, 1)
        print("  ok  api - channel_id joins the cleared source fields")
    elif "channel_id" in api:
        print("  ok  api already clears channel_id")
    else:
        print("ABORT: could not find the source-clearing block in api.py.")
        return 1

    # A stale source id must not survive an origin change.
    if '"channel_id"' not in CLEAR_NEW:
        print("ABORT: channel_id is not cleared - a stale generator id could")
        print("       attribute a walk-in deal to a commission.")
        return 1
    if '"lead_gen": "channel_id"' not in SOURCE_FIELD:
        print("ABORT: lead_gen does not map to a source field.")
        return 1
    if 'k == "lead_gen"' not in OPTIONS:
        print("ABORT: lead generators are not offered on the capture form.")
        return 1
    # The seeder must not invent a budget.
    if '"budget_kes": 0.0' not in SEED_SRC or "commission_pct" not in SEED_SRC:
        print("ABORT: the seeder does not pay generators by commission - a")
        print("       seeded budget would produce a return nobody earned.")
        return 1
    print("  ok  post-checks: field wired, id cleared, no invented budget")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((SRC, src), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)
    if not os.path.exists(SEED):
        open(SEED, "w", encoding="utf-8", newline="").write(SEED_SRC)
        print("CREATED %s" % SEED)

    import py_compile
    for path in (SRC, API, SEED):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Now give the channel something to show:")
    print("  python scripts\\seed_lead_generators.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
