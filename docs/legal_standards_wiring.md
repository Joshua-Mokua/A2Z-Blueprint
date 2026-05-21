# LEGAL — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `legal`

## Summary

- Total standards mapped to this module: **17**
- Wired engines: **15**
- Unwired standalone: **2**
- Orphan (missing engine files): **0**
- Wiring coverage: **88.2%**

## Recommendation

GOOD: 88.2% wired. Address 2 unwired + 0 orphan(s).

## Standards & engine states

| Standard | Engine | State | Pages using |
|---|---|---|---|
| engine.board_reporting 5 standard(s) | `board_reporting` | `unwired_standalone` | _(none)_ |
| engine.executive_resource_dashboard 1 standard(s) | `executive_resource_dashboard` | `wired_via_aggregator` | _(none)_ |
| engine.finance_intelligence_dashboard 1 standard(s) | `finance_intelligence_dashboard` | `wired_via_aggregator` | _(none)_ |
| engine.kyc_onboarding 1 standard(s) | `kyc_onboarding` | `wired_direct` | `24_compliance.py` |
| engine.legal_analytics 1 standard(s) | `legal_analytics` | `wired_direct` | `26_legal.py` |
| engine.legal_case_management 1 standard(s) | `legal_case_management` | `wired_direct` | `26_legal.py` |
| engine.legal_dashboard 1 standard(s) | `legal_dashboard` | `wired_direct` | `26_legal.py` |
| engine.legal_document_management 1 standard(s) | `legal_document_management` | `wired_direct` | `26_legal.py` |
| engine.legal_hold_management 1 standard(s) | `legal_hold_management` | `wired_direct` | `26_legal.py` |
| engine.legal_spend_management 1 standard(s) | `legal_spend_management` | `wired_direct` | `26_legal.py` |
| engine.model_governance 5 standard(s) | `model_governance` | `wired_via_aggregator` | _(none)_ |
| engine.model_governance_runtime 2 standard(s) | `model_governance_runtime` | `unwired_standalone` | _(none)_ |
| engine.product_analytics_dashboard 1 standard(s) | `product_analytics_dashboard` | `wired_direct` | `5_products.py` |
| engine.revenue_dashboard_metrics 1 standard(s) | `revenue_dashboard_metrics` | `wired_direct` | `29_revenue_assurance.py` |
| engine.trade_finance_corporate_portal 3 standard(s) | `trade_finance_corporate_portal` | `wired_direct` | `46_trade_finance.py` |
| engine.treasury_dashboard 1 standard(s) | `treasury_dashboard` | `wired_direct` | `25_treasury.py` |
| engine.utilization_dashboard 1 standard(s) | `utilization_dashboard` | `wired_via_aggregator` | _(none)_ |

## Action items

- Wire 2 standalone engine(s) into this module's pages
