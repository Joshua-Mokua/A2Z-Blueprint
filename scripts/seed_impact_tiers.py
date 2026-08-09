#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Derive the 80/20 impact tiers from ACTUAL logged activity — READ ONLY unless
--apply.

WHY DERIVE RATHER THAN DECLARE. Every activity currently resolves to 'medium'
because none have been assigned, so the impact pie is one colour. Rather than
guess which activities matter, this measures it: each activity's share of the
total index actually produced over the window, sorted descending, with the
cumulative share taken to the Pareto cut.

    HIGH    the activities making up the first 80% of index produced
    MEDIUM  the next 15%
    LOW     the tail

That is the literal Pareto reading, computed from what your people actually did,
not from an opinion about what they ought to be doing.

CAVEAT WORTH READING. Share of index is weight x volume, so a high-weight
activity that rarely happens can land LOW simply because it is rare — a
deliberate under-use is exactly what a Pareto analysis is meant to reveal, not
hide. Treat this as the starting arrangement and rearrange in the admin panel
where the bank's strategy says otherwise. The tiers are stored in
data/branch_log_config.json and can be changed at any time.

    python scripts\\seed_impact_tiers.py                # show the analysis
    python scripts\\seed_impact_tiers.py --days 60
    python scripts\\seed_impact_tiers.py --apply        # write the assignment
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv
    days = 30
    for i, a in enumerate(sys.argv):
        if a == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])

    try:
        from utils.branch_log import BranchLogManager, metric_keys, activity_weights, fields_schema
        from utils.branch_log_analytics import impact_tiers, set_impact_tier
    except Exception as exc:
        print("ABORT: could not import the daily-log modules: %s" % exc)
        return 1

    weights = activity_weights()
    labels = {f["key"]: f.get("label", f["key"]) for f in fields_schema()}
    mkeys = [k for k in metric_keys()]

    logs = BranchLogManager().get_history(days=days)
    if not logs:
        print("ABORT: no logs in the last %d days — nothing to measure." % days)
        print("       Run scripts\\\\seed_daily_logs.py first, or widen --days.")
        return 1

    # Contribution to the index, not raw counts: 400 transactions at 0.2 is
    # worth less than 3 accounts at 2.0, and the index is what people are
    # measured on.
    contrib, volume = {}, {}
    for l in logs:
        for k in mkeys:
            v = float(l.get(k) or 0)
            if v:
                contrib[k] = contrib.get(k, 0.0) + v * float(weights.get(k, 0) or 0)
                volume[k] = volume.get(k, 0.0) + v

    total = sum(contrib.values())
    if total <= 0:
        print("ABORT: total index over the window is zero — nothing to rank.")
        return 1

    ranked = sorted(contrib.items(), key=lambda kv: -kv[1])
    print("=" * 78)
    print("IMPACT ANALYSIS — %d logs over %d days, total index %.0f" % (len(logs), days, total))
    print("=" * 78)
    print("%-30s %10s %8s %8s  %s" % ("ACTIVITY", "INDEX", "SHARE", "CUMUL", "TIER"))
    print("-" * 78)

    plan, cumulative = {}, 0.0
    for k, c in ranked:
        share = c / total * 100
        cumulative += share
        tier = "high" if cumulative <= 80 else ("medium" if cumulative <= 95 else "low")
        # The activity that CROSSES 80 belongs to the high set — excluding it
        # would leave the high tier short of the 80% it is defined by.
        if tier != "high" and cumulative - share < 80:
            tier = "high"
        plan[k] = tier
        print("%-30s %10.0f %7.1f%% %7.1f%%  %s"
              % (labels.get(k, k)[:30], c, share, cumulative, tier.upper()))

    for k in mkeys:
        if k not in plan:
            plan[k] = "low"          # never logged in the window
            print("%-30s %10s %8s %8s  %s" % (labels.get(k, k)[:30], "0", "—", "—", "LOW"))

    counts = {t: sum(1 for v in plan.values() if v == t) for t in ("high", "medium", "low")}
    high_share = sum(contrib.get(k, 0) for k, v in plan.items() if v == "high") / total * 100
    print("-" * 78)
    print("HIGH: %d activities carrying %.1f%% of the index" % (counts["high"], high_share))
    print("MEDIUM: %d    LOW: %d" % (counts["medium"], counts["low"]))
    print("")
    print("Pareto check: %d of %d activities (%.0f%%) produce %.0f%% of the index."
          % (counts["high"], len(plan), counts["high"] / len(plan) * 100, high_share))

    current = impact_tiers()
    if current:
        changed = [k for k, v in plan.items() if current.get(k) and current[k] != v]
        print("\nalready assigned: %d   would change: %d" % (len(current), len(changed)))
        for k in changed[:10]:
            print("   %-30s %s -> %s" % (labels.get(k, k)[:30], current[k], plan[k]))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to save the assignment.")
        return 0

    n = 0
    for k, tier in plan.items():
        try:
            set_impact_tier(k, tier)
            n += 1
        except Exception as exc:
            print("   failed on %s: %s" % (k, exc))
    print("\nassigned %d activities. Stored in data/branch_log_config.json under" % n)
    print("impact_tiers — the admin panel can rearrange any of them.")
    print("Restart uvicorn so the analytics pick it up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
