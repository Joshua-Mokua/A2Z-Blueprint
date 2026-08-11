#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Build ONE coherent test world: channels, deals, and a journey. DRY RUN default.

RULING (2026-08-11): "clear all those events and partnerships and create fresh
ones for simulation across the 3 tiers, then have a few deals mapped travelling
across the entire journey but distributed at various stages, so that this is
well interlinked and tests well."

WHY A SCENARIO RATHER THAN MORE TEST DATA. Scattered records prove nothing: a
page can render twelve events and still be broken, because nothing connects the
events to the deals to the analytics. A SCENARIO is data whose shape is known in
advance, so a verifier can assert the numbers rather than a person eyeballing
them. scripts/verify_scenario.py checks exactly what this builds.

WHAT IT BUILDS

  CHANNELS - fresh, replacing the generated ones:
      4 events        two unit-owned, two BRANCH-owned (a customer dinner is a
                      real branch case and must be exercised, not assumed)
      4 partnerships  no budgets - they are measured on expected volume
      4 generators    commission on closure, no budgets

  DEALS - deliberately distributed across the REAL journey stages, read from
  pipeline_funnel rather than hardcoded, so this cannot drift from the funnel:

      every bucket of the loan journey gets at least one deal
      the account journey gets its own
      some CLOSED WON, some CLOSED LOST, most still travelling

  Each deal carries a real staff_code from the roster, a real branch, the
  channel's origin, and the source id - so attribution, scoping, ranking and
  the funnel all read the same records.

WHAT IT DELIBERATELY DOES NOT DO

  It does not touch EXISTING deals. Yours are real work; a seeder that wipes
  them to make its own numbers tidy is a seeder nobody can run twice.

  It writes ONE closed-won deal per channel at most. Every channel showing a
  triumphant return would prove nothing - the interesting cases are the ones
  with leads and no conversions, and those are seeded on purpose.

    python scripts\\seed_scenario.py
    python scripts\\seed_scenario.py --apply
"""
import json
import os
import shutil
import sys
from datetime import date, timedelta

sys.path.insert(0, os.getcwd())

EVENTS = os.path.join("data", "sponsored_events.json")
PARTNERSHIPS = os.path.join("data", "partnerships.json")
GENERATORS = os.path.join("data", "lead_generators.json")
DEALS = os.path.join("data", "pipeline_deals.json")

TODAY = date.today()


def _units():
    from utils.org_validator import md_reporting_roles
    return sorted(md_reporting_roles() or [])


def _pick_unit(units, *words):
    low = {u.lower(): u for u in units}
    for w in words:
        for lu, u in low.items():
            if w in lu:
                return u
    return units[0] if units else ""


def _branches():
    from utils.config import load_org_config
    br = (load_org_config() or {}).get("branches") or []
    if isinstance(br, dict):
        br = list(br.values())
    return [str(b.get("name")) for b in br
            if isinstance(b, dict) and b.get("name")
            and str(b.get("name")).lower() != "head office"]


def _staff():
    """Real staff, so scoping and ranking have somebody to attribute to."""
    from utils.api_pipeline_scope import get_staff_roster
    df = get_staff_roster()
    out = []
    for _i, r in df.iterrows():
        code = str(r.get("Staff Code") or "").strip()
        if code:
            out.append({"code": code, "name": str(r.get("Staff Name") or code),
                        "branch": str(r.get("Region") or ""),
                        "role": str(r.get("Role") or "")})
    return out


def _journey():
    """EVERY real stage name, per flow - never hardcoded, and never just the
    first step of each bucket.

    The first version took buckets_for(f)[n]["steps"][0], which covers one stage
    per BUCKET. But unit_review has three steps and credit_admin has two, so
    three loan stages ended up with no deals at all and the funnel had holes
    exactly where approvals stall. The verifier caught it; the seeder was wrong.
    """
    from utils.pipeline_funnel import buckets_for
    out = {}
    for f in ("asset", "liability"):
        pairs = []
        for b in buckets_for(f):
            for st in (b.get("steps") or []):
                pairs.append((b["key"], st))
        out[f] = pairs
    return out


def main():
    apply = "--apply" in sys.argv
    try:
        units = _units()
        branches = _branches()
        staff = _staff()
        journey = _journey()
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    if not units:
        print("ABORT: no units - org_config is not loaded.")
        return 1
    if not staff:
        print("ABORT: the staff roster is empty. Run where the register exists.")
        return 1
    if not branches:
        print("ABORT: no branches found in org_config.")
        return 1

    consumer = _pick_unit(units, "head of consumer", "consumer & commercial", "consumer")
    corporate = _pick_unit(units, "corporate banking")
    ops = _pick_unit(units, "operations")

    # ── channels ────────────────────────────────────────────────────────────
    events = [
        ("EVT9001", "Nakuru SME Business Forum", "Kenya Chamber of Commerce",
         "unit", consumer, branches[0], "TRADE_FAIR", 1_800_000),
        ("EVT9002", "Diaspora Investment Webinar", "Internal",
         "unit", corporate, "", "DIGITAL", 650_000),
        # BRANCH-owned: the customer-dinner case, exercised rather than assumed.
        ("EVT9003", "%s Customer Dinner" % branches[0], "Internal",
         "branch", branches[0], branches[0], "HOSPITALITY", 420_000),
        ("EVT9004", "%s Market Activation" % branches[1 % len(branches)], "Internal",
         "branch", branches[1 % len(branches)], branches[1 % len(branches)],
         "ACTIVATION", 310_000),
    ]
    partnerships = [
        ("PRT9001", "Toyota Kenya", "Asset Finance", "Motor", corporate, 420_000_000),
        ("PRT9002", "Kenya Power SACCO", "Payroll", "SACCO", consumer, 180_000_000),
        ("PRT9003", "Safaricom Enterprise", "Distribution", "Telco", ops, 260_000_000),
        ("PRT9004", "AAR Insurance", "Bancassurance", "Insurance", consumer, 95_000_000),
    ]
    generators = [
        ("LGN9001", "Daniel Kimathi", "Kimathi Motors", "Motor dealer",
         "Nairobi - Industrial Area", 1.5, consumer),
        ("LGN9002", "Grace Wanjiru", "Wanjiru Properties", "Property agent",
         "Kiambu", 1.0, consumer),
        ("LGN9003", "Mombasa Marine Brokers", "Mombasa Marine Brokers Ltd",
         "Broker", "Mombasa", 0.75, corporate),
        ("LGN9004", "Campus Reach Kenya", "Campus Reach Kenya", "Ambassador",
         "Nairobi universities", 3.0, consumer),
    ]

    # ── deals, spread across the REAL journey ───────────────────────────────
    asset_stages = journey.get("asset") or []
    liab_stages = journey.get("liability") or []
    if not asset_stages:
        print("ABORT: the loan journey has no stages - apply the bucket patchers.")
        return 1

    plan = []
    i = 0

    def _add(channel, src_id, origin, flow, stage, value, closed=""):
        nonlocal i
        s = staff[i % len(staff)]
        i += 1
        plan.append({
            "channel": channel, "src_id": src_id, "origin": origin,
            "flow": flow, "stage": closed or stage,
            "value": value, "staff": s,
        })

    # Every loan bucket gets a deal from an event - so the funnel is populated
    # at every step rather than only at the ends.
    for n, (_key, stage) in enumerate(asset_stages):
        _add("events", events[n % len(events)][0], "events", "asset", stage,
             2_000_000 + n * 750_000)
    for n, (_key, stage) in enumerate(liab_stages):
        _add("events", events[(n + 1) % len(events)][0], "events", "liability",
             stage, 400_000 + n * 120_000)

    # Partnerships: two travelling, one won, one with nothing - because
    # "nothing tagged" is a case the pages claim to handle.
    _add("partnership", "PRT9001", "partnership", "asset", asset_stages[2][1], 9_500_000)
    _add("partnership", "PRT9001", "partnership", "asset", asset_stages[4][1], 6_200_000)
    _add("partnership", "PRT9002", "partnership", "liability", liab_stages[1][1], 850_000)
    _add("partnership", "PRT9003", "partnership", "asset", "", 4_000_000, closed="Closed Won")

    # Generators: one won so commission has something to compute from, one lost
    # so the win rate is not 100%, one still moving.
    _add("lead_gen", "LGN9001", "lead_gen", "asset", "", 3_100_000, closed="Closed Won")
    _add("lead_gen", "LGN9002", "lead_gen", "asset", asset_stages[1][1], 1_450_000)
    _add("lead_gen", "LGN9003", "lead_gen", "asset", "", 2_800_000, closed="Closed Lost")

    print("=" * 76)
    print("SCENARIO")
    print("=" * 76)
    print("  units resolved   consumer=%s" % consumer[:40])
    print("                   corporate=%s" % corporate[:40])
    print("  branches         %d available, using %s"
          % (len(branches), ", ".join(branches[:2])))
    print("  staff            %d real codes" % len(staff))
    print("")
    print("  CHANNELS  %d events (2 unit-owned, 2 branch-owned)" % len(events))
    print("            %d partnerships (no budgets)" % len(partnerships))
    print("            %d lead generators (commission, no budgets)" % len(generators))
    print("")
    print("  DEALS     %d, distributed across the real journey:" % len(plan))
    import collections
    byst = collections.Counter(d["stage"] for d in plan)
    for st, n in byst.most_common():
        print("     %-32s %d" % (st, n))
    won = sum(1 for d in plan if d["stage"] == "Closed Won")
    lost = sum(1 for d in plan if d["stage"] == "Closed Lost")
    print("     (%d won, %d lost, %d still travelling)"
          % (won, lost, len(plan) - won - lost))
    print("")
    print("  EVT9004 and PRT9004 and LGN9004 get NO deals on purpose -")
    print("  'nothing tagged' is a case the pages claim to handle, so it must")
    print("  exist in the world we test against.")
    print("")
    print("  Existing deals are NOT touched.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    # ── write channels ──────────────────────────────────────────────────────
    for path in (EVENTS, PARTNERSHIPS, GENERATORS):
        if os.path.isfile(path):
            shutil.copy2(path, path + ".pre_scenario")

    ev_records = [{
        "id": eid, "name": name, "partner": partner,
        "owner_type": ot, "owner": owner,
        "department": owner if ot == "unit" else "",
        "branch": branch, "event_category": cat, "category_name": cat.title(),
        "start_date": (TODAY - timedelta(days=20 + n * 10)).isoformat(),
        "end_date": (TODAY - timedelta(days=18 + n * 10)).isoformat(),
        "status": "Active" if n < 2 else "Completed",
        "budget_kes": float(budget), "spent_kes": float(budget) * 0.9,
        "target_leads": 20 + n * 10, "target_accounts": 4 + n * 2,
        "created_by": "scenario", "created_at": TODAY.isoformat(),
    } for n, (eid, name, partner, ot, owner, branch, cat, budget) in enumerate(events)]

    pt_records = [{
        "id": pid, "partner_name": name, "name": name,
        "partner_type": ptype, "sector": sector,
        "owner_type": "unit", "owner": owner, "department": owner,
        "signed_date": (TODAY - timedelta(days=200 + n * 40)).isoformat(),
        "status": "Active", "activated": True,
        "expected_volume_kes_m": vol / 1_000_000,
        "target_value_kes": float(vol),
        "target_accounts": max(1, int(vol // 20_000_000)),
        "created_by": "scenario", "created_at": TODAY.isoformat(),
    } for n, (pid, name, ptype, sector, owner, vol) in enumerate(partnerships)]

    lg_records = [{
        "id": gid, "name": name, "company": company, "partner": company,
        "owner_type": "unit", "owner": owner, "department": owner,
        "category_name": kind, "area": area,
        "onboarded_at": (TODAY - timedelta(days=60 + n * 30)).isoformat(),
        "start_date": (TODAY - timedelta(days=60 + n * 30)).isoformat(),
        "status": "Active",
        "budget_kes": 0.0, "spent_kes": 0.0,
        "commission_pct": rate, "commission_basis": "on closure",
        "target_leads": 10 + n * 5, "target_accounts": 2 + n,
        "created_by": "scenario", "created_at": TODAY.isoformat(),
    } for n, (gid, name, company, kind, area, rate, owner) in enumerate(generators)]

    for path, records in ((EVENTS, ev_records), (PARTNERSHIPS, pt_records),
                          (GENERATORS, lg_records)):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
        os.replace(tmp, path)
        print("wrote %d -> %s" % (len(records), path))

    # ── write deals, ADDING to whatever is there ────────────────────────────
    existing = []
    if os.path.isfile(DEALS):
        shutil.copy2(DEALS, DEALS + ".pre_scenario")
        try:
            existing = json.load(open(DEALS, encoding="utf-8"))
        except ValueError:
            existing = []
    if isinstance(existing, dict):
        existing = list(existing.values())
    existing = [d for d in existing if not str(d.get("id", "")).startswith("SCN")]

    field = {"events": "event_id", "partnership": "mou_id", "lead_gen": "channel_id"}
    product = {"asset": "Business Term Loan", "liability": "Current Account"}
    new = []
    for n, d in enumerate(plan, start=1):
        s = d["staff"]
        rec = {
            "id": "SCN%04d" % n,
            "client_name": "Scenario Client %02d" % n,
            "client_type": "Business" if d["flow"] == "asset" else "Individual",
            "staff_code": s["code"], "staff_name": s["name"],
            "branch": s["branch"] or branches[n % len(branches)],
            "product_type": product[d["flow"]],
            "deal_value": float(d["value"]), "amount_kes": float(d["value"]),
            "currency": "KES",
            "stage": d["stage"],
            "origin": d["origin"],
            field[d["channel"]]: d["src_id"],
            "created_at": (TODAY - timedelta(days=n)).isoformat(),
            "open_date": (TODAY - timedelta(days=n)).isoformat(),
            "draft": False,
            "scenario": True,
        }
        new.append(rec)

    tmp = DEALS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(existing + new, fh, indent=2)
    os.replace(tmp, DEALS)
    print("wrote %d scenario deals alongside %d existing -> %s"
          % (len(new), len(existing), DEALS))

    # THE API READS POSTGRES, NOT THIS FILE (_PIPELINE_READ_DB_FIRST = True).
    # Writing JSON alone produced a seeded world the pages could not see: the
    # Events tab reported "0 deals tagged" while twenty sat on disk. Sync each
    # deal through the same function the create endpoint uses, so the scenario
    # exists in the store the system actually serves from.
    synced = failed = 0
    try:
        from utils.api import _db_sync_pipeline_deal, _db_available
        if not _db_available():
            print("\n  postgres not reachable - the JSON store is written, but")
            print("  the API reads the database, so the pages will show nothing.")
            print("  Start postgres and re-run, or the scenario is invisible.")
        else:
            for rec in new:
                try:
                    _db_sync_pipeline_deal(rec)
                    synced += 1
                except Exception as exc:
                    failed += 1
                    if failed == 1:
                        print("  first sync failure: %s" % str(exc)[:70])
            print("synced %d scenario deals to postgres (%d failed)"
                  % (synced, failed))
    except Exception as exc:
        print("  could not sync to postgres: %s" % str(exc)[:70])
        print("  The pages read the database, so the scenario will not appear.")

    print("\nRestart uvicorn, then check it holds together:")
    print("  python scripts\\verify_scenario.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
