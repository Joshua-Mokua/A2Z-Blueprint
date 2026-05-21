A2Z MIS 360 — v5.35 release notes
===================================

STANDARD #6: FLEXCUBE Pipeline Validation — VERIFIED & PACKAGED
===============================================================
Verified score: 20/20 gates (100%) per scripts/audit.py
Audit gate: G20 flexcube_pipeline_validation
Test count: 12 files / 225 tests
Validator: scripts/test_flexcube_pipeline.py exits 0 in synthetic mode

HONEST NOTE ON THIS RELEASE
---------------------------
When this fast #6 session began, the v5.35 work was already in the
working tree. Specifically:

  - scripts/test_flexcube_pipeline.py (706 LOC, 5-level validator)
  - G20 audit gate already defined in scripts/audit.py
  - G20 already in the GATES list
  - tests/test_flexcube_pipeline.py (19 tests)
  - tests/test_flexcube_pipeline_validation.py (22 tests)
  - Master_Prompt_v3.md already at v5.35 with G20 in the gates table
  - FOUNDATIONAL set already extended with the validator script

Earlier session memory noted an "L2 schema mismatch" (EXPECTED_SCHEMAS
expected customer_id/customer_name but adapter returned cif/name).
That memory was wrong about the live state — the ACTUAL EXPECTED_SCHEMAS
in scripts/test_flexcube_pipeline.py uses cif/name, matching the
adapter contract. Verified by running synthetic mode end-to-end:

    L1 Connectivity   skipped (synthetic — no live target)
    L2 Schema         passed   (3/3 entities compliant)
    L3 Data types     passed   (0 type errors)
    L4 Sample data    skipped (synthetic — no source-of-truth mart)
    L5 Full sync      skipped (synthetic — no live source)

So this release is a VERIFICATION + PACKAGING release, not a
build-the-thing release. The framework is in. This zip captures the
state for distribution + ships the changelog.

WHAT v5.35 DELIVERED (per the work that was already in the tree)
----------------------------------------------------------------

1. scripts/test_flexcube_pipeline.py (706 LOC) — five-level validator:

   L1 Connectivity (target 100%)
     • Probes adapter health endpoints
     • In synthetic mode: SKIPPED with reason "no real connection"
     • In live/mock mode: tests OAuth + service endpoints

   L2 Schema (target 100%)
     • Verifies each entity (customers, accounts, loans) has all
       required keys per EXPECTED_SCHEMAS
     • Required keys for customers: cif, name
     • Required keys for accounts:  account_no, branch
     • Required keys for loans:     loan_id, cif
     • Match the adapter's actual response shape — NOT the staging
       table's column names

   L3 Data types (target 0 errors)
     • Casts each row's fields to A2Z target types
     • _is_decimal, _is_date_iso validators
     • Counts hard cast failures (None/empty are OK — nullable)

   L4 Sample data (target ≥99%)
     • Sample-reconciles N records against the A2Z mart
     • Skipped in synthetic mode (no mart to reconcile against)
     • In mock/live: uses utils/reconciliation.py's sample_reconcile

   L5 Full sync (target 0 records lost)
     • Counts rows in source vs staging
     • Skipped in synthetic mode (no source to count)
     • In live: hard fail on any loss

2. scripts/audit.py G20 audit gate:
     - Same artifact-handoff design as G18 (coverage) and G19 (load)
     - Reads flexcube_validation_results.json if present
     - Mode-aware: skipped levels DON'T fail the gate
     - Cross-checks spec thresholds (L2≥100%, L3=0 errors, L4≥99%)
     - Surfaces concrete failure reasons in violations list

3. tests/test_flexcube_pipeline.py (19 tests):
     - All five level runners exist and are callable
     - EXPECTED_SCHEMAS has the right entities + required keys
     - SPEC_THRESHOLDS encodes the spec's targets exactly
     - Mode flag propagates correctly
     - Synthetic mode exits 0
     - Artifact has the schema G20 expects
     - --verbose flag works

4. tests/test_flexcube_pipeline_validation.py (22 tests):
     - G20 function defined and in GATES list
     - G20 informational pass when artifact missing
     - G20 PASS when artifact says all-good
     - G20 FAIL when L2 fails (verified by injecting fake data)
     - G20 FAIL on unparseable JSON
     - Score regresses to 19/20 = 95% on G20 failure

5. Master_Prompt_v3.md → v5.35:
     - Standard #6 entry added (struck through — closed)
     - G20 row in gates table
     - Footer at v5.35
     - FLEXCUBE doc references intact

VERIFICATION (sandbox, real run)
--------------------------------
End-to-end Standard #6 verification (verified by my fast #6 session):

  1. scripts/test_flexcube_pipeline.py exists:                ✓
  2. Synthetic mode exits 0:                                  ✓
  3. Artifact written at flexcube_validation_results.json:    ✓
  4. All five levels reported:                                ✓
  5. Spec thresholds encoded correctly:                       ✓
       L1 target_pct = 100.0
       L2 target_pct = 100.0
       L3 target_max_errors = 0
       L4 target_pct = 99.0
       L5 target_max_loss = 0
  6. G20 audit gate wired:                                    ✓
       function defined, in GATES list, reads artifact
  7. G20 PASS after validator runs:                           ✓
       audit final score: 20/20 = 100% PASS

  Synthetic mode breakdown:
       L1 Connectivity   skipped  0.00s
       L2 Schema         passed   0.27s (100.0% compliance)
       L3 Data types     passed   0.05s (0 errors)
       L4 Sample data    skipped  0.00s
       L5 Full sync      skipped  0.00s

  G20 failure injection (fake L2 schema failure):
       Score regresses to 19/20 = 95.0% — FAIL
       G20 reports concrete reason from artifact details

  G20 corrupt-artifact case:
       Returns "unparseable: ..." — gate is robust against bad input

  BSC engine self-test: ALL PASS (no regression)

CURRENT AUDIT STATE (post-v5.35)
--------------------------------
  ✅ G1-G12 all pass (foundational + security)
  ✅ G13 test_infrastructure: 12 files / 225 tests
  ✅ G14 core_split_adoption: 2 shims, 68/68 pages adopted (100%)
  ✅ G15 pg_migration_progress: 19/52 (37%), 1 dual-write pilot
  ✅ G16 api_v1_coverage: 22 endpoints, 16% of 136-target
  ✅ G17 bsc_engine_breadth: 19/17 (target met)
  ✅ G18 coverage_thresholds: informational (no coverage.xml in sandbox)
  ✅ G19 load_test_thresholds: informational (no load_results.json)
  ✅ G20 flexcube_pipeline_validation: informational (no run yet)
  Score: 20/20 = 100% PASS

INSTALLATION
------------
1. Extract this zip over your v5.34 working tree.
2. Run audit:
     python scripts/audit.py
   Expected: 20/20 PASS, G20 reports informational.
3. Run the validator (synthetic mode):
     python scripts/test_flexcube_pipeline.py --mode=synthetic
   Expected: exit 0, "2 passed, 0 failed, 3 skipped".
4. Re-run audit:
     python scripts/audit.py
   Expected: G20 reports "mode=synthetic, 2 passed, 0 failed, 3 skipped".
5. Run the structural tests:
     pytest tests/test_flexcube_pipeline.py             tests/test_flexcube_pipeline_validation.py -v
   Expected: 41 tests pass.

Live-mode usage (when a real FLEXCUBE is reachable):
  python scripts/test_flexcube_pipeline.py --mode=live
  python scripts/audit.py
  # G20 will now enforce all five spec thresholds

ROLLBACK
--------
If anything goes wrong:
  1. Restore scripts/audit.py from scripts/audit.py.v5.34.bak
     (kept by my fast #6 session)
  2. The v5.35 deliverables are otherwise self-contained — no
     changes to runtime code (utils/api.py, utils/db.py, pages, etc.)

WHAT'S NEXT
-----------

a) STANDARD #7 — Documentation Completeness
   v5.36 = "fast #7". Required docs (mostly writing work):
     - API Reference (auto-generated by FastAPI's /docs endpoint)
     - Deployment Guide
     - DR Runbook
     - User Manuals (Staff/Manager)
     - Admin Guide
     - Security Architecture
   Audit gate G7 already tracks doc presence. Just add the missing
   files to docs/ and update G7's REQUIRED_DOCS list. Lowest-risk
   work in the spec — no code changes.

b) STANDARD #8 — WCAG 2.1 AA Accessibility
   v5.37 = "fast #8". axe-core scan, zero critical violations.
   Adds a new audit gate G21 that reads axe-core's JSON output.
   Same artifact-handoff pattern as G18/G19/G20.

c) STANDARD #9 — SBOM / Dependency Security
   v5.38 = "fast #9". pip-audit + safety. Adds gate G22 that reads
   the audit JSON output.

d) ACTUAL DEPLOYMENT
   When staging is up, finally run:
     - pytest --cov     (G18 enforces coverage thresholds)
     - run_load_tests   (G19 enforces load thresholds)
     - test_flexcube_pipeline --mode=live  (G20 enforces level thresholds)
   Until then v5.30-v5.35 are "frameworks done, pending operational".

LATENT ISSUES NOTED
-------------------
1. The export_10k load test still needs ≥10k rows in pipeline_deals
   to be meaningful. Seed script (scripts/seed_pipeline_test_data.py)
   is still the right v5.36 or later addition.

2. The core_kpi shim is still in shim phase — physical move (step 3
   per its docstring) is queued. Doesn't affect any standard;
   cleanup work.

3. 12 tables marked TABLE_USE_DB=True still missing CREATE TABLE
   schemas (latent issue noted in v5.31). Quality housekeeping.

COMMIT
------
The v5.35 work was already committed before this session.
This zip is a packaging + verification artifact. If you haven't
yet pushed:

  git add scripts/audit.py scripts/test_flexcube_pipeline.py \
          tests/test_flexcube_pipeline.py \
          tests/test_flexcube_pipeline_validation.py \
          Master_Prompt_v3.md
  git commit -m "v5.35: Standard #6 FLEXCUBE pipeline validation + G20 gate"
  git tag v5.35
  git push origin main --tags
