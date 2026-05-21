# A2Z MIS 360 — CHANGELOG v8.4

**v8.4 L14 streaming infrastructure spike — campaign-defining batch, loops reach 100%**
**Released:** May 2026
**Audit gates:** **108/108** = 100% PASS — **30th consecutive clean**
**Strategic milestone:** **🎯 LOOPS REACH 100% (15 of 15).** The campaign's last unwired loop is now closed. The architectural completeness milestone is reached.

---

## What this batch is

**Pure systems-layer closure.** Closes feedback loop L14 (Channel reliability → Customer experience alerts) — the campaign's last DESIGNED_NOT_WIRED loop, deferred from v7.x as 'requires streaming infrastructure beyond v7.x scope.'

**Three new utility modules** form a complete event-driven architecture without requiring Kafka deployment. Production can swap the file-backed event bus backend for Kafka by reimplementing only `publish()` + `subscribe()` — the producer/consumer API contract is unchanged.

---

## What changed

### `utils/event_bus.py` — new module (~250 lines)

Lightweight file-backed JSON-lines event bus.

| Component | Purpose |
|---|---|
| `_BUS_LOCK` | Thread-safe (threading.Lock) |
| `_BUS_CACHE` | topic → list of Event dataclass instances |
| `_NEXT_EVENT_ID` | Per-topic monotonic counter |
| `publish(topic, payload, ...)` | Returns Event with event_id + UTC timestamp |
| `subscribe(topic, since_event_id, limit)` | Kafka offset-style consumer pattern |
| `get_latest(topic, n)` | N newest events for UI dashboards |
| `list_topics()` / `get_topic_stats()` | Admin/monitoring |
| `clear_topic()` | Admin/test utility |

Persistence: `event_bus_data/<topic>.jsonl`, atomic write via `.tmp` + replace, rolling 1000-event retention per topic.

### `utils/channels_reliability.py` — L14 PRODUCER (~150 lines)

```python
ChannelReliabilityProducer.report_event(
    channel_type="MOBILE_APP",     # 5 channels: ATM, MOBILE_APP, INTERNET_BANKING, AGENT_BANKING, USSD
    severity="OUTAGE",              # 3 severities: OUTAGE, DEGRADATION, SLA_BREACH
    location="BANK_WIDE",
    description="Mobile banking app temporarily down",
    estimated_affected_customers=18000,
)
# → publishes to `channel_reliability` topic
# → returns {status: "PUBLISHED", event_id: N, ...}
```

Per Charter §7 PUBLISHED_LANGUAGE pattern. Validates inputs against 5 × 3 = 15 valid combinations.

### `utils/smart_alerts.py` — L14 CONSUMER (~200 lines)

```python
result = SmartAlertsConsumer.consume(since_event_id=last_seen)
# → {alerts: [...], new_max_event_id: N, consumed_count: K, ...}
```

**Tier classification logic:**

| Severity × Affected | Tier | Delivery channels |
|---|---|---|
| OUTAGE × >5000 affected | URGENT | PUSH + SMS + IN_APP_BANNER |
| OUTAGE/DEGRADATION × 100-5000 | HIGH | PUSH + IN_APP_BANNER |
| Otherwise (SLA_BREACH, <100) | INFO | IN_APP_BANNER only |

**Body templates** include channel-specific alternative-channel guidance: "your usual ATM is down; please use mobile app, internet banking, or visit an agent."

Incremental consumption pattern (caller stores `new_max_event_id`, passes back next call) matches Kafka consumer offsets exactly.

### L14 status flipped: DESIGNED_NOT_WIRED → WIRED

In `utils/system_flows.py` registry. Notes cite all 3 new modules + Kafka-readiness + 100% loops achievement.

### Charter §8 updated — 100%

Wired count 14 → 15 (100%). Narrative: "The campaign's last unwired loop is now closed. Production deployment can swap the file-backed event bus for Kafka without changing producer/consumer logic."

---

## End-to-end smoke test (all green)

```
=== PRODUCER: emit 4 channel reliability events ===
  ✓ event_id=1: MOBILE_APP/OUTAGE → 18000 affected
  ✓ event_id=2: ATM/OUTAGE → 250 affected
  ✓ event_id=3: AGENT_BANKING/DEGRADATION → 1200 affected
  ✓ event_id=4: USSD/SLA_BREACH → 500 affected

=== CONSUMER: derive customer alerts ===
  Consumed 4 events → 4 alerts
  Pattern: PUBLISHED_LANGUAGE, payload_version: 1.0

  [URGENT] Mobile App temporarily unavailable
    Delivery: PUSH + SMS + IN_APP_BANNER
    Recipients: 18,000

  [HIGH] ATM temporarily unavailable
    Delivery: PUSH + IN_APP_BANNER
    Recipients: 250

  [HIGH] Agent Banking experiencing slow response
    Delivery: PUSH + IN_APP_BANNER
    Recipients: 1,200

  [INFO] USSD Banking service notice
    Delivery: IN_APP_BANNER
    Recipients: 500

=== Incremental consumption verified ===
  Second poll consumed_count=0 (correct: nothing new)

=== FULL AUDIT ===
  Score: 108/108 gates = 100.0% — PASS

=== Loop status ===
  Loops WIRED: 15/15 = 100% ⭐
  L14: WIRED
```

---

## ✅ Thirtieth consecutive clean-first-try

30 batches in a row landing clean — v5.96 → v8.4. The full systems-layer campaign + the v8.x main track + the loop-100% milestone, all clean on first try.

---

## Comparison vs v8.3

| | v8.3 | v8.4 |
|---|---|---|
| Audit gates | 108/108 | **108/108** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Stocks ACL-wired | 5 (~85%) | 5 (~85%, unchanged) |
| **Feedback loops WIRED** | **14 (93%)** | **15 (100%)** ⭐ |
| Engines reading from registry | 6 | 6 (unchanged) |
| **Event-driven architecture** | **none** | **event_bus + producer + consumer** ⭐ |
| Standards in UI | 61 | 61 (unchanged) |
| Clean-first-try streak | 29 | **30** |

---

## Strategic narrative — campaign architectural completeness reached

| Phase | Loops |
|---|---|
| v7.0 (start) | 0 of 15 — registry only |
| v7.1 (+L01) | 3 of 15 (Credit Risk depth) |
| v7.2 → v7.6 | 13 of 15 (87%) |
| v7.12 (+L05 cards) | 14 of 15 (93%) |
| v7.13 → v8.3 | unchanged at 14/15 |
| **v8.4 (+L14)** | **15 of 15 (100%)** ⭐ |

**The campaign's architectural completeness milestone is reached.** Every feedback loop the v7.0 charter designed is now functional. The 30-batch clean streak from v5.96 to v8.4 spans:
- The pre-v7 feature batches (v5.96 → v6.2)
- The full v7.x systems-layer expansion (25 batches)
- The v8.x main track to date (5 batches)
- Including the campaign's most ambitious deliverables: ACL pattern, retrospective doc, live FLEXCUBE handlers, retry/circuit/latency, audit hardening gates, and now event-driven streaming

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — 3 modules compile + self-tests pass + end-to-end round-trip verified via Python.
2. **File-backed event bus is single-process** — multi-process deployment needs real Kafka or Redis pub/sub; documented in module docstring.
3. **No actual SMS/PUSH delivery** — `delivery_channels` is targeting metadata; future v8.x batch can wire Twilio/Firebase.
4. **Tier classification thresholds hardcoded** — banks may want CBK-policy-configurable thresholds (read from system_invariants registry); future enhancement.
5. **No deduplication** — 5 events for same outage = 5 alerts; production may want 'don't re-alert within N minutes' policy.
6. **No alert-history tracking** — consume() doesn't persist; events on bus persist but emitted alerts are forgotten on restart.
7. **No new audit gate for L14 specifically** — G106 already verifies loop round-trip-testability; G108 doesn't apply (FLEXCUBE-specific).
8. **No retry on event_bus disk write failures** — best-effort persistence.
9. **Topic name sanitization is permissive** — fine for trusted-internal use; production should validate at producer.
10. **No event_bus admin UI** — `clear_topic()` exists; future systems-view page could surface admin actions.
11. **Customer alert text is English-only** — production multi-language needs i18n.
12. **The 30-batch clean streak is now the dominant story** — unusual for software development; reflects single-purpose batches + comprehensive audit + ratcheting gates.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v8.5 Surface L14 chain on page 91 systems view** | Completes 'engine + loop + UI' canonical sequence; integration tally 61 → 62 |
| (2) | v8.5 Add G109 'PUBLISHED_LANGUAGE loops have payload_version' | Hardens L05 + L14 contract |
| (3) | v8.5 Build v8.x retrospective doc | Captures v8.0 → v8.4 arc |
| (4) | v8.5 Add jitter to retry backoff | Small focused batch from v8.3 backlog |
| (5) | v8.5 Implement `--from-cbs` flag in CBS writer | v8.x readiness |
| (6) | v8.5 Add admin reset_circuit() + replay_events() | Operator UX hardening |

**Strong recommendation: v8.5 = Surface L14 chain on page 91** — completes the L14 visibility chain (engine + loop + UI surface) following the canonical v7.12/v7.13 pattern; pushes integration tally 61 → 62; would be a 31st-clean candidate.

Alternative: v8.x retrospective doc (captures v8.0 → v8.4 main-track arc as canonical reference).

---

🎯 **L14 closed via lightweight event-bus architecture — 15 of 15 loops WIRED (100%). Campaign architectural completeness reached.**

⭐ **30 consecutive clean-first-try batches. The campaign's most ambitious milestone is delivered.**
