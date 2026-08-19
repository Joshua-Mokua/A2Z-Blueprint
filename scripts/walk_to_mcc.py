#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Walk one case the whole way: branch -> department -> MCC -> credit risk -> won.

The longest path a case can take, driven end to end against the real config and
the real logins. Every earlier rehearsal covered a stretch of it; this one asks
whether the stretches JOIN - which is where every fault this fortnight lived.

    python scripts\\walk_to_mcc.py
    python scripts\\walk_to_mcc.py --branch Eldoret

Nothing is written to the real stores. Exit 0 when the case completes the walk.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

STEPS = []


def step(n, what, got="", ok=True):
    STEPS.append((n, what, got, ok))
    print("  %-3s %-46s %s" % ("%d." % n if ok else "FAIL",
                               what[:46], str(got)[:26]))


def main():
    branch = "Eldoret"
    if "--branch" in sys.argv:
        i = sys.argv.index("--branch")
        if i + 1 < len(sys.argv):
            branch = sys.argv[i + 1].strip()

    import utils.api as A
    import utils.api_lms_routes as R
    from utils.core import UserManager

    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
    users = UserManager().users or {}

    def committee(pred):
        return next((c for c in pal if pred(c)), None)

    bcc = committee(lambda c: str(c.get("branch", "")).strip().lower() == branch.lower())
    dcc = committee(lambda c: str(c.get("code")) == "B1")
    mcc = committee(lambda c: str(c.get("code")) == "B4")
    for label, c in (("branch committee at %s" % branch, bcc),
                     ("department committee B1", dcc),
                     ("business committee B4", mcc)):
        if not c or not [m for m in (c.get("members") or []) if isinstance(m, dict)]:
            print("ABORT: no staffed %s." % label)
            return 1

    def member(c, i=0):
        ms = [m for m in (c.get("members") or []) if isinstance(m, dict)
              and str(m.get("staff_code", "")).strip()]
        return ms[i % len(ms)]

    def as_user(m):
        code = str(m.get("staff_code", "") or "")
        rec = next((v for v in users.values()
                    if str(v.get("staff_code", "")).strip() == code), {})
        return {"username": code, "staff_code": code,
                "full_name": str(m.get("name") or rec.get("full_name") or ""),
                "role": str(rec.get("role") or m.get("role") or ""),
                "is_admin": False}

    def mid(m):
        return str(m.get("id") or m.get("member_id") or m.get("staff_code") or "")

    R.audit_log = lambda *a, **k: None
    R.is_manager = lambda u: True
    R.is_valid_lms_transition = lambda a, b: True
    R.resolve_application_permissions = lambda u, a: {
        "can_view": True, "can_update": True, "can_set_committee_readiness": True,
        "can_resolve_dcc": True, "can_submit_to_dcc": True,
        "can_decide": True, "can_record_decision": True}
    R.get_visible_staff_codes = lambda u: {"OW1", "AN1"}

    class S:
        def __init__(s, a): s.a = {a["id"]: dict(a)}
        def get(s, i): return s.a.get(i)
        def update(s, i, u): s.a[i].update(u); return s.a[i]
        def issue_offer(s, *a, **k): pass
        def record_decision(s, *a, **k): return True

    print("=" * 78)
    print("ONE CASE, THE WHOLE WAY")
    print("=" * 78)
    print("  branch committee     %s" % bcc.get("name"))
    print("  department committee %s" % dcc.get("name"))
    print("  business committee   %s" % mcc.get("name"))
    print("")

    # ── 1-3. The branch committee ───────────────────────────────────────────
    A._db_available = lambda: False
    A._deal_for_docs = lambda did, u: (_PM(), _PM().get_deal(did))
    from utils.core import PipelineManager as _PM
    A._acquire_scoped_deals = lambda u: list(_PM().deals)
    A.get_visible_staff_codes = lambda u: {str(member(bcc, i).get("staff_code"))
                                           for i in range(4)} | {"OW1"}
    flow = [str(x) for x in (A._stage_flow_for("Term Loan") or [])]
    doc = next((x for x in flow if "documentation" in x.lower()), flow[0])
    bstage = next((x for x in flow if "branch credit committee" in x.lower()), "")

    pm = _PM()
    pm.deals[:] = [d for d in pm.deals if d.get("id") != "MCCWALK"]
    pm.deals.append({
        "id": "MCCWALK", "client_name": "Highlands Manufacturing PLC",
        "product": "Term Loan", "product_type": "Term Loan",
        "deal_value": 120000000, "amount": 120000000,
        "staff_code": str(member(bcc, 1).get("staff_code")), "staff_name": "Owner",
        "branch": branch, "unit": branch, "client_type": "CIB",
        "stage": doc, "manager_validated": True,
        "committee_records": {}, "committee_votes": {}, "cr": {}})
    pm._save_deals()

    owner = as_user(member(bcc, 1))
    c = A.pipeline_credit_checklist("MCCWALK", user=owner)
    step(1, "the branch can submit from Documentation",
         "yes" if c.get("can_submit") else "NO", bool(c.get("can_submit")))

    pm = _PM(); d = pm.get_deal("MCCWALK"); d["stage"] = bstage; pm._save_deals()
    code = str(bcc.get("code"))
    voted = 0
    for i in range(2):
        m = member(bcc, i)
        try:
            A.cast_committee_vote("MCCWALK", code,
                                  {"vote": "YES", "documents_validated": True},
                                  as_user(m))
            voted += 1
        except Exception as exc:
            step(2, "%s votes" % str(m.get("name"))[:24], str(exc)[:24], False)
    step(2, "the branch committee votes", "%d cast" % voted, voted >= 2)
    _d = _PM().get_deal("MCCWALK")
    moved = _d["stage"]
    if moved == bstage:
        # Say what the committee is waiting for - "it did not move" is not
        # something anybody can act on.
        _rec = (_d.get("committee_records") or {}).get(code) or {}
        _cast = len((_d.get("committee_votes") or {}).get(code) or {})
        _why = ("outcome=%s" % _rec.get("outcome")) if _rec else ("%d vote(s), no decision" % _cast)
        step(3, "the case advances by itself", _why, False)
    else:
        step(3, "the case advances by itself", moved[:24], True)

    # ── 4-6. The department analyst and committee ───────────────────────────
    an = {"username": "an", "staff_code": "AN1", "full_name": "Analyst",
          "role": "Credit Analyst", "is_admin": False}
    base = {"id": "MCCWALK", "status": "assigned", "client_type": "CIB",
            "amount": 120000000, "product": "Term Loan",
            "analyst": {"code": "AN1", "name": "Analyst"}, "rm_code": "OW1"}
    st = S(dict(base)); R._lam = lambda: st
    R.lms_committee_readiness("MCCWALK", {"decision": "ready"}, an)
    a = st.get("MCCWALK")
    step(4, "the analyst recommends it to the committee",
         a.get("status"), a.get("status") == "referred_to_committee")

    # ASK THE SYSTEM WHICH COMMITTEE, rather than assuming B1. The case is CIB,
    # so it resolves to the Corporate committee - voting B1's members recorded
    # nothing and the case looked opposed. My first version failed here and the
    # system was right.
    _roster = R.lms_dcc_roster("MCCWALK", an)
    _dmembers = [m for m in (_roster.get("members") or []) if isinstance(m, dict)]
    for m in _dmembers[:3]:
        try:
            R.lms_dcc_vote("MCCWALK", {"member_id": mid(m), "vote": "YES"}, as_user(m))
        except Exception:
            pass
    R.lms_dcc_resolve("MCCWALK", {}, an)
    a = st.get("MCCWALK")
    step(5, "the department committee releases it to credit",
         a.get("status"), bool(a.get("awaiting_credit_analyst")))

    # ── 6-8. Credit risk refers it up to the MCC ────────────────────────────
    korir = as_user(member(mcc, 0))
    st.update("MCCWALK", {"status": "assigned", "analyst": {"code": korir["staff_code"]}})
    try:
        r = R.lms_escalate_to_chief(
            "MCCWALK",
            {"reason": "Exposure of KES 120m is above my authority.",
             "to": "mcc",
             "note": "Fully packaged. Security perfected, audited accounts attached."},
            korir)
        a = st.get("MCCWALK")
        step(6, "credit risk refers it to the MCC",
             str(r.get("escalated_to"))[:24], a.get("committee_kind") == "mcc")
        step(7, "the circulation note travels with it",
             "yes" if a.get("circulation_note") else "NO",
             bool(a.get("circulation_note")))
    except Exception as exc:
        step(6, "credit risk refers it to the MCC", str(exc)[:24], False)
        return report()

    # ── 8-10. The MCC sits ──────────────────────────────────────────────────
    roster = R.lms_dcc_roster("MCCWALK", korir)
    step(8, "the MCC roster is the one it shows",
         str(roster.get("name"))[:24],
         str(roster.get("name")) == str(mcc.get("name")))

    ms = [m for m in (mcc.get("members") or []) if isinstance(m, dict)
          and str(m.get("staff_code", "")).strip()]
    cast = 0
    for m in ms:
        try:
            R.lms_dcc_vote("MCCWALK", {"member_id": mid(m), "vote": "YES"}, as_user(m))
            cast += 1
        except Exception:
            pass
    step(9, "the MCC votes", "%d of %d" % (cast, len(ms)), cast >= 2)

    R.lms_dcc_resolve("MCCWALK", {}, as_user(ms[0]))
    a = st.get("MCCWALK")
    step(10, "it comes back to credit risk, approved",
         "approved_by_bcc=%s" % a.get("approved_by_bcc"),
         bool(a.get("awaiting_credit_analyst")) and a.get("approved_by_bcc") is True)

    # ── 11-12. Korir decides, and it reaches credit admin ───────────────────
    from utils.api_lms_models import RecordDecisionRequest
    st.update("MCCWALK", {"status": "assigned"})
    R.lms_application_decision(
        "MCCWALK",
        RecordDecisionRequest(
            verdict="approve", authority="%s (%s)" % (korir["full_name"], korir["role"]),
            pre_approval_conditions=["Salary domiciliation to the bank"],
            pre_disbursement_conditions=["Security perfected and charge registered"]),
        korir)
    a = st.get("MCCWALK")
    step(11, "credit risk approves with conditions",
         a.get("status"), a.get("status") == "credit_admin")
    step(12, "both kinds of condition travel to credit admin",
         "%d + %d" % (len(a.get("pre_approval_conditions") or []),
                      len(a.get("pre_disbursement_conditions") or [])),
         bool(a.get("pre_approval_conditions")) and bool(a.get("pre_disbursement_conditions")))

    pm = _PM(); pm.deals[:] = [d for d in pm.deals if d.get("id") != "MCCWALK"]
    pm._save_deals()
    return report()


def report():
    bad = [s for s in STEPS if not s[3]]
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    print("  steps completed  %d of %d" % (len(STEPS) - len(bad), len(STEPS)))
    if not bad:
        print("\nA case travels the whole way: branch committee, department")
        print("committee, credit risk, the MCC, and back to credit admin with")
        print("its conditions.")
        return 0
    print("\n  IT STOPS HERE:\n")
    for n, what, got, _ in bad:
        print("     %s  (%s)" % (what, got))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-8:]:
            print("   %s" % ln[:110])
        sys.exit(1)
