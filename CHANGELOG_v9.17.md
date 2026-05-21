# CHANGELOG v9.17 — Multi-instance load test harness

**Audit:** 115/115 PASS — **70th consecutive clean** ⭐ (70-streak milestone).

## What

Ships `scripts/load_test_multi_instance.py` (~480 lines) — concurrent-user load test harness validating the v9.6-v9.16 architecture under realistic load. Pure Python threading; no external dependencies.

## What it tests

- Per-endpoint circuit breakers (v9.6)
- Retry telemetry (v9.7)
- Latency rolling windows (v9.8)
- Multi-process atomicity (v9.16 event-bus IDs)
- All v9.x state surfaces under concurrent contention

## Verified output (8 users × 25 calls @ 20% failure rate)

```
Total calls:          200
Successful:           184 (92.0%)
Throughput:           60.3 calls/s
Latency p50/p95/p99:  100.3/101.1/101.2 ms
Total retries:        57 (avg 0.28 per call)
Recovery rate:        55.6%
Circuit trips:        0 (failure rate kept below threshold)
```

## CLI features

| Flag | Default | Purpose |
|---|---|---|
| `--users` | 10 | Concurrent simulated users |
| `--calls` | 100 | Calls per user |
| `--failure-rate` | 0.05 | Synthetic endpoint failure rate (0.0-1.0) |
| `--seed` | None | Reproducibility seed |
| `--output` | None | JSON summary file path |
| `--quiet` | False | Suppress text output |
| `--reset-state` | False | Clear all v9.x state surfaces before run |

Exit code: 0 if success rate ≥80%, else 2 — suitable for CI gates.

## FOUNDATIONAL allowlist update

`scripts/load_test_multi_instance.py` added (writes JSON summary file via `write_text(json.dumps(...))`); pattern matches v9.13 redis_admin.py.

## Honest acknowledgements

1. **In-process testing only** — exercises v9.6-v9.16 abstractions but does not test real multi-process Streamlit deployment. Production validation is deployment exercise.
2. **Synthetic latency simulation** — uses `time.sleep` capped at 100ms to keep tests fast; doesn't reflect real FLEXCUBE network latency profile.
3. **Failure injection is uniform random** — real banking workloads have correlated failures (entire endpoint goes down). Future v10.x could add scenario-based failure modes.
4. **Failure rate 5% with 5 endpoints rarely trips circuits** — to exercise circuit-breaker logic, run with higher failure rate (`--failure-rate 0.30`).
5. **Throughput is bounded by `time.sleep` simulation** — the `100ms` simulated latency means each thread does ~10 calls/sec; with 10 users that's ~100 calls/sec. Real Redis-backed deployments would have different throughput characteristics.
6. **No multi-process simulation** — Python threads share memory; for true multi-process simulation, use `multiprocessing.Pool` (v10.x candidate).
7. **Per-endpoint distribution random** — real workloads may have hotspots; tests validate machinery handles uniform distribution.

## Next: v9.18

`docs/OBSERVABILITY_DASHBOARD_RUNBOOK.md` + Grafana dashboard JSON — operational documentation for surfacing v8.x telemetry into Prometheus/Grafana stack.
