# FINANCE — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `finance`

## Summary

- Total standards mapped to this module: **15**
- Wired engines: **14**
- Unwired standalone: **1**
- Orphan (missing engine files): **0**
- Wiring coverage: **93.3%**

## Recommendation

EXCELLENT: 93.3% standards wired. 1 unwired engine(s) to address.

## Standards & engine states

| Standard | Engine | State | Pages using |
|---|---|---|---|
| engine.finance_audit_compliance 1 standard(s) | `finance_audit_compliance` | `wired_via_aggregator` | _(none)_ |
| engine.finance_close_orchestrator 1 standard(s) | `finance_close_orchestrator` | `wired_via_aggregator` | _(none)_ |
| engine.finance_intelligence_dashboard 1 standard(s) | `finance_intelligence_dashboard` | `wired_via_aggregator` | _(none)_ |
| engine.operating_segments 1 standard(s) | `operating_segments` | `unwired_standalone` | _(none)_ |
| engine.trade_finance_accounting 2 standard(s) | `trade_finance_accounting` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_compliance 2 standard(s) | `trade_finance_compliance` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_connectivity 2 standard(s) | `trade_finance_connectivity` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_corporate_portal 3 standard(s) | `trade_finance_corporate_portal` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_document_checking 2 standard(s) | `trade_finance_document_checking` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_instruments 2 standard(s) | `trade_finance_instruments` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_limits 2 standard(s) | `trade_finance_limits` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_reporting 2 standard(s) | `trade_finance_reporting` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_sustainability 2 standard(s) | `trade_finance_sustainability` | `wired_direct` | `46_trade_finance.py` |
| engine.trade_finance_swift 2 standard(s) | `trade_finance_swift` | `wired_direct` | `46_trade_finance.py`, `99_swift_cockpit.py` |
| engine.trading_book_boundary 3 standard(s) | `trading_book_boundary` | `wired_via_aggregator` | _(none)_ |

## Action items

- Wire 1 standalone engine(s) into this module's pages
- Module standards wiring at excellent coverage; maintain
