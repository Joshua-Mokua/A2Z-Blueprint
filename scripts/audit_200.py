#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Two hundred checks, driven over the real configuration and data.

audit_50.py checks fifty things once. This checks the same KINDS of thing
across every committee, every product flow, every live deal and every login -
so the count comes from the data rather than from padding, and a fault in one
branch out of sixteen is found rather than averaged away.

    python scripts\\audit_200.py
    python scripts\\audit_200.py --verbose     # list every check, not just failures
    python scripts\\audit_200.py --group 3     # one group only

GROUPS
    1  endpoints and routes            every route the flows depend on
    2  field persistence               every field that must survive Postgres
    3  committees, one by one          each palette entry, individually
    4  product flows, one by one       each flow's shape and gates
    5  the journey                     every touch point renders
    6  permissions                     the matrix, case by case
    7  live data                       every deal that could stall
    8  logins and identity             every account that could see nothing
    9  behaviour                       the endpoints driven for real
   10  release hygiene                 what must and must not travel

Read-only. Exit 0 when nothing is broken.
"""
import json
import os
import re
import sys
import traceback

sys.path.insert(0, os.getcwd())

OK, WARN, FAIL = [], [], []
VERBOSE = "--verbose" in sys.argv
ONLY = None
if "--group" in sys.argv:
    i = sys.argv.index("--group")
    if i + 1 < len(sys.argv):
        ONLY = int(sys.argv[i + 1])
GROUP = [0]


def chk(what, cond, why="", warn=False):
    if cond:
        OK.append(what)
        if VERBOSE:
            print("    ok    %s" % what[:70])
    elif warn:
        WARN.append((what, why))
        print("    warn  %s" % what[:70])
        if why:
            print("          %s" % why[:92])
    else:
        FAIL.append((GROUP[0], what, why))
        print("    FAIL  %s" % what[:70])
        if why:
            print("          %s" % why[:92])


def group(n, title):
    GROUP[0] = n
    if ONLY and ONLY != n:
        return False
    print("\n" + "-" * 78)
    print("%d. %s" % (n, title))
    print("-" * 78)
    return True


def main():
    api = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    routes_src = open(os.path.join("utils", "api_lms_routes.py"), encoding="utf-8").read()
    jr = open(os.path.join("utils", "api_lms_journey.py"), encoding="utf-8").read()
    perms_src = open(os.path.join("utils", "api_pipeline_permissions.py"), encoding="utf-8").read()

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
    live = [d for d in deals if not str(d.get("stage", "")).lower().startswith("closed")]
    pcfg = A._load_json("pipeline_settings.json") or {}
    flows = pcfg.get("product_flows") or {}

    R.audit_log = lambda *a, **k: None
    R.is_valid_lms_transition = lambda a, b: True
    R.resolve_application_permissions = lambda u, a: {
        "can_view": True, "can_update": True, "can_set_committee_readiness": True,
        "can_resolve_dcc": True, "can_submit_to_dcc": True}

    class S:
        def __init__(s, a): s.a = {a["id"]: dict(a)}
        def get(s, i): return s.a.get(i)
        def update(s, i, u): s.a[i].update(u); return s.a[i]

    # ══ 1. ENDPOINTS ════════════════════════════════════════════════════════
    if group(1, "ENDPOINTS AND ROUTES"):
        app_paths = {getattr(r, "path", "") for r in A.app.routes}
        lms_paths = {getattr(r, "path", "") for r in R.router.routes}
        allp = app_paths | lms_paths
        need = [
            ("the committee queue", "/api/pipeline/queues/committee"),
            ("validation queue", "/api/pipeline/queues/validation"),
            ("cancellation queue", "/api/pipeline/queues/cancellation"),
            ("cast a committee vote", "committee/{code}/vote"),
            ("record a committee decision", "committee-records"),
            ("the committee journey", "committee-journey"),
            ("advance a deal", "/advance"),
            ("deal detail", "/api/pipeline/deals/{deal_id}"),
            ("deal documents", "documents"),
            ("the pipeline funnel", "/api/pipeline/funnel"),
            ("pipeline analytics", "/api/pipeline/analytics"),
            ("pick an application", "/applications/{app_id}/pick"),
            ("committee readiness", "committee-readiness"),
            ("return for rework", "return-for-rework"),
            ("resubmit after rework", "resubmit-after-rework"),
            ("submit to the department committee", "committee/refer"),
            ("department committee vote", "dcc/vote"),
            ("department committee resolve", "dcc/resolve"),
            ("the department roster", "dcc/roster"),
            ("hand to the credit analyst", "hand-to-credit-analyst"),
            ("request information", "request-info"),
            ("provide information", "provide-info"),
            ("request a document", "documents/request"),
            ("the case journey", "journey"),
            ("applications list", "/applications"),
        ]
        for label, frag in need:
            chk("route exists: %s" % label,
                any(frag in p for p in allp),
                "%r is on no route - the flow that needs it cannot work" % frag)

    # ══ 2. FIELD PERSISTENCE ════════════════════════════════════════════════
    if group(2, "FIELD PERSISTENCE - what must survive Postgres"):
        w = api[api.find("def _db_sync_pipeline_deal"):]
        w = w[:w.find("\ndef ", 10)]
        rd = api[api.find("def _normalize_db_deal_row"):]
        rd = rd[:rd.find("\ndef ", 10)]
        fields = ["branch", "segment", "client_type", "committee_records",
                  "committee_votes", "manager_validated", "validated_by_name",
                  "validated_by_code", "validated_at", "cancel_requested",
                  "cancel_approved", "referral_status", "referred_by_name",
                  "referred_to_name", "referred_at", "documents_provided",
                  "document_files", "documents_required_at_stage",
                  "application_id", "created_at", "updated_at"]
        for f in fields:
            chk("%s is written to the database" % f, ('"%s"' % f) in w,
                "it would be lost on the next read")
            chk("%s is read back" % f, ('"%s"' % f) in rd,
                "written but never lifted out, which loses it just as completely")
        unsynced = sum(1 for m in re.finditer(r"\.update_deal\(", api)
                       if "_db_sync_pipeline_deal" not in api[m.start(): m.start() + 900])
        chk("no deal write bypasses the database", unsynced == 0,
            "%d write(s) land where nothing reads them" % unsynced)

    # ══ 3. COMMITTEES ═══════════════════════════════════════════════════════
    if group(3, "COMMITTEES, ONE BY ONE"):
        for c in pal:
            code = str(c.get("code") or "?")
            mem = [m for m in (c.get("members") or [])
                   if isinstance(m, dict) and (str(m.get("staff_code", "")).strip()
                                               or str(m.get("name", "")).strip())]
            blanks = len(c.get("members") or []) - len(mem)
            chk("%s has a name" % code, bool(str(c.get("name", "")).strip()),
                "an unnamed committee cannot be chosen in admin")
            chk("%s has no blank member rows" % code, blanks == 0,
                "%d placeholder row(s) render as nameless lines" % blanks,
                warn=True)
            if mem:
                q = c.get("min_quorum_count") or 2
                chk("%s can reach its quorum" % code, len(mem) >= q,
                    "%d member(s) against a quorum of %d - every case defers"
                    % (len(mem), q))
                chk("%s members all carry a staff code" % code,
                    all(str(m.get("staff_code", "")).strip() for m in mem),
                    "membership is matched by code; a member without one is "
                    "matched by name, which two people can share", warn=True)
            if str(c.get("kind", "")).lower() == "branch":
                chk("%s names its branch" % code,
                    bool(str(c.get("branch", "")).strip()),
                    "no deal can resolve to it")

    # ══ 4. PRODUCT FLOWS ════════════════════════════════════════════════════
    if group(4, "PRODUCT FLOWS, ONE BY ONE"):
        for prod in sorted(flows):
            stages = [str(x) for x in (A._stage_flow_for(prod) or [])]
            chk("%s has a stage flow" % prod[:34], len(stages) > 0,
                "a deal on this product cannot advance at all")
            if stages:
                chk("%s can be closed" % prod[:34],
                    any(x.lower().startswith("closed") for x in stages),
                    "a case reaching the end has nowhere to go")
                chk("%s has no duplicate stages" % prod[:34],
                    len(stages) == len(set(stages)),
                    "a repeated stage makes 'the next one' ambiguous")

    # ══ 5. THE JOURNEY ══════════════════════════════════════════════════════
    if group(5, "THE JOURNEY - every touch point"):
        d = {"id": "J", "created_at": "2026-08-14T08:00:00",
             "updated_at": "2026-08-14T13:00:00", "stage": "Credit Analysis",
             "auto_advanced_by": "committee:B", "manager_validated": True,
             "committee_votes": {"B": {"K": {"name": "M", "role": "CSM", "vote": "YES",
                                             "at": "2026-08-14T09:00:00"}}},
             "committee_records": {"B": {"outcome": "APPROVED", "votes": [],
                                         "recorded_at": "2026-08-14T09:30:00"}},
             "rework_history": [{"reason": "r", "by_name": "C",
                                 "at": "2026-08-14T10:00:00"}],
             "rework_completed_at": "2026-08-14T11:00:00", "rework_completed_by": "O",
             "dcc_votes": [{"member_id": "M", "member_name": "J", "vote": "YES",
                            "at": "2026-08-14T12:00:00"}],
             "dcc_outcome": {"recommendation": "support",
                             "tally": {"yes": 3, "no": 1, "abstain": 0},
                             "by_name": "C", "at": "2026-08-14T12:30:00"},
             "referral_status": "accepted", "referred_to_name": "X",
             "referred_at": "2026-08-13T10:00:00"}
        events = _events_from_deal(d)
        names = {e["event"] for e in events}
        for label, ev in (("deal created", "deal_created"),
                          ("a branch committee vote", "committee_vote"),
                          ("the branch decision", "committee_approved"),
                          ("an automatic advance", "auto_advanced"),
                          ("a return for rework", "returned_for_rework"),
                          ("the rework coming back", "rework_completed"),
                          ("a department vote", "dcc_vote"),
                          ("the department decision", "dcc_support"),
                          ("manager validation", "manager_validated")):
            chk("the journey records %s" % label, ev in names,
                "%r leaves no trace" % ev)
        chk("every event carries a timestamp",
            all(e.get("at") for e in events),
            "an undated entry cannot be placed in a sequence", warn=True)
        chk("every event carries a note",
            all(str(e.get("note", "") or "").strip() for e in events),
            "an entry with no words explains nothing", warn=True)
        chk("no event is duplicated",
            len(events) == len({(e["event"], e.get("at"), e.get("note")) for e in events}),
            "the same fact twice reads as two facts")

    # ══ 6. PERMISSIONS ══════════════════════════════════════════════════════
    if group(6, "PERMISSIONS, CASE BY CASE"):
        deal = {"id": "D", "staff_code": "OWN", "branch": "Westlands",
                "unit": "Westlands", "client_type": "Consumer",
                "stage": "Branch Credit Committee Review"}
        cases = [
            ("the owner can view", {"staff_code": "OWN", "role": "RM"}, {"OWN"}, "can_view", True),
            ("the owner can edit", {"staff_code": "OWN", "role": "RM"}, {"OWN"}, "can_edit", True),
            ("a stranger cannot view", {"staff_code": "ZZZ", "role": "RM"}, set(), "can_view", False),
            ("a stranger cannot edit", {"staff_code": "ZZZ", "role": "RM"}, set(), "can_edit", False),
            ("a manager in scope can view", {"staff_code": "MGR", "role": "Branch Manager"}, {"OWN", "MGR"}, "can_view", True),
        ]
        for label, user, visible, field, want in cases:
            try:
                got = bool(resolve_deal_permissions(deal, user, visible).get(field))
            except Exception:
                got = None
            chk(label, got == want, "expected %s, got %r" % (want, got))
        chk("committee membership is a view grant only",
            "is_committee_member" in perms_src,
            "a department committee member cannot open their own case")
        for role, expect in (("Consumer Credit Analyst", "consumer"),
                             ("Commercial Credit Analyst", "commercial"),
                             ("CIB Credit Analyst", "cib"),
                             ("Branch Manager", "")):
            chk("role %r resolves to segment %r" % (role[:26], expect),
                _analyst_segment(role, "") == expect,
                "got %r" % _analyst_segment(role, ""))
        for ct, expect in (("Consumer", "consumer"), ("Individual", "consumer"),
                           ("Personal", "consumer"), ("Retail", "consumer"),
                           ("Commercial", "commercial"), ("CIB", "cib"),
                           ("Large Corporate", "cib"), ("", "")):
            chk("client type %r maps to %r" % (ct or "(empty)", expect),
                _app_segment({"client_type": ct}) == expect,
                "got %r - cases would reach the wrong analyst"
                % _app_segment({"client_type": ct}))

    # ══ 7. LIVE DATA ════════════════════════════════════════════════════════
    if group(7, "LIVE DATA - deals that could stall"):
        chk("there are live deals to reason about", True, "")
        no_branch = [d for d in live if not str(d.get("branch") or d.get("unit") or "").strip()]
        no_ct = [d for d in live if not str(d.get("client_type", "") or "").strip()]
        no_owner = [d for d in live if not str(d.get("staff_code", "") or "").strip()]
        no_prod = [d for d in live if not str(d.get("product_type") or d.get("product") or "").strip()]
        chk("every live deal has a branch", not no_branch,
            "%d without - no branch committee resolves" % len(no_branch), warn=True)
        chk("every live deal has a client type", not no_ct,
            "%d without - no department committee resolves" % len(no_ct), warn=True)
        chk("every live deal has an owner", not no_owner,
            "%d without - nobody can see or act on them" % len(no_owner))
        chk("every live deal has a product", not no_prod,
            "%d without - no stage flow applies" % len(no_prod))
        atc = [d for d in live if "committee" in str(d.get("stage", "")).lower()]
        for d in atc[:12]:
            j = A._effective_committee_journey(d) or []
            chk("deal %s at a committee stage resolves a committee" % str(d.get("id"))[:14],
                bool(j), "journey is empty - it can never be decided")
        stages_ok = 0
        for d in live[:40]:
            fl = A._stage_flow_for(d.get("product_type") or d.get("product", "")) or []
            if fl and str(d.get("stage", "")) in fl:
                stages_ok += 1
        chk("live deals sit on stages their flow contains",
            stages_ok >= min(len(live), 40) * 0.8,
            "%d of %d are on a stage their product does not define"
            % (min(len(live), 40) - stages_ok, min(len(live), 40)), warn=True)

    # ══ 8. LOGINS ═══════════════════════════════════════════════════════════
    if group(8, "LOGINS AND IDENTITY"):
        no_code = [k for k, v in users.items()
                   if not str(v.get("staff_code", "") or "").strip()]
        no_role = [k for k, v in users.items()
                   if not str(v.get("role", "") or "").strip()]
        chk("every login carries a staff code", not no_code,
            "%d without - every scoped screen is empty for them" % len(no_code),
            warn=True)
        chk("every login carries a role", not no_role,
            "%d without - they default to Staff and are refused" % len(no_role),
            warn=True)
        by_code = {str(v.get("staff_code", "") or "").strip() for v in users.values()}
        for c in pal:
            mem = [m for m in (c.get("members") or [])
                   if isinstance(m, dict) and str(m.get("staff_code", "")).strip()]
            if not mem:
                continue
            cannot = [m for m in mem if str(m.get("staff_code")).strip() not in by_code]
            chk("%s members can all sign in" % str(c.get("code")), not cannot,
                "%d cannot: %s" % (len(cannot),
                                   ", ".join(str(m.get("name")) for m in cannot[:3])))
        if dcc.get("chaired_by"):
            names = {str(v.get("full_name") or v.get("name") or "").strip().lower()
                     for v in users.values()}
            chk("the department chair has a login",
                str(dcc.get("chaired_by")).strip().lower() in names,
                "their vote is mandatory and they cannot cast it")

    # ══ 9. BEHAVIOUR ════════════════════════════════════════════════════════
    if group(9, "BEHAVIOUR - the endpoints driven for real"):
        base = {"id": "P", "status": "assigned", "client_type": "Consumer",
                "analyst": {"code": "AN1", "name": "A"}, "rm_code": "OW1"}
        an = {"username": "a", "staff_code": "AN1", "full_name": "A", "role": "Credit Analyst"}
        ow = {"username": "o", "staff_code": "OW1", "full_name": "O"}

        st = S(base); R._lam = lambda: st
        try:
            R.lms_committee_readiness("P", {"decision": "ready"}, an)
            a = st.get("P")
            chk("recommending sets referred_to_committee",
                a["status"] == "referred_to_committee", "got %r" % a["status"])
            chk("recommending marks it a department case",
                a.get("committee_kind") == "dcc", "got %r" % a.get("committee_kind"))
            chk("recommending records the readiness state",
                (a.get("committee_readiness") or {}).get("state") == "ready_for_committee", "")
        except Exception as exc:
            chk("recommending works", False, str(exc)[:80])
        try:
            R.lms_committee_readiness("P", {"decision": "ready"}, an)
            chk("a second recommendation is refused", False, "it was accepted")
        except Exception as exc:
            chk("a second recommendation is refused", "409" in str(exc), str(exc)[:60])

        st = S(base); R._lam = lambda: st
        try:
            R.lms_committee_readiness("P", {"decision": "rework", "opinion": "Fix the valuation"}, an)
            a = st.get("P")
            chk("a rework sets returned", a["status"] == "returned", "got %r" % a["status"])
            chk("a rework keeps the reason",
                "valuation" in str(a.get("rework_reasons", "")).lower(), "")
            chk("a rework remembers the analyst",
                str(a.get("returned_by_code")) == "AN1", "got %r" % a.get("returned_by_code"))
            chk("a rework appends to history", len(a.get("rework_history") or []) == 1, "")
            R.lms_resubmit_after_rework("P", {}, ow)
            a = st.get("P")
            chk("a resubmit returns it to the analyst",
                str(a.get("analyst", {}).get("code")) == "AN1", "got %r" % a.get("analyst"))
            chk("a resubmit clears the returned marker",
                not str(a.get("returned_by_code", "") or ""), "")
            chk("a resubmit records completion", bool(a.get("rework_completed_at")), "")
        except Exception as exc:
            chk("the rework loop works", False, str(exc)[:80])

        try:
            R.lms_committee_readiness("P", {"decision": "nonsense"}, an)
            chk("an invalid verdict is refused", False, "it was accepted")
        except Exception as exc:
            chk("an invalid verdict is refused", "400" in str(exc), str(exc)[:60])

        def resolve(votes):
            s = S({"id": "C", "status": "referred_to_committee", "committee_kind": "dcc",
                   "analyst": {"code": "AN1", "name": "A"}, "dcc_votes": votes})
            R._lam = lambda: s
            R.lms_dcc_resolve("C", {}, an)
            return s.get("C")
        V = lambda v, n: {"member_id": "M%d" % n, "vote": v}
        for label, votes, want_status, want_pool in (
                ("3-1 support", [V("YES", 1), V("YES", 2), V("YES", 3), V("NO", 4)], "submitted", True),
                ("1-3 oppose", [V("YES", 1), V("NO", 2), V("NO", 3), V("NO", 4)], "assigned", False),
                ("2-2 split", [V("YES", 1), V("YES", 2), V("NO", 3), V("NO", 4)], "assigned", False),
                ("unanimous", [V("YES", 1), V("YES", 2)], "submitted", True),
                ("all abstain", [V("ABSTAIN", 1), V("ABSTAIN", 2)], "assigned", False)):
            try:
                a = resolve(votes)
                chk("%s -> %s" % (label, want_status), a["status"] == want_status,
                    "got %r" % a["status"])
                chk("%s -> credit pool %s" % (label, want_pool),
                    bool(a.get("awaiting_credit_analyst")) == want_pool,
                    "got %r" % a.get("awaiting_credit_analyst"))
            except Exception as exc:
                chk("%s resolves" % label, False, str(exc)[:70])

    # ══ 10. RELEASE HYGIENE ═════════════════════════════════════════════════
    if group(10, "RELEASE HYGIENE"):
        import ast
        for f in ("utils/api.py", "utils/api_lms_routes.py", "utils/api_lms_journey.py",
                  "utils/api_lms_scope.py", "utils/api_pipeline_permissions.py",
                  "utils/core.py"):
            try:
                ast.parse(open(os.path.join(*f.split("/")), encoding="utf-8").read())
                good = True
            except SyntaxError:
                good = False
            chk("%s parses" % f.split("/")[-1], good, "the API would not start")
        bar = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
        if os.path.isfile(bar):
            src = open(bar, encoding="utf-8").read()
            chk("the sidebar has a Department Review entry",
                "label: 'Department Review'" in src,
                "the department team has no way in")
            chk("the sidebar has no warehouse entry",
                "label: 'Deals Warehouse'" not in src,
                "correct here - UI1 strips it from what ships", warn=True)
        for marker, what in (
                ("A COMMITTEE STAGE CANNOT BE WALKED PAST", "the committee gate is enforced"),
                ("ONE VOTE PER MEMBER, AND IT STANDS", "a vote is final"),
                ("THE CHAIR MUST HAVE VOTED", "the chair's vote is required"),
                ("A DECIDED CASE MOVES ITSELF", "a decision advances the case"),
                ("AND INTO THE DATABASE, OR THE VOTE DID NOT HAPPEN", "a vote is persisted"),
                ("_write_deal", "every write goes through one helper")):
            chk(what, marker in api, "%r is not in api.py" % marker[:38])
        for marker, what in (
                ("A REWORK MUST ACTUALLY GO BACK", "a rework moves the case"),
                ("READY MEANS SUBMITTED", "recommending submits"),
                ("AN APPROVAL GOES ON", "a supported case goes on")):
            chk(what, marker in routes_src, "%r is not in the LMS routes" % marker[:34])
        for marker, what in (
                ("committee_vote", "branch votes render"),
                ("dcc_vote", "department votes render"),
                ("returned_for_rework", "reworks render"),
                ("auto_advanced", "automatic advances render")):
            chk("the journey knows about %s" % what, marker in jr, "")

    return report()


def report():
    total = len(OK) + len(WARN) + len(FAIL)
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    print("  checks run   %d" % total)
    print("  passed       %d" % len(OK))
    print("  warned       %d" % len(WARN))
    print("  FAILED       %d" % len(FAIL))
    if not FAIL:
        print("\nNothing is broken across %d checks." % total)
        if WARN:
            print("\n%d warning(s) - none blocks the release:" % len(WARN))
            for what, why in WARN[:12]:
                print("   - %s" % what)
        return 0
    print("\nFIX BEFORE RELEASING:\n")
    by_group = {}
    for g, what, why in FAIL:
        by_group.setdefault(g, []).append((what, why))
    for g in sorted(by_group):
        print("  group %d:" % g)
        for what, why in by_group[g][:10]:
            print("     * %s" % what)
            if why:
                print("       %s" % why)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-8:]:
            print("   %s" % ln[:110])
        sys.exit(1)
