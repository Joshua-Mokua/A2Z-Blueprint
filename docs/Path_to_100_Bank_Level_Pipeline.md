# Path to 100% — Bank-Level Pipeline Architecture

**Status:** proposal / design sketch. Not yet implemented.
**Authored:** v10.126
**Owner:** A2Z MIS 360 / Joshua Mokua
**Targets:** the ~32 unwired KPIs categorised as Category A (bank-level) in `Phase_1D_Integration_Layer_Retro.md`.

---

## Problem statement

The Integration Layer (Phase 1D, v10.108-v10.125) covers 99/131 (75.6%) of operational KPIs in `kpi_library.json`. Per-staff aggregation works. The remaining 32 KPIs are bank-level — aggregates over the whole bank's books at a point in time, with no per-staff dimension.

**They cannot be force-fit into per-staff aggregation** without inventing fake ownership mappings. Examples:
- K080 Capital Adequacy Ratio is computed as (Tier1 Capital + Tier2 Capital) / RWA. There's no "owner" of the ratio — it's a balance sheet snapshot.
- K066 System Uptime is a fraction of seconds the system was up over a window. Not per-engineer.
- K002 Deposits Mobilised is a portfolio-level KES total. Per-RM contribution would be an entirely different KPI (and isn't K002).

These need a **separate aggregation pipeline** with different semantics.

---

## Design

### Two parallel pipelines

```
                       ┌─────────────────────────────┐
                       │ Integration Layer (Phase 1D) │
                       │ data/[per_staff_table].json │
                       │   compute_rule(rule, rows,   │
                       │     period, staff_field)     │
                       │   → {staff_code: value}      │
                       │                              │
                       │ 100 rules, 39 tables, 75.6% │
                       │ STRICT-READY (high)         │
                       └─────────────────────────────┘
                                    │
                                    │  /api/integration/actuals/{period}
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │       BSC Engine                 │
                    │  per-staff scorecards            │
                    └──────────────────────────────────┘
                                    ▲
                                    │  /api/bank_level/aggregates/{period}
                                    │
                       ┌─────────────────────────────┐
                       │ Bank-Level Pipeline (1E)    │
                       │ data/[bank_level_src].json  │
                       │   compute_aggregate(rule,    │
                       │     source_data, period)     │
                       │   → numeric_value            │
                       │                              │
                       │ ~32 rules, ~14 sources       │
                       └─────────────────────────────┘
```

**The BSC engine consumes both** — per-staff scorecards display individual scores; bank-level dashboards display the aggregates. KPIs are owned by one pipeline or the other; never both.

### Bank-level rule shape

Same JSON file (`data/aggregation_rules.json`) — keeps tooling unified — but rules tagged `pipeline: "bank_level"`:

```json
{
  "kpi_id": "K080",
  "active": true,
  "pipeline": "bank_level",
  "source_table": "capital_liquidity",
  "aggregator": "snapshot_field",
  "field": "capital_adequacy_ratio",
  "period_field": "as_at",
  "decimals": 2,
  "_origin": "v10.13X_bank_level_pipeline"
}
```

vs the existing per-staff shape:

```json
{
  "kpi_id": "K018",
  "active": true,
  "pipeline": "per_staff",
  "source_table": "hr",
  "pattern": "PERCENTAGE",
  "numerator_pred": {...},
  "denominator_pred": {...},
  "period_field": "last_updated",
  "decimals": 2,
  "_origin": "v10.123_window4_seeds"
}
```

**The `pipeline` discriminator** is the key new field. Rules without a `pipeline` field default to `per_staff` (preserves all existing v10.108-v10.125 rules unchanged).

### Bank-level aggregator types

Six aggregator types cover the bank-level cases:

| Aggregator | Semantics | Example KPI |
|---|---|---|
| `snapshot_field` | Single-row dict; emit field value as-is | K080 CAR (point-in-time ratio) |
| `sum_field` | Sum a numeric field across rows in period | K002 Deposits Mobilised, K003 Fee Income |
| `count_records` | Count records in period | K006 New Accounts Opened |
| `ratio_fields` | Sum(field_a) / Sum(field_b) | K004 NPL Ratio (npl/total_loans), K021 Cost-to-Income |
| `growth_rate` | (current_period - previous_period) / previous_period | Loan Book Growth, Commercial Deposit Growth |
| `percentage_field` | Bool field's True-rate × 100 | K012 Digital Transactions (% of all txns) |

These are deliberately simpler than the per-staff patterns. Bank-level KPIs are mostly arithmetic on totals; they don't need predicates as complex as the per-staff DSL.

### Source-shape adapters

Bank-level sources come in three shapes:

1. **Single-row dict** (cybersecurity, contact_centre, digital_channels, esg_climate) — already exist this way; aggregator reads field directly
2. **Dict-of-arrays** (alm_liquidity has gap_analysis/funding_sources/alco_meetings/contingency_plans) — adapter selects the named array, then aggregates
3. **List-of-dicts with as_at field** (capital_liquidity, cbs_*, management_accounts, channels, flexcube, observability) — needs to be seeded; aggregator filters to as_at in period, then reduces

Adapter logic lives in `utils/bank_level_aggregator.py` (new file).

### New API endpoint

```
GET /api/bank_level/aggregates/{period}

Response:
{
  "period": "2026-04",
  "aggregates": [
    {
      "kpi_id": "K080",
      "kpi_name": "Capital Adequacy Ratio (%)",
      "value": 18.4,
      "as_at": "2026-04-30",
      "decimals": 2
    },
    ...
  ],
  "missing": [
    {"kpi_id": "K109", "reason": "no flexcube data for period"}
  ]
}
```

JWT-protected. Read-only (no writes for bank-level KPIs — they're computed from upstream sources, not entered by users).

### Coverage gate

New audit gate **G144 `bank_level_aggregator_coverage`** mirrors G143 but for bank-level rules:

```python
def gate_bank_level_aggregator_coverage():
    bank_level_kpis = [k for k in lib['kpis'] if is_bank_level(k)]
    covered = [k for k in bank_level_kpis
               if any(r for r in REGISTRY
                      if r.kpi_id == k['id'] and r.pipeline == 'bank_level')]
    coverage = len(covered) / len(bank_level_kpis)
    # Same strict-preview tier semantics as G143
    return {"passed": True, "summary": f"...{coverage}..."}
```

### Strict-flip semantics revised

**G143 in informational-pass mode** stays unchanged through the bank-level pipeline build. When G143 + G144 both reach 100%, **strict-flip** flips both to `passed: False at < 100%`.

Alternative framing: G143 reframes its denominator to per-staff KPIs only (treating bank-level as out-of-scope), and reaches 100% just by completing the per-staff backlog. Then G144 separately tracks bank-level coverage at its own pace.

Decision deferred to v10.130+ — depends on how the bank-level pipeline lands and how product wants to surface coverage in dashboards.

---

## Effort estimate

| Phase | Drops | Work |
|---|---|---|
| 1E.1 design | 1 | Pipeline contract + rule-shape spec + adapter interfaces |
| 1E.2 first source | 1-2 | Wire one bank-level KPI end-to-end (e.g., K080 CAR on capital_liquidity) — proof of concept |
| 1E.3 single-row sources | 1-2 | cybersecurity, contact_centre, digital_channels, esg_climate (these already exist as single-row dicts) — ~10 KPIs |
| 1E.4 list-of-dicts seeds | 2-3 | Seed capital_liquidity, cbs_loans, cbs_deposits, cbs_fees, management_accounts, channels, flexcube, observability — ~22 KPIs |
| 1E.5 alm_liquidity adapter | 1 | Dict-of-arrays special handling; ~4 KPIs |
| 1E.6 G144 audit gate | 1 | Mirror G143 semantics for bank-level coverage |
| 1E.7 API endpoint | 1 | `GET /api/bank_level/aggregates/{period}` |
| 1E.8 React dashboard | 1-2 | Display bank-level + per-staff aggregates in coordinated cockpit |
| 1E.9 strict-flip | 1 | When G143 + G144 both at 100%, flip both to strict mode |

**Total: ~10-15 drops** for Phase 1E end-to-end.

Alternative: skip the bank-level pipeline entirely if business decides bank-level KPIs come directly from FLEXCUBE/G/L systems via a different ingestion path (e.g., direct ETL into management_accounts schema) and the integration layer only owns per-staff KPIs. In that framing, Phase 1D is complete at v10.125 and Phase 1E focuses on standards #14-#20 / React / FATCA-CRS instead.

---

## Recommendation

The bank-level pipeline is **architecturally clean** but **not on the critical path** for the Eco Bank evaluation. Per-staff KPIs are what differentiate A2Z MIS 360 from competitors — those are the ones that drive cockpit-style 360-degree management intelligence. Bank-level KPIs are commodity reporting that any vendor can produce.

**Recommend Phase 1E focus on standards backlog and React dashboards instead.** Bring the bank-level pipeline back as Phase 1F or 1G when the per-staff cockpit is fully demonstrated and the bank-level reporting becomes the visible gap.

But that's a programme-level call, not a technical one. The technical design above is ready when the call is made.

— v10.126
