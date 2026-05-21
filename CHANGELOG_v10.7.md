# CHANGELOG v10.7 — Phase 2 batch 2: Climate Risk Modeling

**Audit:** 119/119 PASS — **91st consecutive clean.**

## What ships in v10.7

`utils/climate_risk.py` — 1,238 lines covering 3 of 13 Climate/ESG standards:

| Standard | Implemented as |
|---|---|
| **ENH-CLI-05** Physical Climate Risk (Acute + Chronic) | `assess_physical_risk()`, 9 acute + 7 chronic hazards, 17 sector vulnerability baselines, RCP 2.6/4.5/6.0/8.5 scenarios |
| **ENH-CLI-06** Transition Climate Risk | `assess_transition_risk()`, 4 drivers (policy/tech/market/reputation), 18 sector intensities, NGFS v4 scenarios with carbon prices |
| **ENH-CLI-10** Biodiversity & Nature-Related Risks | `assess_tnfd()`, TNFD v1.0 LEAP framework, 4 nature realms, 6 Kenya biomes, 3 risk categories |

## Methodology references

- IPCC AR6 (2021) — RCP scenarios
- NGFS Scenarios v4 (Nov 2023) — central banks' standard set
- ECB Climate Stress Test (2022) — bank transition risk methodology
- TNFD v1.0 (Sept 2023) — LEAP framework
- CBK Climate Risk Management Framework (April 2021) Pillar 3
- PCAF (2022) — financed emissions methodology

## Scoring formula (consistent across all 3 risk types)

**Risk = Hazard × Exposure × Vulnerability** — all on 0–100 scale.

| Score range | Level |
|---|---|
| 0–24 | LOW |
| 25–49 | MEDIUM |
| 50–74 | HIGH |
| 75–100 | EXTREME |

Decimal precision (28 digits) preserved end-to-end.

## Reference data registered

| Constant | Count | Source |
|---|---|---|
| `AcutePhysicalHazard` enum | 9 | flood (riverine/coastal/flash), drought, storm (cyclone/severe), wildfire, heatwave, landslide |
| `ChronicPhysicalHazard` enum | 7 | temperature rise, precipitation change, sea level rise, water stress, soil degradation, desertification, ocean acidification |
| `SECTOR_BASELINE_VULNERABILITY` | 17 sectors | CBK CRMF Pillar 3 + UNEP FI Banking Initiative |
| `TransitionDriver` enum | 4 | policy/legal, technology, market, reputation |
| `SECTOR_TRANSITION_INTENSITY` | 18 sectors | NGFS v4 + ECB STS 2022 |
| `RCPScenario` enum | 4 | RCP 2.6, 4.5, 6.0, 8.5 |
| `NGFSScenario` enum | 6 | Net Zero 2050, Below 2°C, Delayed Transition, NDCs, Current Policies, Fragmented World |
| `NGFS_CARBON_PRICE_2030_USD_PER_TCO2E` | 6 | per scenario; $130 (NetZero) → $10 (Current) |
| `TNFD_LEAP_STAGES` | 4 | Locate, Evaluate, Assess, Prepare |
| `TNFD_NATURE_REALMS` | 4 | land, freshwater, ocean, atmosphere |
| `TNFD_BIOMES_KENYA` | 6 | tropical forest, savanna, freshwater, marine coastal reefs, wetlands, arid/semiarid |

## Engine architecture

```
ClimateRiskEngine (orchestrator)
├── add_physical(PhysicalRiskAssessment)
├── add_transition(TransitionRiskAssessment)
├── add_tnfd(TNFDAssessment)
├── assess_portfolio() → all 3 aggregations
└── board_summary() → weighted overall score (40% physical, 40% transition, 20% TNFD) + attention flags
```

## Key features

- **Three risk types unified** under one engine + one risk-level taxonomy
- **Asset-specific vulnerability override** beats sector default when known
- **Carbon price exposure** computed in USD when emissions data available
- **Stranded asset estimates** for fossil-fuel sectors only (60% under Net Zero, 70% under Delayed Transition)
- **NGFS scenario classification** — orderly / disorderly / hot-house with appropriate severity multipliers
- **Portfolio aggregation** balance-weighted (when balances supplied) or equal-weighted
- **Top-5 most-exposed** automatically surfaced in aggregation summary
- **Attention flags** auto-trigger on portfolio ≥HIGH or carbon exposure ≥USD 1M
- **TNFD scoring** uses dependency + impact count, weighted by realms + biomes + categories

## Tests added

`tests/integration/test_v10_7_climate_risk.py` — 18 integration tests covering:
- Imports + public symbols
- Self-test passes
- Registry alignment (8 active, 5 still planned)
- Physical risk (coastal real estate under RCP 8.5; multi-hazard mean intensity)
- Transition risk (fossil under Net Zero high; renewables low; carbon price calc)
- TNFD (full LEAP; partial completeness)
- Portfolio aggregation
- Scenario coverage
- v10.6/v10.7 engine coexistence

Plus 27 module-level self-tests (run on `python -m utils.climate_risk`).

## Verified output

```
✓ climate_risk self-test passed (27 tests)
Ran 117 tests in 0.149s OK
Audit: 119/119 gates PASS
```

## Standards registry update

3 more Climate/ESG standards active:

```
Climate/ESG active: 8
  ENH-CLI-01: IFRS S1 General Sustainability Disclosures
  ENH-CLI-02: IFRS S2 Climate-Related Disclosures
  ENH-CLI-05: Physical Climate Risk Modeling (Acute + Chronic)        ← NEW
  ENH-CLI-06: Transition Climate Risk Modeling                         ← NEW
  ENH-CLI-08: Scope 1/2/3 Emissions Tracking
  ENH-CLI-09: Green Asset Classification & Tagging
  ENH-CLI-10: Biodiversity & Nature-Related Risks (TNFD)               ← NEW
  ENH-CLI-11: Climate Governance (Board Oversight + Roles)
Climate/ESG still planned: 5
```

## Honest acknowledgements

1. **Sector vulnerability + transition intensity baselines are best-effort defaults**, not Ecobank-specific calibration. Per-bank calibration belongs in v10.8 climate-adjusted ECL deep work where actual portfolio data informs model parameters.
2. **Hazard intensity scores require external climate data** to be useful. The engine accepts them; sourcing them (from Climate-Risk Source Material like Aqueduct, ThinkHazard, EM-DAT, NGFS Climate Impact Explorer) is part of the v10.8+ data integration work.
3. **Stranded asset estimates are scenario-driven heuristics** (60-70% under aggressive scenarios for fossils). Refinement to portfolio-actual reserves and discount rates is v10.8+ work.
4. **Carbon price 2030 figures are NGFS-published reference points**. Year-by-year carbon price evolution to 2050 is part of v10.8 stress-test scenario data.
5. **TNFD scoring uses simple count-based weights**. As the LEAP methodology matures, more sophisticated scoring (e.g., Encore-style dependency materiality) can replace the current heuristic.
6. **Backward-compat fix:** v10.6 registry-alignment tests relaxed from `==5` to `≥5` so they remain green as later batches activate more Climate/ESG standards. The contract is now "v10.6 implemented at least these 5", not "exactly these 5."

## What v10.8 ships next

**Climate-Adjusted ECL + Scenario Stress Testing** (`utils/climate_ecl_adjustment.py`):

- ENH-CLI-07: Climate Scenario Stress Testing — multi-scenario, multi-horizon stress runs feeding ECL macro overlays
- ENH-CLI-12: Climate-Adjusted ECL (IFRS 9 Integration) — integrates with `utils/provisions.py` and `utils/ifrs9_classification.py` to apply forward-looking climate adjustments to ECL provisions per IFRS 9 §5.5.17

This ties together v10.6 (ESG framework) + v10.7 (risk scoring) into actual financial impact via the existing ECL/IFRS 9 infrastructure.

## Phase 2 progress

| Arc | Standards | Cumulative active |
|---|---|---|
| v10.6 ✅ | Climate/ESG core (5 standards) | 5/246 |
| **v10.7 ✅** | **Climate risk modeling (3 standards)** | **8/246** |
| v10.8 (next) | Climate-adjusted ECL + scenarios (2 standards) | 10/246 |
| v10.9 | UI + KGFT/CRDF reporting (3 standards) | 13/246 |
| v10.10 | Audit gate G120 + arc closure | 13/246 (locked) |
