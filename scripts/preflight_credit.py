#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
The pre-release gate: does the whole credit path actually work? READ ONLY.

WHY THIS EXISTS, in the pilot's words: "from the lessons we have learnt, I wish
we take our time and do a very clean release with no back and forths that
consumed so much time previously."

Every wasted cycle this week had the same shape. Something was fixed, the fix
looked applied, and the pilot discovered it was not - a patcher that skipped
because a marker was in the wrong place, a block that overwrote the one before
it, a check that matched its own comment. In each case the CODE was present and
the BEHAVIOUR was absent, and nothing in between asked which.

So this asks the behaviour. It drives the real endpoints against a stand-in
store and reports what a person would actually see. It changes nothing.

    python scripts\\preflight_credit.py
    python scripts\\preflight_credit.py --verbose

Exit code 0 means the path is sound and the release is worth building.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

PASS, FAIL, WARN = [], [], []
VERBOSE = "--verbose" in sys.argv


def ok(what, detail=""):
    PASS.append(what)
    print("  ok     %-52s %s" % (what[:52], detail[:24]))


def bad(what, why):
    FAIL.append((what, why))
    print("  FAIL   %s" % what)
    print("         %s" % why)


def warn(what, why=""):
    WARN.append(what)
    print("  warn   %s" % what)
    if why:
        print("         %s" % why)


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


class Store:
    """A stand-in application store, so the test exercises the endpoints and
    not whatever happens to be on disk."""

    def __init__(self, app):
        self.a = {app["id"]: dict(app)}

    def get(self, i):
        return self.a.get(i)

    def update(self, i, u):
        self.a[i].update(u)
        return self.a[i]


def main():
    try:
        import utils.api as A
        import utils.api_lms_routes as R
        from utils.api_lms_journey import _events_from_deal
        from utils.api_lms_scope import _app_segment, _analyst_segment
    except Exception as exc:
        print("ABORT: cannot load the application: %s" % exc)
        return 1

    # Silence the parts that touch real state.
    R.audit_log = lambda *a, **k: None
    R.is_valid_lms_transition = lambda a, b: True
    R.resolve_application_permissions = lambda u, a: {
        "can_view": True, "can_update": True, "can_set_committee_readiness": True,
        "can_resolve_dcc": True, "can_submit_to_dcc": True}

    analyst = {"username": "cat", "staff_code": "KE1300",
               "full_name": "Catherine Mwikali Mutisya", "role": "Credit Analyst"}

    # ── 1. THE ANALYST'S VERDICT ────────────────────────────────────────────
    rule("1. THE ANALYST RECOMMENDS, AND IT SUBMITS")
    base = {"id": "P1", "status": "assigned", "client_type": "Consumer",
            "analyst": {"code": "KE1300", "name": "Catherine"}, "rm_code": "KE1318"}
    st = Store(base)
    R._lam = lambda: st
    try:
        R.lms_committee_readiness("P1", {"decision": "ready", "opinion": "Well packaged"}, analyst)
        a = st.get("P1")
        if a["status"] == "referred_to_committee" and a.get("committee_kind") == "dcc":
            ok("recommending sends the case to the committee", a["status"])
        else:
            bad("recommending does NOT send the case",
                "status=%r committee_kind=%r - the committee tab will say it "
                "was never submitted" % (a["status"], a.get("committee_kind")))
    except Exception as exc:
        bad("recommending raised", str(exc)[:90])

    try:
        R.lms_committee_readiness("P1", {"decision": "ready"}, analyst)
        bad("a second recommendation was accepted",
            "the journey would show the same verdict twice")
    except Exception as exc:
        if "409" in str(exc):
            ok("a second recommendation is refused", "409")
        else:
            bad("a second recommendation failed for the wrong reason", str(exc)[:80])

    # ── 2. RETURN FOR REWORK ────────────────────────────────────────────────
    rule("2. A REWORK GOES BACK TO THE BRANCH, AND COMES BACK TO HER")
    st = Store(base)
    R._lam = lambda: st
    try:
        R.lms_committee_readiness("P1", {"decision": "rework",
                                         "opinion": "Valuation out of date",
                                         "reasons": ["Valuation Report"]}, analyst)
        a = st.get("P1")
        if a["status"] == "returned":
            ok("a rework returns the case", "status=returned")
        else:
            bad("a rework does not move the case",
                "status=%r - it stays in her queue and the branch is never told"
                % a["status"])
        if a.get("returned_by_code") == "KE1300":
            ok("it remembers which analyst to come back to", "KE1300")
        else:
            bad("the case would return to the pool, not to her",
                "returned_by_code=%r" % a.get("returned_by_code"))
        if a.get("rework_history"):
            ok("the reason is kept in rework_history",
               "%d entry" % len(a["rework_history"]))
        else:
            bad("no rework history", "a second return would overwrite the first")
    except Exception as exc:
        bad("returning for rework raised", str(exc)[:90])

    owner = {"username": "ed", "staff_code": "KE1318", "full_name": "Edward Mwenda"}
    try:
        R.lms_resubmit_after_rework("P1", {"note": "Fresh valuation attached"}, owner)
        a = st.get("P1")
        if str(a.get("analyst", {}).get("code")) == "KE1300":
            ok("a resubmitted case goes back to the same analyst", "KE1300")
        else:
            bad("a resubmitted case does not return to her",
                "analyst=%r" % a.get("analyst"))
    except Exception as exc:
        bad("resubmitting raised", str(exc)[:90])

    # ── 3. THE COMMITTEE ────────────────────────────────────────────────────
    rule("3. THE COMMITTEE DECIDES, AND THE CASE MOVES ON")
    try:
        cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    except Exception as exc:
        bad("lms_config.json unreadable", str(exc)[:70])
        return report()
    cw = cfg.get("credit_workflow") or {}
    dcc = cw.get("dcc") or {}
    members = [m for m in (dcc.get("members") or [])
               if isinstance(m, dict)
               and (str(m.get("staff_code", "")).strip() or str(m.get("name", "")).strip())]

    if not dcc.get("enabled"):
        bad("the department committee is not enabled",
            "run scripts\\enable_dcc.py --apply")
    elif not members:
        bad("the department committee has no real members",
            "the panel would show blank rows and an empty dropdown. Run "
            "scripts\\name_dcc_members.py")
    else:
        ok("the committee is enabled with real members", "%d" % len(members))
        missing_id = [m for m in members
                      if not str(m.get("id", "") or m.get("member_id", "")).strip()]
        if missing_id:
            bad("%d member(s) carry no id" % len(missing_id),
                "the dropdown keys on it - a vote could not be attributed")
        else:
            ok("every member carries the id the panel keys on", "")
        deps = [m for m in members if m.get("deputy_chair")]
        if dcc.get("chaired_by") and not deps:
            warn("the committee has a chair but no deputy",
                 "if %s is away the committee cannot reach a decision"
                 % dcc.get("chaired_by"))
        elif deps:
            ok("deputy chair(s) named", ", ".join(
                str(m.get("name"))[:18] for m in deps[:2]))

    def resolve_with(votes):
        s = Store({"id": "C1", "status": "referred_to_committee",
                   "committee_kind": "dcc",
                   "analyst": {"code": "KE1300", "name": "Catherine"},
                   "dcc_votes": votes})
        R._lam = lambda: s
        R.lms_dcc_resolve("C1", {}, analyst)
        return s.get("C1")

    V = lambda v, n: {"member_id": "M%d" % n, "member_name": "Member %d" % n, "vote": v}
    try:
        a = resolve_with([V("YES", 1), V("YES", 2), V("YES", 3), V("NO", 4)])
        if a["status"] == "submitted" and a.get("awaiting_credit_analyst"):
            ok("a supported case is released to the bank credit pool", a["status"])
        else:
            bad("a supported case does not reach the credit pool",
                "status=%r awaiting_credit_analyst=%r"
                % (a["status"], a.get("awaiting_credit_analyst")))
        a = resolve_with([V("NO", 1), V("NO", 2), V("YES", 3)])
        if a["status"] == "assigned":
            ok("an opposed case goes back to the analyst", a["status"])
        else:
            bad("an opposed case does not return to the analyst", "status=%r" % a["status"])
        a = resolve_with([V("YES", 1), V("NO", 2)])
        if a["status"] == "assigned":
            ok("a split committee returns the case", "not treated as support")
        else:
            bad("a SPLIT committee released the case",
                "a tie is not a recommendation - status=%r" % a["status"])
    except Exception as exc:
        bad("resolving the committee raised", str(exc)[:90])

    # ── 4. THE JOURNEY ──────────────────────────────────────────────────────
    rule("4. WHAT THE CASE JOURNEY WILL SHOW")
    deal = {
        "id": "J1", "created_at": "2026-08-14T08:00:00",
        "updated_at": "2026-08-14T13:00:00",
        "committee_votes": {"BCC_BRN007": {"KE708": {
            "name": "Maryanne Njeri Chege", "role": "CSM", "staff_code": "KE708",
            "vote": "YES", "at": "2026-08-14T09:00:00"}}},
        "auto_advanced_by": "committee:BCC_BRN007",
        "stage": "Department Credit Analysis",
        "rework_history": [{"reason": "Valuation out of date", "items": [],
                            "by": "KE1300", "by_name": "Catherine",
                            "at": "2026-08-14T10:00:00"}],
        "rework_completed_at": "2026-08-14T11:00:00",
        "rework_completed_by": "Edward Mwenda",
        "dcc_votes": [{"member_id": "M1", "member_name": "Jane Jelagat Atugah",
                       "vote": "YES", "at": "2026-08-14T12:00:00"}],
        "dcc_outcome": {"recommendation": "support",
                        "tally": {"yes": 3, "no": 1, "abstain": 0},
                        "by": "KE1300", "by_name": "Catherine",
                        "at": "2026-08-14T12:30:00"},
    }
    events = {e["event"] for e in _events_from_deal(deal)}
    for label, ev in (("a branch committee vote", "committee_vote"),
                      ("an automatic advance", "auto_advanced"),
                      ("a return for rework", "returned_for_rework"),
                      ("the rework coming back", "rework_completed"),
                      ("a department committee vote", "dcc_vote"),
                      ("the department's decision", "dcc_support")):
        if ev in events:
            ok("the journey records %s" % label, ev)
        else:
            bad("the journey does NOT record %s" % label,
                "%r is missing - that touch point leaves no trace" % ev)
    if VERBOSE:
        print("\n  full journey:")
        for e in _events_from_deal(deal):
            print("     %-22s %s" % (e["event"], (e.get("note") or "")[:52]))

    # ── 5. SEGMENT VISIBILITY ───────────────────────────────────────────────
    rule("5. AN ANALYST SEES ONLY THEIR SEGMENT")
    seg = _analyst_segment(analyst["role"], analyst["staff_code"])
    if seg:
        ok("the analyst's segment resolves", seg)
    else:
        bad("the analyst has NO segment",
            "every gate treats them as unrestricted and they see every case. "
            "Run scripts\\diag_analyst_segment.py --user %s" % analyst["staff_code"])
    for ct, want in (("Individual", "consumer"), ("Consumer", "consumer"),
                     ("Commercial", "commercial"), ("Large Corporate", "cib")):
        got = _app_segment({"client_type": ct})
        if got == want:
            ok("client type %r maps to %s" % (ct, want), "")
        else:
            bad("client type %r maps to %r, expected %r" % (ct, got, want),
                "cases would reach the wrong analyst")

    return report()


def report():
    rule("VERDICT")
    print("  passed  %d" % len(PASS))
    print("  warned  %d" % len(WARN))
    print("  FAILED  %d" % len(FAIL))
    if not FAIL:
        print("\nThe credit path is sound. The release is worth building.")
        if WARN:
            print("The warnings above are worth a look but block nothing.")
        return 0
    print("\nDO NOT RELEASE YET:\n")
    for what, why in FAIL:
        print("   * %s" % what)
        print("     %s" % why)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-6:]:
            print("   %s" % ln[:110])
        sys.exit(1)
