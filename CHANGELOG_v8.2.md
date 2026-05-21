# A2Z MIS 360 — CHANGELOG v8.2

**v8.2 Request latency telemetry — completes observability triangle (mode + circuit + latency)**
**Released:** May 2026
**Audit gates:** **107/107** = 100% PASS — **28th consecutive clean**
**Strategic milestone:** **🎯 OBSERVABILITY TRIANGLE COMPLETE.** Page 91 systems view is now a complete operator dashboard for FLEXCUBE integration health: configuration (mode), reliability (circuit), and performance (latency).

---

## What this batch is

**Pure observability addition.** Zero API changes. Zero audit gate changes. Zero retry/circuit contract changes.

**Two things shipped**: per-endpoint p50/p95/p99 latency tracking inside `_live_request()` in `flexcube_adapter.py`, plus an expandable latency table on `pages/91_systems_view.py`.

---

## What changed

### Module-level latency state (thread-safe)

```python
_LATENCY_LOCK = threading.Lock()
_LATENCY_SAMPLES: Dict[str, list] = {}  # endpoint → [(latency_ms, success_bool, ts), ...]
LATENCY_WINDOW_SIZE = 200  # rolling, per-endpoint
```

Memory bounded: 5 endpoints × 200 samples × ~80 bytes = ~80KB total.

### `_record_latency()` internal helper

Called by `_live_request()` exactly once per completed call. Trims to window size on each append.

### `get_latency_state()` public observability helper

```python
{
    "endpoints": {
        "/PortfolioService/Loans/Aggregate": {
            "count": 200,
            "success_count": 198,
            "failure_count": 2,
            "success_rate_pct": 99.0,
            "p50_ms": 45.2,
            "p95_ms": 120.8,
            "p99_ms": 280.3,
            "last_call_ts": 1714564845.123,
            "last_latency_ms": 47.2,
            "latest_outcome": "success",
        },
        ...
    },
    "summary": {
        "endpoints_observed": 5,
        "total_calls": 1000,
        "total_successes": 985,
        "total_failures": 15,
        "overall_success_rate_pct": 98.5,
        "window_size": 200,
    }
}
```

### `reset_latency_state()` admin/test utility

Clears all samples. Useful for test fixtures + operational reset.

### Page 91 latency telemetry expandable

Silent when no calls observed (default synthetic-mode startup state). When calls exist:

```
📊 FLEXCUBE latency telemetry (v8.2) — N calls observed, X% success rate
  ┌─────────────────────────────────────┬───────┬──────────┬─────────┬─────────┬─────────┬─────────┐
  │ Endpoint                            │ Calls │ Success% │ p50 (ms)│ p95 (ms)│ p99 (ms)│ Last    │
  ├─────────────────────────────────────┼───────┼──────────┼─────────┼─────────┼─────────┼─────────┤
  │ /PortfolioService/Loans/Aggregate   │   200 │     99.0 │    45.2 │   120.8 │   280.3 │ success │
  │ /PortfolioService/Deposits/Aggregate│   180 │    100.0 │    38.1 │    95.4 │   145.0 │ success │
  └─────────────────────────────────────┴───────┴──────────┴─────────┴─────────┴─────────┴─────────┘
  Rolling window of last 200 samples per endpoint. Latencies cover full request
  including retry backoff on failures. Circuit-open fast-fail responses are
  suppressed from telemetry (they're not real round-trips).
```

### Critical design choice: circuit-open suppression

When v8.1 circuit is OPEN, `_live_request()` fast-fails BEFORE reaching `_record_latency()`. Circuit-open responses are sub-millisecond synthetic responses that don't represent real FLEXCUBE round-trip times — including them would skew p50/p95/p99 toward 0 and **hide actual production latency**. Circuit-open is already observable via the circuit banner; latency telemetry focuses on real round-trip times.

---

## End-to-end smoke test (4 telemetry scenarios all green)

```
=== Scenario 1: mode=synthetic ===
  get_latency_state() → empty {summary: {total_calls: 0}, endpoints: {}}
  Banner expander silent
  ✓ No noise in default state

=== Scenario 2: mode=live + 4 failed calls (2 per endpoint) ===
  total_calls=4, success_rate=0%, p50≈37ms (reflects 3-retry × ~10ms timeout)
  Both endpoints visible with separate stats (each count=2)
  ✓ Per-endpoint isolation working

=== Scenario 3: mode=live + circuit OPEN ===
  20 fast-fail calls produce ZERO new latency samples
  total_calls unchanged across the burst
  ✓ Circuit-open suppression correct — fast-fails are not real RTTs

=== Scenario 4: per-endpoint isolation ===
  Different endpoints accumulate separate stats
  Operator can see e.g. /Loans 95% but /Customers 100%
  ✓ Independent troubleshooting per endpoint

=== FULL AUDIT ===
  Score: 107/107 gates = 100.0% — PASS
```

---

## ✅ Twenty-eighth consecutive clean-first-try

28th batch in a row landing clean.

---

## Comparison vs v8.1

| | v8.1 | v8.2 |
|---|---|---|
| Audit gates | 107/107 | **107/107** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Stocks ACL-wired | 5 (~85%) | 5 (~85%, unchanged) |
| Live FLEXCUBE handlers | 5 implementations | 5 implementations (unchanged) |
| Retry on live calls | 3 attempts, 1s/3s/9s | unchanged |
| Circuit breaker | 5-failure threshold, 60s open | unchanged |
| **Per-endpoint latency telemetry** | **none** | **p50/p95/p99 + count + success rate** ⭐ |
| **Operator dashboard surfaces** | **mode + circuit (2 of 3)** | **mode + circuit + latency (3 of 3)** ⭐ |
| Feedback loops WIRED | 14 (93%) | 14 (93%, unchanged) |
| Standards in UI | 61 | 61 (unchanged) |
| Clean-first-try streak | 27 | **28** |

---

## Strategic narrative — observability triangle complete

| Batch | Layer | Operator answers |
|---|---|---|
| v7.10 | Mode banner | "Which path are we on?" (synthetic / mock / live) |
| v8.1 | Circuit banner | "Is the path healthy?" (closed / intermittent / open) |
| **v8.2** | **Latency telemetry** | **"How fast is the path?"** (p50/p95/p99 per endpoint) |

The three observability surfaces complement each other and now form a complete operator dashboard on page 91 systems view Tab 2 (System Stocks). When operators ask **"is FLEXCUBE working?"**, they can answer at three levels — configuration, reliability, performance — without leaving the page.

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — adapter + page 91 latency expander compile + tested via Python smoke test across 4 scenarios.
2. **Single-process state model** — `_LATENCY_LOCK` + `_LATENCY_SAMPLES` are module singletons; multi-process deployment needs Redis or shared store (same caveat as v8.1 circuit state).
3. **Nearest-rank percentile method** — simple + robust for small windows but not interpolated; banks may want linear interpolation for sub-sample precision.
4. **Rolling window of 200 samples per endpoint** — keeps memory constant; bank may want larger window (1000) for higher-confidence percentile estimates.
5. **No persistence across restarts** — latency stats reset on process restart; production may want time-series database integration (Prometheus, InfluxDB).
6. **Latencies cover full request including retry backoff** — a failed call retrying 3 times with 1s/3s/9s backoff = ~13s recorded latency; this is the right operator metric but bank may also want raw single-attempt latencies for FLEXCUBE-side SLA reporting.
7. **No metric on retry count per call** — could record histogram of retries per call; future observability batch.
8. **No alerting integration** — `get_latency_state()` is read-only; external monitoring system can poll.
9. **No new audit gate** — observability is additive; doesn't change existing contracts.
10. **Circuit-open suppression is intentional** — including fast-fails would skew percentiles toward 0 and hide production latency; circuit-open is already observable via banner.
11. **Page 91 expander defaults to collapsed** — operators opt-in to view; doesn't crowd banner area in default state.
12. **Observability triangle now fully visible from a single screen** (page 91 Tab 2) — operators answer "is FLEXCUBE working?" without leaving the page.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v8.3 Add G108 audit gate 'retry contract verified via mock'** | Locks v8.1 retry semantics as permanent invariant; 107 → 108 gates |
| (2) | v8.3 L14 streaming infrastructure spike | Closes campaign's last unwired loop; major architectural batch |
| (3) | v8.3 Add jitter to retry backoff | ±20% randomization; small focused batch |
| (4) | v8.3 Add admin reset_circuit() function | Operator can clear breaker without restart |
| (5) | v8.3 Implement `--from-cbs` flag in CBS writer | Self-bootstrapping synthetic mode |
| (6) | v8.3 Add G109 'every WIRED stock returns aggregator-shaped dict' | Defense-in-depth for ACL contract |

**Strong recommendation: v8.3 = Add G108 audit gate for retry contract verification** — locks v8.1 retry semantics as permanent invariant; small focused batch using `unittest.mock`; would push 107 → 108 gates; complements G106 + G107 to fully harden the v8.0/v8.1 implementations.

Alternative: jitter for retry backoff (smaller scope; tactical reliability hardening).

---

🎯 **Latency telemetry added — page 91 is now a complete operator dashboard for FLEXCUBE integration health.**

⭐ **28th consecutive clean-first-try. Observability triangle (mode + circuit + latency) complete.**
