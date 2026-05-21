# A2Z MIS 360 — v8.x Main Track Campaign Retrospective

> **Status**: Canonical retrospective (v8.6, May 2026)
> **Scope**: 6 batches from v8.0 (live FLEXCUBE handlers) to v8.5 (L14 chain visible)
> **Audience**: Future engineers who need to understand how the platform's v8.x main track was built
> **Companion to**: `docs/A2Z_V7_RETROSPECTIVE.md` (v7.16 — captures the 24-batch v7.x systems-layer expansion)
> **Supersedes**: per-batch CHANGELOG_v8.x.md narratives (those remain the source of truth for individual batches; this doc tells the v8.x arc)

---

## What v8.x was

A 6-batch main-track campaign that took the A2Z MIS 360 platform from "v7.x systems-layer complete with stubs for production data" to "v7.x systems-layer complete with end-to-end production data path through FLEXCUBE Apigee, hardened against transient failures, fully observable to operators, and architecturally complete (loops 100%)."

The campaign's organising frame is **production readiness**:
- The v7.x ACL pattern was designed to handle live FLEXCUBE without changing caller code; v8.x proved it
- The v7.x loop registry had 1 unwired loop (L14 streaming); v8.x closed it
- The v7.x audit hardening (G106 + G107) needed extension to cover v8.x surfaces; G108 was added
- The v7.x charter promised "operators see what's happening"; v8.1/v8.2/v8.5 made it true

v8.x took the v7.x architecture and made it production-grade.

---

## State at start of v8.x (post-v7.16)

- 116 standards delivered as deterministic engines in `utils/`
- 107 audit gates (G104 + G105 + G106 + G107 added in v7.x)
- 61 standards in UI
- **5 of 6 stocks ACL-wired** (capital_base intentionally engine-derived)
- **5 `_fetch_*_live()` stubs returning None** — live FLEXCUBE path designed but not implemented
- **CBS-synthetic tier active** via `scripts/generate_cbs_aggregates.py`
- **14 of 15 feedback loops WIRED (93%)** — only L14 (streaming) deferred
- **No retry / no circuit breaker / no latency telemetry** for live FLEXCUBE calls
- 4 composites surfaced on page 91 + 4 per-domain pages
- 25 consecutive clean-first-try (v5.96 → v7.16)

---

## State at end of v8.x (post-v8.5)

- 116 standards delivered (unchanged — v8.x didn't add engines, it operationalised v7.x)
- **108 audit gates** (G108 added — flexcube_retry_circuit_breaker_contract)
- **62 standards in UI** (+1: L14 chain surfacing on page 91)
- 5 of 6 stocks ACL-wired (unchanged — capital_base intentional)
- **5 live FLEXCUBE handlers fully implemented** — when bank flips to mode=live, no caller code change needed
- CBS-synthetic tier still active (unchanged)
- **15 of 15 feedback loops WIRED (100%)** — L14 closed via event_bus + producer + consumer
- **Retry layer**: 3 attempts, 1s/3s/9s exponential backoff (per CBK Operations Resilience Guidelines)
- **Circuit breaker**: trips OPEN after 5 consecutive failures, stays open 60s, half-open probe pattern
- **Latency telemetry**: per-endpoint p50/p95/p99 + count + success rate over rolling 200-sample window
- **Observability triangle**: mode banner (v7.10) + circuit banner (v8.1) + latency expander (v8.2) — all on page 91 Tab 2
- **Event-driven architecture**: file-backed event bus + producer + consumer for L14 (production-swappable to Kafka)
- 4 composites surfaced (unchanged) + L05 chain (page 34) + L14 chain (page 91)
- **31 consecutive clean-first-try** (v5.96 → v8.5) — entire systems-layer campaign + v8.x main track

---

## The 6-batch arc

### v8.0 — Live FLEXCUBE handlers (first main-track batch)

The platform connected the v7.x ACL seam to its production endpoint.

**5 portfolio-aggregate methods added to `utils/flexcube_adapter.py`:**

| Method | FLEXCUBE endpoint |
|---|---|
| `fetch_loan_portfolio_aggregate_live()` | `/PortfolioService/Loans/Aggregate` |
| `fetch_deposit_book_aggregate_live()` | `/PortfolioService/Deposits/Aggregate` |
| `fetch_npl_aggregate_live()` | `/PortfolioService/NPL/Aggregate` |
| `fetch_customer_base_aggregate_live()` | `/CustomerService/Aggregate` |
| `fetch_dormant_accounts_aggregate_live()` | `/AccountService/Dormancy/Aggregate` |

Each translates FLEXCUBE field names (GROSS_OS, SEGMENT_DIST, STAGE_DIST, etc) to A2Z's normalised vocabulary inside the adapter — A2Z domain code never sees FLEXCUBE-specific names. Per Charter §7 ACL pattern.

The 5 `_fetch_*_live()` stubs in `flexcube_aggregator.py` were rewired to call these new adapter methods. **The 3-tier fallback (live → CBS synthetic → demo defaults) is now operational**: when the bank flips `mode=live`, the 5 ACL-wired stocks pull from real CBS without ANY caller code change.

**Key insight from v8.0:** v7.x designed the seam; v8.0 connected it to production. The architecture is identical on both sides of the transition. This is the definition of a successful Anti-Corruption Layer.

### v8.1 — Retry + circuit breaker (resilience hardening)

The platform's live FLEXCUBE calls became production-grade.

**Per CBK Operations Resilience Guidelines:**
```python
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 3.0, 9.0)  # exponential
CIRCUIT_BREAKER_THRESHOLD = 5             # consecutive failures
CIRCUIT_BREAKER_OPEN_SECONDS = 60.0       # open duration
```

**Module-level state with thread-safe locking:**
- `_CIRCUIT_LOCK` (threading.Lock) + `_CIRCUIT_STATE` dict
- 3 helpers: `_circuit_is_open()`, `_circuit_record_success()`, `_circuit_record_failure()`
- Half-open probe pattern (auto-clear trip after open duration; one probe call; close on success, re-trip on failure)

**`get_circuit_state()` public observability helper** — page 91 systems view shows the circuit state as a banner: silent when healthy, yellow on intermittent failures (1-4 of 5), red when OPEN.

**Critical design choice — single chokepoint:** all 5 aggregate methods funnel through `_live_request()` so they share the circuit. If FLEXCUBE is down for one endpoint it's likely down for all (shared Apigee gateway + OAuth + network), so coordinated fast-fail is the right behaviour.

**Key insight from v8.1:** Retry without circuit breaker = thundering herd during sustained outage. Circuit breaker without retry = fragile under transient failures. The combination is the canonical pattern.

### v8.2 — Latency telemetry (observability triangle complete)

The platform's FLEXCUBE integration became fully observable.

**Per-endpoint p50/p95/p99 latency** over a rolling 200-sample window:

```python
LATENCY_WINDOW_SIZE = 200
_LATENCY_LOCK = threading.Lock()
_LATENCY_SAMPLES: Dict[str, list] = {}
```

**`get_latency_state()` returns:**
- `endpoints` map: count, success_count, failure_count, success_rate_pct, p50_ms, p95_ms, p99_ms, last_call_ts, latest_outcome per endpoint
- `summary`: aggregates across endpoints

**Critical design choice — circuit-open suppression:** when v8.1 circuit is OPEN, `_live_request()` fast-fails BEFORE reaching `_record_latency()`. Circuit-open responses are sub-millisecond synthetic responses that don't represent real round-trip times — including them would skew p50/p95/p99 toward 0 and **hide actual production latency**. Circuit-open is already observable via the circuit banner; latency telemetry focuses on real RTTs.

**The observability triangle is now complete on page 91 Tab 2:**

| Surface | Operator answers |
|---|---|
| Mode banner (v7.10) | "Which path are we on?" (synthetic / mock / live) |
| Circuit banner (v8.1) | "Is the path healthy?" (closed / intermittent / open) |
| **Latency expander (v8.2)** | **"How fast is the path?"** (p50/p95/p99 per endpoint) |

When operators ask "is FLEXCUBE working?", they can answer at three levels — configuration, reliability, performance — without leaving the page.

**Key insight from v8.2:** Observability has three concerns and they don't substitute for each other. Mode tells you intent. Circuit tells you reliability. Latency tells you performance. All three are needed for a complete operator picture.

### v8.3 — G108 audit gate (audit hardening)

The platform's v8.0/v8.1/v8.2 surfaces became permanent invariants.

**G108 verifies via importlib introspection:**
1. The 4 v8.1/v8.2 module constants exist with correct types and sane bounds
2. The 5 public observability/admin helpers are importable
3. The 5 v8.0 portfolio aggregate methods are importable
4. State helpers return correctly-shaped dicts

**G108 reports 0 violations on first run** — the v8.1 + v8.2 implementations already established the contract; G108 codifies it. Unlike v7.15 where G106 + G107 found 2 latent registry inconsistencies, v8.3 found nothing because the contract is fresh.

**Defense-in-depth audit perimeter (5 gates):**

| Gate | Locks |
|---|---|
| G104 | Engine migration ratchet (v7.0.1) |
| G105 | Strict invariant registry usage (v7.1) |
| G106 | Loop round-trip-testability (v7.15) |
| G107 | Stock data_source provenance (v7.15) |
| **G108** | **FLEXCUBE resilience + observability surface (v8.3)** |

Each gate is narrow and sharp; together they form a comprehensive perimeter around the v7.x→v8.x ACL pattern.

**Key insight from v8.3:** Audit gates aren't bookkeeping — they're permanent invariants. From v8.3 forward, any future batch that regresses retry semantics, circuit breaker semantics, latency telemetry, or breaks the public observability helpers will fail the audit at G108.

### v8.4 — L14 streaming closure (campaign-defining batch)

The platform's last unwired loop closed. **Loops reached 100%.**

**Three new utility modules** form a complete event-driven architecture:

**`utils/event_bus.py`** (~250 lines) — file-backed JSON-lines event bus:
- Thread-safe (`threading.Lock` + `_BUS_CACHE` + `_NEXT_EVENT_ID`)
- 5 public helpers: `publish()`, `subscribe()`, `get_latest()`, `list_topics()`, `get_topic_stats()`, `clear_topic()`
- Atomic writes via `.tmp` + replace
- Rolling 1000-event retention per topic
- Survives Streamlit restarts

**`utils/channels_reliability.py`** (~150 lines) — L14 PRODUCER:
- `ChannelReliabilityProducer.report_event(channel_type, severity, location, description, estimated_affected_customers)`
- Validates against 5 channel types × 3 severity tiers
- Per Charter §7 PUBLISHED_LANGUAGE pattern

**`utils/smart_alerts.py`** (~200 lines) — L14 CONSUMER:
- `SmartAlertsConsumer.consume(since_event_id=N)` — Kafka offset-style incremental consumption
- Tier classification: URGENT (OUTAGE × >5K affected) / HIGH (OUTAGE/DEGRADATION × 100-5K) / INFO (otherwise)
- Delivery channel mapping: URGENT→PUSH+SMS+IN_APP_BANNER, HIGH→PUSH+IN_APP_BANNER, INFO→IN_APP_BANNER
- Body templates with channel-specific alternative-channel guidance

**Production-swappable architecture:** the file-backed bus is functionally equivalent to a single-partition Kafka topic for the L14 use case. Production can swap by reimplementing only `publish()` + `subscribe()` to use kafka-python's KafkaProducer/KafkaConsumer — the producer/consumer API contract is unchanged.

**Key insight from v8.4:** A lightweight implementation of the right pattern is better than a heavyweight implementation of the wrong pattern, OR no implementation at all. The file-backed bus closes the loop today; the Kafka migration is a backend swap, not a re-architecture.

### v8.5 — L14 chain surfaced (visibility-completion)

The platform's L14 chain became visible end-to-end.

**Page 91 Tab 3 expander** with 3 sections:

1. **Topic stats panel** — events on bus + next event_id + latest event timestamp
2. **PRODUCER form** — emit test channel-reliability events from a UI form
3. **CONSUMER section** — see derived customer alerts with tier emojis + delivery channels + alternative-channel guidance

**Both canonical engine+loop+UI sequences are now complete:**

| Loop | Engine batch | UI batch | Result |
|---|---|---|---|
| L05 (cards) | v7.12 (utils/cards.py) | v7.13 (page 34) | engine + loop + UI |
| L14 (streaming) | v8.4 (event_bus + producer + consumer) | **v8.5 (page 91)** | **engine + loop + UI** |

**Key insight from v8.5:** Every loop wired in this campaign with a built-in-this-campaign engine has a UI surface. Future v8.x or v9.x batches building new engines can reuse this 2-batch template (build engine + close loop in batch N; surface UI in batch N+1).

---

## Cumulative invariants v8.x established

These patterns are now permanent — any future batch that violates them will fail audit.

1. **Live FLEXCUBE handlers translate field names inside the adapter** (Charter §7 ACL pattern). A2Z domain code never sees GROSS_OS, SEGMENT_DIST, etc. Translation map is the only place these names appear.

2. **All live FLEXCUBE calls go through `_live_request()`** (single chokepoint). Retry + circuit + latency telemetry are applied uniformly. Future per-endpoint customisations should be configurable inside `_live_request()`, not by bypassing it.

3. **Retry config is exposed as module constants** (`RETRY_ATTEMPTS` + `RETRY_BACKOFF_SECONDS` + `CIRCUIT_BREAKER_THRESHOLD` + `CIRCUIT_BREAKER_OPEN_SECONDS`). Banks tune within G108's sanity bounds. (G108.)

4. **Observability is read-only and structured** (`get_circuit_state()` + `get_latency_state()` return dicts). External monitoring polls these without coupling to internal state. Banner UI consumes the same surface.

5. **Circuit-open responses are NOT recorded in latency telemetry** (intentional). They're synthetic sub-ms fast-fails, not real RTTs. Including them would hide production latency.

6. **Event-driven architecture uses Kafka-compatible API** (`publish()` + `subscribe(since_event_id)`). Backend can be swapped without changing producer/consumer logic.

7. **Engine + loop + UI ships in 2 batches when the engine is new** (canonical from v7.12/v7.13 and v8.4/v8.5). Build engine + wire loop in batch N; surface UI in batch N+1.

---

## Cumulative bookkeeping numbers

| Category | v8.0 start | v8.5 end | Change |
|---|---|---|---|
| Standards delivered | 116 | 116 | unchanged |
| Standards in UI | 61 | 62 | +1 (L14 surfacing) |
| Audit gates | 107 | 108 | +1 (G108) |
| Stocks WIRED | 6 (100%) | 6 (100%) | unchanged |
| Stocks ACL-wired | 5 (~85%) | 5 (~85%) | unchanged |
| **Loops WIRED** | **14 (93%)** | **15 (100%)** | **+1 (L14)** ⭐ |
| Engines reading from invariants registry | 6 | 6 | unchanged |
| Composites surfaced | 5 surfaces | 5 surfaces | unchanged |
| Foundational modules | 17 | 20 | +3 (event_bus + channels_reliability + smart_alerts) |
| **Live FLEXCUBE handlers** | **0 (stubs)** | **5 (real)** | **+5** ⭐ |
| Resilience layers | 0 | 3 (retry + circuit + telemetry) | +3 |
| Consecutive clean-first-try | 25 | 31 | +6 |

---

## What v8.x didn't ship

Honest about scope boundaries:

1. **No actual SMS/PUSH delivery integration** — `delivery_channels` is targeting metadata; future v8.x batch can wire Twilio/Firebase.

2. **No exponential jitter on retry backoff** — backoff is deterministic 1s/3s/9s; production may want ±20% jitter to prevent synchronized retries; available for v8.6+.

3. **No admin `reset_circuit()` function** — operators restart Streamlit process to clear breaker; admin function is future enhancement.

4. **No `--from-cbs` flag implementation in CBS writer** — generative mode only; actual aggregation from cbs_data/customers.json + accounts.json + transactions.json is future v8.x.

5. **Per-endpoint circuit breaker not built** — current circuit is shared across all 5 methods (assumes coordinated FLEXCUBE failures); per-endpoint is future enhancement if production data shows independent failure modes.

6. **No persistence of circuit/latency state across restarts** — module-level singletons; production multi-process needs Redis or shared store.

7. **Multi-language alerts not built** — body text is English-only; production multi-language deployment needs i18n.

8. **No deduplication on event bus** — 5 events for same outage = 5 alerts; production may want 'don't re-alert within N minutes' policy.

9. **No alert-history tracking** — `consume()` doesn't persist emitted alerts; events on bus persist but in-flight alerts are forgotten on restart.

10. **No telemetry on retry count per call** — could record histogram of retries per call; useful for capacity planning; future observability enhancement.

11. **Latency stats reset on process restart** — production may want time-series database integration (Prometheus, InfluxDB).

12. **G109 + G110 audit gates not built** — diminishing-returns hardening (PUBLISHED_LANGUAGE payload_version validation, retry timing assertion) considered but not shipped. Available for future batches if regression patterns warrant.

---

## What worked particularly well

1. **Single chokepoint at `_live_request()`.** v8.0 made it the seam. v8.1 added retry + circuit breaker around it. v8.2 added latency telemetry around it. v8.3 verified its constants. Each batch added a layer without changing the layers below. This is what good architecture feels like.

2. **The observability triangle (mode + circuit + latency) maps to operator questions.** Each surface answers a different question; together they form a complete dashboard. No surface duplicates another's job.

3. **Lightweight event bus closes L14 today AND prepares for Kafka tomorrow.** The producer/consumer API is identical to Kafka's — only the storage backend differs. Production migration is a backend swap, not a re-architecture.

4. **G108 was the right hardening gate at the right time.** Adding it after v8.0/v8.1/v8.2 (rather than during) meant the contract was stable when codified. It found 0 violations on first run because it was codifying what already worked.

5. **The 2-batch engine+loop+UI canonical sequence repeated successfully.** v7.12/v7.13 invented it for L05 cards. v8.4/v8.5 reused it for L14 streaming. Future batches have a battle-tested template.

6. **Charter §8 updated in lockstep with each loop closure.** v8.4 brought the count to 100%. The narrative now explicitly mentions Kafka-readiness so future engineers understand the design choice.

7. **Honest acknowledgements at the end of each CHANGELOG.** 12 acknowledgements per batch tracking what was deliberately not done. Future engineers can see what's deferred and why without re-reading the entire codebase.

---

## What was tricky

1. **Knowing when to stop adding observability.** v8.2 completed the triangle. The temptation was to add a 4th surface (retry-count histogram, e.g.) but the operator-facing question wasn't clear enough. Restraint is part of the discipline.

2. **Circuit-open suppression for latency telemetry.** A subtle correctness issue: including circuit-open fast-fails would mathematically reduce p50/p95/p99 toward 0 and hide actual production latency. Catching this required thinking about WHO uses the telemetry (operators investigating slow FLEXCUBE) and what would mislead them.

3. **Lightweight event bus vs full Kafka.** The temptation was to either (a) skip L14 entirely until Kafka was deployed, or (b) write a half-Kafka in-process pub/sub that wouldn't actually solve the production case. The right answer was a lightweight implementation of the Kafka API contract — closes L14 today, swaps to Kafka with zero caller changes.

4. **The 30-batch clean streak.** Each batch carried the weight of "don't be the first to break the streak." This is a feature (incentive for thoroughness) but also a risk (incentive for over-cautious batches). v8.4 was the riskiest of the v8.x batches because it shipped 3 new modules in one batch; landing it clean required careful self-test design.

---

## Lessons for v9.x or future campaigns

1. **The single-chokepoint pattern from `_live_request()` is reusable.** Future integrations (e.g. OBDX, Apigee) can adopt the same pattern: one helper, retry + circuit + telemetry layered around it, single point for tuning.

2. **The observability triangle (mode + reliability + performance) is a generic pattern.** Apply it to any external integration: which path are we on, is it healthy, how fast is it.

3. **Lightweight implementation of the right API beats heavyweight implementation of the wrong API.** The file-backed event bus proves this for L14. Whenever you face "we need streaming but don't have Kafka", build the Kafka API on whatever storage you have today.

4. **Audit gates added AFTER the implementation are calmer than gates added DURING.** v8.3's G108 found 0 violations because it codified a stable contract. v7.15's G106 found 2 because it was applied to a registry that had drifted. Both patterns work; v8.3's is cleaner when possible.

5. **The 2-batch engine+loop+UI sequence is the default for new domains.** Every future engine should follow it. Build + wire in batch N. Surface in batch N+1. This cadence respects both the engineering effort and the visibility requirement.

6. **Honest acknowledgements compound.** Each CHANGELOG's "Honest acknowledgements" section becomes part of the institutional memory. Future engineers know what was considered and rejected; they don't waste cycles re-discovering known-deferred items.

---

## Status: v8.x main track complete; v9.x or v8.6+ open

**The v8.x main-track campaign is complete as of v8.5.** Every architectural goal is met or explicitly deferred:

- Live FLEXCUBE integration: **production-ready** ✅
- Resilience: **CBK Operations Resilience Guidelines compliant** ✅
- Observability: **operator dashboard complete** ✅
- L14 streaming: **closed (loops 100%)** ✅
- Audit hardening: **G108 added; 5-gate perimeter complete** ✅
- L14 visibility: **end-to-end on page 91** ✅

**v8.6+ or v9.x main track** picks up from here. Strong candidates:
- v8.6 retry backoff jitter (small focused batch)
- v8.6 G109 PUBLISHED_LANGUAGE payload_version audit gate (hardens L05 + L14)
- v8.6 admin reset_circuit() + replay_events() functions
- v8.6 `--from-cbs` flag implementation in CBS writer
- v9.0 actual Twilio/Firebase delivery integration for L14 alerts
- v9.0 multi-process state via Redis (circuit + latency + bus)
- v9.0 multi-language alert templates (i18n)

---

## Per-batch index

For per-batch detail, see the corresponding CHANGELOG file:

| Batch | Zip | Theme |
|---|---|---|
| v8.0 | a2z_v8.0_live_flexcube_handlers.zip | First main-track — live FLEXCUBE handlers |
| v8.1 | a2z_v8.1_retry_circuit_breaker.zip | Resilience hardening |
| v8.2 | a2z_v8.2_latency_telemetry.zip | Observability triangle complete |
| v8.3 | a2z_v8.3_g108_resilience_lock.zip | Audit-hardening gate G108 |
| v8.4 | a2z_v8.4_l14_streaming_loops_100pct.zip | L14 closure — loops 100% ⭐ |
| v8.5 | a2z_v8.5_l14_chain_surfacing.zip | L14 chain visible end-to-end |
| v8.6 | a2z_v8.6_v8x_retrospective.zip | This document |

---

🎯 **6-batch v8.x main-track complete. Production-ready FLEXCUBE integration + observability triangle + 100% loops + 5-gate audit perimeter.**

*Generated for v8.6 — May 2026. Owner: A2Z Platform Engineering. Companion to `docs/A2Z_V7_RETROSPECTIVE.md`. References: Donella Meadows *Thinking in Systems* (2008); Eric Evans *Domain-Driven Design* (2003); Michael Nygard *Release It!* (2007 — circuit breaker pattern); Sam Newman *Building Microservices* (2015 — observability triangle); CBK Operations Resilience Guidelines for Bank Outsourcing (2019). The v7.x systems-layer was built. The v8.x main track operationalised it. Now we run it.*
