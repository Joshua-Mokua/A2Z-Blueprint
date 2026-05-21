# CHANGELOG v10.131 — PostgreSQL migration step 3: loan_applications

**Status:** PG migration **step 3 of 39**. Architecturally distinct from v10.129/v10.130: where those drops added new CREATE TABLE statements (sla_tickets, debt_recovery — newly-migrated tables), v10.131 adds NO new schema. `loan_applications` has been a PG-backed table since v10.89 (anti-drift Phase 1A migration batch 2). v10.131 just adds **3 supplementary indexes** for Phase 1D query patterns + integration-layer designation. **Default still JSON; per-table opt-in via config.**

**Audit:** 143/143 PASS · **Engine self-tests:** 152/152 · **G143:** 99/131 (75.6%) STRICT-READY (high) — unchanged · **Tests:** 17 in `tests/test_integration_layer_v10_131.py`

---

## Why this drop is structurally different

`loan_applications` was added to PG in v10.89 (anti-drift Phase 1A migration batch 2). The integration layer then built its rule density on top of `data/loan_applications.json` over v10.108-v10.119, accumulating 6 wired rules without ever needing the PG path because the v10.116 `_data_source` shim defaults to JSON.

**v10.131 closes the loop**: declares `loan_applications` part of the integration layer's PG-eligible set. **No new schema needed** — the table already exists in PG along with 60+ pre-Phase-1D anti-drift tables. v10.131 just adds 3 supplementary indexes for the Phase 1D query patterns and updates docs.

This proves the v10.116 shim works with **pre-existing** PG tables, not just newly-added ones. **Banks already running A2Z MIS 360 with the anti-drift PG migration completed will inherit the integration-layer PG path automatically when they flip per-table config — no schema migration required.**

---

## Why loan_applications next

Picked for **rule density**. Most aggressive density check yet for the v10.116 shim:

| KPI | Pattern | Period field | Description |
|---|---|---|---|
| K001 | SUM | last_updated | Loan Disbursements |
| K010 | PERCENTAGE | last_updated | Loan Approval Rate |
| K011 | TAT_DAYS | last_updated | Application Approval TAT |
| K115 | COUNT | last_updated | Loan Application Volume |
| K045 | PERCENTAGE | application_date | Compliance Flag Rate |
| K046 | MEAN_FIELD | application_date | Avg Document Completeness |

All 6 use `rm_code` as the staff_field via `STAFF_FIELD_BY_TABLE`. Two distinct period fields (`last_updated` for 4 rules, `application_date` for 2) — both indexed pre/v10.131.

---

## Scope completion delta

| Dimension | v10.130 | v10.131 | Δ |
|---|---|---|---|
| Master prompt version | v3.24 | **v3.25** | +1 |
| Operational tables PG-eligible | 2 | **3 (+ loan_applications)** | +1 |
| Wired rules now backed by PG-capable schema | 5 | **11 (+ 6 loan_applications rules)** | +6 |
| **G143 coverage** | 99/131 (75.6%) | 99/131 (75.6%) | unchanged |
| Tests | 375 | **392** | +17 |

---

## Deliverable 1 — Supplementary indexes in utils/db.py

Three CREATE INDEX IF NOT EXISTS statements added after the debt_recovery indexes block:

```sql
CREATE INDEX IF NOT EXISTS idx_loan_apps_lastupd      ON loan_applications (last_updated);
CREATE INDEX IF NOT EXISTS idx_loan_apps_tat          ON loan_applications (tat_days);
CREATE INDEX IF NOT EXISTS idx_loan_apps_complflag    ON loan_applications (compliance_flag) WHERE compliance_flag = TRUE;
```

**No CREATE TABLE added.** The single CREATE TABLE for loan_applications remains at line 989 (since v10.89). Tests verify regex match returns exactly one. Pre-existing indexes (`idx_loan_apps_status`, `idx_loan_apps_application_date`, `idx_loan_apps_rm`) cover most query patterns; v10.131's three target the Phase 1D rule-specific columns.

The `idx_loan_apps_complflag` is a **partial index** (`WHERE compliance_flag = TRUE`) — K045's numerator predicate filters to compliance-flagged rows; partial index is more efficient than full index since most rows are False.

## Deliverable 2 — FLAT_MIGRATIONS annotation

`scripts/migrate_to_postgres.py`: the loan_applications entry has been in FLAT_MIGRATIONS since v10.89. v10.131 adds an annotation comment block above it designating v10.131 as the integration-layer activation point. The migration tuple is unchanged — banks already running anti-drift have loan_applications synced.

## Deliverable 3 — Deployment doc

`docs/PG_Migration_loan_applications.md` — documents the structurally-different pattern:

- Why this drop is structurally different (pre-existing PG schema; no migration step needed)
- Scope: 6 wired rules become PG-capable (K001/K010/K011/K115/K045/K046)
- Cutover steps (verify PG state → verify supplementary indexes → flip config → spot-check → audit)
- Rollback (flip back to "json"; non-destructive — anti-drift kept it sync'd since v10.89)
- Verification commands (per-rule JSON-vs-PG output diff for all 6 rules)

## Deliverable 4 — Tests (17 in tests/test_integration_layer_v10_131.py)

Across 7 classes:

- `TestSchemaNotDuplicated` (2) — exactly 1 CREATE TABLE; v10.131 annotation present
- `TestV10_131SupplementaryIndexes` (3) — lastupd, tat, complflag partial all present
- `TestFlatMigrationsAnnotation` (2) — entry preserved + v10.131 annotation adjacency
- `TestPriorMigrationsPreserved` (3) — sla_tickets v10.129 schema + debt_recovery v10.130 schema + _data_source default still "json"
- `TestWiredRulesStillFunctional` (2) — six wired rules present + patterns unchanged
- `TestG143Unchanged` (2) — coverage 99 + tier STRICT-READY (high)
- `TestDeploymentDocPresent` (1) — doc present with all 5 sections

All 17 tests pass via manual replay (pytest unavailable in build sandbox).

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
utils/db.py                                   # MODIFIED — 3 supplementary indexes only
scripts/migrate_to_postgres.py                # MODIFIED — annotation block above pre-existing entry
docs/PG_Migration_loan_applications.md        # NEW — deployment note (structurally different)
tests/test_integration_layer_v10_131.py       # NEW — 17 tests
docs/Master_Prompt_v3.25.md                   # NEW (twenty-fifth anti-drift sync)
SCOPE_LEDGER.md                               # MODIFIED (v10.131 status block; trajectory)
CHANGELOG_v10.131.md                          # this file
```

**No changes to**: rules, seeds, API endpoints, role-gating, audit gates, library, FLAT_MIGRATIONS tuple. Pure additive index work + designation.

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                                          # → 143/143 PASS, G143 99/131 STRICT-READY (high)
$ python scripts/run_engine_self_tests.py                          # → 152/152
$ python -m pytest tests/test_integration_layer_v10_131.py -v      # → 17 pass

$ git add -A
$ git commit -m "v10.131 — PG migration step 3: loan_applications designated PG-eligible (pre-existing schema; 3 supplementary indexes; 6 wired rules)"
$ git tag v10.131
$ git push origin main --tags
```

---

## What v10.131 explicitly does NOT do

- **Does not add a new CREATE TABLE.** loan_applications has been in PG since v10.89. Tests assert exactly 1 CREATE TABLE remains.
- **Does not flip default to PG.** `_data_source._default` stays "json". Banks must explicitly set `_data_source.per_table.loan_applications: "pg_view"` to opt in.
- **Does not change rule logic.** All 6 wired rules produce identical actuals before and after PG path is opt-in.
- **Does not migrate other tables.** sla_tickets stays as v10.129 added it; debt_recovery stays as v10.130 added it. Remaining 36 wired tables stay JSON-only.
- **Does not alter G143 coverage.** PG migration is plumbing; coverage is rule × source matching, which is data-source-agnostic.

The discipline is **drop-by-drop, additive, reversible** — same as v10.129/v10.130, just with the structurally-different pattern for pre-existing schemas.

## Migration trajectory

| Drop | Table | Wired rules | Schema status | Cumulative |
|---|---|---|---|---|
| v10.129 | sla_tickets | 1 (K039) | NEW (added v10.129) | 1 of 39 |
| v10.130 | debt_recovery | 4 (K027, K113, K114, "Collection Throughput") | NEW (added v10.130) | 2 of 39 |
| **v10.131** | **loan_applications** | **6 (K001, K010, K011, K115, K045, K046)** | **PRE-EXISTING (v10.89; v10.131 adds 3 supplementary indexes)** | **3 of 39** |
| v10.132 (planned) | TBD — caller's pick | varies | varies | 4 of 39 |

**Two patterns proven**: (a) new schemas via CREATE TABLE (v10.129/v10.130 — for tables not already in anti-drift); (b) pre-existing schemas via designation (v10.131 — for tables already in anti-drift PG migration). Future drops apply whichever pattern fits each table.

**Realistic v10.132 candidates:**

1. **`hr` table** — 5 wired rules, pre-existing PG schema (v10.131 pattern)
2. **`pipeline` table** — 4 wired rules, pre-existing PG schema (v10.131 pattern)
3. **`audit_reviews`** — 4 wired rules, NEW schema needed (v10.129/v10.130 pattern)
4. **`card_management`** — 4 wired rules, pre-existing PG schema (v10.131 pattern) since v10.89
5. **Pivot entirely** — React dashboard, FATCA-CRS, bank-level pipeline — Phase 1E concerns

---

## Honesty discipline notes

**Refused the temptation to add a duplicate CREATE TABLE.** First attempt added a new CREATE TABLE for loan_applications without checking if one already existed. A grep before shipping caught the duplicate. Without that check, two CREATE TABLE statements would have shipped — either silently failing (if `IF NOT EXISTS` were absent) or creating long-term confusion in the schema file.

**Tests assert exactly 1 CREATE TABLE** to prevent future regression. The regex `CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?loan_applications` is matched against `utils/db.py` content; assertion fails if count != 1. Future drops that touch loan_applications schema will trip this if they add a duplicate.

**The deployment doc explicitly calls out the structural difference.** Banks running cutover for loan_applications shouldn't be surprised that there's no migration step in v10.131 — the doc points to v10.89 as the source of the schema and walks through cutover without a CREATE TABLE step. If ops aren't aware of this distinction, they may run v10.131-specific migration commands and hit "no such migration" errors.

**SCOPE_LEDGER repair pattern continues** — v10.130 status block heading was overwritten when inserting v10.131 above it; restored manually after the insert. v10.130 body content preserved unchanged.

**The architecture lesson is the real win**. v10.131's pattern (pre-existing PG schema + integration-layer designation) is simpler and faster than v10.129/v10.130's pattern (new CREATE TABLE). Future drops can largely follow v10.131's playbook because most of the wired-39 tables are already in PG via anti-drift.

## Consolidation tracker

**v10.131 closes Window 4's PG-migration sub-cycle** — three drops (v10.129, v10.130, v10.131) establishing two patterns and three PG-eligible tables. **Cumulative: 3 of 39 integration-layer operational tables PG-eligible.** Window 4 itself ended at v10.127; the consolidated bundle a2z_v10.123_to_v10.127_consolidated.zip already shipped at v10.127. Future consolidations will batch v10.128+ as they accumulate.
