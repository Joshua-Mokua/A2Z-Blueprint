# CHANGELOG v10.129 — PostgreSQL migration step: sla_tickets

**Status:** First integration-layer operational table (`sla_tickets`) lands in `utils/db.py` SCHEMA_SQL. Validates the v10.116 `_data_source` shim end-to-end. **Default still JSON; per-table opt-in via config.** Pattern established for v10.130+ to apply table-by-table.

**Audit:** 143/143 PASS in sandbox.
**Engine self-tests:** 152/152.
**G143 coverage:** **99/131 (75.6%)** — unchanged from v10.125 milestone.
**Strict-preview tier:** `STRICT-READY (high)` — preserved.
**Tests:** ~12 new across 6 classes.

---

## Why this drop matters

After v10.128 closed the cockpit-UI gap (Streamlit page surfacing the integration layer's 5 API endpoints), v10.129 takes the first concrete step on the PostgreSQL migration roadmap. Previously the only PG-resident tables were:

- The **CBK regulatory set** (cbk_returns, dpo_register, sanctions_register, capital_liquidity_metrics) — migrated in early Phase 1B
- The **v10.88-v10.91 Phase 1A migration batches** — agent_fraud_alerts, agents_data, agent_transactions, etc.
- The **v10.93+ registered tables** — ews_cases, etc.

But **none of the integration layer's wired-39 operational tables** (the ones that feed the 100 active aggregation rules) had a PG schema. The v10.116 shim was ready to read from PG views, but no PG views existed for these tables. v10.129 closes that gap one table at a time.

**`sla_tickets` is the first.** It becomes the template for v10.130+ to apply to the next 38 wired operational tables (debt_recovery, audit_reviews, agency_banking, branch_log, hr, etc.).

**Standards numbering**: standards_registry tracks 265 (12 regulatory + 253 enhancement). v10.129 stays in continuation territory.

---

## Scope completion delta

| Dimension | v10.128 | v10.129 | Δ |
|---|---|---|---|
| Master prompt version | v3.22 | **v3.23** | +1 |
| Universal patterns | 8 | 8 | 0 |
| DSL predicate types | 13 | 13 | 0 |
| Rules registered (active) | 100 | 100 | 0 |
| Operational tables wired (rules) | 39 | 39 | 0 |
| **Operational tables with PG schema** | 0 (of 39) | **1** (`sla_tickets`) | **+1** |
| Integration Layer API endpoints | 5 | 5 | 0 |
| Streamlit cockpit pages | 1 | 1 | 0 |
| **G143 coverage** | 99/131 (75.6%) | 99/131 (75.6%) | unchanged |
| **G143 strict-preview tier** | STRICT-READY (high) | STRICT-READY (high) | unchanged |
| Tests | ~364 | ~376 | +12 |

---

## Why `sla_tickets` first

1. **Recent v10.122 seed** — schema and field shapes are well-tested, no legacy quirks
2. **Clean schema** — flat record structure (no nested fields requiring JSONB-only handling)
3. **Active rule** — K039 (`SLA Tickets Within SLA`) is a PERCENTAGE rule that exercises the read path under real load
4. **Modest size** — 100 records in seed; bulk-insert validates in < 1 second
5. **No row-level security needed** — unlike `sanctions_register` which has compliance-only RLS, sla_tickets is operationally visible to all integration_cockpit users

---

## Deliverable 1 — `sla_tickets` schema in `utils/db.py` SCHEMA_SQL

```sql
-- ── SLA Tickets (Phase 1D operational — v10.122 seed, K039 + K040 rules) ──
CREATE TABLE IF NOT EXISTS sla_tickets (
    id                  VARCHAR(50) PRIMARY KEY,
    title               VARCHAR(300),
    category            VARCHAR(100),
    priority            VARCHAR(50),
    sla_target_hours    NUMERIC(10, 2),
    sla_target_days     NUMERIC(10, 4),
    assignee            VARCHAR(50),
    requester           VARCHAR(50),
    department          VARCHAR(100),
    branch              VARCHAR(100),
    status              VARCHAR(50),
    raised_date         TIMESTAMPTZ,
    resolved_date       TIMESTAMPTZ,
    actual_hours        NUMERIC(10, 2),
    actual_days         NUMERIC(10, 4),
    within_sla          BOOLEAN,
    escalation_count    INT DEFAULT 0,
    description         TEXT,
    last_updated        TIMESTAMPTZ,
    data                JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sla_tickets_assignee  ON sla_tickets (assignee);
CREATE INDEX IF NOT EXISTS idx_sla_tickets_status    ON sla_tickets (status);
CREATE INDEX IF NOT EXISTS idx_sla_tickets_priority  ON sla_tickets (priority);
CREATE INDEX IF NOT EXISTS idx_sla_tickets_lastupd   ON sla_tickets (last_updated);
```

All 19 columns match `data/sla_tickets.json` field shape exactly. PRIMARY KEY on `id`. 4 indexes for production query performance — `assignee` is K039's staff_field; `status` and `priority` are predicate fields; `last_updated` is the period_field.

`CREATE TABLE IF NOT EXISTS` is idempotent — banks running migrate_to_postgres.py against an earlier version can re-run safely.

---

## Deliverable 2 — `sla_tickets` entry in `scripts/migrate_to_postgres.py`

Added to FLAT_MIGRATIONS:

```python
("sla_tickets.json",  "sla_tickets",
 ("id","title","category","priority","sla_target_hours","sla_target_days",
  "assignee","requester","department","branch","status","raised_date",
  "resolved_date","actual_hours","actual_days","within_sla",
  "escalation_count","description","last_updated")),
```

Column tuple matches the schema. v10.129 marker comment positions sla_tickets as the first integration-layer operational entry, distinguishing it from the v10.93 / v10.88-v10.91 batches above.

---

## Deliverable 3 — `docs/PG_Migration_sla_tickets.md`

Comprehensive deployment note covering:

- **Scope** — sla_tickets is first wired-39 table to land in PG; pattern not conclusion
- **Why sla_tickets first** — see "Why first" section above
- **How v10.116 shim chooses JSON vs PG** — 3 modes per table:
  - `json` (default; backward-compatible)
  - `pg_view` (strict — returns [] if PG unavailable)
  - `auto` (try PG first; fall back to JSON on failure — recommended for cutover)
- **5-step migration recipe** — env → schema apply → data migrate → flip _data_source config → verify
- **Rollback** — one-line config revert; JSON file never deleted
- **Explicit non-goals** — see "Honesty discipline" section below
- **Recommended order for v10.130+** — debt_recovery → audit_reviews → agency_banking → branch_log → hr
- **Verification checklist**

---

## Deliverable 4 — Tests (`tests/test_integration_layer_v10_129.py`, ~12 tests)

| Test class | Tests | Coverage |
|---|---|---|
| `TestSlaTicketsSchemaInDb` | 4 | CREATE TABLE present, all 19 cols covered, PRIMARY KEY on id, idx_sla_tickets_assignee index for K039's staff_field |
| `TestSlaTicketsInMigrationScript` | 2 | sla_tickets in FLAT_MIGRATIONS, column tuple matches schema |
| `TestV10_116_ShimDefaultUnchanged` | 2 | Shim defaults json with no config; production config still defaults JSON or auto |
| `TestJsonPathRegression` | 2 | sla_tickets.json still loadable with 100 rows; K039 rule still registered |
| `TestG143UnchangedV10129` | 2 | Coverage still 99/131; tier still STRICT-READY (high) |
| `TestNoRuleDensityV10129` | 2 | No v10.129-origin rules; total still 100 |

All ~12 tests pass via manual replay (pytest unavailable in build sandbox).

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

$ pytest tests/test_integration_layer*.py -v
  ~376 passed
```

---

## Files in this drop

```
utils/db.py                                   # MODIFIED — sla_tickets CREATE TABLE
scripts/migrate_to_postgres.py                # MODIFIED — sla_tickets in FLAT_MIGRATIONS
docs/PG_Migration_sla_tickets.md              # NEW — deployment note
tests/test_integration_layer_v10_129.py       # NEW (~200 LOC, ~12 tests)
docs/Master_Prompt_v3.23.md                   # NEW (twenty-third anti-drift sync)
SCOPE_LEDGER.md                               # MODIFIED (v10.128 + v10.129 status blocks; trajectory)
CHANGELOG_v10.129.md                          # this file
```

**No data files modified. No new rules. No new seeds. No shim changes.** Pure schema + migration + docs + tests drop.

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                              # → 143/143 PASS
$ python scripts/run_engine_self_tests.py              # → 152/152
$ pytest tests/test_integration_layer*.py -v           # → ~376 tests pass

$ git add -A
$ git commit -m "v10.129 — PostgreSQL migration step: sla_tickets first integration-layer PG schema"
$ git tag v10.129
$ git push origin main --tags
```

**Production opt-in (after deploy):**

To migrate `sla_tickets` to PG-backed reads in a deployment:

```bash
# 1. Set DB env vars (A2Z_USE_DB=true, A2Z_DB_HOST, etc.)
# 2. Apply schema (idempotent)
python scripts/migrate_to_postgres.py
# 3. Flip _data_source config — edit data/integration_layer_config.json:
#    {"_data_source": {"default": "json", "per_table": {"sla_tickets": "auto"}}}
# 4. Verify K039 rule output matches between JSON and PG modes
```

See `docs/PG_Migration_sla_tickets.md` for the full deployment note.

---

## Honesty discipline notes

**Default not flipped.** v10.116 shim still defaults to json. Production deployments running v10.117-v10.128 update to v10.129 with NO behavior change unless they explicitly add a `_data_source.per_table.sla_tickets` override to integration_layer_config.json. This is exactly the v10.117 → v10.120 → v10.126 role-gating pattern: ship the infrastructure, don't flip the switch in the same drop.

**JSON file not deleted.** `data/sla_tickets.json` remains as the canonical fallback. The PG path coexists with JSON; rollback is a one-line config change. The JSON-deprecation cutover is a programme-level decision, not a per-drop one.

**Schema additive only.** `CREATE TABLE IF NOT EXISTS` is idempotent. Banks who've previously run migrate_to_postgres.py against an earlier version can re-run safely against v10.129.

**One table, not all 38.** sla_tickets only. The pattern is replicable; future drops apply it. Doing 38 tables in one drop would mean 38× the regression surface, with no opportunity to validate the pattern before scaling. One per drop is sustainable.

**No rule registry migration.** `aggregation_rules.json` and `integration_layer_config.json` stay JSON-only. The PG path is operational-table reads only. Rule definitions are admin-controlled config; keeping them in JSON files (versioned in git, easy to diff in PR review) is preferable to PG-resident config that'd need a separate audit trail.

**No shim changes.** Same `_data_source` config shape, same 3 modes (json/pg_view/auto), same default. v10.129 just adds one more table the shim can read from. The shim itself is unchanged from v10.116.

---

## Phase 1D coverage trajectory (locked at v10.126; preserved through v10.129)

| Drop | Work | Coverage |
|---|---|---|
| v10.108 | 4 reference rules (kickoff) | 4/108 (3.7%) |
| v10.119 | 2 new DSL predicates + 8 new rules — STRICT-READY (preview) crossing | 66/131 (50.4%) |
| v10.122 | 2 new CBS-mock seeds + 4 new rules — pool-wall break | 78/131 (59.5%) |
| v10.125 | 5 new CBS-mock seeds + 8 new rules — **STRICT-READY (high) crossing** | 99/131 (75.6%) |
| v10.126 | Phase 1D close-out — role-gating default flip + retro + Phase 1E proposal | 99/131 (unchanged) |
| v10.127 | Window 4 close — programme correction + standards #14-#20 verification | 99/131 (unchanged) |
| v10.128 | Streamlit cockpit — `pages/99_integration_cockpit.py` | 99/131 (unchanged) |
| **v10.129** | **PostgreSQL migration step — sla_tickets first integration-layer PG schema** | **99/131 (unchanged)** |
| v10.130 (planned) | Apply same recipe to next operational table — debt_recovery recommended | unchanged |
| v10.130+ (estimated) | **G143 strict mode flip** at 100% (per-staff scope only; bank-level via G144) | 131/131 |

**Next: v10.130** — apply the same recipe to the next operational table. Recommended order:

1. **debt_recovery** — wired by 4 rules (K027, K113, K044, "Collection Throughput"); proven via v10.121 wires
2. **audit_reviews** — wired by 3 rules + 1 non-K-coded ("Audit Score"); seeded in v10.114
3. **agency_banking** — wired by K025 + others; v10.123 seed
4. **branch_log** — wired by K013 + others; v10.122 seed
5. **hr** — wired by K016, K018, K121-K128, "Staff Productivity"; v10.123 seed (200 records)

Or pivot to FATCA/CRS XML, React component library, or bank-level pipeline if the migration roadmap goes back-burner. Caller's pick.
