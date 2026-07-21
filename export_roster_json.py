#!/usr/bin/env python3
"""Export the true Postgres roster -> data/staff_roster.json for Alex to load into HIS
Postgres. Includes everything needed for login + hierarchy: username, staff_code,
full_name, role, department, unit, band, gender, active, and metadata (region, reports_to).

Passwords: exported as password_hash so logins work identically. If you'd rather NOT ship
hashes, pass --no-hashes and Alex's loader will set the standard rule password
(EcoStaff+last4) via must_change_password. Default ships hashes so logins match yours.

    python export_roster_json.py            # includes password_hash (logins match)
    python export_roster_json.py --no-hashes
"""
import json, sys
from pathlib import Path
from utils.db import db as _db

include_hash = "--no-hashes" not in sys.argv

cols = ("username, staff_code, full_name, email, role, department, unit, band, gender, "
        "active, is_admin, can_view_all, must_change_password, metadata")
if include_hash:
    cols = "password_hash, " + cols

rows = _db.fetch_all(f"SELECT {cols} FROM users ORDER BY staff_code") or []
# exclude admin/system rows in Python (avoids SQL % placeholder issues)
def _is_admin_row(r):
    role = str(r.get("role","")).strip().lower()
    code = str(r.get("staff_code","")).strip().upper()
    return role == "admin" or code.startswith("ADMIN")
rows = [r for r in rows if not _is_admin_row(dict(r))]
print(f"exporting {len(rows)} users (hashes: {include_hash})")

out = []
for r in rows:
    d = dict(r)
    # normalise metadata to a dict
    md = d.get("metadata")
    if isinstance(md, str):
        try: md = json.loads(md.replace("'", '"'))
        except Exception: md = {}
    d["metadata"] = md or {}
    out.append(d)

payload = {
    "version": 1,
    "source": "postgres_export",
    "count": len(out),
    "includes_hashes": include_hash,
    "users": out,
}

dest = Path("data/staff_roster.json")
dest.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
print(f"wrote {dest} ({dest.stat().st_size:,} bytes)")
print(f"sample: {out[0]['staff_code']} {out[0]['full_name']} / {out[0]['role']}")
print("\n-> ship data/staff_roster.json to Alex with load_roster_json.py")
