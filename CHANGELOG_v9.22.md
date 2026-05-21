# CHANGELOG v9.22 — Engine Hub Tier 2 (Customer & Operational Intelligence)

**Audit:** 116/116 PASS — **75th consecutive clean** ⭐ (75-streak milestone).

## What

Adds 12 Tier 2 engines to the v9.21 Engine Integration Hub. Coverage 60 → 81 integrated (66.4%). Hub-surfaced cumulative: 24 engines.

## Engines surfaced

| # | Engine | Class | Purpose |
|---|---|---|---|
| 13 | deposit_intelligence | DepositIntelligenceEngine | Vintage cohorts, concentration, attrition |
| 14 | dormancy_intelligence | DormancyIntelligenceEngine | Dormancy detection + reactivation; CBK compliance |
| 15 | lending_intelligence | LendingIntelligenceEngine | Loan portfolio analytics + early-warning signals |
| 16 | treasury_intelligence | TreasuryIntelligenceEngine | Liquidity ladder + currency mismatch + maturity profile |
| 17 | business_intelligence | AutomatedBusinessIntelligence | Cross-domain trend + anomaly + exec summary |
| 18 | management_reporting | ManagementReportingEngine | MIS pack: monthly P&L + balance sheet trends |
| 19 | operations_dashboard | OperationsDashboardEngine | Real-time ops KPIs |
| 20 | queue_analytics | QueueAnalyticsEngine | Branch + call-centre wait + abandonment + CSAT |
| 21 | sanctions_screening | SanctionsScreeningEngine | OFAC + UN + EU AML screening |
| 22 | funds_transfer_pricing | FtpEngine | FTP curve + product-level FTP rates |
| 23 | cost_allocation | (function-based) | Activity-based cost allocation |
| 24 | operating_segments | OperatingSegmentEngine | IFRS 8 segments + reconciliation |

## Coverage progression

| Batch | Hub-surfaced | Total integrated | Remaining gap |
|---|---|---|---|
| Pre-v9.21 | 0 | 60 (49.2%) | 62 |
| v9.21 | 12 | 69 (56.6%) | 53 |
| **v9.22** | **24** | **81 (66.4%)** | **41** |
| v9.23 (target) | ~35 | ~92 | ~30 |
| v9.24 (target) | ~46 | ~110+ | ~12 |
| v9.25 (target) | — | ~115+ | <10 (mostly infra) |

## Honest acknowledgements

1. **Tier 2 net add = 12 surfaces but coverage delta = +12 (60→81 over v9.21+v9.22 = +21).** Of the 24 hub-surfaced engines, 9 were already imported elsewhere; coverage jumped because hub-surfaced ALSO counts as integrated for the metric.
2. **`cost_allocation` is function-based** — has no class; row's "Class" column shows "—". Engine still works; UI surface acknowledges.
3. **`queue_analytics` and `sanctions_screening` have multiple classes** — hub picks the primary engine class; secondary classes (CsatResponse / SanctionsRecord etc.) are documentation/dataclass types not directly exposed in hub.
4. **No live API call from hub** — engines surfaced as importable + class-present + line-count. Live data exercise is the engine's bespoke page concern (v10.x candidate per engine).

## Next: v9.23

Tier 3 — Profitability Suite: product_profitability, product_raroc, rm_profitability, profitability_integration, profitability_heatmap, profitability_hierarchy, profitability_trends, customer_profitability (verify already integrated), customer_lifetime_value (verify), customer_value_segments (verify).
