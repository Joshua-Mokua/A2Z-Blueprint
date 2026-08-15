#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
The full pilot rehearsal: every branch, every origin, every gate.

WHY. Two pilots have now been called and neither reached a recommendation.
Each time the code was right in the small and wrong in the joins - a committee
demanded before its turn, a memo demanded before it exists, a committee nobody
sat on. Testing one case at one gate cannot find those. Only volume through
the whole lifecycle can.

So this rehearses the pilot: cases across all 16 branches, from every origin a
branch actually uses, over the real product mix, walked from creation to
credit analysis with committees voting and analysts returning work.

    python scripts\\rehearse_pilot.py                  # default volume
    python scripts\\rehearse_pilot.py --per-staff 20   # the full ask
    python scripts\\rehearse_pilot.py --verbose

NOTHING IS WRITTEN. Deals live in memory; the real stores are never opened for
writing. Run it against a live box safely.

WHAT IT WATCHES FOR, at every step:

    a case that cannot leave a stage, and no reason given
    a gate demanding something that does not exist yet
    a committee with nobody on it - the case vanishes silently
    a stage label that names the wrong destination
    a decision that does not move the case
    a rework that does not come back
    anything that raises
"""
import json
import os
import random
import sys
import traceback
from collections import Counter

sys.path.insert(0, os.getcwd())

ISSUES = []
COUNTS = Counter()
VERBOSE = "--verbose" in sys.argv
PER_STAFF = 3
if "--per-staff" in sys.argv:
    i = sys.argv.index("--per-staff")
    if i + 1 < len(sys.argv):
        PER_STAFF = max(1, int(sys.argv[i + 1]))

random.seed(20260814)


def issue(kind, what, detail=""):
    ISSUES.append((kind, what, detail))
    COUNTS["issue:" + kind] += 1


def note(k):
    COUNTS[k] += 1


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    import utils.api as A
    import utils.api_lms_routes as R
    from utils.core import PipelineManager, UserManager

    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    cw = cfg.get("credit_workflow") or {}
    pal = cw.get("committee_palette") or []
    branch_cttees = {str(c.get("branch", "")).strip().lower(): c
                     for c in pal if str(c.get("kind", "")).lower() == "branch"}

    pcfg = A._load_json("pipeline_settings.json") or {}
    flows = pcfg.get("product_flows") or {}
    all_products = sorted(flows)
    # WALK THE CREDIT PRODUCTS. A current account or a debit card has no
    # committee stage and never touches the credit gate; mixing them in meant
    # most iterations skipped and the volume quietly collapsed to a handful.
    products = [p for p in all_products
                if any("committee" in str(x).lower()
                       for x in (A._stage_flow_for(p) or []))]
    non_credit = len(all_products) - len(products)
    if not products:
        print("ABORT: no product has a committee stage to rehearse.")
        return 1

    # ── Who is where ────────────────────────────────────────────────────────
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        roster = []
        for _i, r in df.iterrows():
            roster.append({"code": str(r.get("Staff Code") or "").strip(),
                           "name": str(r.get("Staff Name") or "").strip(),
                           "role": str(r.get("Role") or "").strip(),
                           "unit": str(r.get("Unit") or "").strip()})
    except Exception as exc:
        print("  note: the staff register is unreadable (%s)" % str(exc)[:40])
        roster = []

    if not roster:
        # NO REGISTER ON THIS BOX. Rehearse against the committees themselves,
        # so the flow is still exercised end to end - the point is the JOINS
        # between stages, and those do not depend on real names.
        print("  note: no staff register - rehearsing with stand-in staff per branch")
        roster = []
        for c in pal:
            if str(c.get("kind", "")).lower() != "branch":
                continue
            br = str(c.get("branch") or "").strip()
            if not br:
                continue
            for n in range(4):
                roster.append({"code": "SIM%s%d" % (br[:3].upper(), n),
                               "name": "%s Officer %d" % (br, n),
                               "role": ["Branch Manager", "Relationship Manager",
                                        "Customer Service Manager",
                                        "Relationship Officer"][n],
                               "unit": br})
        for n, d in enumerate(("Consumer Banking", "Commercial Banking",
                               "Corporate Banking", "Digital Channels")):
            roster.append({"code": "SIMHO%d" % n, "name": "%s Head" % d,
                           "role": "Head, %s" % d, "unit": d})

    by_branch = {}
    for p in roster:
        if p["code"] and p["unit"]:
            by_branch.setdefault(p["unit"].strip().lower(), []).append(p)

    branches = [b for b in by_branch if b in branch_cttees] or list(by_branch)[:16]
    if not branches:
        print("ABORT: no branch has both staff and a committee.")
        return 1

    # Head-office departments, for referrals in.
    ho = [p for p in roster
          if p["unit"] and p["unit"].strip().lower() not in by_branch
          or any(k in p["role"].lower() for k in ("head", "director", "chief"))]
    ho_depts = {}
    for p in ho:
        ho_depts.setdefault(p["unit"] or "Head Office", []).append(p)
    dept_names = sorted(ho_depts)[:6]

    ORIGINS = ["own", "branch referral", "head office referral", "event"]

    print("=" * 78)
    print("PILOT REHEARSAL")
    print("=" * 78)
    print("  branches            %d" % len(branches))
    print("  staff on register   %d" % len(roster))
    print("  head-office units   %d" % len(dept_names))
    print("  credit products     %d  (%d non-credit, not walked)"
          % (len(products), non_credit))
    print("  cases per staff     %d" % PER_STAFF)

    # ── Committees that can hear a case ─────────────────────────────────────
    rule("1. CAN EACH BRANCH'S COMMITTEE ACTUALLY HEAR A CASE")
    blind = []
    for b in branches:
        c = branch_cttees.get(b)
        if not c:
            blind.append((b, "no committee at all"))
            continue
        real = [m for m in (c.get("members") or [])
                if isinstance(m, dict)
                and (str(m.get("staff_code", "")).strip() or str(m.get("name", "")).strip())]
        chair = str(c.get("chaired_by", "") or "").strip()
        if not real and not chair:
            blind.append((b, "%s has nobody on it" % c.get("code")))
        elif len(real) < (c.get("min_quorum_count") or 2):
            print("  warn  %-18s %s: %d member(s), quorum %d - can be seen, cannot decide"
                  % (b[:18], c.get("code"), len(real), c.get("min_quorum_count") or 2))
            note("committee below quorum")
        else:
            note("committee ready")
    for b, why in blind:
        issue("BLACK HOLE", "%s: %s" % (b, why),
              "a case sent here appears in NO queue and nothing reports an error")
    print("  committees ready    %d" % COUNTS["committee ready"])
    print("  below quorum        %d" % COUNTS["committee below quorum"])
    print("  NOBODY ON THEM      %d" % len(blind))

    # ── The rehearsal itself ────────────────────────────────────────────────
    rule("2. WALKING CASES FROM CREATION TO CREDIT ANALYSIS")

    holder = {"deal": None}

    class Store:
        deals = []
        def get_deal(self, i): return holder["deal"]
        def update_deal(self, i, u, by=""): holder["deal"].update(u); return holder["deal"]
        def update_stage(self, i, st, *a, **k): holder["deal"]["stage"] = st
        def _save_deals(self): pass

    A._get_or_hydrate_deal = lambda pm, did: holder["deal"]
    A._deal_for_docs = lambda did, u: (Store(), holder["deal"])
    A._db_available = lambda: False
    A.get_visible_staff_codes = lambda u: {str(u.get("staff_code"))}

    made = 0
    reached_committee = 0
    stuck_here = Counter()

    for b in branches:
        people = [p for p in by_branch.get(b, []) if p["code"]][:6]
        cttee = branch_cttees.get(b)
        for person in people:
            for n in range(PER_STAFF):
                prod = products[(made + n) % len(products)]
                origin = ORIGINS[(made + n) % len(ORIGINS)]
                stages = [str(x) for x in (A._stage_flow_for(prod) or [])]
                if not stages:
                    issue("NO FLOW", "%s has no stage flow" % prod, "no case on it can move")
                    continue
                # NOT EVERY PRODUCT IS CREDIT. A current account, a debit card
                # or an insurance policy has no committee stage and never
                # touches the credit gate - walking one through it reports a
                # healthy product as stuck. Counted, not walked.
                if not any("committee" in x.lower() for x in stages):
                    note("non-credit product (no committee stage)")
                    continue
                ct = ["Consumer", "Commercial", "CIB"][(made) % 3]

                deal = {
                    "id": "SIMR%05d" % made, "client_name": "Rehearsal %d" % made,
                    "product": prod, "product_type": prod,
                    "deal_value": 500000 + (made % 40) * 250000,
                    "staff_code": person["code"], "staff_name": person["name"],
                    "branch": person["unit"], "unit": person["unit"],
                    "client_type": ct, "stage": stages[0],
                    "manager_validated": True, "committee_records": {}, "cr": {},
                    "origin_channel": origin,
                }
                if origin == "head office referral" and dept_names:
                    d = dept_names[made % len(dept_names)]
                    deal["referred_by_unit"] = d
                    deal["referral_status"] = "accepted"
                    note("origin: head office (%s)" % d[:18])
                elif origin == "branch referral":
                    deal["referred_by_unit"] = branches[(made + 1) % len(branches)]
                    deal["referral_status"] = "accepted"
                    note("origin: branch referral")
                elif origin == "event":
                    deal["origin_event"] = "Branch activation %d" % (made % 5)
                    note("origin: event")
                else:
                    note("origin: own")
                note("product: %s" % prod[:22])
                note("client type: %s" % ct)

                holder["deal"] = deal
                made += 1
                user = {"username": person["code"], "staff_code": person["code"],
                        "full_name": person["name"], "role": person["role"]}

                # Walk the case forward through every stage.
                idx = 0
                guard = 0
                while idx < len(stages) - 1 and guard < 40:
                    guard += 1
                    stage = stages[idx]
                    deal["stage"] = stage
                    if stage.lower().startswith("closed"):
                        break

                    try:
                        c = A.pipeline_credit_checklist(deal["id"], user=user)
                    except Exception as exc:
                        issue("RAISED", "%s @ %s" % (prod[:20], stage[:22]), str(exc)[:70])
                        break

                    # Does the wording name the right destination?
                    nxt = stages[idx + 1]
                    lbl = str(c.get("submit_label", "") or "")
                    if lbl and "credit analysis" in lbl.lower() \
                            and "credit analysis" not in nxt.lower():
                        issue("WRONG LABEL",
                              "%s @ %s says %r" % (prod[:16], stage[:18], lbl[:34]),
                              "the case is going to %s" % nxt)

                    if not c.get("can_submit"):
                        pend = c.get("committee_pending") or []
                        # Is it waiting on a committee it has not reached?
                        ahead = []
                        for code in pend:
                            cm = A._committee_by_code(code) or {}
                            cs = str(cm.get("stage", "") or "")
                            if cs and cs in stages and stages.index(cs) > idx:
                                ahead.append(code)
                        if ahead:
                            issue("BLOCKED BY A FUTURE GATE",
                                  "%s @ %s waits on %s" % (prod[:16], stage[:18], ",".join(ahead)),
                                  "that committee sits later in the flow")
                            break
                        if pend:
                            # Its own committee owes a decision: hold the vote.
                            code = pend[0]
                            cm = A._committee_by_code(code) or {}
                            mem = [m for m in (cm.get("members") or [])
                                   if isinstance(m, dict) and str(m.get("name", "")).strip()]
                            if not mem and not str(cm.get("chaired_by", "")).strip():
                                issue("BLACK HOLE",
                                      "%s @ %s waits on %s" % (prod[:16], stage[:18], code),
                                      "nobody sits on that committee - the case stops here "
                                      "and no queue shows it")
                                stuck_here[stage] += 1
                                break
                            outcome = ["APPROVED", "APPROVED", "APPROVED", "REJECTED"][made % 4]
                            deal["committee_records"] = dict(deal.get("committee_records") or {})
                            deal["committee_records"][code] = {
                                "outcome": outcome, "recorded_by": "rehearsal",
                                "recorded_at": "2026-08-14"}
                            note("committee %s" % outcome.lower())
                            reached_committee += 1
                            if outcome == "REJECTED":
                                note("case closed by rejection")
                                break
                            continue          # re-check with the decision in hand
                        if c.get("cr_required") and not c.get("cr_ok"):
                            # The memo: does the flow let it exist by now?
                            bcc = next((s for s in stages
                                        if "branch credit committee" in s.lower()), "")
                            if bcc and stages.index(bcc) > idx:
                                issue("MEMO TOO EARLY",
                                      "%s @ %s" % (prod[:18], stage[:20]),
                                      "the memo is demanded before %s, which produces it" % bcc[:26])
                                break
                            deal["cr"] = {"completed": True}
                            note("memo completed")
                            continue
                        if c.get("manager_validated") is False:
                            deal["manager_validated"] = True
                            continue
                        if c.get("stage_ok") is False:
                            idx += 1          # not a submission point; it advances
                            continue
                        issue("STUCK, NO REASON",
                              "%s @ %s" % (prod[:18], stage[:20]),
                              "cannot submit and nothing on the screen says why")
                        stuck_here[stage] += 1
                        break

                    idx += 1

                # WHERE DID IT ACTUALLY GET TO? The first version only counted
                # cases that ran to the last stage, so rejections and cases
                # that legitimately stop at a decision point read as zero -
                # a metric that says nothing happened while everything did.
                final = stages[min(idx, len(stages) - 1)]
                if "credit analysis" in final.lower():
                    note("got as far as credit analysis")
                elif "committee" in final.lower():
                    note("got as far as a committee")
                elif idx >= len(stages) - 1:
                    note("ran to the end of the flow")
                else:
                    note("stopped at %s" % final[:30])

    print("  cases created       %d" % made)
    print("  committee decisions %d" % reached_committee)
    print("  reached the end     %d" % COUNTS["reached the end"])

    # ── The analyst and department committee ────────────────────────────────
    rule("3. THE ANALYST AND THE DEPARTMENT COMMITTEE")
    R.audit_log = lambda *a, **k: None
    R.is_valid_lms_transition = lambda a, b: True
    R.resolve_application_permissions = lambda u, a: {
        "can_view": True, "can_update": True, "can_set_committee_readiness": True,
        "can_resolve_dcc": True, "can_submit_to_dcc": True}

    class LStore:
        def __init__(s, a): s.a = {a["id"]: dict(a)}
        def get(s, i): return s.a.get(i)
        def update(s, i, u): s.a[i].update(u); return s.a[i]

    an = {"username": "an", "staff_code": "AN1", "full_name": "Analyst", "role": "Credit Analyst"}
    ow = {"username": "ow", "staff_code": "OW1", "full_name": "Owner"}
    V = lambda v, n: {"member_id": "M%d" % n, "vote": v}

    outcomes = Counter()
    for n in range(60):
        base = {"id": "L%03d" % n, "status": "assigned", "client_type": "Consumer",
                "analyst": {"code": "AN1", "name": "Analyst"}, "rm_code": "OW1"}
        st = LStore(base); R._lam = lambda st=st: st
        path = n % 3          # recommend / rework then recommend / rework twice
        try:
            if path >= 1:
                R.lms_committee_readiness("L%03d" % n,
                                          {"decision": "rework", "opinion": "More detail"}, an)
                if st.get("L%03d" % n)["status"] != "returned":
                    issue("REWORK DID NOT RETURN", "case %d" % n,
                          "status is %r" % st.get("L%03d" % n)["status"])
                R.lms_resubmit_after_rework("L%03d" % n, {}, ow)
                if str(st.get("L%03d" % n).get("analyst", {}).get("code")) != "AN1":
                    issue("REWORK LOST THE ANALYST", "case %d" % n, "it went to the pool")
                outcomes["returned for rework"] += 1
            if path == 2:
                R.lms_committee_readiness("L%03d" % n,
                                          {"decision": "rework", "opinion": "Again"}, an)
                R.lms_resubmit_after_rework("L%03d" % n, {}, ow)
                if len(st.get("L%03d" % n).get("rework_history") or []) < 2:
                    issue("SECOND REWORK OVERWROTE THE FIRST", "case %d" % n, "")
                outcomes["returned twice"] += 1

            R.lms_committee_readiness("L%03d" % n, {"decision": "ready"}, an)
            a = st.get("L%03d" % n)
            if a["status"] != "referred_to_committee":
                issue("RECOMMEND DID NOT SUBMIT", "case %d" % n, "status %r" % a["status"])
                continue
            outcomes["recommended to committee"] += 1

            votes = [[V("YES", 1), V("YES", 2), V("YES", 3)],
                     [V("NO", 1), V("NO", 2), V("YES", 3)],
                     [V("YES", 1), V("NO", 2)]][n % 3]
            a["dcc_votes"] = votes
            R.lms_dcc_resolve("L%03d" % n, {}, an)
            a = st.get("L%03d" % n)
            rec = (a.get("dcc_outcome") or {}).get("recommendation")
            if rec == "support":
                if a["status"] != "submitted" or not a.get("awaiting_credit_analyst"):
                    issue("SUPPORTED CASE DID NOT REACH CREDIT", "case %d" % n,
                          "status %r" % a["status"])
                outcomes["supported -> credit pool"] += 1
            else:
                if a["status"] != "assigned":
                    issue("OPPOSED CASE DID NOT RETURN", "case %d" % n,
                          "status %r" % a["status"])
                outcomes["%s -> back to analyst" % rec] += 1
        except Exception as exc:
            issue("RAISED IN THE ANALYST PATH", "case %d" % n, str(exc)[:70])

    for k, v in outcomes.most_common():
        print("  %-34s %d" % (k, v))

    return report(stuck_here)


def report(stuck):
    rule("WHAT THE REHEARSAL SAW")
    for k in sorted(COUNTS):
        if k.startswith("issue:") or not VERBOSE:
            continue
        print("  %-40s %d" % (k, COUNTS[k]))
    if not VERBOSE:
        for grp in ("origin:", "product:", "client type:", "committee "):
            hits = [(k, v) for k, v in COUNTS.items() if k.startswith(grp)]
            if hits:
                print("  %-24s %s" % (grp.rstrip(":"),
                                      ", ".join("%s=%d" % (k.split(":", 1)[-1].strip(), v)
                                                for k, v in sorted(hits)[:6])))

    rule("VERDICT")
    if not ISSUES:
        print("  No issues. The whole lifecycle runs, at volume, from every origin.")
        return 0
    kinds = Counter(k for k, _w, _d in ISSUES)
    print("  %d issue(s), in %d kind(s):\n" % (len(ISSUES), len(kinds)))
    for kind, n in kinds.most_common():
        print("  %s  (%d)" % (kind, n))
        shown = 0
        for k, what, detail in ISSUES:
            if k != kind or shown >= 3:
                continue
            print("     %s" % what)
            if detail:
                print("        %s" % detail)
            shown += 1
        if n > 3:
            print("     ... and %d more" % (n - 3))
        print("")
    if stuck:
        print("  STAGES WHERE CASES STOP:")
        for s, n in stuck.most_common(6):
            print("     %-40s %d case(s)" % (s[:40], n))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-8:]:
            print("   %s" % ln[:110])
        sys.exit(1)
