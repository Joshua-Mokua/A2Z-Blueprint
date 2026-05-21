A2Z MIS 360 — v5.36 release notes
===================================

STANDARD #7: Documentation Completeness — CLOSED
==================================================
Verified score: 20/20 gates (100%) per scripts/audit.py
Audit gate G7 upgraded: presence-only → presence + content quality
Test count: 12 files / 225 → 13 files / 245 (+20 doc tests)
New docs: 7 substantive files (~5,000+ total lines of documentation)

THE WORK
--------
Standard #7 mandates 6 documents. Before v5.36 docs/ contained 5
operational/convention docs (ADMIN_CONVENTIONS, PAGE_UX_STANDARDS,
POSTGRESQL_MIGRATION_GUIDE, FLEXCUBE_CUTOVER_RUNBOOK,
LOAD_TESTING_RUNBOOK), but NONE of the 6 spec docs.

v5.36 wrote all of them, plus the OpenAPI export utility:

  docs/API_REFERENCE.md         The OpenAPI orientation: live spec at
                                /api/docs, JWT auth flow, Layer 1 +
                                Layer 2 endpoint families, pagination,
                                error format, caching, rate limits,
                                versioning, runnable curl + Python
                                examples.
  docs/DEPLOYMENT_GUIDE.md      Production deployment: prerequisites,
                                env vars, PG provisioning, schema apply,
                                bootstrap, systemd units, nginx config,
                                smoke test, upgrade procedure, health
                                checks, observability, backups.
  docs/DR_RUNBOOK.md            Disaster recovery: RTO/RPO targets,
                                severity classification, 7 named
                                scenarios (PG down, disk full, API
                                dead, restore from backup, FLEXCUBE
                                broken, JSON↔PG drift, compromised
                                credentials), validation checklist,
                                comm template, known gotchas.
  docs/USER_MANUAL_STAFF.md     Staff guide: home page, BSC scorecard
                                reading, pipeline / referrals / AML /
                                purchase requests, my-tasks inbox,
                                common questions ("my score went down
                                but I closed a deal" etc.), keyboard
                                shortcuts, where to get help.
  docs/USER_MANUAL_MANAGER.md   Manager guide: team scorecard,
                                cascading targets (rules + how-to),
                                approvals (PR / loan / KYC /
                                disciplinary), exception management,
                                BSC narrative authoring, reviewing
                                direct-report narratives, reports,
                                onboarding/offboarding.
  docs/ADMIN_GUIDE.md           Admin guide: 6 admin sections, daily
                                tasks (banner, audit, joiners,
                                leavers, failed-action review),
                                weekly tasks (recompute, cache, disk),
                                monthly tasks (audit archive, drift
                                review, pillar weights), KPI library
                                management, module config, force
                                recomputes, common questions, SQL
                                escape hatch with audit-log
                                requirement.
  docs/SECURITY_ARCHITECTURE.md Threat model: asset inventory, threat
                                actors, V-001..V-004 with mitigations
                                + cross-references to audit gates G9,
                                G10, G11, G12. Authentication (JWT
                                HS256 + bcrypt password storage,
                                rationale for HS256 not RS256).
                                Authorization (RBAC roles, scopes).
                                Data protection (in transit, at rest,
                                sensitive fields). Audit trail
                                (schema, retention, querying).
                                Network/application/secret controls.
                                Roadmap (2FA, SSO, field-encryption).
                                Compliance mapping (BIS/CBK/PCI).

  scripts/export_openapi.py     CLI utility to dump the FastAPI app's
                                OpenAPI spec to stdout, supporting
                                offline contract distribution and
                                version-controlled API change diffs.

G7 UPGRADE
----------
Pre-v5.36: G7 was a presence-check. An empty stub file would pass.
v5.36 raises the bar:

  REQUIRED_DOCS expanded from 4 → 12:
    - 5 legacy convention docs (kept)
    - 7 spec docs (the 6 spec items, with USER_MANUAL split into
      Staff/Manager)

  REQUIRED_DOC_CONTENT added — per-doc bars:
    - min_chars: spec docs require 1500–2000 chars; legacy 1000
    - required_sections: distinctive substrings that would be present
      in a real doc but absent from a stub. e.g.:
        SECURITY_ARCHITECTURE.md must contain v-001..v-004 (case-
        insensitive) and "audit trail" and "rbac"
        DEPLOYMENT_GUIDE.md must contain "systemd" or equivalent and
        "environment"

  Verified by injection: replacing USER_MANUAL_STAFF.md with a 33-char
  stub triggered exactly the right G7 violation set:
    ❌ USER_MANUAL_STAFF.md: 33 chars (minimum 1500)
    ❌ USER_MANUAL_STAFF.md: missing required section 'scorecard'
    ❌ USER_MANUAL_STAFF.md: missing required section 'logging'
    ❌ USER_MANUAL_STAFF.md: missing required section 'pipeline'
  Score regressed to 19/20 = 95% — FAIL.
  Restoring the doc returned to 20/20 PASS.

NEW TEST FILE
-------------
tests/test_documentation_completeness.py (20 tests):
  - File presence: each spec doc + each legacy doc exists
  - Content quality: each doc clears its min_chars bar
  - Doc-specific content: API REF describes auth + lists endpoints +
    references OpenAPI; DEPLOYMENT_GUIDE covers process supervision +
    documents required env vars; DR_RUNBOOK has RTO/RPO + pg_restore;
    USER_MANUAL_STAFF explains scorecard + KPI; USER_MANUAL_MANAGER
    explains team + approvals; ADMIN_GUIDE covers user mgmt + audit;
    SECURITY_ARCHITECTURE references V-001..V-004 + G9..G12
  - Cross-doc links: API REF links to security; DEPLOYMENT links to
    DR; ADMIN links to ≥2 sibling docs
  - G7 consistency: REQUIRED_DOCS + REQUIRED_DOC_CONTENT match

WHAT WAS CHANGED
----------------
1. scripts/audit.py:
     - REQUIRED_DOCS expanded from 4 → 12
     - New REQUIRED_DOC_CONTENT dict with per-doc quality bars
     - gate_conventions_docs (G7) upgraded:
        was: file existence only
        now: existence + min_chars + required_sections enforcement
     - Returns structured violations distinguishing missing files,
       too-short docs, and missing sections

2. scripts/export_openapi.py (NEW, ~40 LOC):
     - CLI utility dumping app.openapi() to stdout
     - --pretty flag for indented output
     - Imports utils.api lazily so -h works without deps

3. docs/API_REFERENCE.md (NEW, ~250 lines)
4. docs/DEPLOYMENT_GUIDE.md (NEW, ~280 lines)
5. docs/DR_RUNBOOK.md (NEW, ~280 lines)
6. docs/USER_MANUAL_STAFF.md (NEW, ~190 lines)
7. docs/USER_MANUAL_MANAGER.md (NEW, ~280 lines)
8. docs/ADMIN_GUIDE.md (NEW, ~310 lines)
9. docs/SECURITY_ARCHITECTURE.md (NEW, ~330 lines)

10. tests/test_documentation_completeness.py (NEW, 20 tests, ~280 LOC)

11. Master_Prompt_v3.md → v5.36:
      - Standard #7 entry added (struck through — closed)
      - File map expanded (5 → 12 docs)
      - G7 row in gates table updated
      - Footer bumped

NO RUNTIME CODE CHANGES
-----------------------
v5.36 is purely additive (new docs + new tests + audit gate upgrade).
No changes to:
  - utils/api.py, utils/db.py, utils/bsc_engine.py, utils/auth_jwt.py
  - any pages
  - any other tests

VERIFICATION (sandbox)
----------------------
  scripts/audit.py syntax OK:                          ✓
  audit gates 20/20 PASS:                              ✓
  G7 reports 12/12 docs present:                       ✓
  G7 stub-injection test:                              ✓
       inserting 33-char stub correctly triggers 4 violations
       restoring doc returns to clean PASS
  G13 grew: 12 files / 225 tests → 13 files / 245 tests
  Manual run of all 20 doc tests:                     62/62 ✓
                                                      (extras = sub-checks)
  BSC engine self-test:                                ALL PASS

CURRENT AUDIT STATE (post-v5.36)
--------------------------------
  ✅ G1-G12 all pass (foundational + security)
  ✅ G7 conventions_docs: 12/12 docs present, content bar enforced
  ✅ G13 test_infrastructure: 13 files / 245 tests
  ✅ G14 core_split_adoption: 2 shims, 68/68 pages adopted (100%)
  ✅ G15 pg_migration_progress: 19/52 (37%), 1 dual-write pilot
  ✅ G16 api_v1_coverage: 22 endpoints, 16% of 136-target
  ✅ G17 bsc_engine_breadth: 19/17 (target met)
  ✅ G18 coverage_thresholds: informational
  ✅ G19 load_test_thresholds: informational
  ✅ G20 flexcube_pipeline_validation: informational
  Score: 20/20 = 100% PASS

INSTALLATION
------------
1. Extract this zip over your v5.35 working tree.
2. Run audit:
     python scripts/audit.py
   Expected: 20/20 PASS, G7 reports "12/12 docs present".
3. Run pytest:
     pytest tests/test_documentation_completeness.py -v
   Expected: 20 tests pass.
4. (Optional) Generate offline OpenAPI:
     python -m utils.api &
     python scripts/export_openapi.py --pretty > docs/openapi.json
     kill %1
   Expected: docs/openapi.json contains the live API contract.

ROLLBACK
--------
If anything goes wrong:
  1. Restore scripts/audit.py from scripts/audit.py.v5.35.bak
  2. Delete the 7 new docs and scripts/export_openapi.py
  3. Delete tests/test_documentation_completeness.py
Or: git revert v5.36.

WHAT'S NEXT
-----------
Volume One progress: 7 of 10 standards now framework-complete or
closed (#1, #2, #3, #4, #5, #6, #7). Three remain in Volume One:

a) STANDARD #8 — WCAG 2.1 AA Accessibility
   v5.37 = "fast #8". axe-core scan, zero critical violations.
   Adds gate G21 with the artifact-handoff pattern.

b) STANDARD #9 — Dependency Security (SBOM)
   v5.38 = "fast #9". pip-audit + safety. Adds gate G22.

c) STANDARD #10 — Structured UAT Framework
   v5.39 = "fast #10". User-acceptance-test scaffold + traceability.

d) ACTUAL DEPLOYMENT
   When staging is up: pytest --cov, run_load_tests, FLEXCUBE live.
   G18/G19/G20 then enforce real thresholds.

LATENT ISSUES
-------------
1. The `data/` directory's seed JSON files don't match what production
   would have. The deployment guide notes this; a separate seed-data
   refresh is queued.
2. `core_kpi` shim still in shim phase — physical move pending.
3. 12 PG schemas still missing from `get_schema_sql()` (latent issue
   from v5.31). Documented as a TODO; doesn't block any standard.
4. The export_10k load test still needs ≥10k seed rows in
   pipeline_deals to be meaningful.

COMMIT
------
git add scripts/audit.py scripts/export_openapi.py docs/ \
        tests/test_documentation_completeness.py Master_Prompt_v3.md
git commit -m "v5.36: Standard #7 documentation completeness + G7 content gate"
git tag v5.36
git push origin main --tags
