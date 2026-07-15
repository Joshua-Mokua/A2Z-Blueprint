#!/usr/bin/env python3
"""Upload the staff register to PostgreSQL from the command line.

Hits the same endpoints as Admin > Staff > Upload:
    POST /api/admin/staff/upload/preview   validates, changes nothing
    POST /api/admin/staff/upload/apply     DELETEs users not in --keep, inserts the sheet

Preview ALWAYS runs first; --apply is refused if preview reports errors.

    python upload_staff.py --user william0001 --password ...
    python upload_staff.py --user william0001 --password ... --apply

    --keep  comma-separated usernames to preserve (your test logins).
            Defaults to the A2Z test set. Anything NOT in this list is DELETED.
"""
import argparse, base64, json, os, sys
import requests

DEFAULT_KEEP = ["william0001", "frank0731", "lilian0068", "ellen0732",
                "thomas0169", "nicholas0002", "emmanuel0003", "admin"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:8502")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--file", default="data/STAFF_UPLOAD_FILLED.xlsx")
    ap.add_argument("--keep", default=",".join(DEFAULT_KEEP))
    ap.add_argument("--apply", action="store_true", help="actually write PostgreSQL")
    a = ap.parse_args()

    if not os.path.exists(a.file):
        print(f"MISSING {a.file}"); sys.exit(1)
    keep = [k.strip() for k in a.keep.split(",") if k.strip()]

    print(f"host   : {a.host}")
    print(f"file   : {a.file}  ({os.path.getsize(a.file):,} bytes)")
    print(f"keep   : {keep}")
    print(f"mode   : {'APPLY (writes PostgreSQL)' if a.apply else 'PREVIEW ONLY'}\n")

    r = requests.post(f"{a.host}/api/auth/login",
                      json={"username": a.user, "password": a.password}, timeout=30)
    if r.status_code != 200:
        print(f"LOGIN FAILED {r.status_code}: {r.text[:200]}"); sys.exit(1)
    tok = r.json().get("access_token")
    H = {"Authorization": f"Bearer {tok}"}
    me = requests.get(f"{a.host}/api/auth/me", headers=H, timeout=30)
    if me.status_code == 200:
        m = me.json()
        print(f"logged in as {m.get('username')} [{m.get('role')}]\n")

    b64 = base64.b64encode(open(a.file, "rb").read()).decode()
    body = {"filename": os.path.basename(a.file), "content_b64": b64, "keep": keep}

    print("--- PREVIEW ---")
    r = requests.post(f"{a.host}/api/admin/staff/upload/preview", headers=H, json=body, timeout=120)
    if r.status_code != 200:
        print(f"PREVIEW FAILED {r.status_code}: {r.text[:600]}"); sys.exit(1)
    p = r.json()
    if p.get("summary"):
        print(json.dumps(p["summary"], indent=2)[:1500])
    if not p.get("ok"):
        print(f"\nVALIDATION FAILED — {len(p.get('errors') or [])} error(s):")
        for e in (p.get("errors") or [])[:25]:
            print(f"   {e}")
        print("\nNothing was written. Fix the sheet and re-run.")
        sys.exit(1)
    print("\nvalidation OK")

    if not a.apply:
        print("\n[PREVIEW ONLY] re-run with --apply to write PostgreSQL.")
        return

    print("\n--- APPLY ---")
    r = requests.post(f"{a.host}/api/admin/staff/upload/apply", headers=H, json=body, timeout=300)
    if r.status_code != 200:
        print(f"APPLY FAILED {r.status_code}: {r.text[:600]}"); sys.exit(1)
    d = r.json()
    print(f"  users before : {d.get('before')}")
    print(f"  applied      : {d.get('applied')}")
    print(f"  users after  : {d.get('after')}")
    print(f"  preserved    : {d.get('preserved')}")
    if d.get("failed_count"):
        print(f"\n  !! {d['failed_count']} row(s) FAILED to insert — first reasons:")
        for f in (d.get("failed") or [])[:8]:
            print(f"       {f}")
    print("\nPostgreSQL is now the system of record. The projection has rebuilt")
    print("data/staff_register.xlsx and data/users.json from it — check the uvicorn")
    print("console for the [staff_projection] lines.")
    print("\nNEXT: python scripts/test_a2z_smoke.py    (expect Portfolio failures until CBS is re-tagged)")

if __name__ == "__main__":
    main()
