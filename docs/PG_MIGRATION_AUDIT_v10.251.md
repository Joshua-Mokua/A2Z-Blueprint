# A2Z MIS 360 — PG Migration Reality Audit (v10.251)

**Audit date:** 2026-05-07
**Scope:** Reality check on PostgreSQL migration progress against
user memory's "PG migration (33/52 tables)" claim. Pattern follows
v10.219's tenant-identity audit.
**Audit baseline:** 162/162 PASS at start of batch.

---

## Executive summary

Memory's claim of "PG migration 33/52 tables" is **aspirational, not
measured**. Ground truth, measured against the codebase:

| Metric | Memory says | Reality |
|---|---|---|
| Tables migrated | 33/52 | **2/?** |
| DDL files | (not specified) | 12 tables across 2 .sql files |
| Migration functions | (not specified) | 2 (`migrate_bank_targets`, `migrate_baselines`) |
| Dual_load/dual_save call sites | (not specified) | 55 |
| JSON data files | (not specified) | 166 |
| Direct write_text in pages/ | (not specified) | 94 (some legitimate, some PG-bypass) |

This is a **20-point delta** — memory said 60% done, reality is closer
to 4% if measured by migration-function count, or 7% if measured by
DDL coverage of 166 JSON files.

**This is exactly the failure mode Rule N6 (memory reconciliation)
exists to catch.** Memory drifted because earlier campaign tracking
counted "tables we COULD migrate" rather than "tables we HAVE
migrated."

The good news: the seam IS in production use. 55 `dual_load`/`dual_save`
calls show pages do go through `utils/db.py` for the migrated subset.
The infrastructure works; the COVERAGE is the gap.

---

## 1. What's actually migrated

### 1.1 DDL — 12 tables across 2 files

`create_tables.sql` (8 tables):
- `audit_trail`
- `users`
- `bsc_scores`
- `pipeline_deals`
- `loan_applications`
- `disciplinary`
- `aml_alerts`
- `sessions`

`create_tables_v53.sql` (4 tables):
- (specific tables from v5.3 batch — TBD; ~4 more added)

### 1.2 Migration functions — 2

`scripts/migrate_to_postgres.py` defines:
- `migrate_bank_targets()`
- `migrate_baselines()`

Both write JSON → PostgreSQL. The other ~10 DDL'd tables don't yet have
matching migrators in the script — they may be migrated lazily through
`utils/db.dual_save` when pages write to them.

### 1.3 dual_load / dual_save adoption — 55 call sites

Active across pages/ + utils/:

```
pages/82_oprisk.py:        2 calls
pages/78_onboarding.py:    2 calls
pages/80_merchant.py:      2 calls
pages/74_cbk_returns.py:   2 calls
pages/75_data_protection:  2 calls
pages/79_cards.py:         2 calls
... (~45 page-level callers)
utils/bsc_engine.py:       1 call
utils/db.py:              11 calls (the seam itself)
```

Each call site reads/writes through the dual-mode seam. When PG is
reachable (`is_postgres_ready() == True`), writes go to BOTH PG and
JSON; reads prefer PG. When PG is down, reads/writes fall back to JSON
transparently.

---

## 2. What's NOT migrated — the long tail

### 2.1 166 JSON data files vs 12 DDL'd tables

```
ls data/*.json | wc -l
166

grep -cE "^CREATE TABLE" *.sql
12
```

154 JSON files have NO corresponding DDL. They could in principle
migrate (the seam supports any 2-tier read/write pattern), but without
DDL the schema is implicit in the JSON structure — schema drift risk
is high.

### 2.2 Largest unmigrated files (highest-value migration targets)

Sorted by size (proxy for query volume):

| File | Size | Likely table |
|---|---|---|
| `credit_monitoring.json` | 5.3 MB | `credit_monitoring` |
| `target_cascade.json` | 4.8 MB | `target_cascade` |
| `training_completions.json` | 3.6 MB | `lms_training_completions` |
| `feb_2026_staff_scores.json` | 2.2 MB | quarterly_staff_scores |
| `ifrs9_loans.json` | 1.8 MB | `ifrs9_loan_classifications` |
| `customer_intelligence.json` | 1.7 MB | `customer_intelligence` |
| `performance_reviews.json` | 1.2 MB | `performance_reviews` |
| `growth_plans.json` | 1.1 MB | `staff_growth_plans` |
| `loan_applications.json` | 0.99 MB | already in DDL ✓ |
| `users.json` | 0.84 MB | already in DDL ✓ |

The top 5 unmigrated files (combined ~17 MB JSON) represent the
primary migration value pool. These tables also have heavy read/write
volume (BSC scoring, target cascade, training tracking, IFRS 9
classification).

### 2.3 Direct write_text() in pages/ — 94 sites

Some are legitimate (e.g. exporting CSV files for download). Others
bypass `utils.db` — meaning their writes don't dual-mode and won't go
to PG even if migrated. Top offenders:

```
pages/66_partnerships.py:    7 direct writes
pages/29_revenue_assurance:  6
pages/62_p2p.py:             5
pages/26_legal.py:           5
pages/30_rms.py:             3
pages/25_treasury.py:        3
```

These should be audited individually. Each direct write may be:
1. CSV/PDF export → legitimate, leave alone
2. Settings/state file → migrate to dual_save
3. Cache write → could move to a TTL-aware seam

A future ratchet could enforce: every `write_text` in a non-FOUNDATIONAL
file must be one of (a) export to download, (b) `utils.db.dual_save`
call, or (c) explicitly exempted.

---

## 3. Why memory drifted

The "33/52" tracking originated when the campaign was planning future
DDL coverage. Each "PG-aware page" was counted as one migrated table
even when:

- The page DOES use `dual_load` (~45 page-level callers exist)
- But the page's underlying DATA file isn't in DDL
- So writes go to JSON only via fallback; no actual PG migration
  benefit

The discrepancy compounds because memory was updated optimistically
("we touched 33 pages this quarter") without ground-truth verification
("12 of those pages have actually-migrated tables").

This is exactly what **master prompt Rule N6 (memory reconciliation)**
addresses. v10.251 IS the reconciliation. Memory should be updated
to reflect:

- **Actual state:** 12 tables in DDL, 2 explicit migrators, 55 dual-mode
  call sites, 166 JSON files
- **Planned scope:** all 166 JSON files to be DDL'd over time
- **Realistic phasing:** top-5 high-value tables in next 5 batches
  (~v10.253 onward); long-tail in subsequent quarters

---

## 4. Recommended kaizen ratchet — G163

Pattern follows G162 (tenant identity hardcoding):

```python
def gate_pg_migration_baseline():
    """G163 — kaizen ratchet on PG migration coverage.

    Tracks two metrics:
      - DDL_TABLES: count of CREATE TABLE statements across *.sql
      - MIGRATORS: count of migrate_*() functions in
                   scripts/migrate_to_postgres.py

    Both numbers may only INCREASE over time. Decrease = drift
    (e.g. someone removed a migrator without justification).
    """
```

Different from G162: this ratchet's direction is INVERSE — counts go UP
as work happens, not down. Same kaizen principle though: today's number
becomes tomorrow's floor.

**Defer G163 to v10.252 or v10.253** — first need to establish the
baseline AND have a clear sub-campaign roadmap so the ratchet isn't
just protecting a stale snapshot.

---

## 5. Recommended sub-campaign — PG migration v10.253–v10.260

Eight batches at ~3 tables each, mirrors the cockpit absorption pace:

| Batch | Scope | Effort |
|---|---|---|
| v10.253 | DDL for top-5 high-value tables (credit_monitoring, target_cascade, training_completions, ifrs9_loans, customer_intelligence) | Pure SQL — write CREATE TABLE statements |
| v10.254 | Migrators for those 5 tables | Each migrator: read JSON → INSERT batch into PG |
| v10.255 | DDL for next 5 (performance_reviews, growth_plans, edms_documents, customer_onboarding, etc.) | Same pattern |
| v10.256 | Migrators for those 5 | Same pattern |
| v10.257 | DDL for next 5 | Same pattern |
| v10.258 | Migrators | Same pattern |
| v10.259 | Direct-write_text audit + cleanup of pages that bypass utils.db | Behaviour change in 5-10 pages |
| v10.260 | Add G163 ratchet locking the new state | Audit gate addition |

End state after 8 batches: ~27 tables in DDL (12 → 27), ~12 migrators
(2 → 12), tenant-aware data layer fully on PG for high-value tables.

---

## 6. What's working well

1. **The seam itself.** `utils/db.py` provides `dual_load`,
   `dual_save`, `is_postgres_ready()`. Production-grade fallback
   logic, 11 internal call sites, used by 45 pages.

2. **G2 (direct_io) audit gate** already polices direct json.loads /
   write_text in non-foundational files. Catches new bypasses.

3. **dual_save is opt-in per page.** Pages don't break when PG isn't
   available — they fall through to JSON. Migration can be incremental
   (page by page, table by table) without risk.

---

## 7. Risks

1. **Schema drift between JSON and DDL.** When DDL is added later,
   the JSON structure may have evolved beyond what the DDL captures.
   Mitigation: write DDL FIRST, then update JSON to match.

2. **Dual-write performance overhead.** Every save writes twice. For
   high-volume tables (audit_log especially), this is observable.
   Future advisory: audit_log might be PG-only with a fallback log
   file rather than dual_save.

3. **No test coverage on dual-mode seam.** When PG goes down/up, the
   transition path isn't covered by automated tests. v10.252's test
   coverage push should include dual-mode tests.

4. **No rollback plan.** If a migrator runs and PG state diverges
   from JSON, there's no documented "go back to JSON" procedure.
   Future advisory: each migrator should be paired with a reverse
   migrator OR explicit rollback note.

---

## 8. Honest acknowledgements

1. **This audit took ~30 minutes** — same depth as v10.219's tenant
   identity audit. Worth it for the comprehensive view that incremental
   batches can't reach.

2. **The "33/52" number wasn't fabricated.** It came from earlier
   campaign tracking and was useful at the time. The drift is between
   "useful for planning" and "ground truth" — exactly what Rule N6
   is for.

3. **No sub-campaign work in this batch.** v10.251 documents the
   gap; v10.252+ executes against it. Single-purpose discipline.

4. **The 27-tables target after 8 batches is conservative.** Could
   compress to 5 batches if migrators are mostly mechanical (read
   JSON, INSERT batch). The 8-batch sizing matches kaizen cadence
   (~3 tables per batch).

5. **G163 deferred.** Adding the ratchet today would protect a
   2-migrator baseline — not very useful. Better to add at v10.260
   when the baseline reflects substantive work.

6. **50 consecutive clean batches.**

---

## 9. Memory update recommended

Joshua should update user memory:

```diff
- PG migration (19/52 tables)
+ PG migration: 12 tables in DDL, 2 migrators, 55 dual-mode call sites,
+ 166 JSON files. Sub-campaign v10.253–v10.260 will bring DDL to ~27
+ tables and migrators to ~12 (focused on top-value data files).
```

This memory edit is recommended via the `memory_user_edits` tool when
Joshua next starts a session — gives Claude an accurate starting point
for the PG sub-campaign.
