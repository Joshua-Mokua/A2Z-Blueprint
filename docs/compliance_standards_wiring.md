# COMPLIANCE — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `compliance`

## Summary

- Total standards mapped to this module: **10**
- Wired engines: **9**
- Unwired standalone: **1**
- Orphan (missing engine files): **0**
- Wiring coverage: **90.0%**

## Recommendation

EXCELLENT: 90.0% standards wired. 1 unwired engine(s) to address.

## Standards & engine states

| Standard | Engine | State | Pages using |
|---|---|---|---|
| engine.aml_monitoring 1 standard(s) | `aml_monitoring` | `wired_direct` | `24_compliance.py` |
| engine.cbk_regulatory_reporting 1 standard(s) | `cbk_regulatory_reporting` | `wired_direct` | `74_cbk_returns.py` |
| engine.compliance_risk_assessment 1 standard(s) | `compliance_risk_assessment` | `wired_direct` | `24_compliance.py` |
| engine.compliance_training 1 standard(s) | `compliance_training` | `wired_direct` | `24_compliance.py` |
| engine.finance_audit_compliance 1 standard(s) | `finance_audit_compliance` | `wired_via_aggregator` | _(none)_ |
| engine.kra_tax_compliance 1 standard(s) | `kra_tax_compliance` | `wired_via_aggregator` | _(none)_ |
| engine.kyc_aml_risk 1 standard(s) | `kyc_aml_risk` | `wired_direct` | `55_aml.py` |
| engine.kyc_onboarding 1 standard(s) | `kyc_onboarding` | `wired_direct` | `24_compliance.py` |
| engine.regulatory_reporting 5 standard(s) | `regulatory_reporting` | `unwired_standalone` | _(none)_ |
| engine.trade_finance_compliance 2 standard(s) | `trade_finance_compliance` | `wired_direct` | `46_trade_finance.py` |

## Action items

- Wire 1 standalone engine(s) into this module's pages
- Module standards wiring at excellent coverage; maintain
