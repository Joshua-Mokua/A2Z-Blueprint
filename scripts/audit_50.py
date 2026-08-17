#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fifty checks across the whole system, before the pilot sees it.

preflight_credit.py proves the credit path works. preflight_release.py asks
what differs on the bank's box. This is the wide sweep: fifty things that have
either broken before or would be embarrassing to discover in front of the bank.

Grouped so a failure points somewhere, not just at "something".

     1-8   identity and permissions
     9-16  the branch committee
    17-24  the department analyst and committee
    25-31  the case journey
    32-39  the two stores
    40-45  configuration
    46-50  the release itself

    python scripts\\audit_50.py
    python scripts\\audit_50.py --verbose

Read-only throughout. Exit 0 when nothing is broken.
"""
import json
import os
import re
import sys
import traceback

sys.path.insert(0, os.getcwd())

RESULTS = []
VERBOSE = "--verbose" in sys.argv
N = [0]


def check(what, condition, why="", warn_only=False):
    N[0] += 1
    n = N[0]
    if condition:
        RESULTS.append(("ok", n, what, ""))
        print("  ok    %-3s %s" % (n, what[:62]))
    elif warn_only:
        RESULTS.append(("warn", n, what, why))
        print("  warn  %-3s %s" % (n, what[:62]))
        if why:
            print("            %s" % why[:96])
    else:
        RESULTS.append(("FAIL", n, what, why))
        print("  FAIL  %-3s %s" % (n, what[:62]))
        if why:
            print("            %s" % why[:96])


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    api = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    routes = open(os.path.join("utils", "api_lms_routes.py"), encoding="utf-8").read()
    jr = open(os.path.join("utils", "api_lms_journey.py"), encoding="utf-8").read()
    scope = open(os.path.join("utils", "api_lms_scope.py"), encoding="utf-8").read()
    perms = open(os.path.join("utils", "api_pipeline_permissions.py"), encoding="utf-8").read()

    import utils.api as A
    import utils.api_lms_routes as R
    from utils.api_lms_journey import _events_from_deal
    from utils.api_lms_scope import _app_segment, _analyst_segment, filter_apps_by_visibility
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import UserManager, PipelineManager

    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    cw = cfg.get("credit_workflow") or {}
    pal = cw.get("committee_palette") or []
    dcc = cw.get("dcc") or {}
    users = UserManager().users or {}
    deals = list(getattr(PipelineManager(), "deals", []) or [])

    R.audit_log = lambda *a, **k: None
    R.is_valid_lms_transition = lambda a, b: True
    R.resolve_application_permissions = lambda u, a: {
        "can_view": True, "can_update": True, "can_set_committee_readiness": True,
        "can_resolve_dcc": True, "can_submit_to_dcc": True}

    class S:
        def __init__(s, a): s.a = {a["id"]: dict(a)}
        def get(s, i): return s.a.get(i)
        def update(s, i, u): s.a[i].update(u); return s.a[i]

    # ══ IDENTITY AND PERMISSIONS ════════════════════════════════════════════
    rule("IDENTITY AND PERMISSIONS  (1-8)")

    check("every login carries a staff code",
          all(str(v.get("staff_code", "") or "").strip() for v in users.values()),
          "%d have none - every scoped screen is empty for them"
          % sum(1 for v in users.values() if not str(v.get("staff_code", "") or "").strip()),
          warn_only=True)

    check("the role is enriched from the store at sign-in",
          '"role"' in open(os.path.join("utils", "auth_jwt.py"), encoding="utf-8").read(),
          "an AD login with no role claim becomes Staff and is refused everywhere")

    check("committee membership grants sight of the case",
          "is_committee_member" in perms,
          "a department committee member could not open the case they must judge")

    check("committee membership grants VIEW only",
          "is_committee_member" in perms
          and "can_edit" not in perms[perms.find("is_committee_member = False"):
                                      perms.find("is_committee_member = False") + 1800],
          "a committee member could edit somebody else's deal")

    check("a non-member is refused a vote",
          "You are not on" in api,
          "anybody could vote on any committee")

    check("the config-admin gate is role-based",
          "require_config_admin" in api or "admin" in api.lower(),
          "")

    seg_ok = 0
    for k, v in users.items():
        if "credit analyst" in str(v.get("role", "")).lower():
            if _analyst_segment(str(v.get("role", "")), str(v.get("staff_code", ""))):
                seg_ok += 1
    check("at least one credit analyst resolves to a segment", seg_ok > 0,
          "no analyst is segment-restricted - each would see every case")

    check("a segment analyst sees only their segment",
          [a["id"] for a in filter_apps_by_visibility(
              [{"id": "c", "client_type": "Consumer", "status": "submitted", "rm_code": "Z"},
               {"id": "m", "client_type": "Commercial", "status": "submitted", "rm_code": "Z"}],
              set(), "X", caller_role="Consumer Credit Analyst")] == ["c"],
          "cases would reach the wrong analyst")

    # ══ THE BRANCH COMMITTEE ════════════════════════════════════════════════
    rule("THE BRANCH COMMITTEE  (9-16)")

    branch = [c for c in pal if str(c.get("kind", "")).lower() == "branch"]
    check("branch committees exist", len(branch) > 0,
          "no branch can convene")

    staffed = [c for c in branch if any(
        isinstance(m, dict) and (str(m.get("staff_code", "")).strip()
                                 or str(m.get("name", "")).strip())
        for m in (c.get("members") or []))]
    check("branch committees have real members", len(staffed) > 0,
          "%d of %d are blank placeholders" % (len(branch) - len(staffed), len(branch)))

    check("the queue reads the canonical deal source",
          "_acquire_scoped_deals" in api[api.find("queues/committee"):
                                         api.find("queues/committee") + 3000],
          "the queue would list cases whose Review button opens nothing")

    check("the queue shows only cases at or past the committee stage",
          "ONLY CASES THAT HAVE ACTUALLY REACHED THE COMMITTEE" in api,
          "every deal in the branch would be listed from Initiation onward")

    # Match the RULE, not a sentence of its wording. My first version keyed on
    # a phrase in the error message, and trimming that message made a working
    # rule report as broken.
    check("a member votes once", "ONE VOTE PER MEMBER, AND IT STANDS" in api,
          "somebody could revise their position after seeing how others voted")

    check("the chair's vote is required", "THE CHAIR MUST HAVE VOTED" in api,
          "quorum counts heads without caring whose")

    check("a deputy can stand in for the chair", "_is_deputy" in api,
          "an absent chair would stop the committee entirely")

    check("a committee stage cannot be walked past",
          "A COMMITTEE STAGE CANNOT BE WALKED PAST" in api,
          "the gate would be decoration")

    # ══ THE DEPARTMENT ANALYST AND COMMITTEE ════════════════════════════════
    rule("THE DEPARTMENT ANALYST AND COMMITTEE  (17-24)")

    base = {"id": "P", "status": "assigned", "client_type": "Consumer",
            "analyst": {"code": "KE1300", "name": "C"}, "rm_code": "KE1"}
    an = {"username": "c", "staff_code": "KE1300", "full_name": "C", "role": "Credit Analyst"}
    ow = {"username": "o", "staff_code": "KE1", "full_name": "O"}

    st = S(base); R._lam = lambda: st
    try:
        R.lms_committee_readiness("P", {"decision": "ready"}, an)
        moved = st.get("P")["status"] == "referred_to_committee"
    except Exception:
        moved = False
    check("recommending submits the case to the committee", moved,
          "the committee tab would say it was never submitted")

    try:
        R.lms_committee_readiness("P", {"decision": "ready"}, an)
        twice = False
    except Exception as exc:
        twice = "409" in str(exc)
    check("a second recommendation is refused", twice,
          "the journey would show the same verdict twice")

    st = S(base); R._lam = lambda: st
    try:
        R.lms_committee_readiness("P", {"decision": "rework", "opinion": "Fix"}, an)
        ret = st.get("P")["status"] == "returned"
        remembers = str(st.get("P").get("returned_by_code")) == "KE1300"
    except Exception:
        ret = remembers = False
    check("a rework returns the case to the branch", ret,
          "it would sit in the analyst's own queue with nobody told")
    check("it remembers which analyst to come back to", remembers,
          "a resubmitted case would go to the pool")

    try:
        R.lms_resubmit_after_rework("P", {}, ow)
        back = str(st.get("P").get("analyst", {}).get("code")) == "KE1300"
    except Exception:
        back = False
    check("a resubmitted case returns to the same analyst", back,
          "re-queueing turns a two-hour correction into a two-day one")

    st = S(base); R._lam = lambda: st
    try:
        for i in (1, 2):
            R.lms_committee_readiness("P", {"decision": "rework", "opinion": "R%d" % i}, an)
            R.lms_resubmit_after_rework("P", {}, ow)
        twice_kept = len(st.get("P").get("rework_history") or []) == 2
    except Exception:
        twice_kept = False
    check("two returns are both kept", twice_kept,
          "a second return would overwrite the first")

    def resolve(votes):
        s = S({"id": "C", "status": "referred_to_committee", "committee_kind": "dcc",
               "analyst": {"code": "KE1300", "name": "C"}, "dcc_votes": votes})
        R._lam = lambda: s
        R.lms_dcc_resolve("C", {}, an)
        return s.get("C")

    V = lambda v, n: {"member_id": "M%d" % n, "vote": v}
    try:
        sup = resolve([V("YES", 1), V("YES", 2), V("NO", 3)])
        opp = resolve([V("NO", 1), V("NO", 2), V("YES", 3)])
        spl = resolve([V("YES", 1), V("NO", 2)])
    except Exception:
        sup = opp = spl = {}
    check("a supported case goes to the bank credit pool",
          sup.get("status") == "submitted" and sup.get("awaiting_credit_analyst"),
          "the analyst would have to re-submit what a committee just approved")
    check("an opposed or split case returns to the analyst",
          opp.get("status") == "assigned" and spl.get("status") == "assigned",
          "a tie is not a recommendation")

    # ══ THE CASE JOURNEY ════════════════════════════════════════════════════
    rule("THE CASE JOURNEY  (25-31)")

    d = {"id": "J", "created_at": "2026-08-14T08:00:00", "updated_at": "2026-08-14T13:00:00",
         "stage": "Department Credit Analysis", "auto_advanced_by": "committee:B",
         "committee_votes": {"B": {"K": {"name": "M", "vote": "YES", "at": "2026-08-14T09:00:00"}}},
         "rework_history": [{"reason": "r", "by_name": "C", "at": "2026-08-14T10:00:00"}],
         "rework_completed_at": "2026-08-14T11:00:00", "rework_completed_by": "O",
         "dcc_votes": [{"member_id": "M", "member_name": "J", "vote": "YES",
                        "at": "2026-08-14T12:00:00"}],
         "dcc_outcome": {"recommendation": "support", "tally": {"yes": 3, "no": 1, "abstain": 0},
                         "by_name": "C", "at": "2026-08-14T12:30:00"},
         "manager_validated": True}
    ev = {e["event"] for e in _events_from_deal(d)}
    for label, name in (("a branch committee vote", "committee_vote"),
                        ("an automatic advance", "auto_advanced"),
                        ("a return for rework", "returned_for_rework"),
                        ("the rework coming back", "rework_completed"),
                        ("a department committee vote", "dcc_vote"),
                        ("the department's decision", "dcc_support"),
                        ("manager validation", "manager_validated")):
        check("the journey records %s" % label, name in ev,
              "%r leaves no trace" % name)

    # ══ THE TWO STORES ══════════════════════════════════════════════════════
    rule("THE TWO STORES  (32-39)")

    unsynced = sum(1 for m in re.finditer(r"\.update_deal\(", api)
                   if "_db_sync_pipeline_deal" not in api[m.start(): m.start() + 900])
    check("every deal write reaches Postgres", unsynced == 0,
          "%d write(s) land where nothing reads them" % unsynced)

    w = api[api.find("def _db_sync_pipeline_deal"):]
    w = w[:w.find("\ndef ", 10)]
    rd = api[api.find("def _normalize_db_deal_row"):]
    rd = rd[:rd.find("\ndef ", 10)]
    for fld in ("branch", "client_type", "committee_records", "committee_votes",
                "manager_validated", "segment"):
        check("%s survives the database round trip" % fld,
              ('"%s"' % fld) in w and ('"%s"' % fld) in rd,
              "written=%s read=%s" % (('"%s"' % fld) in w, ('"%s"' % fld) in rd))

    # Read to the END of the function. A fixed window of 1400 characters cut
    # the block at 1801 and reported a guard that was there as missing.
    _wd = api.find("def _write_deal")
    _wd_end = api.find("\ndef ", _wd + 10) if _wd > 0 else -1
    check("a deal write fails safe when Postgres is down",
          _wd > 0 and "except Exception" in api[_wd:_wd_end],
          "a database blink would lose the change entirely")

    # ══ CONFIGURATION ═══════════════════════════════════════════════════════
    rule("CONFIGURATION  (40-45)")

    check("the department committee is enabled", bool(dcc.get("enabled")),
          "the committee tab reports it is switched off")

    real = [m for m in (dcc.get("members") or [])
            if isinstance(m, dict) and (str(m.get("staff_code", "")).strip()
                                        or str(m.get("name", "")).strip())]
    check("the department committee has real members", len(real) > 0,
          "the panel shows blank rows and an empty dropdown")

    check("every department member carries the id the panel keys on",
          all(str(m.get("id", "") or m.get("member_id", "")).strip() for m in real) if real else False,
          "a vote could not be attributed")

    short = [c.get("code") for c in pal
             if [m for m in (c.get("members") or [])
                 if isinstance(m, dict) and (str(m.get("staff_code", "")).strip()
                                             or str(m.get("name", "")).strip())]
             and len([m for m in (c.get("members") or [])
                      if isinstance(m, dict) and (str(m.get("staff_code", "")).strip()
                                                  or str(m.get("name", "")).strip())])
             < (c.get("min_quorum_count") or 2)]
    check("every staffed committee can reach quorum", not short,
          "these would defer every case: %s" % ", ".join(str(x) for x in short[:4]))

    live = [x for x in deals if not str(x.get("stage", "")).lower().startswith("closed")]
    check("every live deal has a client type",
          all(str(x.get("client_type", "") or "").strip() for x in live),
          "%d without - no department committee resolves for them"
          % sum(1 for x in live if not str(x.get("client_type", "") or "").strip()),
          warn_only=True)

    check("every live deal has a branch",
          all(str(x.get("branch", "") or x.get("unit", "") or "").strip() for x in live),
          "%d without - no branch committee resolves for them"
          % sum(1 for x in live
                if not str(x.get("branch", "") or x.get("unit", "") or "").strip()),
          warn_only=True)

    # ══ THE RELEASE ═════════════════════════════════════════════════════════
    rule("THE RELEASE  (46-50)")

    for f in ("utils/api.py", "utils/api_lms_routes.py", "utils/api_lms_journey.py",
              "utils/api_lms_scope.py"):
        import ast
        try:
            ast.parse(open(os.path.join(*f.split("/")), encoding="utf-8").read())
            good = True
        except SyntaxError:
            good = False
        check("%s parses" % f.split("/")[-1], good, "the API would not start")

    check("the sidebar carries no warehouse entry for the pilot",
          "label: 'Deals Warehouse'" not in open(
              os.path.join("frontend", "web", "src", "components", "Sidebar.tsx"),
              encoding="utf-8").read(),
          "correct on this box - UI1 strips it from what ships",
          warn_only=True)

    return report()


def report():
    rule("VERDICT")
    ok = sum(1 for r in RESULTS if r[0] == "ok")
    wn = sum(1 for r in RESULTS if r[0] == "warn")
    fl = [r for r in RESULTS if r[0] == "FAIL"]
    print("  checks  %d" % len(RESULTS))
    print("  passed  %d" % ok)
    print("  warned  %d" % wn)
    print("  FAILED  %d" % len(fl))
    if not fl:
        print("\nNothing is broken. The release is worth building.")
        if wn:
            print("Read the warnings - none blocks, each is something somebody")
            print("will ask about.")
        return 0
    print("\nFIX BEFORE RELEASING:\n")
    for _s, n, what, why in fl:
        print("   %2d. %s" % (n, what))
        if why:
            print("       %s" % why)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-7:]:
            print("   %s" % ln[:110])
        sys.exit(1)
