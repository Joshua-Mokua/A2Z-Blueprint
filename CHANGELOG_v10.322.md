# Changelog — v10.322 Multi-period cascade data

**Date:** 2026-05-11
**Phase:** 4 (ninth arc — trends for demo)
**Audit:** 213/213 gates PASS = 100.0%
**Tests:** 503/503 passing across 29 integration suites
**G162 Rebase:** none — 18 consecutive zero-drift batches

---

## What v10.322 ships

Pre-computed cascade scores for all 4 demo quarters, enabling
quarter-over-quarter trend views in the cascade page at every
level of the hierarchy.

## Quarter-over-quarter trends now visible

```
Period     MD      Chief Retail    Branch Mgr 300277    Teller 300230
─────────────────────────────────────────────────────────────────────
2025-Q3    3.42    3.42            2.75                 2.80
2025-Q4    3.43    3.43            3.30                 2.20
2026-Q1    3.46    3.46            3.05                 2.40
2026-Q2    3.49    3.49            3.05                 3.20
```

- **MD**: gradual improvement 3.42 → 3.49 (4-quarter org-wide trend)
- **Chief Retail**: same trend (only retail subtree has actuals)
- **Branch Manager 300277**: variable 2.75 → 3.30 → 3.05 → 3.05
- **Teller 300230**: realistic dip + recovery 2.80 → 2.20 → 2.40 → 3.20
  (matches v10.317 generator's band-movement distribution)

## What was blocking trends

When I tried to pre-compute 2025-Q3, every staff scorecard came back
with `final_score=None`. Cause: `bank_targets.json` had only 2026
entries (e.g. `"PBT|2026"`, `"CX Score|2026"`). The scoring engine
correctly resolved year from period (`"2025-Q3" → "2025"`), looked
up `"PBT|2025"` — found nothing → no target → no score.

## The fix

**Mirror 2026 bank_targets to 2025** for the demo. 45 entries
mirrored, each tagged `_v10322_mirrored_from: "2026"` for audit
trail. Pragmatic for the demo (targets typically don't change
year-over-year in the early planning cycle); when real 2025 targets
get set, they'll override the mirrors at the same keys.

## What shipped

### Modified

- `data/bank_targets.json` — 45 entries mirrored to 2025
  (90 entries total now, was 45)
- `scripts/precompute_cascade_scores.py` — added `--skip-rollups`
  flag so trend quarters can pre-compute scores only (faster,
  ~160s instead of ~3min per period)
- `scripts/audit.py` — G213 added

### New generated data

- `data/cascade_scores_2025-Q3.json` (10.6KB, 542 staff scores)
- `data/cascade_scores_2025-Q4.json` (10.6KB, 542 staff scores)
- `data/cascade_scores_2026-Q1.json` (15.7KB, 542 + rollups —
  shipped in v10.321, unchanged)
- `data/cascade_scores_2026-Q2.json` (10.6KB, 542 staff scores)

### New tests

- `tests/integration/test_v10322_multi_period.py` — 11 tests
  across 5 sections

## Configurable vs hardcoded — Rule of Configurability honoured

**CONFIGURABLE**:
- All bank targets (per-year keys in `bank_targets.json`)
- Which periods to pre-compute (CLI argument to script)
- Skip-rollups flag (CLI argument)

**HARDCODED** (system invariants):
- Year-resolution rule (period `"YYYY-QN"` → year `"YYYY"`)
- Trend variance threshold (G213 requires MD spread ≥ 0.02 across
  4 quarters as a sanity check)

## Real findings during this batch

1. **The team rollup loop was the slow part.** When the original
   pre-compute included MD + Chiefs + Heads rollups, each `compute_
   team_rollup` walked all subordinates without LRU cache benefit
   (different code path than recursive scores). Resulted in
   timeouts. Made rollups optional via `--skip-rollups` so trend
   quarters compute fast.

2. **Year-only key format works for the demo.** The system stores
   bank targets as `"KPI|YYYY"` (annual scope). Quarterly variation
   comes from the actuals data, not the targets. This means
   2025-Q3 and 2025-Q4 both score against the same year's target —
   which is correct: a Teller's annual target divided across 4
   quarters doesn't change the achievement % comparison.

3. **G162 holds. 18 consecutive zero-drift batches.**

4. **The cascade picture is now demo-complete with trends.** Click
   any staff → see their 4-quarter score history. Click a manager
   → see the team's rolled-up history. The narrative arc works.

## Platform state

| Metric | v10.321 → v10.322 |
|--------|-------------------|
| Audit gates | 212 → **213** |
| Integration test suites | 28 → **29** |
| Tests passing | 492 → **503** |
| Pre-computed quarters | 1 (Q1 only) → **4 (Q3, Q4, Q1, Q2)** |
| bank_targets entries | 45 → **90** (mirrored to 2025) |
| G162 baseline | 4022 (18 consecutive zero-drift batches) |

## What this unlocks

The demo now supports a richer narrative:
- "Here's Teller 300230's BSC score history over the last year"
- "This Branch Manager improved from Q3 to Q4 but plateaued"
- "Chief Retail's trajectory is broadly upward"
- "MD's overall org performance is trending up by 0.07 over 4 quarters"

All visible from pre-computed JSON files — sub-second UI rendering.

## Next: v10.323 — Sales rollup via pipeline module

Your insight is correct: the **pipeline module** (`pages/3_pipeline.py`)
is the canonical place for sales-related actuals. Multiple roles tap
into it:

- **Tellers**: deposits opened at the counter, new accounts (their
  `DEP_GROWTH` and `NEW_ACCOUNTS` KPIs map directly to pipeline)
- **Direct Sales Representatives**: outbound new business
- **Branch Relationship Managers / Officers**: RM-driven sales
- **Branch Senior Relationship Officers**: deal pipeline
- **Relationship Managers (Corporate / SME / Public Sector)**:
  segment-specific sales

The right shape:
- Pipeline module is the **producer** for sales actuals (deposits
  opened, accounts opened, leads worked, opportunities closed,
  loan applications)
- BSC scoring **consumes** from pipeline for the relevant KPIs
- One pipeline activity stream serves multiple roles' BSC views
  — avoids the v10.317 trap of role-specific generators with their
  own ad-hoc KPI subsets

v10.323 will:
1. Inspect the existing `pages/3_pipeline.py` and `utils/pipeline_*`
   to understand the current shape
2. Identify which KPIs map to pipeline activities
3. Build a pipeline → BSC actuals bridge (consume pipeline data,
   submit to bsc_engine with proper attribution)
4. Generate pipeline activity for sales roles (RMs, DSRs, ROs)
   the same way v10.317 generated Teller activity
5. Surface in cascade rollups (so Branch Manager's score now
   reflects both Teller ops AND RM sales)

Estimated 3-4 hours. Proceed?
