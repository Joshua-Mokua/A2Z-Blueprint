# Changelog — v10.323 Pipeline → BSC bridge (sales roles scoring)

**Date:** 2026-05-11
**Phase:** 4 (tenth arc — pipeline is the canonical sales producer)
**Audit:** 214/214 gates PASS = 100.0%
**Tests:** 525/525 passing across 30 integration suites
**G162 Rebase:** none — 19 consecutive zero-drift batches

---

## Your design insight (that drove this batch)

> "after this i would love us to also do the sales roles up since
> this encompases the pipeline module, even the teller and other
> roles can also use the pipeline since part of their KPIs
> involve, deposits growth and accounts"

This was the right architectural call. v10.317's Teller activity
generator hardcoded 7 KPIs (CX/Audit/Staff Productivity + four
K-codes) and didn't touch deposits/disbursements — which ARE real
Teller activities. Building separate generators per role would
have meant re-implementing pipeline-like logic 8+ times.

The pipeline module is already the canonical place where sales
activity happens. Multiple roles legitimately tap into it:

- **Tellers** (deposits opened at counter, new accounts)
- **Direct Sales Reps** (outbound new business)
- **Branch Relationship Managers / Officers** Personal & Business
- **Branch Senior Relationship Officers** (deal pipeline)
- **Relationship Managers Corporate/SME/Public Sector**
- **Bancassurance Relationship Officers** (insurance sales)

Their BSC KPIs around `Disbursements Retail/MSME/Corporate`,
`Total NFI`, `Retail & MSME Deposit Growth` should pull data
**from the pipeline** rather than from role-specific generators.
One activity stream serves many BSC views.

## What shipped

### New module: `utils/pipeline_to_bsc.py`

The bridge between the pipeline module and the BSC engine.

```
deal in pipeline.json (Disbursed/Closed Won/Signed/Documentation)
   ↓ (product → KPI mapping)
DealContribution(staff_code, period, kpi_id, value)
   ↓ (aggregate by staff/period/KPI)
AggregatedActual
   ↓ (submit via bsc_engine)
BSC actuals consumed by scoring engine (v10.319-320)
```

Five public functions:
- `load_pipeline()` — reads `data/pipeline.json`
- `load_mapping()` — reads `data/pipeline_kpi_mapping.json`
- `deal_to_contribution(deal, mapping)` — single deal → contribution
- `aggregate_contributions(...)` — sum per (staff, period, kpi)
- `sync_pipeline_to_bsc()` — full pipeline run, idempotent

Plus the canonical helpers:
- `period_from_date(date_str)` — converts `"2026-04-15"` → `"2026-Q2"`
- `is_won_stage(stage, mapping)` — Disbursed/Closed Won/Signed/Documentation
- `all_contributions()` — convenience full-pipeline walk

### New config: `data/pipeline_kpi_mapping.json` (admin-editable)

Maps each pipeline product to its canonical KPI. The 33 products
that show up in pipeline.json all classified:

```
"Personal Loan"      → "Disbursements Retail Loans"
"SME Term Loan"      → "Disbursements MSME Loans"
"Corporate Loan"     → "Disbursements Corporate Loans"
"Current Account"    → "Retail & MSME Deposit Growth"
"Insurance"          → "Total NFI"
... (33 mappings)
```

Plus fee rates per product type for Total NFI estimation (e.g.,
Insurance commission 12.5%, loan origination fees 1.5%) — also
admin-configurable without touching code.

### New config: `data/role_default_targets.json`

Per-role per-period default targets for sales roles when no per-
staff cascaded target exists. 18 sales roles configured:

```
"Branch Relationship Manager":
  Disbursements Retail Loans: 50,000,000 KES per quarter
  Disbursements MSME Loans:   80,000,000 KES per quarter
  Total NFI:                  3,000,000 KES per quarter
  Retail & MSME Deposit Growth: 30,000,000 KES per quarter

"Direct Sales Representative - Assets & Liabilities":
  Disbursements Retail Loans: 30,000,000 KES per quarter
  Total NFI:                  1,500,000 KES per quarter
... (16 more roles)
```

Used by `get_target_for_staff()` as the third fallback layer
(after bank_targets and target_cascade).

### Critical fix in `utils/bsc_score_computation.py`

**Removed the bank_targets fallback in `is_fixed_kpi`.** Previously
any KPI with a bank_targets entry was treated as "fixed"
(bank-level, same target for everyone). That was wrong for volume
KPIs — a Direct Sales Rep shouldn't be scored against the BANK's
50bn deposit growth target. They should be scored against their
own quarterly target.

**Before v10.323**: `is_fixed_kpi("Disbursements Retail Loans",
"2026-Q2")` returned `True` because there's a bank-level target
of 230bn. The Rep's actual 30M got divided by 230bn → 0.01%
achievement → score 1.0.

**After v10.323**: `is_fixed_kpi` now checks `fixed_kpis.json`
ONLY. Score-type bank-level KPIs (CX Score, Audit Score) are still
fixed (admin-marked). Volume KPIs (Disbursements, Loan Growth)
use the per-staff target fallback chain:
1. `target_cascade[staff_code|KPI|YEAR]` (from cascade if set)
2. `role_default_targets[role][period][KPI]` (per-role quarterly)
3. None (KPI skipped from scoring)

## Pipeline data flowing through to scorecards

**42 won deals in pipeline.json** (across 33 products, 2026-Q2)
**→ 41 aggregated BSC actuals** (some staff have multiple deals
   for same KPI)
**→ submitted to bsc_engine** with `source=pipeline_bridge`

Breakdown by KPI:
| KPI | Actuals |
|-----|---------|
| Disbursements MSME Loans | 12 |
| Disbursements Retail Loans | 7 |
| Disbursements Corporate Loans | 5 |
| Retail & MSME Deposit Growth | 4 |
| Total NFI | 13 |

## Cascade scores: 542 → 584 staff with scores in 2026-Q2

The pipeline bridge made **42 additional staff scorecard-computable**
in 2026-Q2:

| Role | Now scoring (was 0) |
|------|---------------------|
| Branch Relationship Manager | 17 |
| Relationship Officer - Business Banker | 6 |
| Relationship Officer - Personal Banker | 6 |
| Branch Senior Relationship Officer | 5 |
| Relationship Officer Bancassurance | 5 |
| Direct Sales Representative - Assets & Liabilities | 1 |
| General Manager - Bancassurance | 1 |
| Manager Underwriting | 1 |

Sample scorecards:
- **Bancassurance RO 300497**: 3.25/5.0 (MSME 50% achievement, Corporate 125%)
- **Branch Senior RO 300237**: 5.0/5.0 (MSME deals well above target)

## MD's Q2 trajectory now genuinely multi-source

Before v10.323, MD's score for any period came only from the
Retail Banking subtree (Tellers via v10.317). 2026-Q2 now also
includes:

- Bancassurance subtree (via Insurance/Investment deal contributions)
- Sales force across all branches (RM/RO sales actuals)

MD's Q2 score (2.95) is the mean of 2 Chief-level scores:
- General Manager Bancassurance: 2.55 (Bancassurance sales)
- Chief Retail Banking: 3.35 (Retail Tellers + RM/RO sales)

The drop from Q1 (3.46) to Q2 (2.95) is **coverage expansion, not
performance degradation** — earlier quarters only saw Chief Retail,
Q2 also sees Bancassurance.

## New audit gate G214 — pipeline_to_bsc_bridge

Locks the bridge surface area + mapping config + role defaults +
the critical `is_fixed_kpi` fix. Checks:

1. `utils.pipeline_to_bsc` exports `load_pipeline`, `load_mapping`,
   `period_from_date`, `is_won_stage`, `deal_to_contribution`,
   `aggregate_contributions`, `all_contributions`,
   `sync_pipeline_to_bsc`, `DealContribution`, `AggregatedActual`,
   `SyncReport`
2. `data/pipeline_kpi_mapping.json` has `product_to_kpi` with ≥30 entries
3. `data/role_default_targets.json` has `role_defaults` with ≥15 sales roles
4. Sample pipeline deal contributions resolve to canonical KPIs
5. `is_fixed_kpi` returns `False` for volume KPIs that aren't in
   `fixed_kpis.json` (the regression test for the fallback removal)
6. Bancassurance RO 300497 scorecard computes in 2026-Q2 (the
   demonstrable sales role scoring case)

## Configurable vs hardcoded — Rule of Configurability honoured

**CONFIGURABLE**:
- `pipeline_kpi_mapping.json`: product → KPI mapping (admin adds
  new products without code changes)
- `pipeline_kpi_mapping.json` fee rates per product type
- Stage names treated as "won" / "lost" (admin can rename pipeline stages)
- `role_default_targets.json`: per-role quarterly defaults
- `fixed_kpis.json`: which KPIs are bank-level fixed per period

**HARDCODED** (system invariants):
- Period-from-date formula (`YYYY-QN` quarter assignment)
- Bridge contribution shape (`DealContribution` dataclass)
- Idempotency key (staff + period + kpi)
- Sum aggregation for money-type KPIs (matches v10.321's
  `aggregation_for_kpi` heuristic)

## Real findings during this batch

1. **The `is_fixed_kpi` fallback was hiding real bugs.** When a
   volume KPI like "Disbursements Retail Loans" has a bank-level
   target of 230bn KES, scoring a 30M deal against it gives 0.01%
   achievement = score 1.0. The system was producing nonsense
   scores for sales staff before v10.323. Removed the fallback,
   now sales scoring uses per-role per-period defaults.

2. **Sales roles needed per-staff or per-role targets to score.**
   Without per-staff cascade entries and without bank-level
   targets being applicable, sales scoring had no target. The
   role_default_targets.json is the pragmatic fallback — admin
   sets a reasonable quarterly target per role, all staff in that
   role share it until per-staff cascade entries are populated.

3. **The bridge is idempotent.** Running `sync_pipeline_to_bsc()`
   twice doesn't double-count — uses `(staff_code, period, kpi_id)`
   as the unique key and `source=pipeline_bridge` + deal ID list
   in `detail` to identify existing submissions.

4. **Pipeline data was ready.** The pipeline.json had 42 won deals
   across 33 products in 2026-Q2 already — just needed the bridge
   to surface them as BSC actuals. No data backfill needed.

5. **G162 holds at 4022. 19 consecutive zero-drift batches.** The
   bridge uses generic terms ("the regulator", "core banking
   system") — no tenant tokens hardcoded.

## Platform state

| Metric | v10.322 → v10.323 |
|--------|-------------------|
| Audit gates | 213 → **214** |
| Integration test suites | 29 → **30** |
| Tests passing | 503 → **525** |
| Bridge modules | 0 → **1** (pipeline_to_bsc) |
| Configurable mappings | 0 → **2** (pipeline_kpi_mapping, role_default_targets) |
| BSC actuals from pipeline | 0 → **41** (across 5 KPIs) |
| Sales staff scoring | 0 → **42** (in 2026-Q2) |
| Total staff scoring 2026-Q2 | 542 → **584** |
| G162 baseline | 4022 (19 consecutive zero-drift batches) |

## Backlog status

| ID | Status |
|----|--------|
| **B-013** | ✅ Closed (v10.321 manager rollup) |
| **B-019** | ✅ Closed (v10.320 bank target hygiene) |
| B-009 | Open | IFRS9 product field |
| B-010 | Partial (v10.320 auto-aliasing) | 26 unresolved refs (B-020) |
| B-011 | Open | Dept naming |
| B-014 | Open | get_org_config Streamlit dep |
| B-015 | Open | core.py stale defaults |
| B-016 | Open | cascade page LEVEL_ORDER/ROLE_MAP fallback |
| B-017 | Open | Direct I/O in pages |
| B-018 | Informational | Weight sums (math correct via runtime normalization) |
| B-020 | Open | 26 KPI refs need definitions |

## What this unlocks for the demo

The cascade demo now genuinely spans sales:

> "Click MD → see organisation scorecard. Drill into Chief Retail
> → see retail performance from both **Tellers** (counter activity
> via v10.317) and **Sales staff** (RM/RO sales via v10.323 pipeline
> bridge). Drill into a Branch Relationship Manager → see their
> sales scorecard with disbursements, deposit growth, NFI. Click
> a specific RO → see their individual KPI breakdown with the
> deals that drove each score."

**Demonstrable end-to-end for the demo**:
- Targets cascade from MD to RM (v10.318)
- Tellers generate counter activity (v10.317)
- Sales staff close deals in pipeline → bridge translates to BSC actuals (v10.323)
- Manager rollups aggregate across team (v10.321)
- Cascade scores pre-computed for trends (v10.322)
- Everything visible at any level in the org tree

## Next batch options

With v10.323 closing, the demo is functionally complete. Remaining
work is polish:

1. **v10.324 — Cleanup B-015 + B-016**: stale-role refs in core.py
   and cascade page fallback constants. Removes confusion. ~2 hours.
2. **v10.324 — Demo dry-run + UI polish**: walk through cascade
   page as MD, document any rough edges, prepare talking points.
3. **v10.324 — Branch Manager activity generator**: extend the
   v10.317 pattern for Branch Managers and Operations Managers
   so they have OWN KPIs (audit, compliance, branch-level CX)
   rather than only team-aggregate views.

Which direction?
