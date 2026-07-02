"""
seed_analyst_cases.py — populate a Credit Analyst's queue for the demo.

Drives the LIVE API (not the DB) to create a handful of loan applications and
assign them to a target analyst, leaving them in analyst-ready states so the
demo shows a populated Loan Applications queue + the analysis workspace
(approve / decline / return-for-rework / escalate).

Default target = Lilian Yego (Credit Analyst, staff 300068).

  python scripts/seed_analyst_cases.py                 # dry-run (counts only)
  python scripts/seed_analyst_cases.py --apply         # create + assign 6 cases
  python scripts/seed_analyst_cases.py --apply --n 10  # create + assign 10
  python scripts/seed_analyst_cases.py --apply --analyst 300068 --analyst-name "Lilian Yego"

Requires the API running on :8502 and the demo logins present
(owner=frank0731, manager=immaculate0716). Idempotent-ish: each run creates
NEW deals (unique client names), so re-running just adds more.
"""
import argparse
import sys
import time
from datetime import datetime

import requests

BASE = "http://127.0.0.1:8502"

OWNER = {"username": "frank0731", "password": "EcoStaff0731"}      # RM / deal owner
MANAGER = {"username": "immaculate0716", "password": "EcoStaff0716"}  # validates + assigns

# A spread of products/amounts so the queue looks realistic.
SAMPLES = [
    ("Term Loan", 3_000_000, "SME", "Manufacturing"),
    ("Term Loan", 8_500_000, "SME", "Wholesale & Retail Trade"),
    ("Asset Finance", 5_200_000, "SME", "Transport & Storage"),
    ("Overdraft", 1_800_000, "Micro", "Accommodation & Food Service"),
    ("Term Loan", 12_000_000, "Corporate", "Agriculture, Forestry & Fishing"),
    ("Invoice Discounting", 4_600_000, "SME", "Construction"),
    ("Mortgage", 9_900_000, "Personal", "Real Estate"),
    ("Term Loan", 6_300_000, "SME", "Information & Communication"),
    ("Asset Finance", 7_100_000, "SME", "Manufacturing"),
    ("Overdraft", 2_400_000, "Micro", "Wholesale & Retail Trade"),
]


def _login(creds):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=15)
    if r.status_code != 200:
        print(f"!! login failed for {creds['username']}: {r.status_code} {r.text[:120]}")
        sys.exit(1)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _post(path, headers, body):
    return requests.post(f"{BASE}{path}", json=body, headers=headers, timeout=20)


def _get(path, headers):
    return requests.get(f"{BASE}{path}", headers=headers, timeout=20)


def _make_one(owner_h, manager_h, product, amount, segment, sector, analyst_code, analyst_name):
    """create -> advance -> manager-validate -> submit-to-credit -> assign analyst."""
    body = {
        "client_name": f"DEMO {product.split()[0]} {datetime.now():%H%M%S%f}"[:48],
        "client_type": "Business" if segment != "Personal" else "Individual",
        "product_type": product, "deal_value": amount, "stage": "Lead",
        "segment": segment, "sector": sector,
    }
    r = _post("/api/pipeline/deals", owner_h, body)
    if r.status_code not in (200, 201):
        return None, f"create failed: {r.status_code} {r.text[:100]}"
    did = r.json().get("id") or r.json().get("deal", {}).get("id")
    for tgt in ["Contacted", "Qualified", "Application", "Credit Assessment"]:
        _post(f"/api/pipeline/deals/{did}/advance", owner_h, {"target_stage": tgt})
    _post(f"/api/pipeline/deals/{did}/validate", manager_h,
          {"approved": True, "note": "validated for demo seed"})
    chk = _get(f"/api/pipeline/deals/{did}/credit-checklist", owner_h)
    req = chk.json().get("required", []) if chk.status_code == 200 else []
    r = _post(f"/api/pipeline/deals/{did}/submit-to-credit", owner_h,
              {"documents_provided": req})
    if r.status_code not in (200, 201):
        return None, f"submit failed: {r.status_code} {r.text[:100]}"
    aid = r.json().get("application_id")
    if not aid:
        return None, "no application_id"
    # Assign to the target analyst (manager performs the assignment).
    r = _post(f"/api/lms/applications/{aid}/assign", manager_h,
              {"analyst_code": analyst_code, "analyst_name": analyst_name})
    if r.status_code not in (200, 201):
        return None, f"assign failed: {r.status_code} {r.text[:100]}"
    return aid, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--analyst", default="300068")
    ap.add_argument("--analyst-name", default="Lilian Yego")
    args = ap.parse_args()

    n = max(1, min(args.n, len(SAMPLES) * 3))
    print(f"Target analyst: {args.analyst_name} ({args.analyst})")
    print(f"Cases to seed:  {n}")
    if not args.apply:
        print("\n[DRY-RUN] Re-run with --apply to create + assign.")
        return

    owner_h = _login(OWNER)
    manager_h = _login(MANAGER)
    made, failed = [], []
    for i in range(n):
        product, amount, segment, sector = SAMPLES[i % len(SAMPLES)]
        aid, err = _make_one(owner_h, manager_h, product, amount, segment, sector,
                             args.analyst, args.analyst_name)
        if aid:
            made.append(aid)
            print(f"  [{i+1}/{n}] assigned {aid}  ({product}, KES {amount:,})")
        else:
            failed.append(err)
            print(f"  [{i+1}/{n}] FAILED: {err}")
        time.sleep(0.2)

    print(f"\nDone. {len(made)} assigned to {args.analyst_name}; {len(failed)} failed.")
    if made:
        print("Log in as the analyst — their Loan Applications queue should now show these,")
        print("each opening the analysis workspace (approve / decline / return / escalate).")


if __name__ == "__main__":
    main()
