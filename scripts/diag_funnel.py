#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why does the Sales Pro funnel show one stage when 28 deals exist? READ ONLY.

The funnel applies three filters, and each one can drop a deal silently:

    1. VALIDATED and ACTIVE only   - a pending or closed deal never appears
    2. stage must be in ALL_ACTIVE_STAGES - a deal parked at a stage the
       canonical list has never heard of VANISHES WITHOUT TRACE. Per-product
       stage_flows (P4a) can legitimately place a deal there.
    3. empty stages hidden          - the defined journey does not show the
       stages that hold nothing yet

This walks all three against the live deals and prints exactly where they go.

    python scripts\\diag_funnel.py
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def rule(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


def main():
    try:
        from utils.core import PipelineManager, ALL_ACTIVE_STAGES, ALL_STAGE_NAMES
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    pm = PipelineManager()
    deals = list(getattr(pm, "deals", []) or [])

    # Postgres is the deal store; the JSON manager may hold only a subset.
    pg = []
    try:
        from utils.db import db
        if db.is_postgres_ready():
            pg = db.fetch_all("SELECT id, stage, staff_code, "
                              "metadata->>'manager_validated' AS mv, "
                              "metadata->>'deal_value' AS val FROM pipeline_deals")
    except Exception as exc:
        print("(Postgres probe failed: %s)" % exc)

    rule("A. WHERE THE DEALS ARE")
    print("JSON store   : %d deals" % len(deals))
    print("Postgres     : %d deals" % len(pg))
    src = pg if len(pg) >= len(deals) else deals
    label = "Postgres" if src is pg else "JSON"
    print("using the larger store for this analysis: %s" % label)

    def stage_of(d):
        return str(d.get("stage") or "").strip()

    def validated(d):
        v = d.get("mv") if src is pg else d.get("manager_validated")
        return str(v).lower() in ("true", "1", "t", "yes")

    import collections
    by_stage = collections.Counter(stage_of(d) or "(blank)" for d in src)

    rule("B. EVERY STAGE PRESENT IN THE DATA")
    known = set(ALL_ACTIVE_STAGES)
    allnames = set(ALL_STAGE_NAMES)
    for s, n in by_stage.most_common():
        if s in known:
            flag = "counted"
        elif s in allnames:
            flag = "CLOSED - excluded by design"
        else:
            flag = "*** NOT IN ALL_ACTIVE_STAGES - DROPPED SILENTLY"
        print("   %-28s %4d   %s" % (s[:28], n, flag))

    rule("C. THE THREE FILTERS, IN ORDER")
    total = len(src)
    v = [d for d in src if validated(d)]
    va = [d for d in v if stage_of(d) in allnames and stage_of(d) in known]
    matched = [d for d in va if stage_of(d) in known]
    print("   all deals                         %4d" % total)
    print("   after 'validated only'            %4d   (-%d)" % (len(v), total - len(v)))
    print("   after 'active stage only'         %4d   (-%d)" % (len(va), len(v) - len(va)))
    print("   after 'stage in canonical list'   %4d   (-%d)" % (len(matched), len(va) - len(matched)))
    stages_shown = {stage_of(d) for d in matched}
    print("   stages the funnel will render     %4d   %s"
          % (len(stages_shown), sorted(stages_shown)))

    rule("D. THE CANONICAL LIST THE FUNNEL CHECKS AGAINST")
    print("ALL_ACTIVE_STAGES (%d):" % len(ALL_ACTIVE_STAGES))
    for s in ALL_ACTIVE_STAGES:
        print("   %s" % s)

    rule("E. PER-PRODUCT FLOWS (P4a) — do they use stages the list lacks?")
    try:
        from utils.core import get_pipeline_settings
        flows = (get_pipeline_settings() or {}).get("stage_flows") or {}
        if not flows:
            print("no stage_flows configured.")
        else:
            unknown = set()
            for name, seq in flows.items():
                miss = [s for s in (seq or []) if s not in allnames]
                print("   %-34s %d stages%s"
                      % (name[:34], len(seq or []),
                         ("   MISSING: %s" % miss) if miss else ""))
                unknown.update(miss)
            if unknown:
                print("\n*** these configured stages are unknown to the canonical list:")
                for s in sorted(unknown):
                    print("      %s" % s)
                print("    a deal parked at one of them cannot appear in the funnel.")
    except Exception as exc:
        print("could not read stage flows: %s" % exc)

    rule("F. READ THIS")
    print("If C loses deals at 'validated only'   -> they are pending, not missing.")
    print("If C loses deals at 'active stage'     -> they are closed; by design.")
    print("If C loses deals at 'canonical list'   -> THAT is the bug: a real deal")
    print("   at a real stage is invisible because the list has not caught up with")
    print("   the configured product flows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
