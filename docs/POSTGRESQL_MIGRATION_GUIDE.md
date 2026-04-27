# PostgreSQL migration guide

How A2Z migrates from JSON files to PostgreSQL, one table at a time, without breaking running pages.

> **Status:** active convention from v5.10 onwards
> **Owner:** A2Z platform engineering
> **Last review:** v5.13

---

## 1. The pattern: dual-mode I/O

Every page in A2Z reads and writes data through `utils.db.db.load_json()` and `utils.db.db.save_json()` — never directly. The function bodies look at a registry called `TABLE_USE_DB` to decide whether the data lives in JSON on disk or in a PostgreSQL table.

```python
# In utils/db.py
TABLE_USE_DB = {
    "users":             False,   # still JSON
    "departments":       True,    # migrated to auth.departments
    "kpi_library":       True,    # migrated to performance.kpi_catalogue
    # ... 50+ entries
}
```

When a page calls `a2z_db.load_json("users")`:
- If `TABLE_USE_DB["users"]` is `False` → reads `data/users.json` from disk.
- If `True` → executes `SELECT ... FROM auth.users` and reconstructs the same shape.

The page never knows which mode is active. Migration is a flag flip.

---

## 2. Migration steps for one table

For each JSON file, run these steps in order. Don't combine them.

### Step 1 — write the SQL schema

Add the table definition to `utils/db.py` under the relevant schema (`auth`, `performance`, `credit`, `finance`, `risk`, `staging`, or `audit`). Use the schema's purpose:

| Schema | Use for |
|--------|---------|
| `auth` | users, roles, permissions, departments, branches |
| `performance` | KPIs, scorecards, actuals, targets |
| `credit` | loans, watchlist, EWS, IFRS9 |
| `finance` | GL, P&L, budget, recon results |
| `risk` | RCSA, AML alerts, compliance |
| `staging` | FLEXCUBE staging tables (transient) |
| `audit` | hash-chained audit log, ETL runs, recon runs |

Example for `kpi_library.json`:

```sql
CREATE TABLE IF NOT EXISTS performance.kpi_catalogue (
    kpi_id        TEXT PRIMARY KEY,
    kpi_name      TEXT NOT NULL,
    pillar        TEXT NOT NULL,
    weight_pct    NUMERIC(5,2),
    direction     TEXT,           -- 'higher_is_better' | 'lower_is_better'
    unit          TEXT,
    config_json   JSONB,          -- everything else stays as JSON for flex
    last_updated  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kpi_catalogue_pillar ON performance.kpi_catalogue(pillar);
```

Run the schema migration via `python scripts/migrate_to_postgres.py --schema-only --table kpi_library`.

### Step 2 — write the load/save adapter

In `utils/db.py`, add the table's load/save logic to the `_load_from_pg()` and `_save_to_pg()` dispatchers. The adapter must produce the **exact same shape** the JSON file has, so callers don't notice the switch.

```python
# in _load_from_pg():
elif table_name == "kpi_library":
    rows = self.fetch_all("SELECT * FROM performance.kpi_catalogue ORDER BY pillar, kpi_id")
    return {"kpis": [_row_to_kpi(r) for r in rows]}
```

If your JSON file is a list, the adapter returns a list. If it's a dict with nested structures, the adapter rebuilds the dict. **Shape parity is non-negotiable.**

### Step 3 — backfill the data

Run `python scripts/migrate_to_postgres.py --table kpi_library --copy`. This reads the existing JSON file and inserts every row into the PG table. Idempotent — uses `ON CONFLICT DO UPDATE`.

### Step 4 — verify shape parity

With the flag still set to `False` (JSON mode), capture a snapshot:

```bash
python -c "from utils.db import db; import json; print(json.dumps(db.load_json('kpi_library'), sort_keys=True))" > /tmp/before.json
```

Now flip the flag to `True` (PG mode) and capture the same:

```bash
python -c "from utils.db import db; import json; print(json.dumps(db.load_json('kpi_library'), sort_keys=True))" > /tmp/after.json
```

Diff them. They must be byte-identical:

```bash
diff /tmp/before.json /tmp/after.json
# expected: empty output
```

If the diff isn't empty, your adapter is wrong. Fix the adapter, don't fix the data.

### Step 5 — flip the flag

Set `TABLE_USE_DB["kpi_library"] = True` in `utils/db.py`. Restart Streamlit. Smoke-test the pages that read this table (BSC, KPI Library, Cascade). If anything breaks, set the flag back to `False` and investigate.

### Step 6 — log the migration

Add an entry to `docs/MIGRATION_LOG.md`:

```markdown
| Date | Table | Schema | Rows | Verified by |
|------|-------|--------|------|-------------|
| 2026-04-27 | kpi_library | performance.kpi_catalogue | 113 | <name> |
```

### Step 7 — run the audit

```bash
python scripts/audit.py
```

The score should not regress. If it does, find out why before continuing.

---

## 3. Per-table priorities

Migrate in this order. Highest-priority tables are touched by the most pages, so migrating them first delivers the biggest reliability and concurrency wins.

| Priority | Table | Pages affected | Why |
|----------|-------|----------------|-----|
| P1 | users | every page (auth) | Concurrency: multiple admins editing |
| P1 | kpi_library | BSC, cascade, KPI library | Read-heavy across all 7K users |
| P1 | departments | every page (RBAC) | Concurrency: org changes |
| P2 | branches | retail, ops, branch log | Concurrency: branch open/close |
| P2 | bsc_actuals_<period> | performance pages | Heavy writes monthly |
| P2 | pipeline_deals | pipeline, deal room | Concurrent deal updates |
| P3 | audit_log | every writer page | Already partially in PG (audit schema) |
| P3 | recon_runs | recon centre | Already partially in PG |
| P4 | tier1_benchmarking | benchmarking page | Read-mostly, small file |
| P4 | proposition_config | admin, propositions | Read-mostly, infrequent updates |

**Don't migrate everything.** Tables that are tiny, read-only, and rarely edited (like `tier1_benchmarking.json`) can stay as JSON forever. The rule: migrate if multi-user write concurrency matters, or if the file is bigger than ~1MB.

---

## 4. Foundational files (do not migrate)

These files are exempt from the migration. They use direct file I/O because **they implement the seam itself** — they cannot route through `a2z_db` without infinite recursion or bootstrap-order issues:

- `utils/db.py` — the seam itself
- `utils/core.py` — bootstrap (UserManager, audit chain)
- `utils/config.py` — config loader
- `utils/reconciliation.py` — reads multiple sources side-by-side
- `utils/flexcube_adapter.py` — synthetic mode reads CSVs
- `utils/api.py` — FastAPI endpoint definitions
- `utils/notifications.py` — notification log primitives
- `scripts/etl_flexcube.py` — the pipeline that **feeds** the seam
- `scripts/migrate_to_postgres.py` — the migration tool itself

The audit script (`scripts/audit.py`) knows about this list and excludes it from violation counts. If you add a new foundational file, add it to both the audit's `FOUNDATIONAL` set and this guide.

---

## 5. Rollback procedure

Every migration must be reversible without data loss. To roll back:

1. Set `TABLE_USE_DB[table_name] = False` in `utils/db.py`.
2. Run `python scripts/migrate_to_postgres.py --table <name> --export-back` to write current PG state back to the JSON file.
3. Restart Streamlit.
4. Pages now read from JSON again. PG table is left intact (data isn't lost).

This means an aborted migration doesn't strand any data. The PG table can sit unused until you're ready to retry.

---

## 6. Status as of v5.13

```
21 / 52 tables  PG-enabled      (40%)
31 / 52 tables  still JSON      (60%)
 9 / 52 tables  foundational     — exempt from migration
```

Run `python scripts/audit.py` and check Gate G2 for the live count.

The master prompt's claim of "91% PG-capable" referred to the **architectural seam** being in place (every page calls `a2z_db`, not direct I/O). The actual **PG-enabled** number is much lower — that's the work this guide is here to drive forward.

---

*Guide v1.0 generated for v5.13. Update the priority list as tables migrate.*
