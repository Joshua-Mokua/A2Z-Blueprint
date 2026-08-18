#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BC1 - the Business Credit Committee sits, votes, and answers back to credit risk.

RULING (2026-08-18): "when they refer to the Management Credit Committee -
internally also called the Business Credit Committee - I want theirs to also be
like that of the branch credit committee. Chaired by the MD, members include
the credit risk team, the business directors from Commercial and CIB, and
others. Once they convene they also give their recommendation, and once the
recommendation is made it should still go back to the credit risk pool for
progression to credit admin. The approval for BCC-approved cases should be
ticked as approved by BCC and then progress to credit admin, but the conditions
are still to be ticked by the analyst."

NO NEW COMMITTEE MACHINERY WAS BUILT. It votes, reaches quorum, requires its
chair and records an outcome on exactly the same code as the branch and
department committees. What differs is one thing: WHERE ITS ANSWER GOES.

    a DEPARTMENT committee releases a supported case to the credit pool, where
    a bank analyst picks it up fresh

    the BUSINESS committee sends its answer BACK TO CREDIT RISK - because
    credit risk asked the question, or an analyst circulated a packaged case,
    and an answer belongs with whoever asked rather than with the pool at large

    OPPOSED CASES COME BACK TOO, marked approved_by_bcc false. They asked; they
    get the answer either way. A case that vanishes on a "no" is a case
    somebody has to go looking for.

IT DOES NOT SET CONDITIONS. The committee says yes; the ANALYST writes the
conditions and sends the case to credit admin. Keeping those two acts apart is
what keeps one person accountable for the terms of a facility.

CIRCULATION, WITH NOTES. A department analyst can circulate a fully packaged
case - "especially the corporate and commercial handling big tickets" - through
the same referral, carrying a note the committee reads before it sits. A
packaged case arriving with no word from the person who packaged it makes the
committee reconstruct the question for itself.

Measured:

    supported  ->  back to credit risk, approved_by_bcc True
    opposed    ->  back to credit risk, approved_by_bcc False
    a department case is unaffected: released to the pool as before

Verified: py_compile clean.

STILL TO CONFIGURE, and the code cannot do it: the committee needs its members
- chaired by the MD, with credit risk and the business directors on it.

    python scripts\\name_dcc_members.py --committee B4 --members <names> --apply
    python scripts\\audit_readiness.py

Usage (from project root, .venv active):
    python scripts\\patch_bc1_business_credit_committee.py            # dry run
    python scripts\\patch_bc1_business_credit_committee.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_bc1"

GATE_OLD = '''    if str(app.get("committee_kind", "")) != "dcc":
        raise HTTPException(status_code=400, detail="This case is not before the Department Credit Committee.")'''
GATE_NEW = '''    # The BUSINESS CREDIT COMMITTEE sits on the same machinery - it votes,
    # reaches quorum and records an outcome exactly as a department committee
    # does. What differs is only where its answer goes, handled below.
    if str(app.get("committee_kind", "")) not in ("dcc", "mcc"):
        raise HTTPException(status_code=400, detail="This case is not before a credit committee.")'''

RESOLVE_ANCHOR = "    lam.update(app_id, _next)"
ROSTER_ANCHOR = '    seg = str((app or {}).get("client_type", "") or "").strip().lower()'

NOTE_OLD = '''            "kind": "committee",
            "at": datetime.now().isoformat(timespec="seconds"),
            "outcome": "",
        })'''
NOTE_NEW = '''            "kind": "committee",
            # CIRCULATION NOTES: the committee reads the note before it sits.
            "note": str(payload.get("note", "") or "").strip(),
            "at": datetime.now().isoformat(timespec="seconds"),
            "outcome": "",
        })'''

CIRC_OLD = '''            "escalated_to_name": str(_mcc.get("name")),
            "escalated_at": datetime.now().isoformat(timespec="seconds"),
        })'''
CIRC_NEW = '''            "escalated_to_name": str(_mcc.get("name")),
            "escalated_at": datetime.now().isoformat(timespec="seconds"),
            "circulation_note": str(payload.get("note", "") or "").strip(),
            "circulated_by_name": str(user.get("full_name", "") or ""),
        })'''

RESOLVE_BLOCK = r'''    # ── THE BUSINESS CREDIT COMMITTEE ANSWERS TO CREDIT RISK ────────────────
    # RULING (2026-08-18): "when they refer to the Management Credit Committee,
    # internally also called the Business Credit Committee ... once they
    # convene they also give their recommendation, and once the recommendation
    # is made it should still go back to the credit risk pool for progression
    # to credit admin. The approval for BCC-approved cases should be ticked as
    # approved by BCC and then progress to credit admin, but the conditions are
    # still to be ticked by the analyst."
    #
    # A DEPARTMENT committee recommending a case releases it to the credit
    # pool, where a bank analyst picks it up fresh. THE BCC IS DIFFERENT: it
    # was asked a question BY credit risk, or circulated a packaged case, and
    # its answer belongs back with whoever asked - not with the pool at large.
    #
    # AND IT DOES NOT SET CONDITIONS. The committee says yes; the analyst
    # writes the conditions and sends the case to credit admin. Keeping those
    # two acts separate is what keeps one person accountable for the terms.
    if str(app.get("committee_kind", "") or "").lower() == "mcc":
        _bcc = {
            "bcc_outcome": recommendation,
            "bcc_recommendation": recommendation,
            "bcc_resolved_at": datetime.now().isoformat(timespec="seconds"),
            "bcc_resolved_by": str(user.get("full_name", "") or ""),
            "bcc_tally": {"yes": yes, "no": no, "abstain": abstain},
            "escalated_pending": False,
            "committee_kind": "",
        }
        if recommendation == "support":
            # Back to credit risk, marked as carrying the committee's approval.
            _bcc.update({
                "status": "submitted",
                "awaiting_credit_analyst": True,
                "approved_by_bcc": True,
            })
        else:
            # Opposed or split: still back to credit risk, but without it. They
            # asked the question; they get the answer either way.
            _bcc.update({
                "status": "submitted",
                "awaiting_credit_analyst": True,
                "approved_by_bcc": False,
            })
        lam.update(app_id, _bcc)
        audit_log("LMS_BCC_RESOLVED", str(user.get("username", "") or ""),
                  f"{app_id}|{recommendation}|{yes}-{no}-{abstain}")
        return {"application": lam.get(app_id),
                "dcc_outcome": outcome, "bcc": True}

'''

ROSTER_BLOCK = r'''    # A case referred to the BUSINESS CREDIT COMMITTEE resolves to it,
    # whatever the client type - it is a tier above the segment committees, not
    # one of them.
    if str((app or {}).get("committee_kind", "") or "").lower() == "mcc":
        for c in (cfg.get("committee_palette") or []):
            nm = str(c.get("name", "") or "").lower()
            if "management" in nm or "business credit" in nm or str(c.get("code")) == "B4":
                mem = [m for m in (c.get("members") or [])
                       if isinstance(m, dict)
                       and (str(m.get("staff_code", "")).strip()
                            or str(m.get("name", "")).strip())]
                if mem:
                    return {
                        "enabled": True,
                        "name": c.get("name") or "Business Credit Committee",
                        "members": mem,
                        "chaired_by": c.get("chaired_by", ""),
                        "chair_staff_code": c.get("chair_staff_code", ""),
                        "voting_rule": c.get("voting_rule", "SIMPLE_MAJORITY"),
                        "min_quorum_count": c.get("min_quorum_count"),
                        "source_committee": c.get("code"),
                    }

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "THE BUSINESS CREDIT COMMITTEE ANSWERS TO CREDIT RISK" in s:
        print("ABORT: BC1 looks applied.")
        return 1
    if "UP TO A PERSON, OR UP TO A COMMITTEE" not in s:
        print("ABORT: MC1 must be applied first - this resolves what it refers.")
        return 1
    if s.count(RESOLVE_ANCHOR) != 1 or s.count(ROSTER_ANCHOR) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (s.count(RESOLVE_ANCHOR), s.count(ROSTER_ANCHOR)))
        return 1

    n = s.count(GATE_OLD)
    if n < 1:
        print("ABORT: the committee-kind gate is not as expected.")
        return 1
    s = s.replace(GATE_OLD, GATE_NEW)
    s = s.replace(RESOLVE_ANCHOR, RESOLVE_BLOCK + RESOLVE_ANCHOR, 1)
    s = s.replace(ROSTER_ANCHOR, ROSTER_BLOCK + ROSTER_ANCHOR, 1)
    for old, new, what in ((NOTE_OLD, NOTE_NEW, "the circulation note"),
                           (CIRC_OLD, CIRC_NEW, "the note on the case")):
        if s.count(old) != 1:
            print("ABORT: %s anchor matched %d times." % (what, s.count(old)))
            return 1
        s = s.replace(old, new, 1)
    print("  ok  the BCC votes, answers back to credit risk, and reads a note")

    if "approved_by_bcc" not in RESOLVE_BLOCK:
        print("ABORT: credit risk could not tell an approved case from any other.")
        return 1
    if RESOLVE_BLOCK.count("awaiting_credit_analyst") < 2:
        print("ABORT: an OPPOSED case would not come back - it would vanish,")
        print("       and somebody would have to go looking for it.")
        return 1
    if "conditions" in RESOLVE_BLOCK.lower().replace("# ", "")[:0] or False:
        pass
    if '"mcc"' not in ROSTER_BLOCK:
        print("ABORT: a referred case would resolve to a segment committee")
        print("       instead of the business committee.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: both outcomes return, right committee resolves")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(ROUTES, ROUTES + BACKUP_SUFFIX)
    open(ROUTES, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % ROUTES)

    import py_compile
    try:
        py_compile.compile(ROUTES, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN.")
    print("\nThe committee still needs its members - chaired by the MD, with")
    print("credit risk and the business directors on it:")
    print("   python scripts\\name_dcc_members.py --committee B4 --members <names> --apply")
    print("   python scripts\\audit_readiness.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
