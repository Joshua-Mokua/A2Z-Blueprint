#!/usr/bin/env python3
"""A2Z MIS 360 — build a local dev staff register and logins. NO REAL PEOPLE.

WHY THIS EXISTS
---------------
data/staff_register.xlsx and data/users.json are gitignored and always will be: the
real ones hold 363 Ecobank employees and 435 live credentials. They must never reach
git, and they should not travel by email either. So instead of copying the bank's
data, this rebuilds an equivalent register locally with invented names.

The STRUCTURE is real — it is read from data/org_config.json, which is in the repo:
the same 153 roles, the same reporting tree, the same 17 branches and 9 regions. So
hierarchy, cascade scope, manager queues and scorecards all behave exactly as they do
on the bank's data. Only the humans are fictional.

That also means it stays correct as the tree changes: it reads org_config rather than
carrying its own copy of the roles, so yesterday's Head of Commercial Banking fix is
already reflected here without anyone remembering to update a second list.

USAGE
-----
    python bootstrap_dev_data.py                 # show what it would create
    python bootstrap_dev_data.py --apply
    python bootstrap_dev_data.py --apply --force # overwrite an existing dev register

It REFUSES to overwrite an existing register unless --force, so it can never quietly
destroy real data on a machine that has it.

Logins follow the same convention as the bank's: username = staff code, password =
"EcoStaff" + the last 4 characters of the staff code. e.g. KE1042 / EcoStaff1042.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ORG = DATA / "org_config.json"
REG = DATA / "staff_register.xlsx"
USERS = DATA / "users.json"

random.seed(4242)  # deterministic: everyone's dev bank looks the same

FIRST = ["James", "John", "Peter", "David", "Paul", "Joseph", "Michael", "Patrick",
         "Francis", "Samuel", "Daniel", "Stephen", "Charles", "Robert", "Simon",
         "Mary", "Grace", "Faith", "Jane", "Ann", "Esther", "Ruth", "Sarah",
         "Lucy", "Catherine", "Agnes", "Rose", "Joyce", "Alice", "Nancy",
         "Kevin", "Brian", "Dennis", "Victor", "Edwin", "Collins", "Eric",
         "Mercy", "Caroline", "Beatrice", "Lydia", "Winnie", "Irene", "Susan"]
LAST = ["Kamau", "Otieno", "Mwangi", "Ochieng", "Wanjiru", "Njoroge", "Achieng",
        "Kiprop", "Mutiso", "Wafula", "Odhiambo", "Chebet", "Muthoni", "Kipchumba",
        "Nyambura", "Omondi", "Waweru", "Auma", "Kirui", "Njeri", "Barasa",
        "Kilonzo", "Wekesa", "Atieno", "Gitonga", "Cheruiyot", "Mueni", "Onyango"]

# Roughly how many people sit in each kind of role. Anything not named gets 1.
HEADCOUNT = {
    "Direct Sales Agent": 60, "Branch Operations Officer": 53,
    "Customer Service Manager": 15, "Relationship Officer": 12,
    "Contact Center Agent": 12, "Relationship Manager": 9,
    "Bancassurance Officer": 9, "Branch Manager": None,   # None = one per branch
    "Assistant Branch Service & Operations Manager": 8,
    "Service Assistant, Operations Officer": 6,
    "Relationship Manager, SME": 6, "Branch DSA Team Lead": 6,
    "Operations Officer": 4, "Credit Analyst": 3,
    "Teller": 20, "Customer Service Officer": 12,
}


def main() -> int:
    apply = "--apply" in sys.argv
    force = "--force" in sys.argv

    if not ORG.exists():
        print(f"REFUSING — {ORG} not found. Run this from the repo root.")
        return 1
    if REG.exists() and not force:
        print(f"REFUSING — {REG} already exists.")
        print("If it is the bank's real register, do NOT overwrite it.")
        print("If it is dev data you want rebuilt, re-run with --force.")
        return 1

    cfg = json.loads(ORG.read_text(encoding="utf-8"))
    hierarchy = cfg.get("hierarchy") or {}
    branches = [b for b in (cfg.get("branches") or []) if b.get("type") != "HO"]
    ho = next((b for b in (cfg.get("branches") or []) if b.get("type") == "HO"),
              {"name": "Head Office", "region": "Head Office"})
    if not hierarchy:
        print("REFUSING — org_config.json has no hierarchy to build from.")
        return 1

    used: set[str] = set()

    def name() -> str:
        for _ in range(400):
            n = f"{random.choice(FIRST)} {random.choice(LAST)}"
            if n not in used:
                used.add(n)
                return n
        return f"{random.choice(FIRST)} {random.choice(LAST)} {len(used)}"

    # Branch-facing roles are placed in branches; everything else at Head Office.
    BRANCHY = ("branch", "teller", "customer service", "direct sales", "dsa",
               "relationship officer", "operations officer", "service assistant",
               "bancassurance")

    rows, seq = [], 1000
    for role in sorted(hierarchy):
        rl = role.lower()
        n = HEADCOUNT.get(role, 1)
        in_branch = any(k in rl for k in BRANCHY)
        if n is None or (role == "Branch Manager"):
            targets = [b["name"] for b in branches]
        elif in_branch and branches:
            targets = [random.choice(branches)["name"] for _ in range(n)]
        else:
            targets = [ho["name"]] * n
        for br in targets:
            seq += 1
            rows.append({
                "Staff Code": f"KE{seq}",
                "Staff Name": name(),
                "Role": role,
                "Branch": br,
                "Region": next((b.get("region") for b in branches
                                if b["name"] == br), ho.get("region", "Head Office")),
                "Department": ("Branch Network" if br != ho["name"] else "Head Office"),
                "Email": "",
                "Join Date": str(date(2015, 1, 1)
                                 + timedelta(days=random.randint(0, 3800))),
                "Status": "Active",
            })

    print(f"org_config: {len(hierarchy)} roles, {len(branches)} branches "
          f"+ {ho['name']}")
    print(f"would create: {len(rows)} synthetic staff, {len(rows)} logins")
    print(f"  {REG}")
    print(f"  {USERS}")
    print("\nsample:")
    for r in rows[:6]:
        print(f"   {r['Staff Code']:8} {r['Staff Name'][:24]:24} "
              f"{r['Role'][:34]:34} {r['Branch']}")
    print("\nlogin convention: username = staff code, password = EcoStaff + last 4")
    print("   e.g. KE1042 / EcoStaff1042")

    if not apply:
        print("\n[DRY-RUN] re-run with --apply")
        return 0

    try:
        import pandas as pd
    except ImportError:
        print("\npandas is required: pip install pandas openpyxl")
        return 1

    DATA.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(REG, index=False)

    try:
        from utils.core import UserManager
        um = UserManager()
        hash_pw = um.hash_pw
    except Exception:
        hash_pw = None
        print("  (could not import UserManager — writing plaintext dev passwords)")

    users = {}
    for r in rows:
        code = r["Staff Code"]
        pw = f"EcoStaff{code[-4:]}"
        users[code] = {
            "username": code,
            "password": hash_pw(pw) if hash_pw else pw,
            "staff_code": code,
            "name": r["Staff Name"],
            "role": r["Role"],
            "branch": r["Branch"],
            "department": r["Department"],
            "active": True,
            "is_admin": False,
            "can_view_all": False,
            "_dev_data": True,
        }
    # One super admin so a fresh clone is usable immediately.
    first_md = next((r for r in rows if r["Role"] == "Managing Director"), rows[0])
    users[first_md["Staff Code"]]["is_admin"] = True
    users[first_md["Staff Code"]]["can_view_all"] = True

    USERS.write_text(json.dumps(users, indent=2), encoding="utf-8")
    print(f"\ncreated {len(rows)} staff and {len(users)} logins — all fictional.")
    print(f"super admin: {first_md['Staff Code']} / EcoStaff{first_md['Staff Code'][-4:]}"
          f"  ({first_md['Role']})")
    print("\nNext: python -m utils.api")
    return 0


if __name__ == "__main__":
    sys.exit(main())
