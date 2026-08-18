#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Put a few cases in front of the bank credit analyst. DRY RUN by default.

So that a decision can actually be tested: approve with conditions, decline
with a reason, or push to the Chief. Without cases at the right status there is
nothing on the screen to press.

Creates three applications sitting at 'submitted' with no analyst - which is
what the credit pool is - one per segment, so the segment filter can be tried
too. They carry a SIMCA prefix and are removed with --clean.

    python scripts\\seed_credit_cases.py --apply
    python scripts\\seed_credit_cases.py --clean
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.getcwd())

PREFIX = "SIMCA"


def main():
    apply = "--apply" in sys.argv
    clean = "--clean" in sys.argv
    if not (apply or clean):
        print("Nothing to do. Pass --apply to create, or --clean to remove.")
        print("  python scripts\\seed_credit_cases.py --apply")
        return 0

    try:
        import utils.api_lms_models as M
        lam = None
        for n in dir(M):
            o = getattr(M, n)
            if isinstance(o, type) and "Manager" in n:
                try:
                    lam = o()
                    break
                except Exception:
                    continue
        if lam is None:
            from utils.core import LoanApplicationManager
            lam = LoanApplicationManager()
    except Exception as exc:
        print("ABORT: cannot open the application store: %s" % exc)
        return 1

    apps = list(getattr(lam, "apps", []) or [])
    mine = [a for a in apps if str(a.get("id", "")).startswith(PREFIX)]

    if clean:
        if not mine:
            print("Nothing to remove.")
            return 0
        keep = [a for a in apps if not str(a.get("id", "")).startswith(PREFIX)]
        lam.apps[:] = keep
        try:
            lam._save()
        except Exception:
            try:
                lam.save()
            except Exception:
                print("  (could not save - remove them from data/loan_applications.json)")
        print("removed %d simulated case(s)." % len(mine))
        return 0

    if mine:
        print("%d already exist. Remove them first with --clean." % len(mine))
        return 1

    # An owner from the register, so the case has a real RM against it.
    rm_code, rm_name, rm_unit = "", "", ""
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        for _i, r in df.iterrows():
            if "relationship" in str(r.get("Role") or "").lower():
                rm_code = str(r.get("Staff Code") or "")
                rm_name = str(r.get("Staff Name") or "")
                rm_unit = str(r.get("Unit") or "")
                break
    except Exception:
        pass

    now = datetime.now()
    spec = [("Consumer", "Personal Loan", 2500000, "Wanjiru Home Improvement"),
            ("Commercial", "Business Loan", 18000000, "Rift Valley Traders Ltd"),
            ("CIB", "Term Loan", 120000000, "Highlands Manufacturing PLC")]

    made = []
    for i, (ct, prod, amt, client) in enumerate(spec, start=1):
        app = {
            "id": "%s%03d" % (PREFIX, i),
            "client_name": client,
            "client_type": ct,
            "product": prod,
            "amount": amt,
            "currency": "KES",
            # 'submitted' with NO analyst is what the pool is - anybody with
            # pool visibility sees it and can pick it.
            "status": "submitted",
            "analyst": None,
            "rm_code": rm_code, "rm_name": rm_name, "rm_unit": rm_unit,
            "application_date": (now - timedelta(days=3 + i)).date().isoformat(),
            "last_updated": now.isoformat(timespec="seconds"),
            "documents_provided": ["ID/Passport", "CRB Report", "Bank Statements (6 months)"],
            "simulated": True,
        }
        lam.apps.append(app)
        made.append(app)

    try:
        lam._save()
    except Exception:
        try:
            lam.save()
        except Exception as exc:
            print("ABORT: created in memory but could not save: %s" % exc)
            return 1

    print("=" * 74)
    print("CASES IN THE CREDIT POOL")
    print("=" * 74)
    for a in made:
        print("  %-10s %-30s %-12s KES %s"
              % (a["id"], a["client_name"][:30], a["client_type"], "{:,}".format(a["amount"])))
    print("\n  owner: %s (%s, %s)" % (rm_name or "unset", rm_code or "-", rm_unit or "-"))
    print("\n  Sign in as the credit analyst and open Credit Analysis > Pool.")
    print("  Pick one, then on its Actions tab: approve with conditions,")
    print("  decline with a reason, or push it to the Chief Credit Risk.")
    print("\n  Remove them with: python scripts\\seed_credit_cases.py --clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
