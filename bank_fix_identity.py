#!/usr/bin/env python3
"""
BANK-SERVER identity fix + diagnosis. Run on the BANK server (where Violet/Humphrey/etc
log in). Explains and fixes the whole access problem in one run.

ROOT CAUSE (confirmed on the dev machine):
  - Login reads role/flags from data/users.json (the LOGIN store).
  - Admin edits in the UI write POSTGRES and call project_quietly() to sync users.json.
  - If that sync ever failed (project_quietly swallows errors), users.json went stale,
    so amended roles (e.g. Violet: Cluster Manager -> Branch Manager) never reached login.

This script:
  1. Shows, for key people, their role in POSTGRES vs users.json (the mismatch = the bug).
  2. Runs the projection explicitly (rebuilds users.json from Postgres; passwords untouched).
  3. Re-shows the comparison to prove it synced.

Then affected users sign out / in and get their correct role (and managers get their queues).

    python bank_fix_identity.py            # diagnose only (no writes)
    python bank_fix_identity.py --apply    # diagnose, run projection, verify
"""
import sys, json
from pathlib import Path

CODES = ["KE395", "KE1298", "KE0406", "KE1347", "KE555", "KE1333"]  # Violet, Humphrey, Benjamin, Josh, Mary, Rabecca
DATA = Path(__file__).resolve().parent / "data"

def load_users_json():
    p = DATA / "users.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "users" in raw:
        raw = raw["users"]
    out = {}
    items = raw.values() if isinstance(raw, dict) else raw
    for u in items:
        if isinstance(u, dict):
            out[str(u.get("staff_code", ""))] = u
    return out

def snapshot(tag):
    from utils.db import db as _db
    print(f"\n=== {tag} ===")
    uj = load_users_json()
    rows = _db.fetch_all(
        "SELECT staff_code, full_name, role, is_admin FROM users "
        "WHERE staff_code = ANY(%s)", (CODES,)) or []
    pg = {str(r["staff_code"]): r for r in rows}
    print(f"   {'CODE':8} {'NAME':24} {'POSTGRES role':28} {'users.json role':28} MATCH")
    for c in CODES:
        p = pg.get(c, {})
        j = uj.get(c, {})
        pr = str(p.get("role", "—"))
        jr = str(j.get("role", "MISSING"))
        match = "OK" if pr == jr else "*** MISMATCH ***"
        name = str(p.get("full_name", j.get("full_name", "?")))[:22]
        print(f"   {c:8} {name:24} {pr[:26]:28} {jr[:26]:28} {match}")
    # also admin flags
    print("\n   admin flags (Postgres):")
    for c in CODES:
        p = pg.get(c, {})
        print(f"      {c}: is_admin={p.get('is_admin')}")

snapshot("BEFORE — Postgres vs users.json")

if "--apply" not in sys.argv:
    print("\n[DIAGNOSE ONLY] Re-run with --apply to sync users.json from Postgres.")
    print("A *** MISMATCH *** above is the bug: login reads users.json, which is stale.")
    sys.exit(0)

print("\n=== running projection (rebuild users.json from Postgres; passwords untouched) ===")
from utils.staff_projection import export_logins_from_db, export_register_from_db
try:
    n = export_register_from_db()
    print(f"   register rebuilt: {n} rows")
except Exception as e:
    print(f"   register rebuild FAILED: {e}")
try:
    r = export_logins_from_db()
    print(f"   logins: +{r['added']} new, {r['updated']} refreshed, {r['deactivated']} deactivated")
except Exception as e:
    print(f"   LOGIN projection FAILED: {e}")
    print("   ^ THIS is why users.json was stale. The error above is the real cause.")
    sys.exit(1)

# force UserManager to re-read
try:
    from utils.core import UserManager
    UserManager().reload_users()
    print("   UserManager reloaded from disk.")
except Exception as e:
    print(f"   (reload note: {e})")

snapshot("AFTER — should now MATCH")
print("\nDONE. Restart the API server, then have the affected people SIGN OUT and back in.")
print("Their tokens are re-issued with the correct role; managers get their queues.")
