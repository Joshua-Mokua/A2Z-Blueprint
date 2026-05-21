# CHANGELOG v10.8 — Phase 2 batch 3: Climate-Adjusted ECL + Scenario Stress Testing

**Audit:** 119/119 PASS — **92nd consecutive clean.**

## What ships in v10.8

`utils/climate_ecl_adjustment.py` — 951 lines covering 2 of 13 Climate/ESG standards. **Risk class Cat A** (financial calculation directly affecting balance-sheet ECL provisions reported under IFRS 9):

| Standard | Implemented as |
|---|---|
| **ENH-CLI-07** Climate Scenario Stress Testing | `run_stress_scenario()`, `ClimateECLEngine.run_three_scenarios()`, multi-horizon (5/10/20/30 yr) sweeps with portfolio aggregation |
| **ENH-CLI-12** Climate-Adjusted ECL (IFRS 9 Integration) | `apply_climate_overlay()`, `compute_probability_weighted_ecl()`, IFRS 9 §5.5.17 forward-looking macro overlay + §5.5.4 probability-weighted ECL |

## Methodology references

- **IFRS 9 §5.5.17** — forward-looking information requirement
- **IFRS 9 §5.5.4** — probability-weighted ECL (≥3 scenarios required)
- **NGFS Phase IV (Nov 2023)** — scenario data for central banks
- **ECB Climate Stress Test 2022** — bank-sector methodology
- **Bank of England BES 2021** — biennial exploratory scenario
- **CBK CRMF (April 2021) Pillar 4** — climate stress testing
- **Basel BCBS (June 2022)** — climate-related financial risks principles

## Adjustment formula

```
climate_adjusted_ecl =
    base_ecl × pd_climate_mult × lgd_climate_mult × ead_climate_mult

where:
    base_ecl       = PD × LGD × EAD (Stage 1: 12m PD; Stage 2/3: lifetime PD)
    pd_climate_mult ∈ [1.0, 3.0]   (40% physical + 60% transition × horizon factor)
    lgd_climate_mult ∈ [1.0, 3.0]  (50% physical; 1.5× for real-estate sectors)
    ead_climate_mult ∈ [1.0, 3.0]  (20% transition; 1.5× for fossil sectors)

Probability-weighted ECL (IFRS 9 §5.5.4):
    weighted = Σ_s(scenario_ecl[s] × scenario_weight[s])
    where Σ_s(scenario_weight[s]) = 1.0 and |scenarios| ≥ 3
```

All multipliers ≥ 1.0 — climate adds risk, never subtracts. **MULTIPLIER_MAX = 3.0** caps prevent runaway in extreme stress.

## Honesty Rule 1 enforced

- `compute_probability_weighted_ecl()` raises `ValueError` if <3 scenarios, weights don't sum to 1.0 (±0.001 tolerance), or scenario keys mismatch.
- `BaseECLInputs` validates PDs/LGD ∈ [0,1], EAD ≥ 0, `pd_lifetime ≥ pd_12m` (term structure invariant).
- All `compute_*_climate_multiplier()` validate risk scores ∈ [0, 100].

## Tests

- **22 module-level self-tests** (`python -m utils.climate_ecl_adjustment`)
- **19 integration tests** in `tests/integration/test_v10_8_climate_ecl.py`

## Standards registry

10 of 13 Climate/ESG standards now active. ENH-CLI-03 (KGFT report), ENH-CLI-04 (CRDF reporting), ENH-CLI-13 (greenwashing) remain for v10.9.

## Honest acknowledgements

1. **Multipliers are heuristics**, not calibrated to historical default data. Production deployment requires regression of historical defaults against physical/transition risk scores.
2. **Weight ratios (40/60, 50% RE bump, 20%/50% fossil bump)** are illustrative — consistent with ECB STS 2022 + BoE BES 2021 but not bank-specific.
3. **Horizon factor (1.0 at 5y → 2.0 at 30y) is linear**; reality has non-linear tipping points.
4. **No persistence layer yet** — engine is in-memory; Postgres integration in v10.9+.
5. **Risk scores enter via callable interface** — decouples engine from v10.7 risk engine. The actual asset → location → hazard → score wiring is per-deployment integration work.

## Phase 2 progress

| Arc | Status | Cumulative active |
|---|---|---|
| v10.6 ✅ | Climate/ESG core engine | 5/246 |
| v10.7 ✅ | Climate risk modeling | 8/246 |
| **v10.8 ✅** | **Climate-adjusted ECL + stress testing** | **10/246** |
| v10.9 (next) | UI + KGFT/CRDF reporting + greenwashing | 13/246 |
| v10.10 | Audit gate G120 + arc closure | 13/246 (locked) |
