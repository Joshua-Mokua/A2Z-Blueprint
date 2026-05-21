# A2Z MIS 360 — Consolidated v10.193 → v10.264 — APPLY INSTRUCTIONS

**Consolidated zip date:** 2026-05-07
**Audit baseline:** 163/163 PASS (gates G1–G163)
**Session window:** v10.193 (cockpit absorption) → v10.264 (CBK reports closure)
**Closed sub-campaigns this session:** 4

This zip supersedes any earlier v10.193 → v10.X consolidated zips.
Apply this single zip to bring your working copy to the v10.264 state.

---

## 1. Quick apply — preserve directory structure

```bash
cd ~/A2Z-Blueprint  # your working copy

# Backup first
cp -r ~/A2Z-Blueprint ~/A2Z-Blueprint.backup-pre-v10.264

# Unzip preserving directory structure
unzip -o a2z_v10.193_to_v10.264_consolidated.zip

# This places:
#   pages/*.py + pages/_manifest.json
#   utils/*.py
#   scripts/*.py
#   docs/*.md
#   data/*.json
#   sql/*.sql           (also copy to repo root if your workflow expects it there)
```

---

## 2. Audit verification (FIRST after apply)

```bash
cd ~/A2Z-Blueprint
python scripts/audit.py
```

**Expected output:**
```
========================================================================
  Score: 163/163 gates = 100.0% — PASS
========================================================================
```

If audit fails, do NOT proceed to apply data/PG changes. Roll back and
investigate.

---

## 3. PG migration — apply DDL + run migrators (OPTIONAL)

This step is needed only if you want to migrate data into PostgreSQL.

### 3a. Apply DDL files in order

```bash
psql -d a2z_mis360 -f sql/create_tables_v10.253.sql  # +5 tables
psql -d a2z_mis360 -f sql/create_tables_v10.255.sql  # +5 tables
psql -d a2z_mis360 -f sql/create_tables_v10.257.sql  # +5 tables
psql -d a2z_mis360 -f sql/create_tables_v10.261.sql  # +4 tables (partnership cluster)
```

After applying all 4, you'll have **31 tables in DDL** (was 12 at session start).

### 3b. Run the migrators (top-15 high-value tables)

```bash
export A2Z_USE_DB=true
export A2Z_DB_HOST=localhost
export A2Z_DB_NAME=a2z_mis360
export A2Z_DB_USER=a2z_app
export A2Z_DB_PASSWORD="<your password>"

python scripts/migrate_to_postgres.py
```

**Expected:** 17 migrators run, populating the top-15 high-value tables
(plus the 2 original: bank_targets + baselines). Partnership cluster
migrators ship in v10.265+ (DDL exists, migrators TBD).

---

## 4. CBK Returns Centre — verify all 8 packages live

After unzipping, navigate to **CBK Returns Centre → Submit Return**:

```
Submit Return
├── 📝 Manual Submission
├── 🤖 BSD Auto-Generators (4 sub-tabs: BSD-1/2/3/17)
└── 🛡️ Risk-Based Auto-Generators (5 sub-tabs: SBL/LXP/FXE/IRR/OPR)
```

Each Risk-Based tab should:
1. Load with default illustrative inputs
2. Have a "Generate <code>" primary button
3. Compute + display 4 metric tiles + severity badge on click
4. Show "Framework refs + raw output" expander
5. Log the generation event to audit log

If any tab fails, check that `utils/cbk_regulatory_reporting.py` is
the engine module (8 generate_*() methods present).

---

## 5. Audit gate suite — three ratchets active

After apply, the audit will report:

```
G161 — module_path_dept_aligned                      Boolean
G162 — tenant_identity_hardcoding (kaizen, decrease) Baseline: 3,662
G163 — pg_migration_progress (kaizen, INVERSE)       Baseline: 27 DDL, 17 migrators
```

These three are STRUCTURAL INVARIANTS:
- **G161** — every page's module_path matches department_primary
- **G162** — tenant hardcoding count may only DECREASE (allows refactors)
- **G163** — PG migration counts may only INCREASE (prevents deletion drift)

Future work passes these by default. Drift requires explicit re-baselining.

---

## 6. Memory updates (Joshua action)

```diff
- "5/8 CBK reports remaining"
+ "All 8/8 CBK regulatory return packages wired in UI 
+  (BSD-1/2/3/17 + SBL/LXP/FXE/IRR/OPR via v10.262-v10.264 sub-campaign).
+  Engine in utils/cbk_regulatory_reporting.py;
+  UI in pages/74_cbk_returns.py 'Risk-Based Auto-Generators' tab."

- "PG migration (33/52 tables)"
+ "PG migration: 31 tables in DDL (27 from v10.253-v10.257 + 4 partnership 
+  cluster v10.261), 17 migrators (top-15 high-value); 78 direct-write 
+  bypass sites identified in v10.259 audit. G163 ratchet active locking 
+  progress."

+ "Three-ratchet audit suite: G161 (boolean module_path), G162 (DECREASE 
+  tenant hardcoding 3,662 baseline), G163 (INCREASE PG migration baseline 
+  27 DDL, 17 migrators)."

+ "Dotted-form access: 100% rolled out (16/16 depts, 96 pages) at v10.250.
+  Hierarchical wildcard grants like finance.* now work platform-wide."
```

---

## 7. What's in this zip

```
APPLY_INSTRUCTIONS.md                            (this file)
CONSOLIDATED_CHANGELOG_v10.193_to_v10.264.md     (rolled-up batch summaries)
SESSION_SUMMARY.md                               (executive overview)

pages/                                           (99 modified pages + manifest)
utils/                                           (43 modified utility modules)
scripts/                                         (4 scripts)
  audit.py                                       (163 ratcheting gates)
  migrate_to_postgres.py                         (17 migrators)
  absorb_cockpit.py                              (NEW v10.213)
  rebaseline_g162.py                             (NEW v10.223)

docs/                                            (7 new docs)
  SYSTEM_AUDIT_v10.219.md
  KAIZEN_FRAMEWORK.md
  MASTER_PROMPT_ADDENDUM.md
  COCKPIT_ABSORPTION_PATTERNS.md
  PG_MIGRATION_AUDIT_v10.251.md
  TEST_COVERAGE_AUDIT_v10.252.md
  DIRECT_WRITE_AUDIT_v10.259.md

data/                                            (manifests + 5 scaffolded data files)
  audit_baselines.json                           (G162 + G163 baselines + scope_history)
  org_config.json                                (tenant identity config)
  bsc_data.json, sbu_pnl.json, revenue_leakage.json,
  capital_adequacy.json, liquidity_metrics.json (NEW v10.215)

sql/                                             (4 new DDL files)
  create_tables_v10.253.sql                      (5 tables)
  create_tables_v10.255.sql                      (5 tables)
  create_tables_v10.257.sql                      (5 tables)
  create_tables_v10.261.sql                      (4 tables — partnership cluster)
```

**Total: 165 files**

---

## 8. Pre-apply checklist

- [ ] Backup working copy (`cp -r ~/A2Z-Blueprint ~/A2Z-Blueprint.backup`)
- [ ] Confirm baseline audit passes
- [ ] Note current state (dotted-form coverage, G162 baseline, etc.)
- [ ] Have rollback plan ready

---

## 9. Post-apply checklist

- [ ] `python scripts/audit.py` shows 163/163 PASS
- [ ] Streamlit app loads (`streamlit run app.py`)
- [ ] Login works
- [ ] Sidebar shows all expected pages
- [ ] MD Cockpit (page 100) loads
- [ ] CBK Returns Centre → Submit Return → Risk-Based Auto-Generators tab visible
- [ ] At least one Risk-Based tab generates a CbkReturnPackage
- [ ] Test users can navigate normally (backward compat working)

If all 8 checks pass, the apply is successful.

---

## 10. Rollback

```bash
# Restore the previous snapshot
git stash               # if using git
# or
cp -r ~/A2Z-Blueprint.backup-pre-v10.264/* ~/A2Z-Blueprint/
```

Each batch's CHANGELOG describes per-batch rollback.

---

## 11. Support

Read `CONSOLIDATED_CHANGELOG_v10.193_to_v10.264.md` for the full batch-by-batch
narrative. Each batch's contribution is described.

Read `SESSION_SUMMARY.md` for the executive overview of all 4 closed
sub-campaigns + advisory work.
