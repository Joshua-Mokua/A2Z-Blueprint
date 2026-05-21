# PG migration deployment note — `debt_recovery`

**Drop:** v10.130
**Status:** schema + migration ready; default still JSON. Opt-in per-table flip required for cutover.
**Pattern:** identical to v10.129 `sla_tickets` (see `docs/PG_Migration_sla_tickets.md` for the full template).

---

## Scope

v10.130 applies the v10.129 sla_tickets recipe to the next operational table: **`debt_recovery`**. Higher rule density (4 wired rules vs sla_tickets' 1) proves the v10.116 `_data_source` shim handles multi-rule tables identically.

**4 rules wire debt_recovery:**

1. **K027** — Recovery Rate (RATIO pattern)
2. **K113** — Active Recovery Cases (COUNT pattern)
3. **K114** — Recovered Amounts (SUM pattern)
4. **Collection Throughput** — non-K-coded library entry (v10.121, COUNT pattern)

All 4 produce per-staff actuals via the `recovery_officer_code` staff_field. K027 + K113 + K114 are core BSC recovery KPIs.

---

## Why `debt_recovery` second

After v10.129 proved the pattern with sla_tickets (1 rule), v10.130 validates multi-rule tables:

1. **4 wired rules** — proves the shim handles read-once-aggregate-many correctly. All 4 rules read the same source_table; the shim returns the same row list to all of them in one call.
2. **150 records** — modest size; bulk-insert validates in < 1 second
3. **Mixed staff_field usage** — most rules use `recovery_officer_code`; some BSC variants may use `rm_code`. Both are indexed.
4. **No row-level security needed** — debt_recovery is operationally visible to credit/recovery teams; not flagged as confidential by audit policy.

---

## Schema

28 columns (including standard `data` JSONB + `created_at`/`updated_at`). PRIMARY KEY on `id`. 5 indexes:

- `idx_debt_recovery_officer` — primary staff_field for K027/K113/Collection Throughput
- `idx_debt_recovery_rm` — alternate staff_field for some BSC variants
- `idx_debt_recovery_status` — predicate field (Active/Settled/etc.)
- `idx_debt_recovery_dpd` — predicate field (overdue thresholds)
- `idx_debt_recovery_lastupd` — period_field for most rules

See `utils/db.py` SCHEMA_SQL for the full DDL. The `CREATE TABLE IF NOT EXISTS` is idempotent — re-runs of `scripts/migrate_to_postgres.py` are safe.

---

## Migration recipe (same as v10.129)

```bash
# 1. Set DB env vars (A2Z_USE_DB=true, A2Z_DB_HOST, etc. — see utils/db.py docstring)
# 2. Apply schema (idempotent — adds debt_recovery if not present)
python scripts/migrate_to_postgres.py
# 3. Flip _data_source for debt_recovery — edit data/integration_layer_config.json:
#    {
#      "_data_source": {
#        "default": "json",
#        "per_table": {
#          "sla_tickets":   "auto",   // already migrated v10.129
#          "debt_recovery": "auto"    // NEW v10.130
#        }
#      }
#    }
# 4. Verify K027/K113/K114/Collection Throughput rules produce identical
#    actuals between JSON and PG modes
python scripts/audit.py    # confirms G143 still 99/131 STRICT-READY (high)
```

---

## Rollback

One-line config revert:

```jsonc
{
  "_data_source": {
    "per_table": {
      "debt_recovery": "json"   // back to JSON-only
    }
  }
}
```

`data/debt_recovery.json` is **never deleted by v10.130** — remains as canonical fallback.

---

## Pattern progress

| Drop | Operational table migrated to PG schema | Wired rules |
|---|---|---|
| v10.129 | `sla_tickets` | 1 (K039) |
| **v10.130** | **`debt_recovery`** | **4 (K027 + K113 + K114 + Collection Throughput)** |
| v10.131 (planned) | `audit_reviews` (recommended) | 4 (3 K-coded + Audit Score) |
| v10.132+ (estimated) | agency_banking, branch_log, hr, ... | one per drop |

**2 of 39 integration-layer operational tables now have PG schemas: `sla_tickets` (v10.129) + `debt_recovery` (v10.130).** Remaining 37 wired tables follow the same recipe in subsequent drops.

---

— v10.130 PostgreSQL migration step 2
