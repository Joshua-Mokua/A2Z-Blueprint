# ADMIN — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `admin`

## Summary

- Total standards mapped to this module: **7**
- Wired engines: **5**
- Unwired standalone: **2**
- Orphan (missing engine files): **0**
- Wiring coverage: **71.4%**

## Recommendation

GOOD: 71.4% wired. Address 2 unwired + 0 orphan(s).

## Standards & engine states

| Standard | Engine | State | Pages using |
|---|---|---|---|
| engine.audit_reporting 8 standard(s) | `audit_reporting` | `unwired_standalone` | _(none)_ |
| engine.audit_universe 13 standard(s) | `audit_universe` | `unwired_standalone` | _(none)_ |
| engine.compliance_risk_assessment 1 standard(s) | `compliance_risk_assessment` | `wired_direct` | `24_compliance.py` |
| engine.compliance_training 1 standard(s) | `compliance_training` | `wired_direct` | `24_compliance.py` |
| engine.finance_audit_compliance 1 standard(s) | `finance_audit_compliance` | `wired_via_aggregator` | _(none)_ |
| engine.kra_tax_compliance 1 standard(s) | `kra_tax_compliance` | `wired_via_aggregator` | _(none)_ |
| engine.trade_finance_compliance 2 standard(s) | `trade_finance_compliance` | `wired_direct` | `46_trade_finance.py` |

## Action items

- Wire 2 standalone engine(s) into this module's pages
