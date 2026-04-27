A2Z MIS 360 — v5.14 release notes
=================================

Verified score: 8/8 gates (100%) per scripts/audit.py
Previous claim: 92% (self-graded, unverified)

WHAT WAS WRONG
--------------
External audits found the v5.13 score was self-graded and over-counted.
Verified violations:
  - 5 admin/shared files with direct json.loads/write_text (bypassing a2z_db)
  - 32_ifrs9.py and 53_irrbb.py had no audit_log calls
  - 7_admin.py People & Org section had 8 sub-tabs (over the 7-tab limit)
  - POSTGRESQL_MIGRATION_GUIDE.md was referenced but didn't exist
  - The renderer crashed on number_input fields with min > 0 and no stored value

WHAT WAS FIXED IN v5.14
-----------------------
1. Renderer fix from previous session:
   - pages/_admin_module_renderer.py
   - safe-default resolution: stored value > field default > min > 0
   - clamps stored values into [min, max] in case spec tightened

2. Direct I/O routed through a2z_db:
   - pages/_admin_sprint.py        (6 sites: FTP, RCSA, propositions, CAB)
   - pages/_shared.py              (1 site, with bootstrap fallback)
   - pages/_admin_postgres.py      (1 site)
   - pages/_admin_module_config.py (2 sites: load + save)
   - pages/_admin_cutover.py       (4 sites: checklist + cutover + rollback)

3. Audit logging added to read-only sensitive pages:
   - pages/32_ifrs9.py             (added PAGE_VIEWED audit_log)
   - pages/53_irrbb.py             (added PAGE_VIEWED audit_log)

4. Tab restructure:
   - pages/7_admin.py: People & Org reduced 8 -> 7 sub-tabs
     (Dept Manager + Branch Manager merged into one Org structure tab
      with internal radio toggle)

5. New automated audit script:
   - scripts/audit.py
   - 8 verifiable gates: G1 syntax, G2 direct_io, G3 audit_coverage,
     G4 tab_counts, G5 admin_sections, G6 registry_coverage,
     G7 conventions_docs, G8 bsc_contract
   - JSON output mode for CI integration
   - Exit 0 on PASS, 1 on FAIL — drop-in for CI/CD

6. Missing convention doc created:
   - docs/POSTGRESQL_MIGRATION_GUIDE.md
   - Per-table flag-flip pattern, priorities, foundational exemptions

7. Master prompt v3.0:
   - Master_Prompt_v3.md
   - Incorporates the addendum's 10 mandatory execution standards
   - State of Play replaces self-grading with mandatory `scripts/audit.py`
   - Verified gaps section (security, PG migration, API expansion) replaces
     "zero red items" with honest, sized future work
   - Recurring audit cadence specified (commit/monthly/quarterly)

WHAT'S STILL OPEN (the audit script doesn't and can't catch these)
------------------------------------------------------------------
These need their own dedicated work, not flag flips:

  - API authentication (CVSS 9.1, 3 days)
  - SHA-256 -> bcrypt password hashing (CVSS 9.0, 1 day)
  - SQL injection patterns in db.py (CVSS 9.0, 4 hours)
  - PG migration of 31 remaining tables (3 weeks)
  - API expansion 12 -> 144 endpoints (6-8 weeks)
  - Test suite + CI/CD (4 weeks)
  - core.py 6,596-line split (1 week)
  - BSC central engine implementation (1 week)
  - UI design system + component library (4 weeks)

The audit script reports BSC writers as "0 found, 0 compliant" because the
central BSC integration engine isn't built yet. That's the correct signal:
when modules start using the contract, the gate will start counting them.

INSTALLATION
------------
1. Extract this zip over your project root, replacing files where prompted.
2. Run:    python scripts/audit.py
   Expected: 8/8 PASS, exit 0
3. Restart Streamlit. Smoke-test:
   - Login: william001 / ECOStaff001
   - Open Admin -> People & Org section -> verify 7 sub-tabs
     including the new "Org structure" tab with Departments/Branches toggle
   - Open Admin -> Modules -> Module Config Centre -> Registered configs
     verify the renderer no longer crashes on Pipeline (stale_days has min=7)

COMMIT
------
git add .
git commit -m "v5.14: audit fixes, automated audit script, master prompt v3.0"
git tag v5.14-audit-fixes
git push origin main --tags
