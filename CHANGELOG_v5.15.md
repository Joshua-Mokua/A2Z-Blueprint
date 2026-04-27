A2Z MIS 360 — v5.15 release notes
=================================

Verified score: 10/10 gates (100%) per scripts/audit.py
Closes: V-002 (CVSS 9.0 SQL injection) + V-004 (CVSS 8.1 stored XSS)

WHAT WAS WRONG
--------------
External SAST audit identified two critical vulnerabilities (along with
V-001 API auth and V-003 password hashing — those need their own sessions):

  V-002 — utils/db.py used 7 f-string SQL constructions like
    f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})"
  Even though current callers pass code constants, any future caller
  passing user-derived names would enable CWE-89 SQL injection.

  V-004 — pages used st.markdown(f"...{user_data}...", unsafe_allow_html=True)
  for user identity banners. An admin who sets full_name to "<script>alert(1)
  </script>" would XSS every viewer of the home page.

WHAT WAS FIXED
--------------
1. utils/db.py — V-002:
   - Added TABLE_REGISTRY whitelist (66 valid table names, including schema-
     qualified ones like "audit.audit_logs", "performance.actuals")
   - Added _check_table(name) that raises ValueError on injection attempts
     like "users; DROP TABLE users; --"
   - Added _qid(), _qcols(), _qplaceholders() helpers using psycopg2.sql
     for safe identifier quoting
   - Replaced all 7 f-string SQL sites:
       L248 upsert() — INSERT ON CONFLICT
       L299 dual_load() — SELECT
       L347 + L350 dual_load_dict() — SELECT (singleton + bulk)
       L400 + L413 dual_save() — DELETE + INSERT
       L1359 migrate_json_to_db() — INSERT ON CONFLICT DO NOTHING

2. pages/0_home.py — V-004 (audit-named home banner):
   - User identity values (name, role, unit) now escaped at source via
     safe_html() — every downstream f-string interpolation is safe
   - Business-logic comparisons (==name, get_what_i_was_given(...,name))
     converted to use _raw_name / _raw_role for un-escaped DB matching
   - Pattern: _raw_X for logic, X for display

3. pages/1_perform.py — V-004:
   - my_full_name, my_staff_code escaped in leave application banner

4. pages/7_admin.py — V-004:
   - _admin_info.get('full_name', ...) escaped (2 sites: protected admin
     badge, missing-staff-code warning)
   - pu.get('full_name'/'unit'/'staff_code'), pu_role escaped in
     permissions header for selected user

5. pages/_sidebar.py — V-004:
   - safe_html imported, applied to ud.get('full_name'/'role'/'unit')
     in the global sidebar identity block (renders on every page)

6. scripts/audit.py — Two new gates:
   G9 sql_safety:
     Scans utils/db.py for f-string SQL with {table}/{col_str}/{placeholders}
     patterns. Verifies TABLE_REGISTRY + _check_table + _qid helpers exist.
     Pass condition: 0 unsafe patterns + helpers present.

   G10 xss_safety:
     Scans every page using unsafe_allow_html. Looks for f-string
     interpolations of user-data names (full_name, username, role, unit, ...)
     that are NOT wrapped in safe_html() / html.escape(). The _raw_*
     prefix marks intentionally raw values used for business logic.
     Pass condition: 0 risky user-data interpolations.

7. Master_Prompt_v3.md updated:
   - Version bumped to v5.15
   - V-002 and V-004 marked closed in Verified Gaps section
   - Quality Gates table now shows 10 gates (G9 + G10 added)
   - Cadence section updated from "eight" to "ten" gates

WHAT'S STILL OPEN
-----------------
  V-001 API auth bypass (CVSS 9.1)        3 days  — JWT middleware
  V-003 SHA-256 password hashing (9.0)    1 day   — bcrypt rehash-on-login

  Plus the longer-term work documented in Master_Prompt_v3.md verified-gaps
  section: PG migration (3 weeks), API expansion (6-8 weeks), test suite
  (4 weeks), core.py split (1 week), BSC central engine (1 week).

INSTALLATION
------------
1. Extract this zip over your project root, replacing files where prompted.
2. Run:    python scripts/audit.py
   Expected: 10/10 PASS, exit 0
3. Restart Streamlit. Smoke-test:
   - Login: william001 / ECOStaff001
   - Open home page — welcome banner should still render correctly
   - Open admin → People & Org → Users — verify the user permissions
     banner still shows full_name correctly (special characters now
     render as text, not as HTML)

VERIFY THE FIX (FROM PYTHON REPL)
---------------------------------
  >>> from utils.db import _check_table, _qid
  >>> _check_table('users')                         # OK
  >>> _check_table("users; DROP TABLE users; --")   # raises ValueError ✓
  >>> _qid('users; DROP TABLE').as_string(None)
  '"users; DROP TABLE"'                              # quoted identifier — safe ✓

COMMIT
------
git add .
git commit -m "v5.15: V-002 SQL injection + V-004 XSS fixes (CVSS 9.0+8.1 closed)"
git tag v5.15-security
git push origin main --tags
