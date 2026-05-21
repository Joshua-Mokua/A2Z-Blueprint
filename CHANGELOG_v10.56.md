# CHANGELOG v10.56 — revenue_assurance arc · ENH-247 Commission & Incentive Assurance

**Status:** revenue_assurance arc 7/8+1 batches (1 standard remaining + closure)
**Audit:** 132/132 PASS · **G128:** STABLE (321 modules · 803 imports · 3 HARD)
**Active standards:** 125 → **126** / 260 · **Scenario library:** 78 → **82** (4 CMA-* added)

## What this batch does

Plan-based commission recomputation. Closes the loop with ENH-242: where ENH-242 takes `(paid, expected)` and flags mismatches, ENH-247 *computes* the expected from a tiered IncentivePlan + actual revenue. The two engines are now genuinely composable — ENH-247's `expected_commission_kes` slots into ENH-242's `CommissionRecord.expected_commission_kes` field.

## New module

`utils/commission_assurance.py` (~1100 lines · 20 self-tests). Single public engine `CommissionAssuranceEngine` with 4 capabilities: `compute_expected_commission`, `validate_paid_vs_computed`, `validate_overrides`, `summarize_disputes`.

## Tier walk semantics

| Basis | Example: revenue 200k against [0,100k]@2% / [100k,500k]@3% / [500k,∞]@5% |
| ----- | --- |
| MARGINAL | 100k × 2% + 100k × 3% = 5,000 |
| CUMULATIVE | 200k × 3% (whole revenue at the rate of the tier it falls in) = 6,000 |

**All tiers surface as contributions even when zero** — Rule 1 transparency for RMs disputing. CMA-01 verifies the 3-tier plan against revenue 1m produces 3 `CommissionContribution` entries totaling 39k.

## Validation envelope

- `CommissionTier`: `tier_max > tier_min`, `rate_pct ∈ [0,1]`
- `IncentivePlan`: non-empty tiers, ascending tier ordering with no overlaps, `effective_to ≥ effective_from`
- `CommissionOverride`: non-empty `reason`
- `CommissionDispute`: non-OPEN status requires `resolved_date`

## Override + dispute handling

- `validate_overrides` flags APPROVED-status overrides without `approval_id` as invalid (matches the discount-auth pattern from ENH-246)
- `summarize_disputes` aggregates counts + avg resolution days; never resolves disputes itself per Rule 7

## Scenario library

- **CMA-01** 3-tier marginal walk → 39k expected, 3 contributions surfaced (4 assertions)
- **CMA-02** revenue 200k → expected 5k, paid 4k → UNDERPAID variance -1000 (2 assertions)
- **CMA-03** APPROVED override missing approval_id → invalid; with approval_id → valid (2 assertions)
- **CMA-04** 3 disputes → counts + avg resolution 10.5d (2 assertions)

10/10 PASS.

## Standards registry

ENH-247 activated: `planned → active`, `v10.40+ → v10.56`, `affected_engines: ("revenue_assurance", "rm_profitability") → ("commission_assurance",)`. Description rewritten with full architectural detail.

## Verification

- `python3 -m utils.commission_assurance` → ✓ 20 tests
- `python3 scripts/audit.py` → **132/132 PASS**
- `python3 scripts/structure_audit.py` → STABLE (321 modules · 803 imports · HARD=3)

## Honest scope notes

1. **No clawback semantics.** `CommissionOverride` has `delta_kes` (positive bonus, negative clawback) but the engine doesn't validate that clawbacks correspond to reversed deals. That belongs to a future revision combining ENH-247 with ENH-244's deal-recall data.
2. **No tier-blend basis.** Some banks use "marginal up to X, cumulative above" hybrid plans. Currently `MARGINAL` and `CUMULATIVE` are exclusive; production hybrid plans need translation by the caller.
3. **No team/pool incentives.** Engine assumes per-RM commission; team-pooled incentives split among multiple RMs require composition with a pool-allocation layer not shipped here.
4. **No FX.** Foreign-currency revenue must be converted to KES before feeding the engine.

## Files changed

- **NEW** `utils/commission_assurance.py`
- **MOD** `utils/standards_registry.py` (ENH-247)
- **MOD** `utils/scenario_simulator.py` (+4 CMA-*)

**Next:** v10.57 ENH-248 Regulatory Revenue Reporting.
