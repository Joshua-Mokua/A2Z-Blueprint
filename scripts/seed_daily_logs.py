#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed realistic Daily Log activity so the grid, the validation tab and the
reconciliation gate can be seen working.

WHY NOT BranchLogManager.submit(): it hardcodes date.today(), so it cannot
backfill. This writes records in exactly the same shape - including the hourly
map, so the Day Planner renders them - and appends through the manager's own
store.

WHAT IT PRODUCES
  * working days only (utils.workcal), so no Sunday or gazetted-holiday rows
  * a realistic spread: most staff file, some do not, a few are well ahead
  * activity weighted to the ROLE - a teller processes transactions, an RO
    opens accounts and refers loans, a CSM handles complaints
  * ~30% carry a remark
  * older days already validated; the most recent two days left pending so the
    validation tab has something to action
  * branch control totals per branch/day, set slightly ABOVE the staff sum
    (healthy), except one deliberate branch/day where the total is BELOW the
    reported sum so the over-reporting gate can be demonstrated firing

SAFE: dry-run by default. --apply backs up data/branch_logs.json first and
skips any staff/day that already has a log, so re-running does not duplicate.

    python scripts\\seed_daily_logs.py                  # dry run, 10 working days
    python scripts\\seed_daily_logs.py --days 15
    python scripts\\seed_daily_logs.py --apply
    python scripts\\seed_daily_logs.py --branch Fortis --apply
"""
import os
import random
import shutil
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.getcwd())

random.seed(20260808)   # reproducible runs

# Role -> (metric, low, high) activity profile. Anything not listed gets the
# default profile. Keys must exist in the configured metric set; unknown keys
# are dropped rather than invented.
PROFILES = {
    "teller": [("transactions_count", 30, 90), ("customer_visits", 20, 60),
               ("digital_txns", 2, 10), ("teller_errors", 0, 1)],
    "ops":    [("transactions_count", 10, 60), ("accounts_opened", 0, 3),
               ("cards_issued", 0, 4), ("customer_visits", 5, 30),
               ("dfs_registrations", 0, 4)],
    "ro":     [("accounts_opened", 1, 5), ("new_leads", 1, 6),
               ("loans_referred", 0, 3), ("deposits_mobilised", 0, 900000),
               ("cross_sell_success", 0, 3), ("dfs_registrations", 0, 5)],
    "rm":     [("accounts_opened", 0, 3), ("new_leads", 1, 5),
               ("loans_referred", 0, 2), ("loans_disbursed", 0, 2500000),
               ("deposits_mobilised", 0, 2000000), ("cross_sell_success", 0, 2)],
    "csm":    [("complaints_received", 0, 6), ("complaints_resolved", 0, 5),
               ("accounts_opened", 0, 2), ("nps_collected", 0, 12),
               ("customer_visits", 5, 25)],
    "dsa":    [("accounts_opened", 1, 6), ("dfs_registrations", 1, 8),
               ("new_leads", 2, 9)],
    "default": [("accounts_opened", 0, 2), ("customer_visits", 2, 15),
                ("new_leads", 0, 3)],
}

REMARKS = [
    "System slow in the morning, cleared by midday.",
    "Two customers referred to credit for facility restructure.",
    "Cash shortage at the ATM — logged with ops.",
    "Heavy walk-in traffic; queue managed with the floor host.",
    "Follow-up visit to a SME client, proposal shared.",
    "Network outage for about an hour after lunch.",
    "Trained a new colleague on the DFS onboarding flow.",
]


def profile_for(role: str):
    r = str(role).lower()
    if "teller" in r:
        return PROFILES["teller"]
    if "customer service" in r or "service manager" in r:
        return PROFILES["csm"]
    if "direct sales" in r or "dsa" in r:
        return PROFILES["dsa"]
    if "relationship manager" in r:
        return PROFILES["rm"]
    if "relationship officer" in r or r.startswith("ro "):
        return PROFILES["ro"]
    if "operations" in r or "branch operations" in r:
        return PROFILES["ops"]
    return PROFILES["default"]


def main():
    apply = "--apply" in sys.argv
    days = 10
    only_branch = ""
    for i, a in enumerate(sys.argv):
        if a == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])
        if a == "--branch" and i + 1 < len(sys.argv):
            only_branch = sys.argv[i + 1]

    try:
        import pandas as pd
    except ImportError:
        print("pandas not available.")
        return 1

    reg = os.path.join("data", "staff_register.xlsx")
    if not os.path.isfile(reg):
        print("ABORT: %s not found." % reg)
        return 1
    df = pd.read_excel(reg)
    bcol = "Branch" if "Branch" in df.columns else "Unit"

    from utils.branch_log import (
        BranchLogManager, metric_keys, sanitize_hourly, activity_weights,
    )
    from utils import workcal

    mkeys = set(metric_keys())
    weights = activity_weights()

    # Working days, most recent first.
    wdays, d = [], date.today()
    while len(wdays) < days and (date.today() - d).days < days * 3:
        if workcal.is_working_day(d):
            wdays.append(d)
        d -= timedelta(days=1)
    wdays.sort()
    print("seeding %d working days: %s .. %s" % (len(wdays), wdays[0], wdays[-1]))

    blm = BranchLogManager()
    existing = {(str(l.get("staff_code")), str(l.get("log_date"))[:10]) for l in blm.logs}
    print("existing logs in store: %d" % len(blm.logs))

    people = df if not only_branch else df[
        df[bcol].astype(str).str.strip().str.lower() == only_branch.strip().lower()]
    if people.empty:
        print("ABORT: no staff matched branch %r." % only_branch)
        return 1
    print("staff in scope: %d" % len(people))

    new_logs = []
    per_branch_day = {}      # (branch, day) -> {metric: reported_sum}
    seq = len(blm.logs) + 1

    for _, r in people.iterrows():
        code = str(r.get("Staff Code", "")).strip()
        name = str(r.get("Staff Name", "")).strip()
        role = str(r.get("Role", "")).strip()
        branch = str(r.get(bcol, "")).strip()
        if not code:
            continue
        prof = [(k, lo, hi) for k, lo, hi in profile_for(role) if k in mkeys]
        if not prof:
            continue

        # A few people are habitual non-filers; everyone else files most days.
        diligence = random.choice([0.95, 0.9, 0.85, 0.75, 0.55, 0.3])

        for day in wdays:
            iso = day.isoformat()
            if (code, iso) in existing:
                continue
            if random.random() > diligence:
                continue

            weight = workcal.target_weight(day)      # Saturday is a half day
            scale = 0.5 if weight == 0.5 else 1.0
            counts = {}
            for k, lo, hi in prof:
                v = random.randint(int(lo * scale), max(int(hi * scale), int(lo * scale)))
                if v:
                    counts[k] = v
            if not counts:
                continue

            # Spread the day's counts across 2-5 working hours as an hourly map,
            # so the Day Planner renders a real day rather than a flat total.
            hours = sorted(random.sample(range(9, 17), random.randint(2, 5)))
            hourly = {}
            for k, total in counts.items():
                left = total
                for idx, h in enumerate(hours):
                    take = left if idx == len(hours) - 1 else random.randint(0, left)
                    if take:
                        hh = "%02d" % h
                        hourly.setdefault(hh, {"counts": {}, "meetings": [], "note": ""})
                        hourly[hh]["counts"][k] = hourly[hh]["counts"].get(k, 0) + take
                    left -= take
                    if left <= 0:
                        break

            idx_val = round(sum(v * float(weights.get(k, 0)) for k, v in counts.items()), 2)
            recent = (date.today() - day).days <= 1
            log = {
                "id": "LOG%06d" % seq,
                "log_date": iso,
                "staff_code": code,
                "staff_name": name,
                "role": role,
                "unit": branch,
                "status": "submitted",
                "submitted_at": datetime.combine(day, datetime.min.time())
                                        .replace(hour=17, minute=random.randint(0, 59)).isoformat(),
                "validated": not recent,
                "validated_at": None if recent else datetime.combine(
                    day + timedelta(days=1), datetime.min.time()).replace(hour=9).isoformat(),
                "validated_by": None if recent else "seed",
                "rejected": False,
                "auto_submitted": False,
                "remarks": random.choice(REMARKS) if random.random() < 0.3 else "",
                "manager_note": "",
                "index": idx_val,
                "hourly": sanitize_hourly(hourly),
            }
            for k in mkeys:
                log[k] = counts.get(k, 0)
            new_logs.append(log)
            seq += 1

            b = per_branch_day.setdefault((branch, iso), {})
            for k, v in counts.items():
                b[k] = b.get(k, 0) + v

    print("\nwould create %d logs across %d branch-days"
          % (len(new_logs), len(per_branch_day)))
    if new_logs:
        filed = len({(l["staff_code"], l["log_date"]) for l in new_logs})
        print("distinct staff-days filed: %d" % filed)
        print("sample:")
        for l in new_logs[:5]:
            print("   %s %-9s %-24s index=%-7s %s"
                  % (l["log_date"], l["staff_code"], l["staff_name"][:24],
                     l["index"], (l["remarks"] or "")[:32]))

    # Branch control totals: slightly above the reported sum (healthy), with one
    # branch-day deliberately BELOW so the over-reporting gate can be shown.
    keys = sorted(per_branch_day.keys())
    breach = keys[len(keys) // 2] if keys else None
    totals_plan = {}
    for k, sums in per_branch_day.items():
        if k == breach:
            totals_plan[k] = {m: max(int(v * 0.7), 0) for m, v in sums.items()}
        else:
            totals_plan[k] = {m: int(v * random.uniform(1.02, 1.15)) + 1
                              for m, v in sums.items()}
    if breach:
        print("\ndeliberate over-report breach seeded at: %s %s" % breach)

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    bak = os.path.join("data", "branch_logs.json.pre_seed")
    src = os.path.join("data", "branch_logs.json")
    if os.path.isfile(src):
        shutil.copy2(src, bak)
        print("\nbacked up %s -> %s" % (src, bak))

    blm.logs.extend(new_logs)
    blm._save()
    print("wrote %d logs (store now %d)" % (len(new_logs), len(blm.logs)))

    from utils.branch_log_reconcile import set_control_totals
    n = 0
    for (branch, iso), totals in totals_plan.items():
        try:
            set_control_totals(branch, iso, totals)
            n += 1
        except Exception as exc:
            print("  control totals failed for %s %s: %s" % (branch, iso, exc))
    print("set control totals for %d branch-days" % n)
    print("\nRestart uvicorn, then open Manager Queues -> Daily log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
