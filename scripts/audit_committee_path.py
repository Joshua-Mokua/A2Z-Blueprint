#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Would a branch credit committee actually work? READ ONLY. Exit 1 on a blocker.

RULING (2026-08-12): "before we release, can we do a full audit that the branch
committee would work - assuming we set one up, view documents, and give their
recommendation, and we can advance a case. Let us test from all angles so we
avoid coming back."

WHY A WALK AND NOT A REVIEW. Reading each endpoint tells you it is correct in
isolation. Only walking the path tells you whether step 4 accepts what step 3
produced - and every expensive fault on this system has lived in that seam.

WHAT IT WALKS, in the order a real case meets it:

     1  a branch committee EXISTS and is complete enough to sit
     2  a product ROUTES through it
     3  the deal can REACH the committee's stage
     4  members can SEE the case and its documents
     5  a recommendation can be RECORDED
     6  the case can move ON afterwards
     7  the journey SHOWS what happened

It reports BLOCKERS - things that stop a case - separately from WARNINGS, which
will confuse somebody without stopping them. Only blockers fail the run.

Nothing is written. Every check reads config and code as they stand.

    python scripts\\audit_committee_path.py
    python scripts\\audit_committee_path.py --committee BCC_BRN002
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

BLOCK, WARN = [], []


def block(what, detail=""):
    BLOCK.append((what, detail))
    print("  BLOCK  %s" % what)
    if detail:
        print("         %s" % detail)


def warn(what, detail=""):
    WARN.append((what, detail))
    print("  warn   %s" % what)
    if detail:
        print("         %s" % detail)


def ok(what, detail=""):
    print("  ok     %-46s %s" % (what[:46], detail))


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def jload(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def main():
    want = ""
    if "--committee" in sys.argv:
        i = sys.argv.index("--committee")
        if i + 1 < len(sys.argv):
            want = sys.argv[i + 1].strip()

    lms = jload(os.path.join("data", "lms_config.json"))
    ps = jload(os.path.join("data", "pipeline_settings.json"))
    api = ""
    try:
        api = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    except OSError:
        pass

    pal = ((lms.get("credit_workflow") or {}).get("committee_palette") or [])
    flows = ps.get("product_flows") or {}

    # ── 1. DOES A COMMITTEE EXIST, AND CAN IT SIT? ──────────────────────────
    rule("1. THE COMMITTEE ITSELF")
    branch = [c for c in pal if str(c.get("kind", "")).lower() == "branch"]
    if not branch:
        block("no branch committee exists",
              "run pilot_apply.py --apply, or the generate-branch endpoint")
    else:
        ok("branch committees exist", "%d" % len(branch))

    # KEEP GOING even with no committees. An audit that stops at the first
    # blocker hides everything behind it - and when the first thing is broken
    # is exactly when somebody needs to know what else is.
    target = None
    if branch:
        if want:
            target = next((c for c in branch if str(c.get("code")) == want), None)
            if not target:
                block("no committee with code %r" % want)
        else:
            # Prefer one that could actually sit, so the walk is realistic.
            target = next((c for c in branch if (c.get("members") or [])), branch[0])
    if target:
        print("  walking: %s (%s)" % (target.get("name"), target.get("code")))

    mode = str((target or {}).get("recording_mode", "") or "").lower()
    members = (target or {}).get("members") or []
    chair = str((target or {}).get("chaired_by", "") or "")

    if target and mode == "voting":
        # A VOTING committee with no members cannot produce a decision: the
        # endpoint refuses an empty votes[] with a 400. The case would reach
        # the gate and stop there with no way forward through the interface.
        if not members:
            block("%s is a VOTING committee with NO members" % target.get("code"),
                  "recording a decision requires votes[], and there is nobody "
                  "to vote - a case reaching this gate cannot leave it")
        else:
            ok("members", "%d" % len(members))
        if not chair:
            warn("no chair named",
                 "it can still sit; nobody is identified as convening it")
    else:
        ok("recording mode", mode or "(unset)")

    n_empty = sum(1 for c in branch if not (c.get("members") or [])) if branch else 0
    if n_empty:
        warn("%d of %d branch committees have no members" % (n_empty, len(branch)),
             "each is a gate that would stop a case if assigned")

    # ── 2. DOES ANY PRODUCT ROUTE THROUGH IT? ───────────────────────────────
    rule("2. IS IT ON A PRODUCT'S PATH")
    codes = {str(c.get("code")) for c in pal}
    routed = {}
    for prod, e in flows.items():
        j = (e or {}).get("committee_journey") or []
        if j:
            routed[prod] = j
    if not routed:
        block("no product routes through any committee",
              "Admin > product flow > '+ Add committee gate'. Until then the "
              "committee exists but no case ever reaches it")
    else:
        ok("products with a committee gate", ", ".join(list(routed)[:4]))
        for prod, j in routed.items():
            unknown = [g for g in j if g not in codes]
            if unknown:
                block("%s routes through unknown committee(s): %s"
                      % (prod, ", ".join(unknown)),
                      "the gate cannot be resolved, so the case stops")

    # ── 3. CAN A DEAL REACH THE GATE? ───────────────────────────────────────
    rule("3. CAN A CASE REACH IT")
    for prod in (routed or {}):
        stages = [str(s.get("stage", "")) for s in ((flows.get(prod) or {}).get("stages") or [])]
        if not stages:
            block("%s has no stages" % prod)
            continue
        has_cttee_stage = any("committee" in s.lower() for s in stages)
        if has_cttee_stage:
            ok("%s has a committee stage" % prod[:28],
               next(s for s in stages if "committee" in s.lower()))
        else:
            warn("%s routes through a committee but has no committee stage" % prod,
                 "the gate is recorded against the deal rather than being a "
                 "stage it sits at - workable, but the journey will not show "
                 "it waiting")
        if not any("closed" in s.lower() for s in stages):
            block("%s has NO closing stage" % prod,
                  "even after the committee decides, the case can never be closed")

    # ── 4. CAN MEMBERS SEE THE CASE AND ITS DOCUMENTS? ──────────────────────
    rule("4. CAN THE COMMITTEE SEE THE CASE")
    # Committee members are branch staff; they see a deal through the normal
    # cascade scope. If the deal is outside it, the endpoint answers 404 by
    # design - so a member not in the owner's tree sees nothing at all.
    if "resolve_deal_permissions" in api:
        ok("deal visibility is scope-based", "committee members need scope on the deal")
        warn("a member outside the owner's reporting tree sees a 404",
             "check that BCC members sit in the same branch as the deals they "
             "are asked to decide - this is the same class of fault as the "
             "orphaned validations")
    else:
        warn("could not verify deal visibility")

    if "lms_application_documents_list" in open(
            os.path.join("utils", "api_lms_routes.py"), encoding="utf-8").read():
        ok("documents are readable on the credit side", "carried with the case")
    else:
        warn("could not verify document visibility")

    # ── 5. CAN A RECOMMENDATION BE RECORDED? ────────────────────────────────
    rule("5. RECORDING THE RECOMMENDATION")
    if 'detail="voting committee requires votes[]"' in api:
        ok("a voting committee requires votes", "empty votes are refused")
    if "voted YES without confirming" in api:
        ok("a YES needs documentation confirmed", "governance check present")
    if "_derive_outcome_from_votes" in api:
        ok("outcome derives from the votes", "not typed by hand")
    i = api.find("def record_deal_committee_decision")
    seg = api[i:i + 4000] if i > 0 else ""
    if seg and "is not in this deal's committee journey" in seg:
        ok("a gate not on the deal's journey is refused", "")
    if seg and "can_view" in seg:
        # WORTH FLAGGING: recording is gated on can_view, not on membership.
        warn("recording is gated on can_view, not on COMMITTEE MEMBERSHIP",
             "anyone who can see the deal can record the committee's decision. "
             "For a pilot that is workable; for a bank it is a control gap")

    # ── 6. CAN THE CASE MOVE ON? ────────────────────────────────────────────
    rule("6. AFTER THE DECISION")
    if "committee_journey" in api and "_COMMITTEE_OUTCOMES" in api:
        ok("outcomes are constrained", "not free text")
    if "ADVANCE ON VALIDATION" in api:
        ok("validation advances the deal", "AV1")
    else:
        warn("validation does not advance the deal", "AV1 not applied here")
    if "committee-appeal" in api:
        ok("a declined case can be appealed", "")

    # ── 7. DOES THE JOURNEY SHOW IT? ────────────────────────────────────────
    rule("7. WHAT THE JOURNEY SHOWS")
    jr = ""
    try:
        jr = open(os.path.join("utils", "api_lms_journey.py"), encoding="utf-8").read()
    except OSError:
        pass
    for label, needle in (("committee outcome", "committee_{outcome}"),
                          ("committee appeal", "committee_appeal"),
                          ("manager validation", "manager_validated"),
                          ("stage changes", "deal_stage_change")):
        if needle in jr:
            ok("journey records %s" % label, "")
        else:
            warn("journey does NOT record %s" % label, "")

    # ── 8. DEPARTMENT COMMITTEE THROUGH TO THE CREDIT ANALYST ───────────────
    # The path the pilot is delivering today. Two config switches gate all of
    # it, and neither announces itself when unset - the buttons simply do not
    # appear, which reads as a permission fault rather than a setting.
    rule("8. DEPARTMENT COMMITTEE -> CREDIT ANALYST")
    # READ THROUGH THE ACCESSOR, not the file. get_credit_workflow_config()
    # falls back to complete code defaults, so a section absent from
    # lms_config.json is not absent from the system - it is running on the
    # default, which is DISABLED. The first version of this audit read the file
    # and reported "not configured", which sent somebody looking for a missing
    # block that was really a switch set to off.
    cw = (lms.get("credit_workflow") or {})
    try:
        from utils.api_lms_mutations import get_credit_workflow_config
        eff = get_credit_workflow_config() or {}
    except Exception:
        eff = cw
    da = eff.get("department_analyst") or {}
    dcc = eff.get("dcc") or {}
    if not da:
        block("department_analyst is missing entirely",
              "not even a default - the layer cannot be switched on")
    elif not da.get("enabled"):
        block("the Department Analyst layer is DISABLED",
              "can_submit_to_dcc AND can_hand_to_credit_analyst both require "
              "department_analyst.enabled. An analyst cannot send a case to "
              "the DCC and nobody can hand it to the credit analyst - neither "
              "button appears, and nothing says why. "
              "Run scripts\\enable_department_analyst.py")
    else:
        ok("department analyst layer enabled", "")
        if not dcc.get("enabled"):
            block("the DCC itself is DISABLED while the analyst layer is on",
                  "a case could be submitted to a committee that is switched "
                  "off, and would stop between the two")
        else:
            # THE OPERATIVE DCC IS THE ONE client_type_to_dcc POINTS AT, not
            # credit_workflow.dcc.members. That third structure is a P4
            # scaffold nothing currently reads, and checking it made this
            # audit report an empty roster while B1/B2/B3 sat there with four
            # members each. Second time today a check has read a different
            # structure from the one the code uses.
            route = (ps.get("committee_routing") or {}).get("client_type_to_dcc") or {}
            if not route:
                block("no client type routes to a DCC",
                      "committee_routing.client_type_to_dcc is unset, so a "
                      "case has no department committee to go to")
            else:
                for ct, code in route.items():
                    c = next((x for x in pal if str(x.get("code")) == str(code)), None)
                    if not c:
                        block("%s routes to %r, which is not in the palette"
                              % (ct, code),
                              "the case stops at a gate that does not exist - "
                              "run scripts\\fix_committee_routing.py")
                    elif len(c.get("members") or []) < 2:
                        block("%s routes to %s with %d member(s)"
                              % (ct, code, len(c.get("members") or [])),
                              "below the default quorum, so every decision "
                              "would DEFER")
                    else:
                        ok("%s routes to %s" % (ct, code),
                           "%s, %d members" % (str(c.get("name"))[:34],
                                               len(c.get("members") or [])))

    perms = ""
    try:
        perms = open(os.path.join("utils", "api_lms_permissions.py"),
                     encoding="utf-8").read()
    except OSError:
        pass
    if "dcc_outcome" in perms:
        ok("the handoff waits for a DCC outcome", "a case cannot skip the committee")
    if "is_assigned_analyst and status ==" in perms:
        ok("only the ASSIGNED analyst may hand over", "not anyone who can view")
        warn("both steps require status 'assigned'",
             "a case that has moved on - to credit_admin, say - loses both "
             "buttons even though the work is unfinished. That is what took "
             "Catherine's attach away earlier today")

    # ── 9. IS THERE ONE PLACE TO CREATE A COMMITTEE? ────────────────────────
    rule("9. IS THERE ONE PLACE TO CREATE A COMMITTEE")
    single = cw.get("committee")
    mode = str(cw.get("committee_mode", "") or "")
    if single and pal:
        warn("TWO committee models exist in credit_workflow",
             "'committee' - a single charter, id %r, honoured only when "
             "committee_mode is 'committee_voting', currently %r - and "
             "'committee_palette', the list the admin page edits and the "
             "product journeys use. They do not corrupt each other, but a "
             "committee created in the first NEVER appears in the second"
             % (str(single.get("committee_id", "?")), mode or "unset"))
        if mode != "committee_voting":
            ok("the single-charter model is INERT", "committee_mode is %r" % mode)
    elif pal:
        ok("one committee model in use", "committee_palette")

    return report()


def report():
    rule("VERDICT")
    if not BLOCK:
        print("A case could travel through a branch credit committee.")
        if WARN:
            print("%d warning(s) - none stop a case; all will confuse somebody."
                  % len(WARN))
        return 0
    print("%d BLOCKER(S) between a case and a committee decision:\n" % len(BLOCK))
    for what, detail in BLOCK:
        print("   * %s" % what)
        if detail:
            print("     %s" % detail)
    if WARN:
        print("\n%d warning(s) as well." % len(WARN))
    return 1


if __name__ == "__main__":
    sys.exit(main())
