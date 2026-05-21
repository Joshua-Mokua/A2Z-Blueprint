# PG migration deployment note — `loan_applications`

**Drop:** v10.131
**Status:** PG schema pre-existing since v10.89; integration-layer designation + supplementary indexes added v10.131. Default still JSON. Per-table opt-in required for cutover.
**Pattern:** different from v10.129/v10.130 — this is the **first integration-layer designation against a pre-existing PG table**. Architectural significance documented below.

---

## Why this drop is structurally different

`loan_applications` was added to PG in v10.89 (anti-drift Phase 1A migration batch 2). The integration layer then built its rule density on top of `data/loan_applications.json` over v10.108-v10.119, accumulating 6 wired rules without ever needing the PG path because the v10.116 `_data_source` shim defaults to JSON.

v10.131 closes the loop: declares `loan_applications` part of the integration layer's PG-eligible set. **No new schema needed** — the table already exists in PG with 60+ pre-Phase-1D anti-drift tables. v10.131 just adds 3 supplementary indexes for the Phase 1D query patterns and updates docs.

This proves the v10.116 shim works with **pre-existing** PG tables, not just newly-added ones. **Banks already running A2Z MIS 360 with the anti-drift PG migration completed will inherit the integration-layer PG path automatically when they flip per-table config — no schema migration required.**

---

## Scope — 6 wired rules become PG-capable

| KPI | Pattern | Period field | Notes |
|---|---|---|---|
| K001 | SUM | last_updated | Loan Disbursements (sum amount where status=Disbursed) |
| K010 | PERCENTAGE | last_updated | Loan Approval Rate |
| K011 | TAT_DAYS | last_updated | Application Approval TAT |
| K115 | COUNT | last_updated | Loan Application Volume |
| K045 | PERCENTAGE | application_date | Compliance Flag Rate |
| K046 | MEAN_FIELD | application_date | Avg Document Completeness |

All 6 rules use `rm_code` as the staff_field (registered in `STAFF_FIELD_BY_TABLE`). Pre-existing PG indexes already cover `status`, `rm_code`, and `application_date`. v10.131 adds:

- `idx_loan_apps_lastupd` — speeds period filtering for the 4 rules using `last_updated`
- `idx_loan_apps_tat` — K011 / K046 read `tat_days` directly
- `idx_loan_apps_complflag` (partial index, WHERE compliance_flag = TRUE) — K045 numerator predicate

---

## Cutover steps

Identical mechanics to v10.129/v10.130 — no PG schema migration step needed because the table already exists.

1. **Verify PG state:**
   ```sql
   SELECT count(*) FROM loan_applications;
   ```
   Should match `len(json.load(open('data/loan_applications.json')))`. If not, run `python scripts/migrate_to_postgres.py` to sync.

2. **Verify supplementary indexes:**
   ```sql
   \di+ loan_applications
   ```
   Confirm `idx_loan_apps_lastupd`, `idx_loan_apps_tat`, `idx_loan_apps_complflag` are present (added v10.131).

3. **Flip the integration-layer config:**
   ```json
   "_data_source": {
     "_default": "json",
     "per_table": {
       "sla_tickets": "pg_view",        // v10.129
       "debt_recovery": "pg_view",      // v10.130
       "loan_applications": "pg_view"   // v10.131
     }
   }
   ```

4. **Spot-check rule outputs:**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
        "$API/api/integration/actuals/2026-04?rule=K001"
   ```
   Compare with the pre-flip JSON-path output. Should be identical for the same period.

5. **Audit + monitor:**
   ```bash
   python scripts/audit.py    # G143 should still report 99/131
   ```

---

## Rollback

Same as v10.129/v10.130 — non-destructive:

1. Flip `_data_source.per_table.loan_applications` back to `"json"` (or remove the entry; falls back to `_default`).
2. The PG `loan_applications` table is untouched — no data loss because anti-drift migration kept it sync'd since v10.89.

The supplementary indexes (`idx_loan_apps_lastupd`, etc.) stay because they're idempotent CREATE INDEX IF NOT EXISTS. They benefit the existing Phase 1A anti-drift queries too.

---

## Verification commands

After flipping config:

```bash
# Verify per-rule output identical between JSON and PG paths
python -c "
import json
from utils.actuals_engine import compute_actuals_from_operational_tables

# Force JSON path
import os; os.environ.pop('A2Z_USE_DB', None)
json_out = compute_actuals_from_operational_tables('2026-04')

# Force PG path (assumes _data_source flipped + DB reachable)
os.environ['A2Z_USE_DB'] = '1'
pg_out = compute_actuals_from_operational_tables('2026-04')

# Compare loan_applications-related rules
for rule in ('K001', 'K010', 'K011', 'K115', 'K045', 'K046'):
    j = json_out.get(rule, {})
    p = pg_out.get(rule, {})
    match = j == p
    print(f'{rule}: {\"OK\" if match else \"DIFF\"} (JSON staff={len(j)}, PG staff={len(p)})')
"
```

All 6 should report `OK`. Any `DIFF` means a JSONB-vs-typed-column edge case (most likely a NULL-handling difference) — investigate before broader cutover.

---

## Summary

| Field | Value |
|---|---|
| Pattern | Integration-layer designation of pre-existing PG table |
| Schema work | 3 supplementary CREATE INDEX statements |
| FLAT_MIGRATIONS | Annotated; entry already existed since v10.89 |
| Wired rules covered | 6 (K001/K010/K011/K115/K045/K046) |
| Default behaviour | JSON (no change) |
| Opt-in | Per-table config flip in `_data_source.per_table.loan_applications` |
| Cumulative tables | **3 of 39** |

This is the most architecturally significant migration drop so far — it proves the v10.116 shim is universal across the 60+ pre-existing PG tables AND the new wired-39 set. The remaining 37 wired tables can be migrated drop-by-drop using whichever path applies (newly-added vs. pre-existing PG schema).
