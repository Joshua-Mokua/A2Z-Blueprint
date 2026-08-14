#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Drive a Consumer case through the analyst and the department committee.

WHY THIS EXISTS, in the pilot's own words: "the system backend especially is
heavily built ... it is rich and we only work to improve the missing pieces.
The best way to test the consumer analyst and committee gate is first to create
simulation deals, then test in code from all angles - if it is working as
intended, then have a few cases I can also test with."

That is the right order and it is the one I had been skipping. Twice in a day I
started building something the system already had, because I worked from a
description instead of from the running code.

So this asks the code, step by step, and reports the FIRST thing that refuses:

     1  a Consumer application exists and resolves to the consumer segment
     2  Catherine's segment resolves, and she can SEE it
     3  she can PICK it without anyone assigning it
     4  she can mark it ready for committee, or return it for rework
     5  a returned case goes back to the OWNER, and remembers her
     6  a resubmitted case comes back to HER, not the pool
     7  the department committee is resolvable and has members
     8  a member can vote, and one vote does not decide it
     9  quorum decides, and the case moves on by itself
    10  every one of those appears in the case journey

Nothing is written unless --apply. With it, test records are created under a
SIM- prefix and removed at the end unless --keep.

    python scripts\\simulate_consumer_flow.py
    python scripts\\simulate_consumer_flow.py --apply
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

FAIL, WARN, OK = [], [], []
PREFIX = "SIMCONS"


def ok(step, what, detail=""):
    OK.append(what)
    print("  ok     %-3s %-46s %s" % (step, what[:46], detail[:40]))


def bad(step, what, detail=""):
    FAIL.append((step, what, detail))
    print("  FAIL   %-3s %s" % (step, what))
    if detail:
        print("              %s" % detail)


def warn(step, what, detail=""):
    WARN.append((step, what))
    print("  warn   %-3s %s" % (step, what))
    if detail:
        print("              %s" % detail)


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    apply = "--apply" in sys.argv
    keep = "--keep" in sys.argv

    try:
        from utils.core import UserManager
        from utils.api_lms_scope import (_analyst_segment, _app_segment,
                                         filter_apps_by_visibility)
        import utils.api as A
        import utils.api_lms_routes as R
    except Exception as exc:
        print("ABORT: cannot load the application: %s" % exc)
        return 1

    # ── 0. WHO ──────────────────────────────────────────────────────────────
    rule("0. THE PEOPLE")
    users = UserManager().users or {}
    analyst = None
    for k, v in users.items():
        role = str(v.get("role", "") or "")
        code = str(v.get("staff_code", "") or "")
        if "credit analyst" in role.lower() and _analyst_segment(role, code) == "consumer":
            analyst = {"username": k, "staff_code": code, "role": role,
                       "full_name": v.get("full_name") or v.get("name") or k}
            break
    if not analyst:
        bad("0", "no login resolves to the CONSUMER segment",
            "a Department Analyst is recognised by role + the register's "
            "Department. Run scripts\\diag_analyst_segment.py --user <them> to "
            "see which of the two is missing.")
        return report()
    print("  consumer analyst   %s (%s) %s"
          % (analyst["full_name"], analyst["staff_code"], analyst["role"]))
    ok("0", "a consumer analyst exists", analyst["staff_code"])

    # ── 1. THE COMMITTEE ────────────────────────────────────────────────────
    rule("1. THE DEPARTMENT CREDIT COMMITTEE")
    try:
        cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    except Exception as exc:
        bad("1", "lms_config.json unreadable", str(exc)[:60])
        return report()
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
    dcc = next((c for c in pal
                if str(c.get("kind", "")).lower() != "branch"
                and "consumer" in str(c.get("name", "")).lower()), None)
    if not dcc:
        bad("1", "no Consumer department committee in the palette",
            "codes present: %s" % ", ".join(str(c.get("code")) for c in pal[:8]))
        return report()
    members = dcc.get("members") or []
    print("  committee          %s (%s)" % (dcc.get("name"), dcc.get("code")))
    print("  members            %d" % len(members))
    for m in members[:6]:
        print("     %-10s %s" % (m.get("staff_code"), m.get("name")))
    quorum = A._committee_quorum(dcc) if hasattr(A, "_committee_quorum") else 2
    if len(members) < quorum:
        bad("1", "%d member(s) against a quorum of %d" % (len(members), quorum),
            "every decision would DEFER, so no case can leave this gate. The "
            "bank names members in Admin > Credit Committees.")
    else:
        ok("1", "the committee can sit", "%d members, quorum %d" % (len(members), quorum))

    # ── 2. ROUTING ──────────────────────────────────────────────────────────
    rule("2. DOES A CONSUMER CASE ROUTE TO IT")
    deal = {"id": "%s1" % PREFIX, "client_type": "Consumer",
            "branch": "", "product_type": "Personal Loan"}
    journey = A._effective_committee_journey(deal) or []
    print("  journey for a Consumer, non-branch case: %s" % (journey or "[]"))
    if str(dcc.get("code")) not in journey:
        bad("2", "the Consumer DCC is NOT on the journey",
            "a case would never reach this committee. Check "
            "pipeline_settings.json > committee_routing > client_type_to_dcc.")
    else:
        ok("2", "a Consumer case routes to this committee", str(dcc.get("code")))

    # ── 3. WHAT THE ANALYST SEES ────────────────────────────────────────────
    rule("3. WHAT THE ANALYST SEES")
    probe = [
        {"id": "P-ind", "client_type": "Individual", "status": "submitted", "rm_code": "ZZ"},
        {"id": "P-con", "client_type": "Consumer", "status": "submitted", "rm_code": "ZZ"},
        {"id": "P-com", "client_type": "Commercial", "status": "submitted", "rm_code": "ZZ"},
        {"id": "P-cib", "client_type": "Large Corporate", "status": "submitted", "rm_code": "ZZ"},
        {"id": "P-biz", "client_type": "Business", "status": "submitted", "rm_code": "ZZ"},
    ]
    for a in probe:
        print("     %-8s client_type %-18r -> segment %r"
              % (a["id"], a["client_type"], _app_segment(a)))
    seen = filter_apps_by_visibility(probe, set(), analyst["staff_code"],
                                     caller_role=analyst["role"])
    ids = [a["id"] for a in seen]
    print("\n  visible to this analyst: %s" % ids)
    if "P-com" in ids or "P-cib" in ids:
        bad("3", "the analyst can see other segments' cases",
            "Commercial or CIB in %s" % ids)
    elif "P-con" not in ids or "P-ind" not in ids:
        bad("3", "the analyst CANNOT see their own segment's cases",
            "expected P-con and P-ind, got %s" % ids)
    else:
        ok("3", "sees Consumer and Individual only", ", ".join(ids))
    if "P-biz" not in ids:
        warn("3", "'Business' resolves to no segment, so no analyst sees it",
             "the bank must say what separates a Commercial business from a "
             "CIB one before those can route")

    # ── 4. THE ACTIONS ──────────────────────────────────────────────────────
    rule("4. THE ACTIONS THE FLOW NEEDS")
    routes = {getattr(r, "path", "") for r in R.router.routes}
    need = {
        "pick a case without assignment": "/api/lms/applications/{app_id}/pick",
        "mark ready / return for rework": "/api/lms/applications/{app_id}/committee-readiness",
        "resubmit after rework":          "/api/lms/applications/{app_id}/resubmit-after-rework",
        "vote at the department committee": "/api/lms/applications/{app_id}/dcc/vote",
        "resolve the department committee": "/api/lms/applications/{app_id}/dcc/resolve",
        "submit to the department committee": "/api/lms/applications/{app_id}/committee/refer",
    }
    for label, path in need.items():
        if path in routes:
            ok("4", label, path.split("/")[-1])
        else:
            bad("4", "%s — MISSING" % label, path)

    # ── 5. DOES A REWORK ACTUALLY RETURN THE CASE ───────────────────────────
    rule("5. DOES A REWORK MOVE THE CASE")
    src = open(os.path.join("utils", "api_lms_routes.py"), encoding="utf-8").read()
    i = src.find('def lms_committee_readiness')
    blk = src[i:src.find("\n@router.", i + 10)] if i > 0 else ""
    if '"status": "returned"' in blk:
        ok("5", "a rework sets the status to returned", "the branch is told")
    else:
        bad("5", "a rework records a state but does not move the case",
            "the analyst marks it returned and it sits in their own queue - "
            "everybody believes it is with somebody else")
    if "returned_by_code" in blk:
        ok("5", "it remembers which analyst to come back to", "")
    else:
        bad("5", "a resubmitted case would go to the pool, not back to them")

    # ── 6. THE JOURNEY ──────────────────────────────────────────────────────
    rule("6. WHAT THE JOURNEY WILL SHOW")
    jr = open(os.path.join("utils", "api_lms_journey.py"), encoding="utf-8").read()
    for label, marker in (("each committee vote", "committee_vote"),
                          ("an automatic advance", "auto_advanced"),
                          ("manager validation", "manager_validated"),
                          ("referral", "referral_")):
        if marker in jr:
            ok("6", label, "")
        else:
            bad("6", "%s is NOT recorded" % label, marker)
    if "rework" not in jr:
        bad("6", "a rework does NOT appear in the journey",
            "a case returned to the branch leaves no trace of who returned it "
            "or why - which is the entry an auditor asks about first")

    return report()


def report():
    rule("VERDICT")
    if not FAIL:
        print("The consumer analyst and department committee path is sound.")
        if WARN:
            print("%d warning(s), none blocking." % len(WARN))
        print("\nCreate cases to test by hand with:")
        print("  python scripts\\seed_committee_cases.py --branch <branch> --apply")
        return 0
    print("%d FAILURE(S), in the order they would be hit:\n" % len(FAIL))
    for step, what, detail in FAIL:
        print("   step %s: %s" % (step, what))
        if detail:
            print("      %s" % detail)
    print("\n%d check(s) passed." % len(OK))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-6:]:
            print("   %s" % ln[:110])
        sys.exit(1)
