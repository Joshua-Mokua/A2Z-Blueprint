#!/usr/bin/env python3
"""ALEX RUNS THIS on the bank server. Fixes the staff split-brain: rebuilds
staff_register.xlsx FROM his (now correct) Postgres, so the pipeline scope tree stops
using stale test staff. Prints ONLY pass/fail flags (no data), which are safe to relay.

The problem: app reads staff from TWO places — admin=Postgres (loader fixed this) but
pipeline scope=staff_register.xlsx (gitignored, still test data). This aligns the xlsx.

    python alex_align_and_check.py --check     # read-only: shows what's mismatched
    python alex_align_and_check.py --apply     # rebuild xlsx from Postgres, then restart API
"""
import sys, json
from pathlib import Path

def flag(ok, label):
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}")

mode = "--apply" if "--apply" in sys.argv else "--check"
print(f"=== staff-source alignment ({mode}) — no names printed, only flags ===\n")

from utils.db import db as _db

# 1. Postgres staff count (should be ~362 real, not test)
pg = _db.fetch_all("SELECT staff_code, full_name, role, unit, metadata FROM users "
                   "WHERE UPPER(COALESCE(role,''))<>'ADMIN'") or []
flag(len(pg) > 300, f"Postgres has >300 staff (got {len(pg)})")

# 2. register xlsx
reg_path = Path("data/staff_register.xlsx")
reg_exists = reg_path.exists()
flag(reg_exists, "staff_register.xlsx exists")

import pandas as pd
if reg_exists:
    reg = pd.read_excel(reg_path).fillna("")
    reg_codes = set(reg["Staff Code"].astype(str).str.strip()) if "Staff Code" in reg.columns else set()
    pg_codes = {str(r.get("staff_code","")).strip() for r in pg}
    overlap = len(reg_codes & pg_codes)
    pct = (overlap / max(1, len(pg_codes))) * 100
    flag(pct > 90, f"register matches Postgres staff (>90%): got {pct:.0f}% overlap")
    print(f"        (register has {len(reg_codes)} codes, Postgres {len(pg_codes)}, overlap {overlap})")
    aligned = pct > 90
else:
    aligned = False

if mode == "--check":
    print("\n   If the overlap FAILED, the register is stale (test staff) and the")
    print("   pipeline scope tree is built from it. Run with --apply to rebuild it.")
    sys.exit(0)

# --apply: rebuild register from Postgres
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
import shutil, time
if reg_exists:
    shutil.copy2(reg_path, reg_path.with_suffix(f".xlsx.pre_align_{int(time.time())}"))
pd.DataFrame(rows).to_excel(reg_path, index=False)
flag(True, f"rebuilt staff_register.xlsx from Postgres ({len(rows)} staff)")
print("\n   NOW: restart the API server. Then pipeline scope uses the correct staff.")
print("   Re-run with --check to confirm overlap is PASS.")
