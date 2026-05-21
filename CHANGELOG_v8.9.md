# A2Z MIS 360 — CHANGELOG v8.9

**v8.9 Admin operations: reset_circuit() + replay_events() — closes v8.6 retrospective acks #3 + #4**
**Released:** May 2026
**Audit gates:** **109/109** = 100% PASS — **35th consecutive clean**
**Strategic milestone:** **🎯 V8.X BACKLOG BURNDOWN AT 4 OF 12 (33%) CLOSED.** v8.7 (G109) + v8.8 (jitter) + v8.9 × 2 (reset_circuit + replay_events) = 4 honest acknowledgements turned into shipped code.

---

## What this batch is

**Pure operator UX hardening.** Zero domain feature additions. Audit gate count unchanged at 109/109. G108 extended to verify reset_circuit is importable.

**Two things shipped**: `flexcube_adapter.reset_circuit()` (clear breaker without restart) + `event_bus.replay_events()` (audit-trail snapshot). Both surfaced as buttons on page 91.

This single batch closes **2 of 12** v8.6 retrospective acknowledgements (#3 + #4) — operators can now manage circuit breaker state and inspect event history without process restarts.

---

## What changed

### `flexcube_adapter.reset_circuit()` — new public admin function

```python
def reset_circuit() -> Dict[str, Any]:
    """Manually clear the circuit breaker state without restarting."""
    with _CIRCUIT_LOCK:
        prior_failures = _CIRCUIT_STATE["consecutive_failures"]
        prior_tripped = _CIRCUIT_STATE["tripped_until"]
        was_open = prior_tripped > _time.time()
        _CIRCUIT_STATE["consecutive_failures"] = 0
        _CIRCUIT_STATE["tripped_until"] = 0.0
    return {
        "reset_at_iso": datetime.now(timezone.utc).isoformat(),
        "prior_consecutive_failures": prior_failures,
        "prior_was_open": was_open,
        "current_state": "closed",
    }
```

**Audit-trail return value** so operators have a record of what was cleared.

**Use cases:**
- FLEXCUBE outage resolved before the open-duration timeout (60s default)
- Operator wants to re-probe after fixing a config issue
- Test/dev environments where stale state needs clearing

**Note:** latency telemetry is **not** touched (separate state with its own `reset_latency_state()` admin).

### `event_bus.replay_events(topic, since_event_id, limit)` — new admin function

```python
def replay_events(topic, since_event_id=0, limit=None) -> Dict[str, Any]:
    """Re-emit consumer-style replay of events for a topic."""
```

Distinct from the consumer-facing `subscribe()` — this is for **operator debugging**:

Returns dict with full Event metadata (`event_id` + `topic` + `payload` + `timestamp_iso` + `payload_version`) per event PLUS aggregates (`count`, `oldest_ts`, `newest_ts`, `replay_at_iso`).

**Use cases:**
- Investigating a customer-alert false positive — replay channel_reliability events
- Test/dev environments — re-derive consumer alerts from a known event sequence
- Audit trail — produce a JSON snapshot for regulatory or internal review

Graceful no-op on non-existent topics (returns `count=0`, `oldest_ts=None`).

### Page 91 Tab 2 — 🔄 Reset circuit breaker button

Sits **below** the v8.1 circuit banner. Visible only when `is_open=True` OR `consecutive_failures > 0` (silent in healthy state — keeps banner clean).

Click handler calls `reset_circuit()` and renders an `st.success` message with the full audit-trail dict.

### Page 91 Tab 3 — 🔁 Replay events (audit snapshot) button

Sits **next to** the existing v8.5 Clear bus button. Calls `replay_events(CHANNEL_RELIABILITY_TOPIC, limit=10)`. When events present, renders an inner `st.expander` with the full snapshot via `st.json` so operators can copy-paste for tickets/regulatory submissions.

### G108 extended to verify reset_circuit is importable

Added `'reset_circuit'` to G108's public helpers list. Future batches that delete/rename `reset_circuit` will fail audit. **G108 still reports 0 violations.**

### `flexcube_adapter` datetime import extended

`from datetime import date, datetime, timedelta` → `from datetime import date, datetime, timedelta, timezone` — `reset_circuit()` returns `datetime.now(timezone.utc).isoformat()` for the audit timestamp.

---

## End-to-end smoke test (4 scenarios all green)

```
=== Scenario 1: reset_circuit when circuit is OPEN ===
  Recorded 5 failures via _circuit_record_failure()
  Circuit before reset: failures=5, is_open=True
  reset_circuit() returned: {
    'reset_at_iso': '2026-05-01T15:55:27.841376+00:00',
    'prior_consecutive_failures': 5,
    'prior_was_open': True,
    'current_state': 'closed'
  }
  Circuit after reset: failures=0, is_open=False ✓

=== Scenario 2: replay_events full + incremental + limited ===
  Published 3 events to test topic
  Full replay: count=3, events[0]=event_id=1, events[2]=event_id=3
  Incremental replay (since_event_id=1): count=2 ✓
  Limited replay (limit=1): count=1 + only first event ✓

=== Scenario 3: replay_events on non-existent topic ===
  count=0, oldest_ts=None, replay_at_iso populated
  ✓ Graceful no-op pattern

=== Scenario 4: G108 extended verification ===
  G108 verifies reset_circuit is importable via hasattr
  ✓ 0 violations on first run

=== FULL AUDIT ===
  Score: 109/109 gates = 100.0% — PASS
```

---

## ✅ Thirty-fifth consecutive clean-first-try

35 batches in a row landing clean — v5.96 → v8.9.

---

## Comparison vs v8.8

| | v8.8 | v8.9 |
|---|---|---|
| Audit gates | 109/109 | **109/109** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Stocks ACL-wired | 5 (~85%) | 5 (~85%, unchanged) |
| Feedback loops WIRED | 15 (100%) | 15 (100%, unchanged) |
| Retry on live calls | 3 attempts, 1s/3s/9s + ±20% jitter | unchanged |
| Circuit breaker | 5-failure threshold, 60s open | unchanged |
| **Admin reset_circuit()** | **none (process restart required)** | **restart-free with audit trail** ⭐ |
| **Event-bus replay_events()** | **none** | **JSON-style audit snapshot** ⭐ |
| Standards in UI | 62 | 62 (unchanged) |
| Clean-first-try streak | 34 | **35** |

---

## Strategic narrative — v8.x backlog burndown 4 of 12 (33%) closed

| # | v8.6 retrospective acknowledgement | Closed |
|---|---|---|
| 1 | G109 audit gate not built | **v8.7** ✓ |
| 2 | No exponential jitter on retry backoff | **v8.8** ✓ |
| 3 | No admin reset_circuit() function | **v8.9** ✓ |
| 4 | No event-bus replay function | **v8.9** ✓ |
| 5 | --from-cbs flag not implemented | open |
| 6 | Per-endpoint circuit breaker | open |
| 7 | No multi-process state | open |
| 8 | English-only alerts (no i18n) | open |
| 9 | No event-bus deduplication | open |
| 10 | No alert-history persistence | open |
| 11 | No retry-count telemetry | open |
| 12 | Latency stats reset on restart | open |

The remaining 8 acks split into:
- **Tactical (3)**: --from-cbs (#5), event-bus dedup (#9), retry-count telemetry (#11) — small focused batches
- **Architectural (5)**: per-endpoint circuit (#6), multi-process state (#7), i18n (#8), alert-history persistence (#10), latency persistence (#12) — warrant own focused batches or v9.x consideration

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — adapter + page 91 buttons compile + smoke-tested via Python.
2. **Reset circuit button visible only when failures > 0** — keeps banner clean in healthy state; could alternatively always show; conditional matches existing UI conventions.
3. **Replay button shows first 10 events** — bounded by `limit=10` for manageable inner expander; programmatic callers can omit limit.
4. **No confirmation dialog before reset** — single-click matches v8.5 Clear bus admin pattern; production may want 2-step confirm.
5. **reset_circuit() doesn't touch latency telemetry** — intentional state separation; `reset_latency_state()` is independent admin.
6. **replay_events() returns full event payloads** — including potentially-sensitive operational data; fine for trusted-internal admin; production may want PII-scrubbed variant.
7. **No audit-trail of WHO clicked the reset button** — Streamlit doesn't have built-in user identity; production with auth can wrap reset_circuit() with logging.
8. **G108 extended in-place vs adding G110** — minimal change; G108 already enumerates public helpers so extending was the cleaner path.
9. **replay_events() is on event_bus not channels_reliability** — generic helper for any topic; matches bus API style; future modules using event_bus get replay capability for free.
10. **Page 91 buttons use existing emoji vocabulary** — 🔄 + 🔁 join 🚨/⚠️/ℹ️/📤/🗑️/📊/📡; consistent visual language.
11. **No regressions in any other gate** — adding admin functions + buttons + G108 extension didn't change any existing gate.
12. **v8.x backlog burndown 4 of 12 (33%) closed** — remaining 8 acks split into tactical (small batches) and architectural (warrant focused batches or v9.x).

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v8.10 Implement `--from-cbs` flag in CBS writer** | Addresses ack #5; self-bootstrapping synthetic mode |
| (2) | v8.10 Per-endpoint circuit breaker | Addresses ack #6; finer-grained resilience |
| (3) | v8.10 Add G110 audit gate 'RETRY_JITTER_PCT bounds' | Small enhancement to G108 |
| (4) | v9.0 Multi-process state via Redis | Major architectural batch; addresses ack #7 |
| (5) | v9.0 Multi-language alert templates (i18n) | Addresses ack #8 |
| (6) | v8.10 Event-bus deduplication | Addresses ack #9; "don't re-alert within N minutes" |

**Strong recommendation: v8.10 = Implement `--from-cbs` flag in CBS writer** — addresses v8.6 retrospective ack #5; small focused batch (~80 lines change to scripts/generate_cbs_aggregates.py + a few lines to flexcube_aggregator's CBS-tier loader); turns synthetic mode self-bootstrapping when CBS files exist; 36th-clean candidate.

Alternative: G110 audit gate 'RETRY_JITTER_PCT bounds' (small + tactical; closes a small G108 sanity-check gap from v8.8).

---

🎯 **2 admin operations shipped — operators can clear circuit + replay events without restart.**

⭐ **35th consecutive clean-first-try. v8.x backlog burndown 4 of 12 (33%) closed.**
