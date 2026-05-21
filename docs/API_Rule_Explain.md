# API Reference — `GET /api/integration/rule-explain/{kpi_id}`

**Drop:** v10.132
**Status:** stable
**JWT:** required (`Depends(get_current_user)`)
**Role gating:** read-only, not gated (any authenticated role can call it)

---

## Endpoint

```
GET /api/integration/rule-explain/{kpi_id}?period={period}
                                          &staff_code={staff_code}
                                          &sample_size={n}
```

Returns a complete trace of how the integration layer computes actuals for `kpi_id` in `period`. Useful for:

- **Audit** — confirming a published number is correctly derived
- **Troubleshooting** — diagnosing why a number on a dashboard looks wrong
- **Onboarding** — showing new ops/analysts how a KPI is computed
- **Rule design** — verifying that a newly-added rule emits expected actuals

---

## Request

### Path parameters

| Param | Type | Description |
|---|---|---|
| `kpi_id` | string | The KPI identifier whose rule should be explained. Must be a registered active rule (see `GET /api/integration/rules` for the list). |

### Query parameters

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `period` | string | yes | — | Period filter in `YYYY-MM` format (e.g. `2026-04`). |
| `staff_code` | string | no | (all) | Narrow per-staff slice to one staff. When set, the response's `final_value.value` is the scalar for that staff. |
| `sample_size` | int | no | 5 | Number of sample matched rows to return in the response. Capped to range `[1, 20]`. |

---

## Response shape

```json
{
  "kpi_id":          "K001",
  "period":          "2026-04",
  "rule": {
    "kpi_id":            "K001",
    "source_table":      "loan_applications",
    "pattern":           "SUM",
    "description":       "Loan Disbursements",
    "value_field":       "amount",
    "period_field":      "last_updated",
    "decimals":          2,
    "invert":            false,
    "uses_extractor":    false,
    "...":               "(more rule metadata)"
  },
  "duplicate_rules": 0,
  "input_summary": {
    "total_rows_in_table":     724,
    "rows_in_period":          234,
    "rows_matching_predicate": 187,
    "distinct_staff_codes":    38
  },
  "sample_matched_rows": [
    {"id": "LMS00001", "client_name": "Strathmore University", "amount": 2372427, "...": "..."},
    "...up to sample_size rows..."
  ],
  "per_staff_actuals": {
    "300028": 12345678.90,
    "300080":  9876543.21,
    "...":     "..."
  },
  "final_value": {
    "for_staff": null,
    "value":     null,
    "decimals":  2
  },
  "source": "rule_explain_v10_132"
}
```

### Field reference

| Field | Description |
|---|---|
| `rule` | Full `_rule_to_dict()` output for the resolved rule. Same shape returned by `GET /api/integration/rules`. |
| `duplicate_rules` | Count of additional matching rules (library duplicates like K028/K048 — see Phase 1D retro). The first match is explained; this signals if more exist. |
| `input_summary.total_rows_in_table` | Raw row count in the operational JSON file. |
| `input_summary.rows_in_period` | Rows whose `period_field` value starts with `period` (uses internal `_row_in_period`). |
| `input_summary.rows_matching_predicate` | Rows that pass the rule's primary predicate (varies by pattern: `predicate` for COUNT, `numerator_pred` for PERCENTAGE, etc.). |
| `input_summary.distinct_staff_codes` | Number of distinct staff identifiers extracted from the matching rows. May exceed `per_staff_actuals` count if some predicate stages drop rows beyond the primary filter. |
| `sample_matched_rows` | Top `sample_size` rows from `rows_matching_predicate`. Strings >120 chars truncated to `…`; lists >5 items truncated to first 5 + count. |
| `per_staff_actuals` | Result of `compute_rule(rule, rows, period, staff_field)`. When `staff_code` is set, narrowed to one entry. |
| `final_value.value` | When `staff_code` is set: the scalar value for that staff. When `staff_code` is null: null (use `per_staff_actuals` for the dict). |

---

## Errors

| Status | Condition | Body |
|---|---|---|
| 400 | `period` not in `YYYY-MM` format | `{"detail": "Invalid period 'XYZ'; expected YYYY-MM"}` |
| 401 | JWT missing/invalid | (handled by `Depends(get_current_user)`) |
| 404 | `kpi_id` has no active rule in `REGISTRY` | `{"detail": "No active aggregation rule for kpi_id 'K9999'. Try GET /api/integration/rules to list available rules."}` |
| 500 | Operational table file missing | `{"detail": "Operational table 'foo' not found"}` |

---

## Use cases

### Use case 1 — explain a number on a dashboard

A user sees "K001 Loan Disbursements: KES 12,345,678.90" on their dashboard and wants to verify. Query:

```
GET /api/integration/rule-explain/K001?period=2026-04&staff_code=300028
```

Response shows:
- 187 loan rows matched the predicate in 2026-04
- 38 distinct rms have at least one row
- Their per-staff value is computed from N specific applications (visible in `sample_matched_rows`)
- The final scalar matches what the dashboard shows

### Use case 2 — debug why a rule emits zero

A newly-added rule shows 0 actuals. Query:

```
GET /api/integration/rule-explain/K123?period=2026-04
```

Response funnel reveals:
- `rows_in_period` = 0 → period_field is wrong, or no rows for this period
- `rows_matching_predicate` = 0 → predicate too restrictive
- `distinct_staff_codes` = 0 → staff_field doesn't appear in matching rows

This was the discipline used in v10.120's K090 pivot (initial period_field=issue_date yielded 0 fraud cards; pivoted to dispute_filed_date) — but back then it required manual scripting. Now it's an API call.

### Use case 3 — sanity-check before rule rollout

When wiring a new rule, hit the endpoint immediately after registering to verify:
- Sample rows look right
- Per-staff distribution is plausible
- Final value within expected range

Caught before the audit script runs and propagates bad numbers to the BSC engine.

---

## Equivalent CLI command

For ops without a REST client:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$API/api/integration/rule-explain/K001?period=2026-04&staff_code=300028" \
  | jq '.'
```

---

## Cockpit equivalent

The Streamlit cockpit at `pages/99_integration_cockpit.py` has a **Debug tab** (added v10.132) that mirrors this endpoint's output via direct utility calls (no HTTP round-trip). Same input funnel, same per-staff table, same sample row preview. Use the cockpit for interactive debugging; use the endpoint for automation, dashboards, and ops scripting.

---

## Implementation notes

- The endpoint imports `_row_in_period` and `compute_rule` directly from `utils.kpi_aggregation_rules` — same helpers `/api/integration/actuals/{period}` uses. **Funnel numbers and per-staff values are guaranteed identical** to what `/actuals` would return for the same rule in the same period.
- Sample row truncation prevents JSON bloat when source rows have >10K-char description fields (rare but possible in `audit_findings`, `legal_matters`).
- Library-duplicate handling (e.g. K028/K048 same name): explains the first match, signals duplicate count in `duplicate_rules` field.
- Read-only endpoint — no role-gating beyond JWT. Anyone authenticated can call it. (v10.117's role-gating applies only to writes via `POST /api/integration/run-period`.)
- Cache-free — explain calls always re-compute. Each call is bounded by table size (operational tables are <1K rows).

---

## See also

- `GET /api/integration/rules` — rule catalog
- `GET /api/integration/actuals/{period}` — bulk per-rule actuals (no per-row trace)
- `GET /api/integration/coverage` — G143 coverage summary
- `docs/Phase_1D_Integration_Layer_Retro.md` — full Phase 1D context
