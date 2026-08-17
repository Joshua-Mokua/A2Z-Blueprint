#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Write the funnel model into ADMIN CONFIG so nothing lives in code.

RULING (2026-08-09): "let me also be categorical that the stages should not be
hardcoded". Defaults exist in utils/pipeline_funnel so a fresh install is
coherent, but the bank must be able to change every number from the admin
screen. This writes them into data/pipeline_settings.json, after which the
defaults are never consulted again for those keys.

WHAT IT WRITES
    stage_probabilities   {flow: {stage: win probability}}
        PER STAGE WITHIN EACH FLOW (ruling): "Negotiation" on a liability
        product is not the same likelihood as "Negotiation" on a corporate
        facility, so one global map would misstate assured value on every
        product but one.

    credit_bands          the SIDE LAYER: Documentation, Branch Credit,
        Department, Credit Analysis, Credit Administration, TROPS - where a deal
        probably sits inside the bank, inferred from its probability bracket.
        Not a sales stage, and it never filters the journey.

    Any flow present in stage_flows but missing a probability table gets an even
    progression, so a product added later is never silently worth zero.

SAFE: dry-run by default; --apply writes through the existing settings saver,
which refuses to write a config missing its core keys and writes atomically.

    python scripts\\seed_funnel_config.py            # show what would change
    python scripts\\seed_funnel_config.py --apply
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv

    try:
        from utils.core import get_pipeline_settings, save_pipeline_settings
        from utils.pipeline_funnel import (
            DEFAULT_STAGE_PROBABILITIES, DEFAULT_CREDIT_BANDS, CLOSED,
        )
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    ps = get_pipeline_settings() or {}
    flows = ps.get("stage_flows") or {}
    if not flows:
        print("ABORT: no stage_flows configured — nothing to attach probabilities to.")
        return 1

    existing_p = ps.get("stage_probabilities") or {}
    existing_b = ps.get("credit_bands") or []

    plan = {k: dict(v) for k, v in DEFAULT_STAGE_PROBABILITIES.items() if k in flows}

    # A flow with no default gets an even progression rather than nothing: a
    # product added later must never be silently worth zero.
    for flow, seq in flows.items():
        if flow in plan:
            continue
        active = [s for s in (seq or []) if s not in CLOSED]
        table = {}
        for i, s in enumerate(active):
            table[s] = round((i + 1) / (len(active) + 1), 2)
        table["Closed Won"] = 1.0
        table["Closed Lost"] = 0.0
        plan[flow] = table
        print("  note: %r had no default; assigned an even progression" % flow)

    print("=" * 74)
    print("STAGE PROBABILITIES — per stage within each flow")
    print("=" * 74)
    for flow in sorted(plan):
        cur = existing_p.get(flow) or {}
        print("\n  %s" % flow)
        for s in (flows.get(flow) or []):
            new = plan[flow].get(s)
            if new is None:
                continue
            old = cur.get(s)
            mark = "" if old is None else ("  (unchanged)" if float(old) == float(new)
                                           else "  was %s" % old)
            print("     %-22s %.2f%s" % (s, new, mark))

    print("\n" + "=" * 74)
    print("CREDIT BANDS — the side layer, inferred from probability")
    print("=" * 74)
    for b in DEFAULT_CREDIT_BANDS:
        print("   %-22s %.0f%% – %.0f%%"
              % (b["label"], b["min"] * 100, min(b["max"], 1.0) * 100))
    if existing_b:
        print("\n   (%d bands already configured — they will be REPLACED)" % len(existing_b))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        print("Everything above becomes editable in admin once written.")
        return 0

    ps["stage_probabilities"] = plan
    ps["credit_bands"] = [dict(b) for b in DEFAULT_CREDIT_BANDS]
    try:
        save_pipeline_settings(ps)
    except Exception as exc:
        print("ABORT: could not save settings: %s" % exc)
        return 1

    check = get_pipeline_settings() or {}
    if not check.get("stage_probabilities") or not check.get("credit_bands"):
        print("ABORT: settings saved but read back without the new keys.")
        return 1
    print("\nwrote stage_probabilities for %d flows and %d credit bands."
          % (len(plan), len(DEFAULT_CREDIT_BANDS)))
    print("Restart uvicorn. These are now config, not code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
