#!/usr/bin/env python3
"""Diagnose the lockout: what logins actually exist, in both stores."""
import json, os
from pathlib import Path

print("=== data/users.json (LOGIN store) ===")
p = Path("data/users.json")
if p.exists():
    u = json.loads(p.read_text(encoding="utf-8"))
    users = u.get("users", u) if isinstance(u, dict) else u
    if isinstance(users, dict):
        for un, rec in list(users.items())[:20]:
            print(f"  {un:16} active={rec.get('active')}  role={rec.get('role','')[:30]}  code={rec.get('staff_code','')}")
        print(f"  ... total {len(users)} logins")
    else:
        print("  unexpected shape:", type(users))
else:
    print("  MISSING")

print("\n=== PostgreSQL users table ===")
try:
    from utils.db import db
    rows = db.fetch_all("SELECT username, role, staff_code, active FROM users ORDER BY username") or []
    for r in rows[:20]:
        try:
            print(f"  {r['username']:16} active={r['active']}  role={str(r['role'])[:30]}  code={r['staff_code']}")
        except Exception:
            print(" ", r)
    print(f"  ... total {len(rows)} rows")
except Exception as e:
    print("  DB error:", e)
