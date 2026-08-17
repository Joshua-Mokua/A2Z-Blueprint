#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Can each unit actually REACH the daily target? Propose weights so it can.

THE PROBLEM THIS SOLVES. AS1 gave Head Office units their own activity sets.
Those sets are much smaller than the branch base - Credit Risk has TWO earning
activities against the branch's fifteen - so at bank-wide weights those units
cannot reach the shared target of 25 no matter how hard anyone works.

    branch base                     15 activities, weights sum 26.0
    Director, Credit Risk           2 activities, weights sum  3.0
    Director, Treasury & FICC       3 activities, weights sum  5.0
    Director Operations & Tech      5 activities, weights sum  7.0   (59 people)

That is a CONFIGURATION deficit, not a performance one, and it would show on a
manager's screen as people failing. Ruling 2026-08-10: the target stays the
same, the weights vary - so the weights have to be raised for units with fewer
ways to earn.

HOW THE PROPOSAL IS DERIVED. For each unit we ask: on a normal day, what volume
of each activity is realistic? Multiply by weight, and the total should land
near the target. Rather than invent volumes, this scales the unit's existing
weights by the ratio that makes a NORMAL DAY reach the target, using the branch
base as the reference for what "normal" means:

    factor = branch_weight_sum / unit_weight_sum

applied to every activity in that unit's set, rounded to one decimal.

WHAT THIS IS NOT. It is not a claim about the right relative value of an
auditor's day against a teller's. It makes each unit REACHABLE, so nobody is
under target for a reason that is not theirs; the bank should then adjust the
relative values deliberately. A proposal that gets people onto the scale beats
leaving them off it.

NOTHING is written without --apply, and the numbers print first.

    python scripts\\propose_unit_weights.py
    python scripts\\propose_unit_weights.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv
    try:
        from utils.branch_log import (activity_sets, fields_for_unit,
                                      weights_for_unit, activity_weights,
                                      daily_index_target, fields_schema,
                                      load_log_config)
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    sets = activity_sets()
    if not sets:
        print("No unit activity sets configured yet.")
        print("Run scripts\\seed_unit_activities.py --apply first - there is")
        print("nothing to weight until a unit has its own activities.")
        return 1

    target = daily_index_target()
    g = activity_weights()
    base_keys = [f["key"] for f in fields_schema()
                 if float(g.get(f["key"], 0) or 0) > 0]
    base_sum = sum(float(g.get(k, 0) or 0) for k in base_keys)

    print("=" * 74)
    print("REACHABILITY AGAINST A TARGET OF %s" % target)
    print("=" * 74)
    print("branch base: %d earning activities, weights sum %.1f"
          % (len(base_keys), base_sum))
    print("")

    proposal = {}
    skipped = []
    for u in sorted(sets):
        w = weights_for_unit(u)
        keys = [f["key"] for f in fields_for_unit(u)
                if float(w.get(f["key"], 0) or 0) > 0]
        usum = sum(float(w.get(k, 0) or 0) for k in keys)
        if usum <= 0:
            print("%-46s NO EARNING ACTIVITIES - skipped" % u[:46])
            continue
        # SCALING BREAKS DOWN ON A THIN SET. With two earning activities, the
        # factor is ~8.7 and a single referral becomes worth 26 - a whole day's
        # target from one action. That is not a weighting, it is a distortion,
        # and it would be gamed within a week.
        #
        # A unit this thin does not need better weights; it needs its real
        # activities, which do not exist yet. Until then it belongs on the
        # branch base, where at least the arithmetic is honest.
        MIN_ACTIVITIES = 4
        MAX_FACTOR = 3.0
        factor = base_sum / usum
        if len(keys) < MIN_ACTIVITIES or factor > MAX_FACTOR:
            print("%s" % u[:70])
            print("   %d activities, sum %.1f  ->  would need x%.2f"
                  % (len(keys), usum, factor))
            print("   *** NOT PROPOSED. Too few ways to earn: scaling would make")
            print("       one action worth %.0f, most of a day's target."
                  % (max(float(w.get(k, 0) or 0) for k in keys) * factor))
            print("       Take this unit OFF the activity set until its real")
            print("       activities exist, so its people keep the branch base:")
            print("         remove %r from activity_sets in branch_log_config.json" % u)
            print("")
            skipped.append(u)
            continue
        print("%s" % u[:70])
        print("   %d activities, sum %.1f  ->  scale x%.2f" % (len(keys), usum, factor))
        got = {}
        for k in keys:
            old = float(w.get(k, 0) or 0)
            new = round(old * factor, 1)
            got[k] = new
            if abs(new - old) >= 0.05:
                print("      %-24s %5.1f  ->  %5.1f" % (k, old, new))
        # Penalties keep their sign and are NOT scaled up: multiplying a
        # deterrent makes one bad day unrecoverable.
        for k in keys:
            if float(g.get(k, 0) or 0) < 0:
                got[k] = float(g.get(k))
                print("      %-24s kept at %.1f (penalty, not scaled)"
                      % (k, got[k]))
        proposal[u] = got
        print("")

    print("=" * 74)
    print("%d units proposed · %d held back" % (len(proposal), len(skipped)))
    print("=" * 74)
    if skipped:
        print("HELD BACK - too thin to weight honestly:")
        for u in skipped:
            print("   %s" % u)
        print("These should return to the branch base until their activities")
        print("exist. Leaving them configured guarantees their people miss")
        print("target every day for a reason that is not theirs.")
        print("")
    print("This makes each unit REACHABLE. It does not claim an auditor's day is")
    print("worth the same as a teller's - the bank should tune the relative")
    print("values from here. But nobody should sit under target because their")
    print("unit was given fewer ways to earn.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    cfg = load_log_config() or {}
    existing = cfg.get("unit_activity_weights") or {}
    for u, m in proposal.items():
        cur = dict(existing.get(u) or {})
        cur.update(m)
        existing[u] = cur
    cfg["unit_activity_weights"] = existing

    path = os.path.join("data", "branch_log_config.json")
    backup = path + ".pre_unitweights"
    if os.path.isfile(path):
        shutil.copy2(path, backup)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, path)
    print("\nwrote weights for %d units to %s (backup: %s)"
          % (len(proposal), path, os.path.basename(backup)))
    print("Restart uvicorn, then check a unit's people against target.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
