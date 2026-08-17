#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Walk every product from initiation to close. Five hundred-odd checks.

WHY THIS EXISTS. audit_200 ran 376 checks and passed, and two hours later the
pilot could not submit a deal. Both faults were the same shape:

    a rule that is CORRECT at the stage it was tested at,
    and WRONG at the stage before it

    * a committee three stages ahead blocked submission from Documentation
    * the Transaction Memo was demanded before the committee that produces it

Every test I had written put a case AT a stage and checked the gate there. Not
one walked a case from creation through to the end. Testing states is not
testing journeys, and the gap between them is exactly where a case gets stuck.

So this walks. For every product in the catalogue it creates a deal at the
first stage and steps it forward, asking at each step: can this case leave this
stage, and if not, is the reason a real one?

    python scripts\\walk_all_flows.py
    python scripts\\walk_all_flows.py --verbose        # every check
    python scripts\\walk_all_flows.py --product "Mortgage"

Read-only: deals are built in memory and never saved. Exit 0 when every product
can be walked end to end.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

OK, WARN, FAIL = [], [], []
VERBOSE = "--verbose" in sys.argv
ONLY = None
if "--product" in sys.argv:
    i = sys.argv.index("--product")
    if i + 1 < len(sys.argv):
        ONLY = sys.argv[i + 1]


def ok(what):
    OK.append(what)
    if VERBOSE:
        print("      ok   %s" % what[:68])


def bad(what, why=""):
    FAIL.append((what, why))
    print("      FAIL %s" % what[:68])
    if why:
        print("           %s" % why[:88])


def warn(what, why=""):
    WARN.append((what, why))
    if VERBOSE:
        print("      warn %s" % what[:68])


def main():
    import utils.api as A
    from utils.core import PipelineManager

    pcfg = A._load_json("pipeline_settings.json") or {}
    flows = pcfg.get("product_flows") or {}
    products = sorted(flows) if not ONLY else [p for p in flows if p == ONLY]
    if not products:
        print("ABORT: no products to walk%s." % (" matching %r" % ONLY if ONLY else ""))
        return 1

    # A stand-in deal store: the walk must never touch the real one.
    real = PipelineManager()
    holder = {"deal": None}

    class Walker:
        deals = []
        def get_deal(self, i):
            return holder["deal"]
        def update_deal(self, i, u, by=""):
            holder["deal"].update(u)
            return holder["deal"]
        def _save_deals(self):
            pass

    # THE SEAM THE ENDPOINT ACTUALLY USES. It calls _get_or_hydrate_deal, not
    # _deal_for_docs - mocking the wrong one gave 404 on every product and
    # would have reported a healthy system as broken.
    A._get_or_hydrate_deal = lambda pm, did: holder["deal"]
    A._deal_for_docs = lambda did, u: (Walker(), holder["deal"])
    A.get_visible_staff_codes = lambda u: {"WALK1"}
    A._db_available = lambda: False

    print("=" * 78)
    print("WALKING %d PRODUCT FLOW(S) FROM INITIATION" % len(products))
    print("=" * 78)

    user = {"username": "walker", "staff_code": "WALK1",
            "full_name": "Walk Tester", "role": "Relationship Manager"}

    stuck_products = []

    for prod in products:
        stages = [str(x) for x in (A._stage_flow_for(prod) or [])]
        if not stages:
            bad("%s has no stage flow" % prod[:40],
                "a deal on this product cannot move at all")
            continue

        print("\n  %s  (%d stages)" % (prod[:46], len(stages)))

        # The deal, as a branch would create it: Consumer, at a real branch,
        # every document attached, manager validated.
        deal = {
            "id": "WALK", "client_name": "Walk Test", "product": prod,
            "product_type": prod, "deal_value": 5000000,
            "staff_code": "WALK1", "staff_name": "Walk Tester",
            "branch": "Fortis", "unit": "Fortis", "client_type": "Consumer",
            "stage": stages[0], "manager_validated": True,
            "committee_records": {}, "cr": {},
            "documents_provided": [], "document_files": {},
        }
        holder["deal"] = deal

        journey = A._effective_committee_journey(deal) or []
        if journey:
            ok("%s routes to %s" % (prod[:24], ", ".join(journey)))
        else:
            warn("%s routes to no committee" % prod[:30],
                 "a Consumer case at a branch should reach one")

        stuck_at = None
        for idx, stage in enumerate(stages):
            deal["stage"] = stage
            last = idx >= len(stages) - 1
            closing = stage.lower().startswith("closed")

            # 1. The checklist must answer at all.
            try:
                c = A.pipeline_credit_checklist("WALK", user=user)
            except Exception as exc:
                bad("%s @ %s: the checklist raised" % (prod[:20], stage[:22]),
                    str(exc)[:80])
                stuck_at = stage
                break
            ok("%s @ %s: checklist answers" % (prod[:20], stage[:20]))

            if closing or last:
                continue

            # 2. Nothing may demand a committee the case has not reached.
            pending = c.get("committee_pending") or []
            ahead = []
            for code in pending:
                try:
                    cm = A._committee_by_code(code) or {}
                except Exception:
                    continue
                cstage = str(cm.get("stage", "") or "")
                if cstage and cstage in stages and stages.index(cstage) > idx:
                    ahead.append("%s@%s" % (code, cstage))
            if ahead:
                bad("%s @ %s: blocked by a committee AHEAD" % (prod[:18], stage[:20]),
                    "%s - it cannot have decided yet, so the case can never "
                    "move" % ", ".join(ahead))
                stuck_at = stuck_at or stage
            else:
                ok("%s @ %s: no committee ahead blocks it" % (prod[:18], stage[:18]))

            # 3. Nothing may demand a document that this stage cannot produce.
            #    The memo is written after the branch committee: if it is
            #    required BEFORE that committee, the case is trapped.
            if c.get("cr_required") and not c.get("cr_ok"):
                bcc = next((s for s in stages if "branch credit committee" in s.lower()), "")
                if bcc and stages.index(bcc) > idx:
                    bad("%s @ %s: the memo is required before %s"
                        % (prod[:16], stage[:18], bcc[:24]),
                        "the memo is written after that committee, so it "
                        "cannot exist yet")
                    stuck_at = stuck_at or stage
                else:
                    ok("%s @ %s: the memo is required at a sensible point"
                       % (prod[:16], stage[:16]))

            # 4. A case with everything a branch can supply must be able to
            #    LEAVE this stage - either can_submit, or a reason a person
            #    can act on.
            if not c.get("can_submit"):
                reasons = []
                if c.get("manager_validated") is False:
                    reasons.append("not validated")
                if c.get("stage_ok") is False:
                    reasons.append("wrong stage (%s)" % c.get("stage_required"))
                if pending and not ahead:
                    reasons.append("committee %s owes a decision" % ", ".join(pending))
                if c.get("committee_rejected"):
                    reasons.append("rejected by %s" % ", ".join(c["committee_rejected"]))
                if c.get("cr_required") and not c.get("cr_ok"):
                    reasons.append("memo incomplete")
                if reasons:
                    ok("%s @ %s: held for a real reason (%s)"
                       % (prod[:16], stage[:16], reasons[0][:26]))
                else:
                    bad("%s @ %s: cannot submit and NO reason is given"
                        % (prod[:16], stage[:20]),
                        "the button is disabled and the screen cannot say why "
                        "- this is what the pilot hit twice today")
                    stuck_at = stuck_at or stage
            else:
                ok("%s @ %s: can submit" % (prod[:20], stage[:20]))

            # 5. There must be a next stage to go to.
            nxt = stages[idx + 1] if idx + 1 < len(stages) else ""
            if nxt:
                ok("%s @ %s: next is %s" % (prod[:16], stage[:16], nxt[:20]))
            else:
                bad("%s @ %s: nothing follows" % (prod[:20], stage[:22]),
                    "the case would stop here")

        if stuck_at:
            stuck_products.append((prod, stuck_at))

    # ── The branch journey, walked with its committee actually deciding ─────
    print("\n" + "=" * 78)
    print("THE BRANCH COMMITTEE, DECIDED IN SEQUENCE")
    print("=" * 78)
    for prod in products[:6]:
        stages = [str(x) for x in (A._stage_flow_for(prod) or [])]
        bcc_stage = next((s for s in stages if "branch credit committee" in s.lower()), "")
        if not bcc_stage:
            continue
        deal = {"id": "WALK2", "product": prod, "product_type": prod,
                "staff_code": "WALK1", "branch": "Fortis", "unit": "Fortis",
                "client_type": "Consumer", "stage": bcc_stage,
                "manager_validated": True, "cr": {"completed": True},
                "committee_records": {}}
        holder["deal"] = deal
        j = A._effective_committee_journey(deal) or []
        if not j:
            continue
        c = A.pipeline_credit_checklist("WALK2", user=user)
        before = list(c.get("committee_pending") or [])
        # Record the branch committee's recommendation.
        deal["committee_records"] = {j[0]: {"outcome": "APPROVED",
                                            "recorded_by": "test",
                                            "recorded_at": "2026-08-14"}}
        c2 = A.pipeline_credit_checklist("WALK2", user=user)
        after = list(c2.get("committee_pending") or [])
        if j[0] in before and j[0] not in after:
            ok("%s: a recommendation clears its own gate" % prod[:34])
        else:
            bad("%s: a recommendation does NOT clear the gate" % prod[:30],
                "pending was %s, now %s" % (before, after))
        # SUBMISSION HAPPENS FROM THE DOCUMENT STAGE, not from the committee's.
        # A case sitting at the committee has stage_ok False and that is
        # correct - it ADVANCES from there, it does not submit again. My first
        # version called that a failure and would have sent us chasing a
        # working system.
        if c2.get("can_submit"):
            ok("%s: the case can move on once recommended" % prod[:34])
        elif c2.get("stage_ok") is False:
            ok("%s: past the submission point, advances instead" % prod[:34])
        else:
            bad("%s: still held after a recommendation" % prod[:32],
                "memo=%s pending=%s - nothing explains it"
                % (c2.get("cr_ok"), after))

    return report(stuck_products)


def report(stuck):
    total = len(OK) + len(WARN) + len(FAIL)
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    print("  checks run   %d" % total)
    print("  passed       %d" % len(OK))
    print("  warned       %d" % len(WARN))
    print("  FAILED       %d" % len(FAIL))
    if stuck:
        print("\n  PRODUCTS THAT GET STUCK (%d):" % len(stuck))
        for prod, stage in stuck[:14]:
            print("     %-34s at %s" % (prod[:34], stage))
    if not FAIL:
        print("\nEvery product can be walked from initiation to close.")
        return 0
    print("\nFIX BEFORE ANYBODY USES THESE:\n")
    seen = set()
    for what, why in FAIL:
        key = why[:50]
        if key in seen:
            continue
        seen.add(key)
        print("   * %s" % what)
        if why:
            print("     %s" % why)
    if len(FAIL) > len(seen):
        print("\n   (%d more with the same causes)" % (len(FAIL) - len(seen)))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-8:]:
            print("   %s" % ln[:110])
        sys.exit(1)
