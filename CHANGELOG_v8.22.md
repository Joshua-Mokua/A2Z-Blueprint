# CHANGELOG v8.22 — G111 audit gate `flexcube_resilience_v2_contract`

**Audit:** **111/111** PASS — **48th consecutive clean.** ⭐ (110 → 111 gates)

## What

Closes the 5-batch v8.18-v8.22 resilience-hardening arc. Adds G111 to lock the v8.17 + v8.19 + v8.20 FLEXCUBE resilience improvements as permanent invariants. Future regressions (anyone deleting or renaming the per-endpoint surfaces, breaking telemetry shape, removing endpoint_timeouts) fail the build.

## What G111 verifies

1. **v8.17 per-endpoint circuit state**: `get_circuit_state()` must return `per_endpoint` dict + `endpoints_tracked` count alongside aggregate keys
2. **v8.17 reset_circuit() signature**: must accept optional `endpoint_key` parameter
3. **v8.19 retry telemetry surface**: `get_retry_telemetry()` + `reset_retry_telemetry()` + `_record_retry_outcome()` all importable; `get_retry_telemetry()` returns expected `summary` shape with all 8 keys + `per_endpoint` dict
4. **v8.20 endpoint timeouts**: `get_config()` returns `endpoint_timeouts` dict containing all 5 known endpoint keys with positive numeric values
5. **v8.17 _endpoint_key() stability**: helper produces deterministic, stable keys (same input → same output, expected normalization)

## Drift test (verified)

```
=== Clean run ===
  G111 passed: 0 violations
  Audit: 111/111 PASS

=== Drift test (endpoint_timeouts removed from config) ===
  G111 passed: False
  - config: missing endpoint_timeouts dict (v8.20)
  
✓ G111 fires correctly on regression. Restored clean state.
```

## The 8-gate defense-in-depth perimeter

| Gate | Locks | Shipped |
|---|---|---|
| G104 | Engine migration ratchet | v7.0.1 |
| G105 | Strict invariant registry usage | v7.1 |
| G106 | Loop round-trip-testability | v7.15 |
| G107 | Stock data_source provenance | v7.15 |
| G108 | FLEXCUBE retry + circuit (v8.1 contract) | v8.3 |
| G109 | PUBLISHED_LANGUAGE payload_version | v8.7 |
| G110 | Collateral claims traceable | v8.16 |
| **G111** | **FLEXCUBE resilience v2 (v8.17+v8.19+v8.20)** | **v8.22** ⭐ |

Coverage: engines (G104), domain models (G105), system flows (G106), system stocks (G107), runtime resilience v1 + v2 (G108 + G111), inter-context messaging (G109), documentation generation (G110). Every cross-cutting structural property of the platform is now audit-locked.

## v8.18-v8.22 batch arc summary

| Batch | What | Cumulative streak |
|---|---|---|
| v8.18 | Per-endpoint circuit UI surface | 44 |
| v8.19 | Retry-count telemetry engine (closes ack #9) | 45 |
| v8.20 | Per-endpoint timeout config engine (closes ack #7) | 46 |
| v8.21 | Combined UI surface for v8.19 + v8.20 | 47 |
| **v8.22** | **G111 audit gate locking the v8.17-v8.21 contracts** | **48** ⭐ |

## v8.6 retrospective backlog burndown — now 8/12 closed (67%)

| # | Ack | Status | Closed in |
|---|---|---|---|
| 1-5 | (closed v8.7-v8.10) | ✅ | — |
| 6 | Per-endpoint circuit breaker | ✅ | v8.17 |
| **7** | **Per-endpoint timeout config** | **✅** | **v8.20** |
| **9** | **Retry-count telemetry** | **✅** | **v8.19** |
| 8 | Event-bus deduplication | ⏳ | — |
| 10 | Latency persistence | ⏳ | — |
| 11 | Alert-history persistence | ⏳ | — |
| 12 | Multi-language alerts (i18n) | ⏳ | — |

## Honest acknowledgements

1. G111 imports `flexcube_adapter` at audit time — adds ~30ms to audit run; acceptable cost.
2. G111's `endpoint_timeouts` check assumes the 5 known endpoints; if a 6th endpoint is added later (e.g. v9.x cards aggregate), G111's `known_endpoints` set must be updated.
3. G111 doesn't verify that `_record_retry_outcome` is actually CALLED in `_live_request()`; it only checks the function exists. A regression where someone deleted the call-site but kept the function would slip through; mitigated by behavioral tests.
4. The drift test is in-process monkey-patch (sufficient for verification); a more robust test would commit a deliberately-broken state, run audit, observe failure, revert.
5. G108 and G111 overlap on `get_circuit_state()` — G108 verifies the v8.1 keys (preserved aggregate), G111 verifies the v8.17 additions (per_endpoint, endpoints_tracked). Intentional layering: G108 locks original contract, G111 locks the v8.17 extension.
6. Inspecting function signatures via `inspect.signature` (for reset_circuit endpoint_key parameter) works on Python 3.4+; baseline is 3.10+ so this is fine.

## Status snapshot at end of v8.22

- **Audit gates**: **111/111** ⭐ (110 → 111)
- **Defense-in-depth perimeter**: 8 gates (G104-G111)
- **Clean-first-try streak**: **48 consecutive** (v5.96 → v8.22)
- **v8.6 backlog**: 8/12 closed (67%)
- **Sub-campaigns active**:
  - Living Documentation: COMPLETE (5-batch arc closed at v8.16)
  - Legal Infrastructure: plan + Tier 1 LICENSE.md shipped; awaiting Joshua's lawyer engagement

## Next batch options (for v8.23+)

| Priority | Batch | Strategy |
|---|---|---|
| (1) | v8.23 Event-bus deduplication (ack #8) | ~80 lines event_bus; prevents duplicate event delivery; closes another v8.6 ack |
| (2) | v8.23 Latency persistence (ack #10) | ~100 lines flexcube_adapter; SQLite/JSON dump rolling window for restart-survival |
| (3) | v8.23 Alert-history persistence (ack #11) | ~80 lines smart_alerts; persists alert history across restarts |
| (4) | v8.23 Operational Legal Tier 1 templates | Author NDA + IP Assignment drafts in `docs/legal_templates/` for Joshua's lawyer to refine |

**Recommended: v8.23 = Event-bus deduplication (ack #8)** — closes another v8.6 ack; complements the v8.4 event_bus work; ~80 lines focused engineering; consistent with the resilience theme.
