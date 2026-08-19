#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Rehearse the Business Credit Committee, all the way through. READ ONLY.

RULING (2026-08-18): "this ought to be the carefully created committee and
should work well, since it is directly involving the MD. I wouldn't wish a show
like the one we had at Eldoret to replay before the MD - we need to take time
and ensure we get this very accurate and right."

Eldoret failed on a thing no test asked: the chair sat in `chaired_by` and not
on the roster, so the vote the rules demanded could never be cast. Everything
else was correct, and it did not matter.

So this asks, of the real config and the real logins, the questions that would
have caught it - and then DRIVES THE WHOLE PATH, because the Eldoret lesson was
that testing each gate is not the same as walking the case.

    python scripts\\rehearse_bcc.py
    python scripts\\rehearse_bcc.py --committee B4

Nothing is written. Exit 0 when the committee could genuinely sit.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

FAIL, WARN, OK = [], [], []


def ok(w):
    OK.append(w)
    print("  ok    %s" % w[:70])


def bad(w, why=""):
    FAIL.append((w, why))
    print("  FAIL  %s" % w[:70])
    if why:
        print("        %s" % why[:88])


def warn(w, why=""):
    WARN.append((w, why))
    print("  warn  %s" % w[:70])
    if why:
        print("        %s" % why[:88])


def main():
    code = "B4"
    if "--committee" in sys.argv:
        i = sys.argv.index("--committee")
        if i + 1 < len(sys.argv):
            code = sys.argv[i + 1].strip().upper()

    import utils.api_lms_routes as R
    from utils.core import UserManager

    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
    c = next((x for x in pal if str(x.get("code")) == code), None)
    if not c:
        print("ABORT: no committee %r in the palette." % code)
        return 1

    users = UserManager().users or {}
    by_code, by_name = {}, {}
    for k, v in users.items():
        sc = str(v.get("staff_code", "") or "").strip()
        fn = str(v.get("full_name", "") or "").strip().lower()
        if sc:
            by_code[sc] = (k, v)
        if fn:
            by_name[fn] = (k, v)

    members = [m for m in (c.get("members") or []) if isinstance(m, dict)
               and (str(m.get("staff_code", "")).strip() or str(m.get("name", "")).strip())]
    chair = str(c.get("chaired_by", "") or "").strip()
    chair_code = str(c.get("chair_staff_code", "") or "").strip()
    quorum = c.get("min_quorum_count") or 2

    print("=" * 78)
    print("%s  —  %s" % (code, c.get("name")))
    print("=" * 78)
    print("  chair   %s%s" % (chair or "*** NOBODY ***",
                              " (%s)" % chair_code if chair_code else ""))
    print("  quorum  %d" % quorum)
    print("  members %d\n" % len(members))
    for m in members:
        mc = str(m.get("staff_code", "") or "")
        lg = by_code.get(mc) or by_name.get(str(m.get("name", "")).strip().lower())
        print("     %-10s %-30s %-28s %s"
              % (mc or "—", str(m.get("name"))[:30], str(m.get("role"))[:28],
                 "can sign in" if lg else "*** NO LOGIN ***"))

    print("\n" + "-" * 78)
    print("1. COULD IT SIT AT ALL")
    print("-" * 78)

    if not members:
        bad("somebody sits on it", "a case sent here is invisible to everyone")
        return report()
    ok("%d member(s) on the roster" % len(members))

    # THE ELDORET CHECK.
    seated = any((chair_code and str(m.get("staff_code", "")).strip() == chair_code)
                 or str(m.get("name", "")).strip().lower() == chair.lower()
                 for m in members)
    if chair and not seated:
        bad("the chair sits on their own committee",
            "%s is in chaired_by and not on the roster - their MANDATORY vote "
            "can never be cast. THIS IS THE ELDORET FAULT." % chair)
    elif chair:
        ok("the chair sits on their own roster (%s)" % chair)
    else:
        bad("a chair is named", "with no chair nothing requires a decision")

    can_login = [m for m in members
                 if by_code.get(str(m.get("staff_code", "")).strip())
                 or by_name.get(str(m.get("name", "")).strip().lower())]
    if len(can_login) < len(members):
        cannot = [str(m.get("name")) for m in members if m not in can_login]
        bad("every member can sign in",
            "%d cannot: %s" % (len(members) - len(can_login), ", ".join(cannot[:4])))
    else:
        ok("every member can sign in")

    if len(can_login) < quorum:
        bad("quorum is reachable by people who can sign in",
            "%d able against a quorum of %d" % (len(can_login), quorum))
    else:
        ok("quorum of %d is reachable (%d can sign in)" % (quorum, len(can_login)))

    deputies = [m for m in members if m.get("deputy_chair")]
    if not deputies:
        warn("no deputy chair named",
             "if %s is away the committee cannot complete a decision"
             % (chair.split()[0] if chair else "the chair"))
    else:
        ok("a deputy can stand in (%s)" % ", ".join(str(d.get("name")) for d in deputies))

    # ── Drive it ────────────────────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("2. WALKING A CASE THROUGH IT")
    print("-" * 78)

    R.audit_log = lambda *a, **k: None
    R.resolve_application_permissions = lambda u, a: {
        "can_view": True, "can_update": True, "can_resolve_dcc": True}

    class S:
        def __init__(s, a): s.a = {a["id"]: dict(a)}
        def get(s, i): return s.a.get(i)
        def update(s, i, u): s.a[i].update(u); return s.a[i]

    def _mid(m):
        """The id the roster keys on - id, then member_id, then staff code."""
        return str(m.get("id") or m.get("member_id")
                   or m.get("staff_code") or "").strip()

    def as_user(m):
        mc = str(m.get("staff_code", "") or "")
        hit = by_code.get(mc) or by_name.get(str(m.get("name", "")).strip().lower())
        rec = hit[1] if hit else {}
        return {"username": hit[0] if hit else mc, "staff_code": mc,
                "full_name": str(m.get("name") or rec.get("full_name") or ""),
                "role": str(rec.get("role") or m.get("role") or "")}

    base = {"id": "BCCTEST", "status": "referred_to_committee",
            "committee_kind": "mcc", "client_type": "CIB",
            "amount": 120000000, "product": "Term Loan",
            "circulation_note": "Fully packaged, seeking approval at KES 120m.",
            "analyst": {"code": "AN1", "name": "Credit Risk"}, "rm_code": "OW1"}

    # Does the right committee resolve, and does each member get a vote?
    st = S(dict(base)); R._lam = lambda: st
    try:
        roster = R.lms_dcc_roster("BCCTEST", as_user(members[0]))
        if str(roster.get("name", "")).strip() == str(c.get("name", "")).strip():
            ok("a referred case resolves to THIS committee")
        else:
            bad("a referred case resolves to this committee",
                "it resolved to %r instead" % roster.get("name"))
        if len(roster.get("members") or []) == len(members):
            ok("the panel would show all %d member(s)" % len(members))
        else:
            bad("the panel shows every member",
                "%d of %d" % (len(roster.get("members") or []), len(members)))
    except Exception as exc:
        bad("the roster resolves", str(exc)[:80])

    # Every member votes, then it resolves.
    st = S(dict(base)); R._lam = lambda: st
    cast = 0
    for m in members:
        try:
            # THE PANEL SENDS member_id AND SO MUST THIS. My first version
            # omitted it and reported four failures against a working system -
            # a test that cries wolf costs more than no test, because the next
            # real failure is read as noise.
            R.lms_dcc_vote("BCCTEST",
                           {"member_id": _mid(m), "vote": "YES"}, as_user(m))
            cast += 1
        except Exception as exc:
            bad("%s can cast a vote" % str(m.get("name"))[:30], str(exc)[:70])
    if cast == len(members):
        ok("all %d member(s) could vote" % cast)

    # A member must not vote twice.
    if members:
        try:
            R.lms_dcc_vote("BCCTEST",
                           {"member_id": _mid(members[0]), "vote": "NO"},
                           as_user(members[0]))
            bad("a member votes once", "a second vote was accepted")
        except Exception as exc:
            if "409" in str(exc):
                ok("a member votes once (a second is refused)")
            else:
                warn("a second vote is refused", str(exc)[:60])

    # NOBODY VOTES IN ANOTHER MEMBER'S NAME. This is the hole found while
    # rehearsing this very committee, and the check that would have caught it.
    if len(members) > 1:
        st2 = S(dict(base)); R._lam = lambda: st2
        try:
            R.lms_dcc_vote("BCCTEST",
                           {"member_id": _mid(members[1]), "vote": "YES"},
                           as_user(members[0]))
            bad("a member cannot vote in another's name",
                "%s cast a vote as %s - on a committee whose chair's vote is "
                "mandatory, one member could decide alone"
                % (str(members[0].get("name"))[:24], str(members[1].get("name"))[:24]))
        except Exception as exc:
            if "403" in str(exc):
                ok("a member cannot vote in another member's name")
            else:
                warn("voting as another member is refused", str(exc)[:60])
        R._lam = lambda: st

    # And the answer goes back to credit risk.
    try:
        R.lms_dcc_resolve("BCCTEST", {}, as_user(members[0]))
        a = st.get("BCCTEST")
        if a.get("awaiting_credit_analyst"):
            ok("a supported case goes BACK TO CREDIT RISK, not to the pool")
        else:
            bad("the answer returns to credit risk",
                "status=%r awaiting_credit_analyst=%r"
                % (a.get("status"), a.get("awaiting_credit_analyst")))
        if a.get("approved_by_bcc") is True:
            ok("it is marked approved by the committee")
        else:
            bad("the approval is recorded",
                "approved_by_bcc=%r - credit risk could not tell it apart"
                % a.get("approved_by_bcc"))
        if not (a.get("pre_approval_conditions") or a.get("decision_conditions")):
            ok("the committee set no conditions (the analyst writes those)")
        else:
            warn("the committee set conditions",
                 "conditions are the analyst's to write")
    except Exception as exc:
        bad("the committee's decision resolves", str(exc)[:80])

    # An opposed case must come back too, not vanish.
    st = S(dict(base)); R._lam = lambda: st
    for m in members:
        try:
            R.lms_dcc_vote("BCCTEST",
                           {"member_id": _mid(m), "vote": "NO"}, as_user(m))
        except Exception:
            pass
    try:
        R.lms_dcc_resolve("BCCTEST", {}, as_user(members[0]))
        a = st.get("BCCTEST")
        if a.get("awaiting_credit_analyst") and a.get("approved_by_bcc") is False:
            ok("an opposed case comes back too, marked not approved")
        else:
            bad("an opposed case returns",
                "status=%r - it would vanish and somebody would hunt for it"
                % a.get("status"))
    except Exception as exc:
        bad("an opposed case resolves", str(exc)[:80])

    return report()


def report():
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    print("  passed  %d" % len(OK))
    print("  warned  %d" % len(WARN))
    print("  FAILED  %d" % len(FAIL))
    if not FAIL:
        print("\nThis committee can sit, vote, and return its answer.")
        if WARN:
            print("\nWorth reading, none blocking:")
            for w, why in WARN:
                print("   - %s" % w)
                if why:
                    print("     %s" % why)
        return 0
    print("\nDO NOT CONVENE IT YET:\n")
    for w, why in FAIL:
        print("   * %s" % w)
        if why:
            print("     %s" % why)
    print("\n   python scripts\\seat_the_chairs.py --apply")
    print("   python scripts\\name_dcc_members.py --committee B4 --members <names> --apply")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-8:]:
            print("   %s" % ln[:110])
        sys.exit(1)
