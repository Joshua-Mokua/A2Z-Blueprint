"""scripts/seed_branch_test_logins.py — real-staff test logins for ONE branch
chain (frontline -> CEO), drawn from data/staff_register.xlsx.

Accounts are created through UserManager.add_user, so passwords are bcrypt-hashed
exactly like the canonical seed (scripts/seed_test_logins.py). A standalone
plaintext write does NOT authenticate — verify_pw accepts only bcrypt,
envelope-bcrypt, or SHA-256 hex.

Password convention: EcoStaff + last-4 of staff_code.
Username: lowercase first name + last-4 of staff_code (e.g. william0001).

Safe: backs up users.json (timestamped) before writing; idempotent (re-running
refreshes/repairs accounts); aborts if users.json is missing/empty.

USAGE (project root, venv active):
    python scripts/seed_branch_test_logins.py --branch Thika
    python scripts/seed_branch_test_logins.py --branch Thika --list
"""
from __future__ import annotations
import argparse, shutil, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REGISTER = DATA / "staff_register.xlsx"
sys.path.insert(0, str(ROOT))


def _load_register():
    from openpyxl import load_workbook
    wb = load_workbook(REGISTER, read_only=True); ws = wb.active
    it = ws.iter_rows(values_only=True); hdr = list(next(it))
    rows = [dict(zip(hdr, r)) for r in it]
    for r in rows:
        for k in ("Staff Code", "Staff Name", "Role", "Unit", "Region", "Reports To"):
            r[k] = "" if r.get(k) is None else str(r[k]).strip()
    return rows


def _chain_for_branch(rows, branch):
    branch_staff = [r for r in rows if r["Unit"] == branch]
    if not branch_staff:
        raise SystemExit(f"No staff for branch Unit '{branch}'. "
                         f"Sample: {sorted({r['Unit'] for r in rows})[:10]}")

    def find_mgr(child):
        cand = [r for r in rows if r["Role"] == child["Reports To"]]
        if not cand:
            return None
        same = [c for c in cand if c["Region"] == child["Region"]]
        return (same or cand)[0]

    picked, seen = [], set()
    def add(r):
        if r and r["Staff Code"] not in seen:
            seen.add(r["Staff Code"]); picked.append(r)

    want_roles = ["Teller", "Customer Service Officer",
                  "Relationship Officer-Personal Banker",
                  "Branch Operations Supervisor", "Branch Relationship Manager",
                  "Branch Operations Manager", "Senior Branch Manager", "Branch Manager"]
    for role in want_roles:
        for r in branch_staff:
            if r["Role"] == role:
                add(r); break

    top = next((r for r in branch_staff
                if r["Role"] in ("Senior Branch Manager", "Branch Manager")), None)
    node = top or (branch_staff[0] if branch_staff else None)
    guard = 0
    while node and guard < 20:
        guard += 1
        add(node)
        if node["Reports To"] in ("", "None", "nan"):
            break
        node = find_mgr(node)
    return picked


def _username(r):
    first = r["Staff Name"].split()[0].lower() if r["Staff Name"] else "staff"
    return f"{first}{r['Staff Code'][-4:]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="Thika")
    ap.add_argument("--list", action="store_true", help="just print, don't write")
    args = ap.parse_args()

    rows = _load_register()
    chain = _chain_for_branch(rows, args.branch)
    creds = [(_username(r), "EcoStaff" + r["Staff Code"][-4:], r["Role"],
              r["Staff Code"], r["Staff Name"], r["Unit"], r["Region"],
              r["Reports To"] in ("", "None", "nan")) for r in chain]

    if args.list:
        print(f"Branch chain '{args.branch}' ({len(creds)} logins):")
        for u, p, role, code, name, *_ in creds:
            print(f"  {u:18s} {p:14s} {code}  {role:34s} {name}")
        return

    from utils.core import DATA_DIR, UserManager  # type: ignore
    users_file = DATA_DIR / "users.json"
    raw = users_file.read_text(encoding="utf-8") if users_file.exists() else ""
    if not raw.strip():
        raise SystemExit(f"ABORT: {users_file} missing/empty — run "
                         f"scripts/seed_test_logins.py first.")

    backup = users_file.with_name(f"users.json.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(users_file, backup)

    um = UserManager()
    for uname, pw, role, code, name, unit, region, is_root in creds:
        um.add_user(uname, pw, name, role=role, unit=unit, staff_code=code,
                    can_view_all=bool(is_root), can_execute=True)
        um.users[uname]["region"] = region
        um.users[uname]["_protected"] = True
        um.users[uname]["must_change_password"] = False
    um.save_users()

    doc = ROOT / "BRANCH_TEST_LOGINS.md"
    lines = [f"# Branch test logins — {args.branch} chain (frontline → CEO)\n",
             f"_Generated {datetime.now():%Y-%m-%d %H:%M}. Password = EcoStaff + last-4 of staff code._\n",
             "| Username | Password | Staff code | Role | Name |", "|---|---|---|---|---|"]
    for u, p, role, code, name, *_ in creds:
        lines.append(f"| `{u}` | `{p}` | {code} | {role} | {name} |")
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Backed up users.json -> {backup.name}")
    print(f"Seeded {len(creds)} branch logins (bcrypt-hashed) into users.json")
    print(f"Wrote {doc.name}")
    for u, p, role, *_ in creds:
        print(f"  {u:18s} {p:14s} {role}")


if __name__ == "__main__":
    main()
