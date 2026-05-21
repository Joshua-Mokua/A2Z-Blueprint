# ICT — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `ict`

## Summary

- Total standards mapped to this module: **15**
- Wired engines: **11**
- Unwired standalone: **3**
- Orphan (missing engine files): **0**
- Wiring coverage: **73.3%**

## Recommendation

GOOD: 73.3% wired. Address 3 unwired + 0 orphan(s).

## Standards & engine states

| Standard | Engine | State | Pages using |
|---|---|---|---|
| engine.audit_reporting 8 standard(s) | `audit_reporting` | `unwired_standalone` | _(none)_ |
| engine.audit_universe 13 standard(s) | `audit_universe` | `unwired_standalone` | _(none)_ |
| engine.channel_sla 7 standard(s) | `channel_sla` | `wired_direct` | `73_channels.py` |
| engine.churn_prediction 1 standard(s) | `churn_prediction` | `wired_direct` | `34_customer360.py` |
| engine.credit_alt_scoring 1 standard(s) | `credit_alt_scoring` | `wired_direct` | `22_credit_analysis.py` |
| engine.credit_committee 1 standard(s) | `credit_committee` | `wired_direct` | `22_credit_analysis.py` |
| engine.credit_risk_irb 1 standard(s) | `credit_risk_irb` | `wired_direct` | `35_stress_testing.py` |
| engine.credit_risk_scoring 31 standard(s) | `credit_risk_scoring` | `wired_direct` | `19_credit_monitoring.py`, `89_capital_risk_engines.py` |
| engine.daily_strategy_integration 1 standard(s) | `daily_strategy_integration` | `wired_direct` | `83_strategy.py` |
| engine.deposit_intelligence 1 standard(s) | `deposit_intelligence` | `unwired_standalone` | _(none)_ |
| engine.finance_audit_compliance 1 standard(s) | `finance_audit_compliance` | `wired_via_aggregator` | _(none)_ |
| engine.flexcube_adapter 2 standard(s) | `flexcube_adapter` | `expected_infrastructure` | _(none)_ |
| engine.islamic_treasury 1 standard(s) | `islamic_treasury` | `wired_direct` | `25_treasury.py` |
| engine.predictive_financial_analytics 1 standard(s) | `predictive_financial_analytics` | `wired_via_aggregator` | _(none)_ |
| engine.wellbeing_integration 1 standard(s) | `wellbeing_integration` | `wired_via_aggregator` | _(none)_ |

## Action items

- Wire 3 standalone engine(s) into this module's pages
