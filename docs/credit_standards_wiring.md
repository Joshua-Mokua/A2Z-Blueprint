# CREDIT — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `credit`

## Summary

- Total standards mapped to this module: **5**
- Wired engines: **4**
- Unwired standalone: **1**
- Orphan (missing engine files): **0**
- Wiring coverage: **80.0%**

## Recommendation

GOOD: 80.0% wired. Address 1 unwired + 0 orphan(s).

## Standards & engine states

| Standard | Engine | State | Pages using |
|---|---|---|---|
| engine.credit_alt_scoring 1 standard(s) | `credit_alt_scoring` | `wired_direct` | `22_credit_analysis.py` |
| engine.credit_committee 1 standard(s) | `credit_committee` | `wired_direct` | `22_credit_analysis.py` |
| engine.credit_risk_irb 1 standard(s) | `credit_risk_irb` | `wired_direct` | `35_stress_testing.py` |
| engine.credit_risk_scoring 31 standard(s) | `credit_risk_scoring` | `wired_direct` | `19_credit_monitoring.py`, `89_capital_risk_engines.py` |
| engine.ifrs9_classification 3 standard(s) | `ifrs9_classification` | `unwired_standalone` | _(none)_ |

## Action items

- Wire 1 standalone engine(s) into this module's pages
