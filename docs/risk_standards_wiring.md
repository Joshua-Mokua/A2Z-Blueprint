# RISK — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `risk`

## Summary

- Total standards mapped to this module: **9**
- Wired engines: **7**
- Unwired standalone: **2**
- Orphan (missing engine files): **0**
- Wiring coverage: **77.8%**

## Recommendation

GOOD: 77.8% wired. Address 2 unwired + 0 orphan(s).

## Standards & engine states

| Standard | Engine | State | Pages using |
|---|---|---|---|
| engine.compliance_risk_assessment 1 standard(s) | `compliance_risk_assessment` | `wired_direct` | `24_compliance.py` |
| engine.credit_risk_irb 1 standard(s) | `credit_risk_irb` | `wired_direct` | `35_stress_testing.py` |
| engine.credit_risk_scoring 31 standard(s) | `credit_risk_scoring` | `wired_direct` | `19_credit_monitoring.py`, `89_capital_risk_engines.py` |
| engine.market_risk_factors 1 standard(s) | `market_risk_factors` | `wired_via_aggregator` | _(none)_ |
| engine.market_risk_limits 2 standard(s) | `market_risk_limits` | `wired_via_aggregator` | _(none)_ |
| engine.market_risk_sensitivities 1 standard(s) | `market_risk_sensitivities` | `wired_via_aggregator` | _(none)_ |
| engine.market_risk_var 3 standard(s) | `market_risk_var` | `wired_direct` | `35_stress_testing.py` |
| engine.risk_based_pricing 1 standard(s) | `risk_based_pricing` | `unwired_standalone` | _(none)_ |
| engine.risk_weighted_assets 3 standard(s) | `risk_weighted_assets` | `unwired_standalone` | _(none)_ |

## Action items

- Wire 2 standalone engine(s) into this module's pages
