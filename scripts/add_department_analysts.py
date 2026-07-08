#!/usr/bin/env python3
"""add_department_analysts.py — add three Department Analyst staff to the register.

The org hierarchy has the roles (Consumer / Commercial / CIB Credit Analyst) but
no PERSON holds them, so make_demo_logins finds no match. This appends three
staff rows to data/staff_register.xlsx by CLONING an existing credit analyst
(default: 300068 Lilian Yego) as a template — same Unit / Department / Reports To
/ Category / Band, so the rows are structurally valid (Reports To resolves, Role
is credit) — and only changes Staff Code, Staff Name and Role.

After running this (with --apply), run:
    python scripts/make_demo_logins.py --apply
to create their logins (consumer0901 / EcoStaff0901, etc.).

Idempotent: skips a role whose Staff Code or Role already exists in the register.
Backs up the register (.pre_deptanalysts) before writing.

Usage (repo root):
    python scripts/add_department_analysts.py            # DRY-RUN
    python scripts/add_department_analysts.py --apply     # append + save

Optional: --template <staff_code>  (default 300068)
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REGISTER = DATA_DIR / "staff_register.xlsx"

# (Staff Code, Staff Name, Role) — the three new analysts. Codes 3090xx are
# chosen to sit clear of the generated 300xxx / 301xxx ranges.
NEW_ANALYSTS = [
    ("309001", "Caleb Mwangi",   "Consumer Credit Analyst"),
    ("309002", "Cynthia Otieno", "Commercial Credit Analyst"),
    ("309003", "Clifford Kimani", "CIB Credit Analyst"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--template", default="300068",
                    help="Staff Code of the credit analyst to clone (default 300068 Lilian Yego).")
    args = ap.parse_args()

    if not REGISTER.exists():
        print(f"!! register not found at {REGISTER}")
        return 1

    wb = openpyxl.load_workbook(REGISTER)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    ix = {h: i for i, h in enumerate(header)}
    for req in ("Staff Code", "Staff Name", "Role"):
        if req not in ix:
            print(f"!! register missing required column '{req}'. Columns: {header}")
            return 1

    # Index existing codes/roles for idempotency + find the template row.
    existing_codes = set()
    existing_roles = set()
    template_row = None
    for r in rows[1:]:
        code = str(r[ix["Staff Code"]]).strip() if r[ix["Staff Code"]] is not None else ""
        role = str(r[ix["Role"]]).strip() if r[ix["Role"]] is not None else ""
        if code:
            existing_codes.add(code)
        if role:
            existing_roles.add(role.lower())
        if code == str(args.template):
            template_row = list(r)

    if template_row is None:
        print(f"!! template staff code {args.template} not found in register. "
              "Pass --template <an existing Credit Analyst's Staff Code>.")
        return 1

    tmpl_name = str(template_row[ix["Staff Name"]])
    tmpl_role = str(template_row[ix["Role"]])
    print(f"register: {len(rows) - 1} staff rows")
    print(f"template: {args.template}  {tmpl_name}  ::  {tmpl_role}")
    print(f"          (Unit={template_row[ix.get('Unit', -1)] if 'Unit' in ix else '?'}, "
          f"Dept={template_row[ix.get('Department', -1)] if 'Department' in ix else '?'}, "
          f"ReportsTo={template_row[ix.get('Reports To', -1)] if 'Reports To' in ix else '?'})")
    print()

    to_add = []
    for code, name, role in NEW_ANALYSTS:
        if code in existing_codes:
            print(f"  [skip] {role}: staff code {code} already in register")
            continue
        if role.lower() in existing_roles:
            print(f"  [skip] {role}: a staff member already holds this role")
            continue
        new_row = list(template_row)                      # clone the template
        new_row[ix["Staff Code"]] = code
        new_row[ix["Staff Name"]] = name
        new_row[ix["Role"]] = role
        to_add.append((code, name, role, new_row))
        print(f"  [ADD ] {role}")
        print(f"      staff: {code}  {name}  ::  {role}  (cloned from {args.template})")
    print()

    if not to_add:
        print("Nothing to add (all three already present).")
        return 0

    if not args.apply:
        print("[DRY-RUN] No rows written. Re-run with --apply to append them.")
        print("Then: python scripts/make_demo_logins.py --apply   (creates their logins)")
        return 0

    bak = REGISTER.with_name(f"staff_register.xlsx.pre_deptanalysts-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(REGISTER, bak)
    print(f"[backup] {bak.name}")

    for _code, _name, _role, new_row in to_add:
        ws.append(new_row)
    wb.save(REGISTER)
    print(f"[apply] appended {len(to_add)} staff rows; staff_register.xlsx saved.")
    print()
    print("NEXT: python scripts/make_demo_logins.py --apply   (creates the three logins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
