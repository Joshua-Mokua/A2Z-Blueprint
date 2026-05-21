# CRM — Standards Wiring Report

**Generated:** 2026-05-15 (v10.460 real per-module audit)
**Module key:** `crm`

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
| engine.channel_sla 7 standard(s) | `channel_sla` | `wired_direct` | `73_channels.py` |
| engine.cross_channel_balancing 1 standard(s) | `cross_channel_balancing` | `wired_via_aggregator` | _(none)_ |
| engine.cross_sell_bandit 1 standard(s) | `cross_sell_bandit` | `unwired_standalone` | _(none)_ |
| engine.cross_sell_nba 1 standard(s) | `cross_sell_nba` | `wired_direct` | `45_crosssell.py` |
| engine.kyc_onboarding 1 standard(s) | `kyc_onboarding` | `wired_direct` | `24_compliance.py` |

## Action items

- Wire 1 standalone engine(s) into this module's pages
