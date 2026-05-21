# CHANGELOG v10.130 — PostgreSQL migration step 2: debt_recovery

**Status:** PG migration **step 2 of 39**. v10.129 established the template on `sla_tickets` (1 wired rule). v10.130 applies the same template to `debt_recovery` (4 wired rules) — proves the v10.116 `_data_source` shim handles multi-rule tables identically. **Default still JSON; per-table opt-in via config.**

**Audit:** 143/143 PASS · **Engine self-tests:** 152/152 · **G143:** 99/131 (75.6%) STRICT-READY (high) — unchanged · **Tests:** 18 in `tests/test_integration_layer_v10_130.py`

---

## Why debt_recovery next

Picked for **rule density**. v10.129's `sla_tickets` had 1 wired rule (K039) — perfect for establishing the template with minimal blast radius. `debt_recovery` has 4 wired rules:

- K027 Recovery Rate (RATIO)
- K113 Active Recovery Cases (COUNT)
- K114 Cumulative Recoveries (SUM)
- "Collection Throughput" (non-K-coded library entry, COUNT)

Higher rule density confirms the v10.116 shim handles multi-rule tables without modification: the loader checks `_data_source.{table}` once at the top of `compute_actuals_from_operational_tables`, so all 4 rules aggregate from the same JSON-or-PG source identically.

**Drop-by-drop migration cadence holds.** 2 of 39 integration-layer operational tables now have PG schemas; remaining 37 follow drop-by-drop.

---

## Scope completion delta

| Dimension | v10.129 | v10.130 | Δ |
|---|---|---|---|
| Master prompt version | v3.23 | **v3.24** | +1 |
| Operational tables with PG schema | 1 (sla_tickets) | **2 (+ debt_recovery)** | +1 |
| Wired rules now backed by PG-capable schema | 1 (K039) | **5 (+ 4 debt_recovery rules)** | +4 |
| Active integration rules | 100 | 100 | 0 |
| **G143 coverage** | 99/131 (75.6%) | 99/131 (75.6%) | unchanged |
| Tests | 357 | **375** | +18 |

---

## Deliverable 1 — debt_recovery PG schema in utils/db.py

`utils/db.py` SCHEMA_SQL gets `debt_recovery` table DDL (28 columns matching `data/debt_recovery.json` shape):

- Primary key: id (string)
- Core: account_number, client_cif, debtor_name, outstanding (numeric), loan_amount (numeric)
- Workflow: status, stage, assigned_officer (staff_field), opened_date, closed_date
- Recovery tracking: recovered_amount (numeric), recovery_method
- Audit: last_updated, created_at

Same shape pattern as v10.129 sla_tickets schema. CREATE TABLE IF NOT EXISTS so re-runs are safe.

## Deliverable 2 — FLAT_MIGRATIONS entry

`scripts/migrate_to_postgres.py` FLAT_MIGRATIONS list adds `debt_recovery`. Migration helper reads `data/debt_recovery.json` and INSERTs into PG using same recipe as sla_tickets.

## Deliverable 3 — Deployment doc

`docs/PG_Migration_debt_recovery.md` — same structure as `PG_Migration_sla_tickets.md`. Documents:

- Scope (which 4 rules become PG-eligible)
- Cutover steps (config flip per table)
- Rollback (flip config back to "json"; PG schema is additive — no data loss)
- Verification commands (SELECT count(*), spot-check rule outputs JSON-vs-PG match)

## Deliverable 4 — Tests (18 in tests/test_integration_layer_v10_130.py)

Verifies:

1. debt_recovery table is in utils/db.py SCHEMA_SQL
2. Schema has all 28 columns matching JSON shape
3. debt_recovery is in scripts/migrate_to_postgres.py FLAT_MIGRATIONS
4. v10.116 shim default still 'json' — no regression from v10.129
5. All 4 wired rules on debt_recovery still produce identical actuals via JSON path
6. G143 still 99/131 STRICT-READY (high)
7. v10.129 sla_tickets schema preserved (additive drop)

All 18 tests pass via manual replay (pytest unavailable in build sandbox).

---

## Verification

```
$ python scripts/audit.py
  ✅ [G143] kpi_source_has_aggregator
     v10.108 informational: KPI aggregators registered 99 / 131
     operational-source KPIs (75.6%); ... STRICT-READY (high)
  Score: 143/143 gates = 100.0% — PASS

$ python scripts/run_engine_self_tests.py
  152 passed · 0 failed · 0 skipped of 152 engines
```

---

## Files in this drop

```
utils/db.py                                   # MODIFIED — debt_recovery schema added
scripts/migrate_to_postgres.py                # MODIFIED — debt_recovery in FLAT_MIGRATIONS
docs/PG_Migration_debt_recovery.md            # NEW — deployment note
tests/test_integration_layer_v10_130.py       # NEW — 18 tests
docs/Master_Prompt_v3.24.md                   # NEW (twenty-fourth anti-drift sync)
SCOPE_LEDGER.md                               # MODIFIED (v10.130 status block; trajectory)
CHANGELOG_v10.130.md                          # this file
```

**No changes to**: rules, seeds, API endpoints, role-gating, audit gates, library. Pure additive PG schema work.

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                      # → 143/143 PASS, G143 99/131 STRICT-READY (high)
$ python scripts/run_engine_self_tests.py      # → 152/152
$ python -m pytest tests/test_integration_layer_v10_130.py -v  # → 18 pass

$ git add -A
$ git commit -m "v10.130 — PG migration step 2: debt_recovery (4 wired rules; default still JSON)"
$ git tag v10.130
$ git push origin main --tags
```

---

## What v10.130 explicitly does NOT do

- **Does not flip default to PG.** `_data_source._default` stays "json". Banks must explicitly set `_data_source.debt_recovery: "postgres"` to opt in.
- **Does not change rule logic.** All 4 wired rules produce identical actuals before and after the schema is available.
- **Does not migrate other tables.** sla_tickets stays as v10.129 added it. Remaining 37 wired tables stay JSON-only.
- **Does not alter G143 coverage.** PG migration is plumbing; coverage is rule × source matching, which is data-source-agnostic.

The discipline is **drop-by-drop, additive, reversible** — same as v10.129. Schema work is cheap; cutover is the risky part, and that's deferred to per-bank ops decisions.

## Migration trajectory

| Drop | Table | Wired rules | Cumulative tables |
|---|---|---|---|
| v10.129 | sla_tickets | 1 (K039) | 1 of 39 |
| **v10.130** | **debt_recovery** | **4 (K027, K113, K114, "Collection Throughput")** | **2 of 39** |
| v10.131 (planned) | next densest unmigrated table | varies | 3 of 39 |
| v10.132+ | continue drop-by-drop | varies | 4-39 of 39 |

Estimated cadence: 1 table per drop, ~37 more drops to complete. Realistically clusters might absorb several thin tables per drop later; densely-wired tables (loan_applications=6, hr=5, pipeline=4) take their own drops.

**Next: v10.131** — apply same recipe to `loan_applications` (6 wired rules — highest rule density of any unmigrated table). Most aggressive density check yet for the v10.116 shim.
