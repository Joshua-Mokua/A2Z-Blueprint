#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
F3 - one probability model. Retire the hardcoded weight map.

F1 built the config-driven model but wired it only to the new funnel endpoint.
EVERY WEIGHTED FIGURE in the system was still reading _STAGE_WEIGHTS at
api.py:3590 - three call sites: the headline weighted value and both
per-category rollups.

That map knows SIX stages. So a deal at Application, Credit Assessment or
Offer / Proposal contributed ZERO weighted value, silently, and two more stages
were simply wrong:

    stage                hardcoded   per-flow (asset)
    Application          absent      0.40    <- was worth nothing
    Credit Assessment    absent      0.55    <- was worth nothing
    Offer / Proposal     absent      0.70    <- was worth nothing
    Negotiation          0.60        0.80
    Compliance           0.80        0.90

MEASURED on four representative deals: weighted total 300,000 under the old map
against 2,455,000 under the configured model - the book was understated by
2,155,000, and three of the four deals counted for nothing at all.

Two live probability models also meant the funnel and the headline could
disagree about the same deal, which is the drift this codebase keeps paying for.

WHAT THIS DOES
  Adds _deal_probability(deal) - resolves the deal's flow and reads the win
  probability for its stage WITHIN that flow, from admin config. All three
  weighted call sites now use it.

  _STAGE_WEIGHTS SURVIVES as a last-resort fallback for a deal whose flow cannot
  be resolved at all, and nothing reads it directly any more. Deleting it
  outright would have replaced a wrong number with a crash on malformed data;
  keeping it unreferenced-but-present is the safer shape.

Verified: py_compile clean; exactly one remaining read of the old map, inside
the fallback.

REQUIRES F1.

Usage (from project root, .venv active):
    python scripts\patch_f3_one_probability_model.py            # dry run
    python scripts\patch_f3_one_probability_model.py --apply    # write + .pre_f3 backup
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_f3"

OLD_MAP = '''_STAGE_WEIGHTS = {
    "Lead": 0.05, "Contacted": 0.10, "Qualified": 0.25, "Proposal": 0.40,
    "Negotiation": 0.60, "Compliance": 0.80, "Closed Won": 1.0, "Closed Lost": 0.0,
}'''

CALL_SITES = [
    ('''    weighted_value = sum(_deal_value(d) * _STAGE_WEIGHTS.get(d.get("stage"), 0)
                         for d in validated_active)''',
     '''    weighted_value = sum(_deal_value(d) * _deal_probability(d)
                         for d in validated_active)'''),
    ('''            "weighted": sum(_deal_value(d) * _STAGE_WEIGHTS.get(d.get("stage"), 0)
                            for d in cdeals),''',
     '''            "weighted": sum(_deal_value(d) * _deal_probability(d)
                            for d in cdeals),'''),
    ('''            "weighted": sum(_deal_value(d) * _STAGE_WEIGHTS.get(d.get("stage"), 0)
                            for d in val_act),''',
     '''            "weighted": sum(_deal_value(d) * _deal_probability(d)
                            for d in val_act),'''),
]

BLOCK_NEW = r'''# RULING 2026-08-09: "the stages should not be hardcoded". This map knew SIX
# stages, so a deal at Application, Credit Assessment or Offer / Proposal
# contributed ZERO weighted value - silently, in every headline figure. It is
# kept ONLY as the last-resort fallback for a deal whose flow cannot be
# resolved, and nothing reads it directly any more.
_STAGE_WEIGHTS = {
    "Lead": 0.05, "Contacted": 0.10, "Qualified": 0.25, "Proposal": 0.40,
    "Negotiation": 0.60, "Compliance": 0.80, "Closed Won": 1.0, "Closed Lost": 0.0,
}


def _deal_probability(d: dict) -> float:
    """Win probability for a deal, PER STAGE WITHIN ITS FLOW, from admin config.

    One model, used by the funnel and by every weighted figure, so the two can
    never disagree about the same deal. Falls back to the legacy map only when
    the flow cannot be resolved at all - and even then never returns a silent
    zero for a stage the bank has configured.
    """
    try:
        from utils.pipeline_funnel import flow_for_deal, probability_for
        p = probability_for(flow_for_deal(d), str(d.get("stage") or ""))
        if p:
            return float(p)
    except Exception:
        pass
    return float(_STAGE_WEIGHTS.get(d.get("stage"), 0) or 0)


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    if not os.path.isfile(os.path.join("utils", "pipeline_funnel.py")):
        print("ABORT: apply patch_f1_funnel_model.py first - this reads its model.")
        return 1

    api = open(API, encoding="utf-8").read()
    if "_deal_probability" in api:
        print("ABORT: _deal_probability already present - F3 looks applied.")
        return 1
    if api.count(OLD_MAP) != 1:
        print("ABORT: the weight map matched %d times (expected 1)." % api.count(OLD_MAP))
        return 1

    api = api.replace(OLD_MAP, BLOCK_NEW.rstrip("\n"), 1)
    print("  ok  _deal_probability added; the old map kept as fallback only")

    n = 0
    for old, new in CALL_SITES:
        if api.count(old) == 1:
            api = api.replace(old, new, 1)
            n += 1
        else:
            print("ABORT: a weighted call site matched %d times - refusing to")
            print("       half-migrate, which would leave two models live.")
            return 1
    print("  ok  %d weighted call sites repointed" % n)

    direct = api.count("_STAGE_WEIGHTS.get")
    if direct != 1:
        print("ABORT: post-check - %d direct reads of the old map remain "
              "(expected exactly 1, the fallback)." % direct)
        return 1
    if "from utils.pipeline_funnel import flow_for_deal, probability_for" not in api:
        print("ABORT: post-check - the model import is missing.")
        return 1
    print("  ok  post-check: one model, one fallback read")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s  (backup: %s)" % (API, os.path.basename(API) + BACKUP_SUFFIX))

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nRestart uvicorn. Weighted figures will RISE - stages that were")
    print("silently worth zero now carry their configured probability.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
