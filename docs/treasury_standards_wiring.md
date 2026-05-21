# TREASURY — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `treasury`

## Summary

- Total standards mapped to this module: **19**
- Wired engines: **16**
- Unwired standalone: **3**
- Orphan (missing engine files): **0**
- Wiring coverage: **84.2%**

## Recommendation

GOOD: 84.2% wired. Address 3 unwired + 0 orphan(s).

## Standards & engine states

| Standard | Engine | State | Pages using |
|---|---|---|---|
| engine.benchmark_rates 1 standard(s) | `benchmark_rates` | `unwired_standalone` | _(none)_ |
| engine.climate_treasury_limits 1 standard(s) | `climate_treasury_limits` | `wired_direct` | `25_treasury.py` |
| engine.funds_transfer_pricing 1 standard(s) | `funds_transfer_pricing` | `unwired_standalone` | _(none)_ |
| engine.islamic_treasury 1 standard(s) | `islamic_treasury` | `wired_direct` | `25_treasury.py` |
| engine.liquidity_risk 2 standard(s) | `liquidity_risk` | `wired_direct` | `25_treasury.py`, `81_alm.py` |
| engine.liquidity_stress 1 standard(s) | `liquidity_stress` | `wired_direct` | `25_treasury.py`, `35_stress_testing.py` |
| engine.market_risk 2 standard(s) | `market_risk` | `unwired_standalone` | _(none)_ |
| engine.market_risk_factors 1 standard(s) | `market_risk_factors` | `wired_via_aggregator` | _(none)_ |
| engine.market_risk_limits 2 standard(s) | `market_risk_limits` | `wired_via_aggregator` | _(none)_ |
| engine.market_risk_sensitivities 1 standard(s) | `market_risk_sensitivities` | `wired_via_aggregator` | _(none)_ |
| engine.market_risk_var 3 standard(s) | `market_risk_var` | `wired_direct` | `35_stress_testing.py` |
| engine.treasury_agents 1 standard(s) | `treasury_agents` | `wired_direct` | `25_treasury.py` |
| engine.treasury_alm 3 standard(s) | `treasury_alm` | `wired_direct` | `25_treasury.py` |
| engine.treasury_connectivity 3 standard(s) | `treasury_connectivity` | `wired_direct` | `25_treasury.py` |
| engine.treasury_dashboard 1 standard(s) | `treasury_dashboard` | `wired_direct` | `25_treasury.py` |
| engine.treasury_digital_assets 1 standard(s) | `treasury_digital_assets` | `wired_direct` | `25_treasury.py` |
| engine.treasury_intelligence 17 standard(s) | `treasury_intelligence` | `wired_direct` | `25_treasury.py` |
| engine.treasury_products 1 standard(s) | `treasury_products` | `wired_direct` | `25_treasury.py` |
| engine.treasury_unified_platform 1 standard(s) | `treasury_unified_platform` | `wired_direct` | `25_treasury.py` |

## Action items

- Wire 3 standalone engine(s) into this module's pages
