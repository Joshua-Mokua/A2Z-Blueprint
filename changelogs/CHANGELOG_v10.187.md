# CHANGELOG — v10.187

**Drop:** v10.187
**Standard:** ENH-163 — Resource Investment Case Generator
**Module:** Resource Optimization
**Status:** active

---

## Summary

Eighth drop of the Resource Optimization arc. Turns a baseline + alternative
`ScenarioProjection` (from ENH-162) plus caller-supplied cost assumptions
into a board-ready investment case with NPV, payback, IRR, and a full
per-year cash-flow series.

The engine refuses to default any cost input. If the caller doesn't supply
`annual_cost_per_fte`, `one_time_implementation_cost`, `discount_rate`, and
`horizon_years`, the call fails. This is deliberate — silently inventing
salary numbers from training data would smuggle assumptions into a board
paper.

Revenue upside is out of scope. SL improvement might drive customer
retention, lower attrition, or upsell revenue. The engine does not
monetise any of that. `REVENUE_UPSIDE_FROM_SL` is named in deferrals.
The case is a cost-side analysis only.

---

## Files added

- `utils/resource_investment_case.py` — engine (~330 LOC)
- `tests/test_resource_investment_case_v10_187.py` — 42 tests across
  12 classes

## Files modified

- `utils/standards_registry.py` — ENH-163 set to `status='active'`,
  `affected_engines=('resource_investment_case',)`,
  `implementation_batch='v10.187'`
- `pages/7_admin.py` — Tier 32 Resource Optimization Suite gains an eighth
  entry under `resource_investment_case`

## Audit gates

No new gates this drop (closure-tier gates G156/G157 land at v10.190 with
the arc closure ceremony). Audit holds at **155/155 PASS = 100.0%**.

---

## Engine surface

### Inputs

`CostAssumptions`:
- `annual_cost_per_fte` — required, all-in (salary + benefits + ops)
- `one_time_implementation_cost` — required (office reconfig, tech setup)
- `discount_rate` — required, decimal (e.g. 0.12 for 12%)
- `horizon_years` — required, integer 1–30
- `annual_other_costs` — defaults 0 (licenses, vendor fees, etc.)
- `qualitative_benefits` — defaults `()`, free-form text tuple

### Validation

- `annual_cost_per_fte`, `one_time_implementation_cost`,
  `annual_other_costs` must be non-negative
- `discount_rate` ∈ [0, 1.0] (anything above is treated as a typo)
- `horizon_years` ∈ [1, 30]
- `case_id` must be non-empty

All five rules tested explicitly.

### Outputs

`InvestmentCase`:
- `baseline_effective_fte`, `alternative_effective_fte`,
  `annual_fte_delta`
- `annual_labour_cost_delta` — `fte_delta × annual_cost_per_fte`
  (negative = saving)
- `annual_other_cost_delta` — alternative's other-costs as additional
  outflow (the engine does not subtract baseline's other-costs because
  those were already in BAU)
- `annual_net_cash_flow` — convention: positive = saving
- `npv` — standard DCF: `NPV = -one_time + Σ_{t=1..N} CF_t / (1+r)^t`
- `payback_years_undiscounted` — `one_time / annual_net` if positive,
  else `None`
- `payback_years_discounted` — bisection through cumulative discounted
  CFs, with linear interpolation within the recouping year. `None` if
  never recouped within horizon.
- `irr` — bisection on `[-0.999, 5.0]`. `None` if no sign change in NPV
  across the bracket.
- `annual_cash_flows` — per-year records with `nominal`, `discounted`,
  `cumulative_nominal`, `cumulative_discounted`
- `qualitative_benefits` — passes caller's text through unchanged
- `deferrals_acknowledged` — `('DETAILED_TAX_TREATMENT',
  'INFLATION_INDEXATION', 'REVENUE_UPSIDE_FROM_SL', 'MULTI_YEAR_RAMP')`

### Honest deferrals (declared in `board_summary()`)

1. **DETAILED_TAX_TREATMENT** — pre-tax cash flows only. No tax shield
   on labour cost, no deferred-tax assets. The engine produces a
   pre-tax IRR that the operator can compare against pre-tax hurdle
   rates only.
2. **INFLATION_INDEXATION** — constant nominal salaries assumed. No
   salary escalator across the horizon.
3. **REVENUE_UPSIDE_FROM_SL** — engine quantifies the cost side only.
   SL-driven retention or upsell value remains qualitative.
4. **MULTI_YEAR_RAMP** — steady-state cost structure from year 1. No
   headcount ramp curve.

### Sample math (verified by probe)

Baseline 10 FTE, alternative 8 FTE, KES 1.5M per FTE, 200k other costs,
KES 5M one-time, 12% discount, 5y horizon:

- FTE delta = -2 → labour saving = KES 3.0M
- Annual net = 3.0M − 0.2M = KES 2.8M
- NPV = -5.0M + (2.8M × annuity factor at 12% / 5y) = **KES 5.09M**
- Undiscounted payback = 5.0M / 2.8M = **1.79 years**
- Discounted payback = **2.13 years**
- IRR = **48.2%**

Worse case (alternative = 15 FTE, more cost): NPV = KES -32.8M,
payback = `None`.

---

## Validation

### Tests

```
PASSED: 42 | FAILED: 0
```

Coverage spans:

- `TestModuleShape` — public surface (4 tests)
- `TestRegistry` — ENH-163 active and wired (3)
- `TestHubIntegration` — Tier 32 entry + ordering (2)
- `TestAssumptionValidation` — 7 rejection paths (7)
- `TestNPVMath` — savings, no-savings, zero-one-time, monotonicity vs
  discount rate (5)
- `TestPaybackMath` — undiscounted, no-savings None, discounted
  longer than undiscounted, never-recouped None (4)
- `TestIRR` — savings IRR, no-savings None (2)
- `TestCashFlowSeries` — count, cumulative growth, discounted < nominal (4)
- `TestQualitativeBenefits` — passthrough, no fabrication (2)
- `TestScenarioProjectionComposition` — end-to-end with real ENH-162
  projections (1)
- `TestDeferralsAcknowledgement` — case carries deferrals, board has
  all 4, NPV formula declared (3)
- `TestSerialization` — JSON round-trip, assumptions to_dict (2)
- `TestNoRegression` — ENH-156, 162, 160, 161 still active (3)

### Audit

```
Score: 155/155 gates = 100.0% — PASS
```

---

## What this unlocks

ENH-164 (Integrity Culture Score & Benchmarking) is the next drop. After
that, ENH-165 (Executive Resource Optimization Dashboard) is the
final standard before the arc closure ceremony at v10.190 with G156/G157.

---

## Notes

- Engine is pure Python deterministic. No solver, no scipy, no numpy.
- IRR uses bisection — robust, slow-converging-but-converging always
  when a sign change exists in `[-0.999, 5.0]`.
- The `npv_formula` is exposed verbatim in `board_summary()`:
  `NPV = -one_time + Σ_{t=1..N} CF_t / (1+r)^t`. Operators can sanity-
  check the engine's math against the formula at any time.
- Regulatory basis: Internal Capital Allocation Policy + BSC Financial
  + BSC People.
