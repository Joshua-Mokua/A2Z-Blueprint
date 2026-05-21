# CHANGELOG v9.23 — Engine Hub Tier 3 (Profitability Suite)

**Audit:** 116/116 PASS — **76th consecutive clean.**

## What

Adds 11 Tier 3 engines to the Engine Hub. Coverage: 81 → 88 (66.4% → 72.1%). Cumulative hub: 35 engines. Remaining gap: 34.

## Engines surfaced (Tier 3)

Profitability suite + asset impairment + channel performance:

| # | Engine | Class | Purpose |
|---|---|---|---|
| 25 | product_profitability | ProductProfitabilityEngine | Per-product P&L: revenue + cost-to-serve + capital |
| 26 | product_raroc | ProductRarocEngine | Risk-Adjusted ROC for pricing + portfolio |
| 27 | rm_profitability | RMProfitabilityDashboard | Per-RM P&L; feeds incentive computation |
| 28 | profitability_integration | (function-based) | Harmonizes product/RM/customer P&Ls |
| 29 | profitability_heatmap | (function-based) | 2D customer×product / branch×RM heatmaps |
| 30 | profitability_hierarchy | CustomerProfitabilityHierarchy | Customer→RM→branch→region rollup |
| 31 | profitability_trends | ProfitabilityTrends | 12-month rolling + vintage + seasonality |
| 32 | asset_impairment | ImpairmentEngine | IAS 36 impairment loss recognition |
| 33 | channel_income | ChannelIncomeEngine | Per-channel revenue attribution (ATM/USSD/Mobile/Branch) |
| 34 | channel_performance | ChannelPerformanceEngine | Channel KPIs: throughput / success / uptime |
| 35 | channel_sla | ChannelSlaMonitoringEngine | Channel SLA tracking + outage cost analysis |

## Coverage progression

| Batch | Cumulative hub | Total integrated | Remaining gap |
|---|---|---|---|
| Pre-v9.21 | 0 | 60 (49.2%) | 62 |
| v9.21 | 12 | 69 (56.6%) | 53 |
| v9.22 | 24 | 81 (66.4%) | 41 |
| **v9.23** | **35** | **88 (72.1%)** | **34** |

## Honest acknowledgements

1. **profitability_integration / heatmap have no class** — function-based engines; "Class" column shows "—".
2. **`channel_*` family is 3 closely-related engines** — surfaced separately for operator clarity; could consolidate later if too verbose.
3. **No live profitability calculation from hub** — engines surfaced as importable; live data exercise is a per-engine concern.

## Next: v9.24

Tier 4-5 — Strategy + Operations: initiative_dependency, initiative_impact, initiative_resource, stage_gate, strategic_planning, microtask_engine, nudge_engine, gamification, peer_learning, wellness, workforce_analytics, growth_path_engine, employee_benefits, edms.
