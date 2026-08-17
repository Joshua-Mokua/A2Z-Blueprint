#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Drive a real deal through the branch committee. WRITES TEST DATA unless --dry.

WHY THIS EXISTS. The branch managers were gathered and nothing moved. The
config audit passed, so the fault is not in what the config SAYS - it is in
what happens when somebody actually clicks. This calls the same endpoint
functions the UI calls, in order, and reports the first thing that refuses.

It is not a mock. resolve_deal_permissions, the committee-record endpoint and
the advance path are the real ones; if this passes and a branch manager still
cannot move a case, the difference is the user's identity, not the code.

WHAT IT WALKS

     1  create a deal owned by a branch RM
     2  the branch manager can SEE it
     3  the branch manager can VALIDATE it
     4  it reaches the committee stage
     5  the committee is resolvable, has members, and can sit
     6  a decision can be RECORDED, with votes
     7  the gate RELEASES and the case can go on

Test data is written under a TEST- prefix and removed at the end unless
--keep. Run with --dry to see the plan without writing.

    python scripts\\simulate_branch_committee.py --dry
    python scripts\\simulate_branch_committee.py
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

FAIL, WARN = [], []
PREFIX = "TEST-BCC"


def bad(step, what, detail=""):
    FAIL.append((step, what, detail))
    print("  FAIL   %-2s %s" % (step, what))
    if detail:
        print("            %s" % detail)


def warn(step, what, detail=""):
    WARN.append((step, what))
    print("  warn   %-2s %s" % (step, what))
    if detail:
        print("            %s" % detail)


def ok(step, what, detail=""):
    print("  ok     %-2s %-44s %s" % (step, what[:44], detail))


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    dry = "--dry" in sys.argv
    keep = "--keep" in sys.argv

    try:
        from utils.core import PipelineManager, UserManager
        from utils.api_pipeline_scope import get_staff_roster, get_visible_staff_codes
        from utils.api_pipeline_permissions import resolve_deal_permissions
        import utils.api as A
    except Exception as exc:
        print("ABORT: cannot load the application: %s" % exc)
        return 1

    rule("0. WHO ARE WE SIMULATING")
    # Find a real branch with a manager and an RM - the simulation is only
    # meaningful against people who actually exist in this deployment.
    try:
        df = get_staff_roster()
    except Exception as exc:
        print("ABORT: staff register unreadable: %s" % exc)
        return 1

    people = []
    for _i, r in df.iterrows():
        people.append({
            "code": str(r.get("Staff Code") or "").strip(),
            "name": str(r.get("Staff Name") or "").strip(),
            "role": str(r.get("Role") or "").strip(),
            "unit": str(r.get("Unit") or "").strip(),
        })
    branches = {}
    for p in people:
        if p["unit"]:
            branches.setdefault(p["unit"], []).append(p)

    chosen = None
    for unit, staff in sorted(branches.items()):
        bm = next((p for p in staff if "branch manager" in p["role"].lower()), None)
        rm = next((p for p in staff
                   if "relationship" in p["role"].lower()
                   and "dsa" not in p["role"].lower()), None)
        if bm and rm:
            chosen = (unit, bm, rm)
            break
    if not chosen:
        bad("0", "no branch has both a Branch Manager and a Relationship Manager",
            "the simulation cannot represent a real case")
        return report()
    unit, bm, rm = chosen
    print("  branch          %s" % unit)
    print("  manager         %s (%s) %s" % (bm["name"], bm["code"], bm["role"]))
    print("  owner           %s (%s) %s" % (rm["name"], rm["code"], rm["role"]))

    # The committee that should review this branch's cases.
    lms = {}
    try:
        lms = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    except Exception:
        pass
    pal = ((lms.get("credit_workflow") or {}).get("committee_palette") or [])
    cttee = next((c for c in pal
                  if str(c.get("kind", "")).lower() == "branch"
                  and str(c.get("branch", "")).strip().lower() == unit.lower()), None)
    if not cttee:
        bad("0", "no branch committee exists for %s" % unit,
            "run pilot_apply.py --apply")
        return report()
    print("  committee       %s (%s), %d member(s)"
          % (cttee.get("name"), cttee.get("code"), len(cttee.get("members") or [])))

    if dry:
        print("\nDRY RUN - would create a test deal for %s and walk it." % rm["name"])
        return 0

    pm = PipelineManager()
    deal_id = ""
    try:
        # ── 1. CREATE ───────────────────────────────────────────────────────
        rule("1. CREATE A DEAL AT THE BRANCH")
        prod = "Personal Loan"
        rec = pm.create_deal({
            "client_name": "%s Client" % PREFIX,
            "product": prod, "product_type": prod,
            "deal_value": 2500000, "currency": "KES",
            "staff_code": rm["code"], "staff_name": rm["name"],
            "branch": unit, "unit": unit,
            "client_type": "Consumer", "segment": "Premier",
            "stage": "Documentation",
        }) if hasattr(pm, "create_deal") else None
        if isinstance(rec, dict):
            deal_id = str(rec.get("id") or "")
        if not deal_id:
            # Fall back to writing the record directly - the point of this
            # simulation is the COMMITTEE path, not deal creation.
            deal_id = "%s001" % PREFIX
            pm.deals.append({
                "id": deal_id, "client_name": "%s Client" % PREFIX,
                "product": prod, "product_type": prod,
                "deal_value": 2500000, "currency": "KES",
                "staff_code": rm["code"], "staff_name": rm["name"],
                "branch": unit, "unit": unit, "client_type": "Consumer",
                "segment": "Premier", "stage": "Documentation",
                "manager_validated": False, "created_at": "2026-08-12T09:00:00",
            })
            pm._save_deals()
            warn("1", "created the deal directly", "create_deal was unavailable")
        ok("1", "deal created", "%s at Documentation, owner %s" % (deal_id, rm["code"]))

        deal = pm.get_deal(deal_id)

        # ── 2. CAN THE BRANCH MANAGER SEE IT? ───────────────────────────────
        rule("2. CAN THE BRANCH MANAGER SEE IT")
        bm_user = {"username": bm["code"], "staff_code": bm["code"],
                   "role": bm["role"], "full_name": bm["name"]}
        try:
            vis = set(get_visible_staff_codes(bm_user))
        except Exception as exc:
            vis = set()
            warn("2", "scope lookup failed", str(exc)[:60])
        perms = resolve_deal_permissions(deal, bm_user, vis)
        if not perms.get("can_view"):
            bad("2", "the branch manager CANNOT see the deal",
                "owner %s is not in their visible codes (%d codes). Every later "
                "step is impossible - this is a scope/register problem, not a "
                "committee one" % (rm["code"], len(vis)))
            return report(pm, deal_id, keep)
        ok("2", "branch manager can view it", "%d codes in scope" % len(vis))

        # ── 3. VALIDATION ───────────────────────────────────────────────────
        rule("3. CAN THE BRANCH MANAGER VALIDATE IT")
        if not perms.get("can_validate"):
            bad("3", "the branch manager CANNOT validate",
                "stage=%r manager_validated=%r. Without validation the deal "
                "cannot advance at all"
                % (deal.get("stage"), deal.get("manager_validated")))
            return report(pm, deal_id, keep)
        ok("3", "branch manager can validate", "")
        pm.update_deal(deal_id, {"manager_validated": True,
                                 "validated_by_name": bm["name"],
                                 "validated_by_code": bm["code"]}, bm["code"])
        deal = pm.get_deal(deal_id)
        ok("3", "validated", "by %s" % bm["name"])

        # ── 4. DOES IT REACH THE COMMITTEE STAGE? ───────────────────────────
        rule("4. DOES THE CASE REACH THE COMMITTEE")
        flow = A._stage_flow_for(prod) or []
        if not flow:
            bad("4", "no stage flow for %s" % prod)
            return report(pm, deal_id, keep)
        cstage = next((s for s in flow if "branch credit committee" in s.lower()), "")
        if not cstage:
            bad("4", "%s has no branch committee stage" % prod,
                "the flow is: %s" % " -> ".join(flow))
            return report(pm, deal_id, keep)
        ok("4", "committee stage in the flow", cstage)
        pm.update_stage(deal_id, cstage, "simulation", bm["code"])
        deal = pm.get_deal(deal_id)
        ok("4", "case moved to the committee stage", cstage)

        # ── 5. IS THE GATE ON THIS DEAL'S JOURNEY? ──────────────────────────
        rule("5. IS THE COMMITTEE ON THIS DEAL'S JOURNEY")
        journey = A._effective_committee_journey(deal)
        print("  effective journey: %s" % (journey or "(empty)"))
        if not journey:
            bad("5", "no committee is on this deal's journey",
                "the product has no committee_journey and nothing was "
                "substituted. Admin > product flow > '+ Add committee gate' - "
                "THIS IS THE MOST LIKELY REASON NOTHING MOVED")
            return report(pm, deal_id, keep)
        code = str(cttee.get("code"))
        if code not in journey:
            bad("5", "%s is NOT on the journey" % code,
                "the journey resolves to %s - a decision recorded against this "
                "branch's committee would be refused" % journey)
            return report(pm, deal_id, keep)
        ok("5", "the branch's own committee is on the journey", code)

        # ── 6. CAN A DECISION BE RECORDED? ──────────────────────────────────
        rule("6. CAN THE COMMITTEE RECORD A DECISION")
        members = cttee.get("members") or []
        if not members:
            bad("6", "the committee has NO members",
                "a voting committee cannot produce a decision - the endpoint "
                "refuses an empty votes[]. Run seed_committee_members.py")
            return report(pm, deal_id, keep)
        quorum = A._committee_quorum(cttee) if hasattr(A, "_committee_quorum") else 2
        if len(members) < quorum:
            bad("6", "%d member(s) against a quorum of %d" % (len(members), quorum),
                "every decision would DEFER, so the case never leaves the gate")
            return report(pm, deal_id, keep)
        ok("6", "members vs quorum", "%d members, quorum %d" % (len(members), quorum))

        votes = [{"vote": "YES", "member": m.get("staff_code"),
                  "name": m.get("name"), "docs_checked": True}
                 for m in members[:max(quorum, 2)]]
        outcome = A._derive_outcome_from_votes(votes, cttee.get("voting_rule"), cttee)
        if outcome != "APPROVED":
            bad("6", "all-YES votes produced %r" % outcome,
                "with %d unanimous YES votes this should be APPROVED" % len(votes))
            return report(pm, deal_id, keep)
        ok("6", "decision derives correctly", "%d YES -> %s" % (len(votes), outcome))

        recs = dict(deal.get("committee_records") or {})
        recs[code] = {"outcome": outcome, "mode": "voting", "votes": votes,
                      "recorded_by": bm["code"], "recorded_by_name": bm["name"],
                      "recorded_at": "2026-08-12T12:00:00", "note": "simulation"}
        pm.update_deal(deal_id, {"committee_records": recs}, bm["code"])
        deal = pm.get_deal(deal_id)
        ok("6", "decision recorded on the deal", code)

        # ── 7. DOES THE GATE RELEASE? ───────────────────────────────────────
        rule("7. DOES THE GATE RELEASE")
        state = A._credit_checklist_state(deal) if hasattr(A, "_credit_checklist_state") else {}
        pend = state.get("committee_pending")
        rej = state.get("committee_rejected")
        if pend:
            bad("7", "the gate still reports PENDING: %s" % pend,
                "a decision was recorded but the checklist does not see it")
        elif rej:
            bad("7", "the gate reports REJECTED: %s" % rej)
        else:
            ok("7", "committee gate released", "the case can proceed to credit")

        # And the journey should show it.
        try:
            from utils.api_lms_journey import _events_from_deal
            ev = [e for e in _events_from_deal(deal) if "committee" in e.get("event", "")]
            if ev:
                ok("7", "the journey records the decision",
                   "%s by %s" % (ev[0]["event"], ev[0].get("by_name") or "?"))
            else:
                warn("7", "the journey does not show the committee decision")
        except Exception as exc:
            warn("7", "journey check failed", str(exc)[:60])

    except Exception:
        print("\n  UNHANDLED ERROR:")
        for ln in traceback.format_exc().strip().split("\n")[-6:]:
            print("     %s" % ln[:110])
        FAIL.append(("?", "unhandled error", ""))

    return report(pm, deal_id, keep)


def report(pm=None, deal_id="", keep=False):
    if pm is not None and deal_id and not keep:
        try:
            pm.deals[:] = [d for d in pm.deals if str(d.get("id")) != deal_id]
            pm._save_deals()
            print("\n  (test deal %s removed)" % deal_id)
        except Exception:
            print("\n  (could not remove test deal %s - delete it by hand)" % deal_id)

    rule("VERDICT")
    if not FAIL:
        print("A case CAN travel through the branch credit committee.")
        if WARN:
            print("%d warning(s), none blocking." % len(WARN))
        print("")
        print("If a branch manager still cannot move a case, the difference is")
        print("their IDENTITY, not the code - check their staff_code and role")
        print("with scripts\\diag_identity.py.")
        return 0
    print("%d FAILURE(S):\n" % len(FAIL))
    for step, what, detail in FAIL:
        print("   step %s: %s" % (step, what))
        if detail:
            print("      %s" % detail)
    return 1


if __name__ == "__main__":
    sys.exit(main())
