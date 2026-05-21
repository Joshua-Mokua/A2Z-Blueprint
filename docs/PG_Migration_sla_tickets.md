# PG migration deployment note — `sla_tickets`

**Drop:** v10.129
**Status:** schema + migration ready; default still JSON. Opt-in per-table flip required for production cutover.

---

## Scope

v10.129 makes `sla_tickets` the first integration-layer operational table to land in the PostgreSQL schema. Previously the only PG-resident tables were the CBK regulatory set (cbk_returns, dpo_register, sanctions_register, capital_liquidity_metrics) plus the v10.88-v10.91 Phase 1A migration batches. `sla_tickets` is the first member of the integration layer's wired-39 set to get a PG schema, validating the v10.116 `_data_source` shim end-to-end.

**This is the pattern; not the conclusion.** Once `sla_tickets` is proven in production, the other 38 wired operational tables follow the same recipe drop-by-drop. v10.129 establishes the template; future drops apply it.

---

## Why `sla_tickets` first

1. **Recent v10.122 seed** — schema and field shapes are well-tested, no legacy quirks
2. **Clean schema** — flat record structure (no nested fields requiring JSONB-only handling)
3. **Active rule** — K039 (`SLA Tickets Within SLA`) is a PERCENTAGE rule that exercises the read path under real load
4. **Modest size** — 100 records in seed; bulk-insert validates in < 1 second
5. **No row-level security required** — unlike `sanctions_register` which has compliance-only RLS, sla_tickets is operationally visible to all users with integration_cockpit access

---

## How the v10.116 shim chooses JSON vs PG

The shim lives in `utils/actuals_engine.py::_read_operational_table()`. For each operational table, it consults `integration_layer_config.json` `_data_source` config:

```jsonc
{
  "_data_source": {
    "default": "json",          // applies to tables not in per_table
    "per_table": {
      "sla_tickets": "auto"     // try PG first; fall back to JSON on failure
    }
  }
}
```

Three modes per table:

| Mode | Semantics |
|---|---|
| `json` | Read `data/<table>.json`. (Default; backward-compatible.) |
| `pg_view` | `SELECT * FROM <table>`. **Strict** — returns `[]` if PG unavailable rather than silently downgrading. |
| `auto` | Try PG first; fall back to JSON on any failure. **Recommended for cutover** — banks can validate PG path while keeping JSON safety net. |

The default for a missing `_data_source` block is still `"json"`, so v10.129 changes **no production behavior** for any deployment that doesn't explicitly opt in.

---

## Migration recipe

Per `utils/db.py` documentation, A2Z uses a per-table opt-in PG migration. To migrate `sla_tickets` to PG in a deployment:

### 1. Set environment

```bash
export A2Z_USE_DB=true
export A2Z_DB_HOST=<host>
export A2Z_DB_PORT=5432
export A2Z_DB_NAME=a2z_mис360
export A2Z_DB_USER=a2z_app
export A2Z_DB_PASSWORD='<password>'   # never in code
export A2Z_DB_SSLMODE=require          # always in production
```

### 2. Apply schema

The `sla_tickets` `CREATE TABLE` is part of `utils/db.py::SCHEMA_SQL` (added in v10.129). If you've previously run `scripts/migrate_to_postgres.py` against an earlier version, the new `CREATE TABLE IF NOT EXISTS sla_tickets` runs idempotently — no manual schema work needed.

```bash
# Idempotent — re-applies schema, only creates missing tables
python scripts/migrate_to_postgres.py
```

### 3. Migrate data

`scripts/migrate_to_postgres.py` v10.129 includes `sla_tickets` in `FLAT_MIGRATIONS`. Running the migration script reads `data/sla_tickets.json` and bulk-inserts into the PG `sla_tickets` table.

### 4. Flip `_data_source` in config

Edit `data/integration_layer_config.json` to opt-in:

```jsonc
{
  "_data_source": {
    "default": "json",
    "per_table": {
      "sla_tickets": "auto"   // try PG, fall back to JSON
    }
  }
}
```

**Recommendation: start with `auto` mode.** This lets the integration layer verify the PG path is producing correct results while keeping JSON as a safety net. Once verified across a few cycles, switch to `pg_view` (strict) or remove the per-table override (back to default JSON).

### 5. Verify

After flipping the toggle, run the integration cockpit's "Preview Actuals" tab for a recent period. The K039 (`SLA Tickets Within SLA`) numbers should match what JSON-only mode produced. If they differ, switch back to `json` mode and investigate before flipping again.

```bash
# CLI verification — both modes should produce identical actuals
python scripts/audit.py    # confirms G143 still 99/131 STRICT-READY (high)
```

---

## Rollback

If the PG path produces bad results, rollback is one-line:

```jsonc
{
  "_data_source": {
    "default": "json",
    "per_table": {
      "sla_tickets": "json"   // back to JSON-only
    }
  }
}
```

No data migration is required for rollback because the PG table coexists with `data/sla_tickets.json`. The JSON file is **never deleted by v10.129** — it remains the operationally-canonical source until the bank-level cutover decision (v10.130+ or later).

---

## What v10.129 explicitly does NOT do

- **Does not flip the default to PG** — `_data_source` still defaults to `"json"` for any deployment that doesn't explicitly opt in.
- **Does not delete the JSON seed** — `data/sla_tickets.json` remains as the canonical fallback. Banks running JSON-only continue to work unchanged.
- **Does not migrate the other 38 operational tables** — only `sla_tickets` gets a schema in v10.129. Other operational tables (debt_recovery, cards, audit_reviews, etc.) follow in subsequent drops, one at a time.
- **Does not migrate the rule registry** — `data/aggregation_rules.json` and `data/integration_layer_config.json` stay JSON-only for now. The PG path is operational-table reads only.
- **Does not change the v10.116 shim** — same `_data_source` config shape, same json/pg_view/auto modes, same default. v10.129 just adds one more table that the shim can read from.

---

## Next operational tables (recommended order for v10.130+)

Same recipe applied in order. Recommended sequence based on integration layer rule density:

1. **debt_recovery** — wired by 4 rules (K027, K113, K044, "Collection Throughput"); proven via v10.121 wires
2. **audit_reviews** — wired by 3 rules + 1 non-K-coded ("Audit Score"); seeded in v10.114
3. **agency_banking** — wired by K025 + others; v10.123 seed
4. **branch_log** — wired by K013 + others; v10.122 seed
5. **hr** — wired by K016, K018, K121-K128, "Staff Productivity"; v10.123 seed (200 records)

Each follows the same template: schema in `utils/db.py`, FLAT_MIGRATIONS entry in `scripts/migrate_to_postgres.py`, deployment note.

---

## Verification checklist

- [x] `sla_tickets` `CREATE TABLE` in `utils/db.py::SCHEMA_SQL`
- [x] All 19 columns from `data/sla_tickets.json` covered
- [x] PRIMARY KEY on `id`
- [x] Index on `assignee` (K039's staff_field)
- [x] Indexes on `status`, `priority`, `last_updated` (K039's predicate fields)
- [x] `sla_tickets` entry in `FLAT_MIGRATIONS` with column-tuple matching the schema
- [x] v10.116 shim default unchanged (still `"json"`)
- [x] v10.116 shim `_data_source` config supports `per_table.sla_tickets` override
- [x] G143 still 99/131 (75.6%) STRICT-READY (high) — no rule-density work in v10.129
- [x] Tests: `tests/test_integration_layer_v10_129.py`

---

— v10.129 PostgreSQL migration step
