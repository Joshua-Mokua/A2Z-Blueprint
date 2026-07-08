"""
make_demo_logins.py — create demo login accounts for a coherent Thika-branch
hierarchy plus a few bank-wide roles, for an evening demo.

WHY a script (not hardcoded users.json edits):
  users.json is gitignored/runtime — the authoritative copy lives on the dev's
  machine, and the staff register differs from any sandbox copy. So we resolve
  the target staff DYNAMICALLY from the LIVE register at run time (find Thika
  staff whose Role matches each target, pick one), then create the login via
  the same UserManager.hash_pw path the real app uses. No hardcoded staff codes.

CREDENTIALS pattern (mirrors the existing Thika test team, e.g. frank0731):
  username = <first-name-lowercased> + <last 4 of staff code>
  password = "EcoStaff" + <last 4 of staff code>
  e.g. staff 300731 "Frank ..." -> frank0731 / EcoStaff0731

USAGE:
  python scripts/make_demo_logins.py            # DRY-RUN: shows who WOULD be created
  python scripts/make_demo_logins.py --apply    # creates the logins + saves users.json

SAFETY:
  - Dry-run by default. --apply required to write.
  - Backs up users.json (.pre_demologins) before writing.
  - Never prints password hashes — only the plaintext demo password (synthetic).
  - Skips a target if a matching login already exists (idempotent-ish).
"""
import sys
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402
from utils.core import UserManager, DATA_DIR  # noqa: E402

APPLY = "--apply" in sys.argv

# Logins created by an earlier (incorrect) mapping that should be removed on
# --apply so the demo doesn't carry stale/mislabeled director accounts.
# stella0017 was wrongly created as "Director CIB" (Head Of Corporates & Trade
# Finance); the correct CIB is the Chief Commercial Officer. emmanuel0003 is NOT
# listed — he's the Chief Commercial Officer and is now correctly the CIB, so he
# is kept (the apply pass will see his login already exists and skip recreating).
SUPERSEDE = ["stella0017"]

# ── Target roles ──────────────────────────────────────────────────────
# Each entry: (label, [role substrings to match], unit_filter or None).
# Role matching is LENIENT (case-insensitive substring) because role strings
# vary across the register. unit='Thika' ties the DSA tree + branch roles to
# Frank's branch for a coherent demo hierarchy; bank-wide roles use unit=None.
TARGETS = [
    # Thika branch hierarchy (same branch as Frank). Exact role strings from
    # the live register (confirmed 2026-06-23).
    ("DSA (Thika)",                  ["direct sales agent"],        "Thika"),
    ("Branch DSA Team Lead (Thika)", ["branch dsa team lead"],      "Thika"),
    ("Regional DSA Head",            ["regional dsa head"],         None),
    # Bank-wide roles — exact strings.
    ("Credit Analyst",               ["credit analyst"],            None),
    # Department Analyst layer (P1) — segment-specific credit analysts. These
    # are exact-matched first, so they don't collide with the plain "Credit
    # Analyst" target above. Needs matching staff in the register; if a DRY-RUN
    # shows "no register match", add staff carrying these roles first.
    ("Consumer Credit Analyst",      ["consumer credit analyst"],   None),
    ("Commercial Credit Analyst",    ["commercial credit analyst"], None),
    ("CIB Credit Analyst",           ["cib credit analyst"],        None),
    ("Treasury desk",                ["treasury front office officer", "treasury dealer"], None),
    # Directors: per the Ecobank-structure adoption, Chief Retail Banking
    # Officer -> Director CCB and Chief Commercial Officer -> Director CIB.
    # (The register still carries the pre-rename role strings; we target those.)
    ("Director CCB (Chief Retail Banking Officer)", ["chief retail banking officer"], None),
    ("Director CIB (Chief Commercial Officer)", ["chief commercial officer"], None),
    ("Sales Head (mapped: DSA Head)", ["dsa head"],                 None),
    ("MD / Admin",                   ["chief executive & managing director", "managing director"], None),
]


def load_register():
    f = DATA_DIR / "staff_register.xlsx"
    if not f.exists():
        print(f"!! register not found at {f}")
        sys.exit(1)
    wb = openpyxl.load_workbook(f, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    wb.close()
    H = [str(c).strip() if c is not None else "" for c in rows[0]]
    ix = {h: i for i, h in enumerate(H)}
    out = []
    for r in rows[1:]:
        def cell(name, default=""):
            i = ix.get(name)
            return str(r[i]).strip() if i is not None and r[i] is not None else default
        sc = cell("Staff Code")
        if not sc or sc.lower() == "staff code":
            continue
        out.append({
            "staff_code": sc,
            "name": cell("Staff Name"),
            "role": cell("Role"),
            "unit": cell("Unit"),
            "region": cell("Region"),
            "department": cell("Department"),
        })
    return out


def find_match(register, role_subs, unit_filter):
    """First register row whose role matches. Exact (case-insensitive) match is
    preferred over substring so e.g. 'credit analyst' doesn't catch
    'Senior Manager -Credit Analysis'."""
    role_subs = [s.lower() for s in role_subs]

    def unit_ok(row):
        return not unit_filter or unit_filter.lower() in row["unit"].lower()

    # Pass 1: exact role equality.
    for row in register:
        if unit_ok(row) and row["role"].lower() in role_subs:
            return row
    # Pass 2: substring fallback.
    for row in register:
        if unit_ok(row) and any(s in row["role"].lower() for s in role_subs):
            return row
    return None


def make_creds(row):
    sc = row["staff_code"]
    last4 = sc[-4:] if len(sc) >= 4 else sc
    first = (row["name"].split() or ["user"])[0].lower()
    first = "".join(ch for ch in first if ch.isalnum())
    username = f"{first}{last4}"
    password = f"EcoStaff{last4}"
    return username, password


def main():
    register = load_register()
    print(f"register: {len(register)} staff rows")
    thika = [r for r in register if "thika" in r["unit"].lower()]
    print(f"Thika staff: {len(thika)}")
    print()

    um = UserManager()
    existing_usernames = set(um.users.keys())
    existing_codes = {str(u.get("staff_code", "")) for u in um.users.values()}

    planned = []
    for label, role_subs, unit_filter in TARGETS:
        row = find_match(register, role_subs, unit_filter)
        if not row:
            print(f"  [skip] {label}: no register match for roles {role_subs}"
                  + (f" in unit '{unit_filter}'" if unit_filter else ""))
            continue
        username, password = make_creds(row)
        status = "NEW"
        if username in existing_usernames:
            status = "exists (login already present)"
        elif row["staff_code"] in existing_codes:
            status = "staff already has a login (different username)"
        planned.append((label, row, username, password, status))
        print(f"  [{status:42}] {label}")
        print(f"      staff: {row['staff_code']}  {row['name']}  ::  {row['role']}  ({row['unit']})")
        print(f"      login: {username} / {password}")
        print()

    if not APPLY:
        print("[DRY-RUN] No logins written. Re-run with --apply to create them.")
        return

    # Apply: create logins for NEW ones only.
    users_file = DATA_DIR / "users.json"
    if users_file.exists():
        bak = users_file.with_name(f"users.json.pre_demologins-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(users_file, bak)
        print(f"[backup] {bak.name}")

    created = 0
    # Remove superseded (incorrectly-mapped) logins first.
    removed = 0
    for uname in SUPERSEDE:
        if uname in um.users:
            del um.users[uname]
            removed += 1
            print(f"[remove] superseded login: {uname}")
    for label, row, username, password, status in planned:
        if username in um.users:
            continue
        um.users[username] = {
            "password":   um.hash_pw(password),
            "full_name":  row["name"],
            "role":       row["role"],
            "department": row["department"] or "All",
            "staff_code": row["staff_code"],
            "unit":       row["unit"],
            "region":     row["region"],
            "active":     True,
            "managed_roles": [], "managed_units": [], "managed_staff_codes": [],
        }
        created += 1
    um._save()
    print(f"[apply] created {created} new demo logins, removed {removed} superseded; users.json saved.")
    print()
    print("=== DEMO LOGIN SHEET ===")
    for label, row, username, password, status in planned:
        print(f"  {label:28}  {username:16}  {password}")


if __name__ == "__main__":
    main()
