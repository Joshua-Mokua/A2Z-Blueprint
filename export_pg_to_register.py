#!/usr/bin/env python3
"""Export the true Postgres users table -> data/staff_register.xlsx (the file the roster
and BSC read). Makes the register match Postgres, so committing it lets Alex get the
correct roster by pulling — no DB step on his side.

Maps PG columns + metadata to the register template:
  Staff Code   <- staff_code
  Staff Name   <- full_name
  Role         <- role
  Unit/Branch  <- unit
  Department   <- department
  Region       <- metadata.region (fallback: org_config region for the unit)
  Reports To Code <- metadata.reports_to
  Email/Band/Gender <- as-is

    python export_pg_to_register.py            # dry run — writes a .preview file
    python export_pg_to_register.py --apply    # overwrites data/staff_register.xlsx
"""
import json, shutil, sys, time
from pathlib import Path
import pandas as pd
from utils.db import db as _db

REG = Path("data/staff_register.xlsx")

def md_of(raw):
    if isinstance(raw, dict): return raw
    if isinstance(raw, str):
        for attempt in (raw, raw.replace("'", '"')):
            try: return json.loads(attempt)
            except Exception: pass
    return {}

rows = _db.fetch_all(
    "SELECT staff_code, full_name, role, unit, department, email, band, gender, metadata "
    "FROM users WHERE active = true ORDER BY staff_code") or []
print(f"Postgres active users: {len(rows)}")

out = []
missing_reports = 0
for r in rows:
    md = md_of(r.get("metadata"))
    reports_to = md.get("reports_to", "") or ""
    if not reports_to: missing_reports += 1
    out.append({
        "Staff Code":      r.get("staff_code", ""),
        "Staff Name":      r.get("full_name", ""),
        "Role":            r.get("role", ""),
        "Unit":            r.get("unit", ""),
        "Department":      r.get("department", ""),
        "Branch":          r.get("unit", ""),         # branch == unit in this schema
        "Region":          md.get("region", "") or "",
        "Reports To Code": reports_to,
        "Email":           r.get("email", "") or "",
        "Band":            r.get("band", "") or "",
        "Gender":          (r.get("gender", "") or "").strip(),
    })

df = pd.DataFrame(out)
print(f"built {len(df)} register rows")
print(f"  rows missing Reports To Code: {missing_reports}")
print(f"  sample:\n{df.head(4).to_string(index=False)[:600]}")

apply = "--apply" in sys.argv
if not apply:
    prev = REG.with_suffix(".preview.xlsx")
    df.to_excel(prev, index=False)
    print(f"\n[DRY-RUN] wrote preview -> {prev}")
    print("Open it, confirm names/roles/reports-to look right, then --apply.")
    sys.exit(0)

if REG.exists():
    shutil.copy2(REG, REG.with_suffix(f".xlsx.pre_pgexport_{int(time.time())}"))
df.to_excel(REG, index=False)
print(f"\napplied -> {REG} now matches Postgres ({len(df)} staff).")
print("Next: verify roster reads it, then commit + track for Alex.")
