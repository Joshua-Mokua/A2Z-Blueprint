# BSC actuals — closing the loop (design, for review before build)

**Symptom:** every Actual/Achievement on every scorecard renders "—", "0 scored", OVERALL —/5.

## Root causes (both confirmed by probe)

1. **Period format.** The scorecard route defaults to `period="2026"`, but
   `bsc_engine._normalise_period` accepts only `YYYY-MM` / `YYYY-QN` and returns `None`
   for a bare year — so `get_actual` bails before looking. Proven:
   `get_actual('300001','K001','2026-01') -> 1.0` but `('...','2026') -> None`.
2. **No 2026 data.** `bsc_actuals_2026-01.json` holds 3 records. The CBS engine computes
   33,219 rows into `actuals_*.xlsx`, but nothing feeds them into the store via `submit()`.

## What ALREADY exists — reuse, do not rebuild

| component | role |
|---|---|
| `bsc_engine.submit()` | canonical write: validate → enrich → persist → audit → invalidate index |
| `bsc_engine.get_actual()` | O(1) indexed read, mtime-invalidated |
| `bsc_engine._normalise_period` | single-period validator (`YYYY-MM`, `YYYY-QN`) |
| `bsc_score_computation.resolve_role_kpis` | role → KPI set, effective weights, canonical ids |
| `bsc_score_computation.compute_staff_scorecard(.., basis)` | `basis` = **stretch/target** (NOT aggregation — name is taken) |
| `kpi_aggregation_rules.py` | registry: rules read operational tables → per-staff actuals. Patterns COUNT/SUM/PERCENTAGE/TAT_DAYS/RATIO/BOOL_FRACTION/TAT_FIELD/MEAN_FIELD. **Aggregates rows WITHIN a period.** |
| `kpi_alias_resolver` | alias → canonical KPI id |
| `cbs_manager.get_portfolio_for_codes` | managed/introduced lens; computes `deposit_movement` vs baseline |
| `data/cbs_baseline_2025_Dec_31.json` | frozen 31-Dec snapshot with `bank_aggregates`, `per_rm`, `per_branch` |

## The genuine gap: aggregation ACROSS periods

Per Josh's domain correction there are three kinds of KPI:

| aggregation | KPIs | meaning of "2026 actual" |
|---|---|---|
| `cumulative` | Revenue, PBT, Fee Income, disbursement volumes | sum of the year's periods (YTD) |
| `balance_growth` | Total Deposits, Net Loans, loan book, portfolio balances | **closing balance** (a stock, not a flow) + growth vs the 31-Dec baseline. Can be NEGATIVE — you can lose deposits. Base is the portfolio/branch/unit total balance. |
| `latest` | NPL %, Cost-to-Income, ROE, LDR, CX/NPS, TAT days | most recent period's value. Never summed. |

No KPI in `kpi_library.json` declares this today (union of keys has no aggregation field).

## Proposed build (3 phases, each independently verifiable)

### Phase 1 — declare aggregation per KPI
- Add an optional `aggregation` field to `kpi_library.json` KPI records.
- Where absent, DERIVE conservatively:
  - unit in {%, ratio, score, days, percent} OR direction 'lower' → `latest`
  - name matches deposit/loan book/portfolio/balance/book → `balance_growth`
  - else → `cumulative`
- Ship a report of the derived classification for Josh to correct before it is written.
  Deriving silently would bake in wrong assumptions on 400 KPIs.

### Phase 2 — year resolution in bsc_engine (additive, no behaviour change to existing calls)
- Keep `_normalise_period` exactly as-is (canonical single-period validator).
- ADD `get_actual_for_year(staff_code, kpi_id, year, aggregation)`:
  - `cumulative`   → sum of that year's period values present in the store
  - `latest`       → value from the most recent period present
  - `balance_growth` → latest balance, plus baseline from
    `cbs_baseline_2025_Dec_31.json` (per_rm / per_branch / bank_aggregates by scope)
    returning {value, baseline, growth}
- `bsc_score_computation._get_actual` calls it when the period is a bare year;
  single-period calls keep working unchanged.

### Phase 3 — feed 2026 actuals through the canonical path
- The CBS engine already computes the numbers. Bridge them via `bsc_engine.submit()`
  (never by writing the JSON directly) so validation, audit and index invalidation hold.
- Prefer registering rules in `kpi_aggregation_rules` where the source is an operational
  table, so this rides the existing autofit pipeline rather than a parallel one.

## Decisions needed from Josh
1. **Growth display.** For `balance_growth` KPIs should the scorecard's Actual column show
   the closing balance, or the growth (current − baseline)? Target is a growth target, so
   comparing a balance to a growth target would be wrong. Recommendation: Actual = growth,
   with the balance shown as context.
2. **Cumulative source.** Are stored monthly values discrete per-month amounts (so summing
   is right), or already YTD-to-date figures (so summing would double-count and we should
   take the latest)? The source xlsx has a `YTD_Actual` column, which suggests the latter.
3. Confirm the derived classification report before it is written to the library.
