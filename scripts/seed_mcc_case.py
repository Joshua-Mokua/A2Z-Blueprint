#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Put a case in front of the Business Credit Committee, and say how to walk it.

RULING (2026-08-18): "where does Korir for instance get to see the MCC for a
vote, as well as the others? Can we have sample cases and try to make the vote
as the MD, then see how the MCC vote resolves back to Korir to advance the
case."

So this seeds a case already referred to the committee, prints every member
with their login, and sets out the walk in order - who signs in, where they
click, what they should see.

    python scripts\\seed_mcc_case.py --apply
    python scripts\\seed_mcc_case.py --clean

WHERE THE COMMITTEE FINDS IT, which is the part that is not obvious: a member
does NOT need a credit pool role. Committee membership alone grants sight of
the cases before their own committee - that is what MV2 added, because the MD,
the CFO and treasury have no business seeing the whole credit book in order to
vote on one case.

They open CREDIT ANALYSIS and the case is there. Not Manager Queues - that is
the branch committee's route, and a different thing.
"""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.getcwd())

PREFIX = "MCCASE"


def main():
    apply = "--apply" in sys.argv
    clean = "--clean" in sys.argv
    if not (apply or clean):
        print("Nothing to do. Pass --apply to create, or --clean to remove.")
        return 0

    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
    mcc = next((c for c in pal
                if "management" in str(c.get("name", "")).lower()
                or "business credit" in str(c.get("name", "")).lower()
                or str(c.get("code")) == "B4"), None)
    if not mcc:
        print("ABORT: no Management / Business Credit Committee in the palette.")
        return 1
    members = [m for m in (mcc.get("members") or []) if isinstance(m, dict)
               and str(m.get("staff_code", "")).strip()]
    if not members:
        print("ABORT: %s has no members. Name them first:" % mcc.get("code"))
        print("   python scripts\\name_dcc_members.py --committee %s --members <names> --apply"
              % mcc.get("code"))
        return 1

    from utils.core import LoanApplicationManager, UserManager
    lam = LoanApplicationManager()
    users = UserManager().users or {}
    by_code = {}
    for k, v in users.items():
        c = str(v.get("staff_code", "") or "").strip()
        if c:
            by_code[c] = k

    apps = list(getattr(lam, "apps", []) or [])
    mine = [a for a in apps if str(a.get("id", "")).startswith(PREFIX)]

    if clean:
        if not mine:
            print("Nothing to remove.")
            return 0
        lam.apps[:] = [a for a in apps if not str(a.get("id", "")).startswith(PREFIX)]
        try:
            lam._save()
        except Exception:
            try:
                lam.save()
            except Exception:
                print("  (could not save - remove them by hand)")
        print("removed %d case(s)." % len(mine))
        return 0

    if mine:
        print("%d already exist. Remove them first with --clean." % len(mine))
        return 1

    # A case the committee would actually be asked about: large, corporate,
    # already recommended by the department and referred up by credit risk.
    now = datetime.now()
    circulator = next((m for m in members
                       if "credit" in str(m.get("role", "")).lower()), members[0])
    app = {
        "id": "%s001" % PREFIX,
        "client_name": "Highlands Manufacturing PLC",
        "client_type": "CIB",
        "product": "Term Loan",
        "amount": 120000000,
        "currency": "KES",
        # Referred to the committee, awaiting its sitting.
        "status": "referred_to_committee",
        "committee_kind": "mcc",
        "escalated_pending": True,
        "escalated_to_name": str(mcc.get("name")),
        "escalated_at": now.isoformat(timespec="seconds"),
        "circulation_note": ("Exposure of KES 120m is above departmental "
                             "authority. Fully packaged: security perfected, "
                             "three years of audited accounts attached, "
                             "gearing within policy. Seeking approval."),
        "circulated_by_name": str(circulator.get("name")),
        "analyst": {"code": str(circulator.get("staff_code")),
                    "name": str(circulator.get("name"))},
        "rm_code": "", "rm_name": "", "rm_unit": "",
        "application_date": (now - timedelta(days=9)).date().isoformat(),
        "last_updated": now.isoformat(timespec="seconds"),
        "documents_provided": ["ID/Passport", "CRB Report",
                               "Bank Statements (6 months)", "Audited Accounts",
                               "Board Resolution", "Valuation Report"],
        "dcc_votes": [],
        "simulated": True,
    }
    lam.apps.append(app)
    try:
        lam._save()
    except Exception:
        try:
            lam.save()
        except Exception as exc:
            print("ABORT: created in memory but could not save: %s" % exc)
            return 1

    quorum = mcc.get("min_quorum_count") or 2
    chair = str(mcc.get("chaired_by", "") or "")

    print("=" * 78)
    print("A CASE BEFORE THE %s" % str(mcc.get("name")).upper())
    print("=" * 78)
    print("  %s   %s" % (app["id"], app["client_name"]))
    print("  KES %s, %s, %s" % ("{:,}".format(app["amount"]),
                                app["client_type"], app["product"]))
    print("  circulated by %s" % app["circulated_by_name"])
    print("")
    print("  WHO CAN VOTE, and how they sign in")
    print("  %-10s %-30s %s" % ("CODE", "NAME", "LOGIN"))
    for m in members:
        c = str(m.get("staff_code"))
        lg = by_code.get(c)
        mark = "  (chair)" if str(m.get("name", "")).strip().lower() == chair.lower() else ""
        print("     %-10s %-30s %s%s"
              % (c, str(m.get("name"))[:30], lg or "*** NO LOGIN ***", mark))

    print("""
  WHERE THEY FIND IT
     Credit Analysis. NOT Manager Queues - that is the branch committee's
     route. A committee member needs no credit pool role: sitting on the
     committee is what grants sight of its cases, and nothing else.

  THE WALK
     1. Sign in as any member and open Credit Analysis. %s should be
        listed. Open it.

     2. The tab reads BUSINESS CREDIT COMMITTEE - not Department. Above the
        bench is the note %s wrote when circulating it.

     3. Vote. Each member votes once and it stands; a second is refused, and
        nobody can vote in another member's name.

     4. Sign in as the MD, %s, and vote. Her vote is
        mandatory - %s or %s stands in when she is away.

     5. AT LEAST ONE PERSON FROM CREDIT MUST HAVE VOTED. An abstention counts.
        Without one the committee is refused - it cannot decide a case with no
        credit voice in the room.

     6. With %d votes cast, close the sitting. Any member of the committee may
        record the decision.

  WHAT SHOULD THEN HAPPEN
     The case goes BACK TO CREDIT RISK, marked approved by the committee. It
     does NOT go to the pool at large, and the committee sets no conditions -
     those are the analyst's to write.

     Sign in as %s. The case is in Credit Analysis, carrying
     the committee's approval. On Credit Risk Review: approve it with the
     pre-approval and pre-disbursement conditions, and it travels to Credit
     Administration.

  Remove this case afterwards:  python scripts\\seed_mcc_case.py --clean
""" % (app["id"], app["circulated_by_name"], chair or "the chair",
       *( [str(d.get("name")) for d in members if d.get("deputy_chair")][:2]
          or ["the deputy", "the second deputy"] ),
       quorum, app["circulated_by_name"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
