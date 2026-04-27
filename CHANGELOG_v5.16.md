A2Z MIS 360 — v5.16 release notes
=================================

Verified score: 11/11 gates (100%) per scripts/audit.py
Closes: V-003 (CVSS 9.0 SHA-256 password hashing)

WHAT WAS WRONG
--------------
The audit said V-003 needed a 1-day rebuild. When I read core.py I found
the runtime bcrypt path was already in place:

  hash_pw()       — bcrypt rounds=12 with SHA-256 fallback
  verify_pw()     — handles both bcrypt and legacy SHA-256
  authenticate()  — rehash-on-login pattern
  add_user()      — uses hash_pw()
  change_password() — uses hash_pw()

What was missing:

  - Bootstrap _load() and _defaults() seeded admin/manager/staff with
    raw hashlib.sha256(...) hashes instead of going through hash_pw().
    This meant first-time deployment created weak hashes that only got
    upgraded on user login.

  - pages/7_admin.py had two more sites: bulk staff import (L715) and
    admin account restoration button (L796).

  - No audit gate caught any of this. A future regression introducing
    fresh SHA-256 wouldn't trip a build.

WHAT WAS FIXED
--------------
1. utils/core.py — module-level helper:
   - Added _hash_password() above UserManager class
   - bcrypt rounds=12, SHA-256 fallback only if bcrypt unimportable
   - Fixed 4 bootstrap sites: L5789 (admin in _load),
     L5816 (admin in _defaults), L5823 (manager1), L5830 (staff1)
   - hash_pw() instance method now delegates to _hash_password() —
     one implementation everywhere

2. pages/7_admin.py — admin UI password-creation sites:
   - Bulk staff import: _hl.sha256(pwd.encode()) → um.hash_pw(pwd)
   - Admin account restoration: hashlib.sha256(b"admin123") → um.hash_pw("admin123")

3. scripts/audit.py — G11 password_safety gate:
   - Verifies bcrypt is in requirements.txt
   - Scans every .py file for password-related SHA-256 calls
   - Recognises legitimate exception sites (the fallback inside
     _hash_password and the legacy verify path inside verify_pw)
   - Pass condition: 0 unsafe sites + bcrypt in deps

4. Master_Prompt_v3.md updated:
   - Version v5.15 → v5.16
   - V-003 marked closed in Verified Gaps
   - Quality Gates table now shows 11 gates
   - Cadence section updated from "ten" to "eleven"

WHAT'S STILL OPEN
-----------------
  V-001 API auth bypass (CVSS 9.1)        3 days  — JWT middleware
  Plus PG migration (3 weeks), API expansion (6-8 weeks), test suite
  (4 weeks), core.py split (1 week), BSC central engine (1 week).

V-001 is now the only remaining critical CVE. After it, all four
critical security findings are closed.

INSTALLATION
------------
1. Extract this zip over your project root, replacing files where prompted.
2. Run:    python scripts/audit.py
   Expected: 11/11 PASS, exit 0
3. Restart Streamlit. Smoke-test:
   - Existing users: log in normally — first login auto-rehashes their
     SHA-256 to bcrypt (this was already in v5.13's authenticate())
   - First-time deployment: admin/manager1/staff1 default users now
     have bcrypt hashes from the moment they're created
   - Admin → People & Org → Bulk staff import: imported users now get
     bcrypt hashes
   - Admin → restoration of deleted admin account uses bcrypt

VERIFY THE FIX (FROM PYTHON REPL)
---------------------------------
  >>> from utils.core import _hash_password
  >>> h1 = _hash_password("admin123")
  >>> h1.startswith("$2b$") or h1.startswith("$2a$")  # True with bcrypt installed
  True
  >>> _hash_password("admin123") != _hash_password("admin123")  # different salt
  True

COMMIT
------
git add .
git commit -m "v5.16: V-003 password hashing fix — bcrypt in bootstrap (CVSS 9.0 closed)"
git tag v5.16-bcrypt
git push origin main --tags
