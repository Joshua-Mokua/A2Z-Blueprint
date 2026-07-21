#!/usr/bin/env python3
"""ALEX RUNS THIS — the consolidated, self-verifying fix for 'test names + zero pipeline'.

Root cause (confirmed via the scope logic): the app reads the pipeline scope tree from
staff_register.xlsx, which on Alex's machine is still TEST data (gitignored, never synced).
The JSON loader fixed Postgres but not the xlsx. So the reporting tree is built from test
staff, and admin (which sees 'everyone in the roster') sees the test roster — while real
deals owned by real staff are invisible.

Fix: rebuild staff_register.xlsx from the (correct) Postgres, and verify the admin account
qualifies for all-view. Prints ONLY PASS/FAIL flags — safe to relay verbally.

    python alex_fix_visibility.py --check     # read-only diagnosis
    python alex_fix_visibility.py --apply     # rebuild xlsx + verify admin, then RESTART API
"""
import sys, json, shutil, time
from pathlib import Path

def flag(ok, label):
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}")

mode = "--apply" if "--apply" in sys.argv else "--check"
print(f"=== pipeline visibility fix ({mode}) — flags only, no names ===\n")

from utils.db import db as _db
import pandas as pd

# A. Postgres has real staff?
pg = _db.fetch_all("SELECT staff_code, full_name, role, unit, metadata FROM users "
                   "WHERE UPPER(COALESCE(role,''))<>'ADMIN'") or []
flag(len(pg) > 300, f"Postgres has >300 real staff (got {len(pg)})")

# B. admin account qualifies for all-view?
adm = _db.fetch_all("SELECT username, role, is_admin, staff_code FROM users "
                    "WHERE username='admin'") or []
admin_ok = False
if adm:
    a = adm[0]
    role_l = str(a.get("role","")).lower()
    admin_ok = bool(a.get("is_admin")) or ("admin" in role_l)
    flag(admin_ok, f"admin account qualifies for all-view (is_admin or role~admin)")
    if not admin_ok:
        print(f"        admin role={a.get('role')!r} is_admin={a.get('is_admin')} — needs fixing")
else:
    flag(False, "admin account exists")

# C. register xlsx matches Postgres?
reg_path = Path("data/staff_register.xlsx")
aligned = False
if reg_path.exists():
    reg = pd.read_excel(reg_path).fillna("")
    reg_codes = set(reg["Staff Code"].astype(str).str.strip()) if "Staff Code" in reg.columns else set()
    pg_codes = {str(r.get("staff_code","")).strip() for r in pg}
    overlap = len(reg_codes & pg_codes)
    pct = (overlap / max(1, len(pg_codes))) * 100
    aligned = pct > 90
    flag(aligned, f"staff_register.xlsx matches Postgres (>90%): {pct:.0f}%")
else:
    flag(False, "staff_register.xlsx exists")

if mode == "--check":
    print("\n   Any FAIL above explains the problem. Run with --apply to fix.")
    sys.exit(0)

# ---- APPLY ----
changed = []

# Fix admin all-view if needed
if not admin_ok and adm:
    _db.execute("UPDATE users SET is_admin=TRUE WHERE username='admin'", ())
    changed.append("set admin.is_admin=TRUE")

# Rebuild register from Postgres
def md_of(raw):
    if isinstance(raw, dict): return raw
    if isinstance(raw, str):
        try: return json.loads(raw.replace("'", '"'))
        except Exception: return {}
    return {}
rows = []
for r in pg:
    md = md_of(r.get("metadata"))
    rows.append({
        "Staff Code": r.get("staff_code",""), "Staff Name": r.get("full_name",""),
        "Role": r.get("role",""), "Unit": r.get("unit",""),
        "Department": "", "Branch": r.get("unit",""),
        "Region": md.get("region","") or "", "Reports To Code": md.get("reports_to","") or "",
        "Email": "", "Band": "", "Gender": "",
    })
if reg_path.exists():
    shutil.copy2(reg_path, reg_path.with_suffix(f".xlsx.pre_fix_{int(time.time())}"))
pd.DataFrame(rows).to_excel(reg_path, index=False)
changed.append(f"rebuilt staff_register.xlsx ({len(rows)} staff)")

print("   applied:")
for c in changed:
    print(f"     - {c}")
print("\n   >>> NOW RESTART THE API SERVER <<<")
print("   Then re-run:  python alex_fix_visibility.py --check")
print("   All flags should be PASS. Hard-refresh browser; admin should see the pipeline.")
