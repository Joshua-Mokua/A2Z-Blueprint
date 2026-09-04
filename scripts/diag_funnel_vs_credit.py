#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Which deals are at credit but not showing it in the funnel? READ ONLY.

FROM THE BANK (2026-09-04): "I have several cases submitted to the department
credit analyst but the funnel is not displaying as such."

    python scripts\diag_funnel_vs_credit.py

A deal that reaches credit is auto-advanced one stage in its product's flow.
That advance is best-effort and used to fail silently in three ways:

    the deal's stage is not in its product's flow   the commonest - the next
                                                    stage cannot be computed
                                                    from a position that is
                                                    not on the map
    it is already at the last stage
    the next stage is a closing stage               deliberately skipped

This lists every deal that HAS a credit case but whose funnel position has not
moved past origination, and says which of those applies to each. That is the
list to correct - FN2 stops it happening quietly from now on, but the deals
already in this state stay where they are until somebody moves them.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    from utils.core import PipelineManager
    import utils.api as A

    pm = PipelineManager()
    deals = pm.deals or []
    linked = [d for d in deals if str(d.get("lms_application_id") or "").strip()]

    print("=" * 88)
    print("DEALS AT CREDIT WHOSE FUNNEL HAS NOT MOVED")
    print("=" * 88)
    print("  deals            %d" % len(deals))
    print("  with a credit case %d\n" % len(linked))
    if not linked:
        print("  No deal has been submitted to credit yet.")
        return 0

    stuck, moved = [], 0
    for d in linked:
        prod = str(d.get("product_type") or d.get("product") or "")
        stage = str(d.get("stage") or "")
        try:
            flow = [str(x) for x in (A._stage_flow_for(prod) or [])]
        except Exception:
            flow = []
        if not flow:
            stuck.append((d, "the product %r has no flow at all" % prod))
            continue
        if stage not in flow:
            stuck.append((d, "stage %r is not in the %r flow" % (stage, prod)))
            continue
        idx = flow.index(stage)
        # Where in the flow is it? A deal at credit should be past the early
        # origination stages.
        if idx <= 1:
            nxt = flow[idx + 1] if idx + 1 < len(flow) else ""
            if not nxt:
                stuck.append((d, "already at the last stage of its flow"))
            elif nxt.lower().startswith("closed"):
                stuck.append((d, "the next stage %r is a closing stage" % nxt))
            else:
                stuck.append((d, "at %r (position %d of %d) - it should have "
                              "advanced to %r" % (stage, idx + 1, len(flow), nxt)))
        else:
            moved += 1

    print("  funnel moved     %d" % moved)
    print("  NOT MOVED        %d\n" % len(stuck))
    if stuck:
        print("  %-10s %-26s %-22s %s"
              % ("DEAL", "CLIENT", "STAGE", "WHY"))
        for d, why in stuck[:25]:
            print("  %-10s %-26s %-22s %s"
                  % (str(d.get("id"))[:10], str(d.get("client_name"))[:26],
                     str(d.get("stage"))[:22], why[:44]))
        if len(stuck) > 25:
            print("     ... and %d more" % (len(stuck) - 25))

    print("\n" + "=" * 88)
    if not stuck:
        print("EVERY DEAL AT CREDIT HAS MOVED IN THE FUNNEL")
        print("=" * 88)
        return 0
    print("WHAT TO DO")
    print("=" * 88)
    print("  FN2 stops this happening quietly from now on - the audit records")
    print("  which of the reasons applied. These deals stay where they are")
    print("  until somebody moves them.")
    print("\n  Where the reason is 'stage is not in the flow', the flow is the")
    print("  thing to fix - the deal is standing somewhere its product does")
    print("  not define, which also stops it being closed:")
    print("     python scripts\\close_the_flows.py --apply")
    print("\n  Where a deal simply did not advance, moving it by hand from the")
    print("  deal screen is safer than a script guessing which stage it")
    print("  should have reached.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
