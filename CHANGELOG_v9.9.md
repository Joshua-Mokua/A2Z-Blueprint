# CHANGELOG v9.9 — State Backend admin UI surface

**Audit:** 113/113 PASS — **62nd consecutive clean.**

## What

Surfaces the v9.6-v9.8 multi-process state migration in the admin dashboard. Adds 5th sub-tab "🗄️ State Backend" to System section.

## Sub-tab contents

1. **Active backend** — backend name, health, multi-process indicator (3 metrics)
2. **Configuration** — A2Z_REDIS_URL value, backend class, window sizes, persist paths (table)
3. **State by domain** — circuit / retry / latency / alert / dedup key counts and samples (table)
4. **Live state verification** — 5 metric tiles showing circuit endpoints, retry totals, latency endpoints, alert counts, dedup topics; refresh button to re-read
5. **Migration map** — markdown table of v9.6-v9.8 migrations

System section grows from 4 to 5 sub-tabs (G4 7-tab cap; remaining headroom = 2).

## Honest acknowledgements

1. **No live Redis test by Claude** — UI compile-tested; user runs `streamlit run app.py` to verify rendering. With InMemoryBackend (default), all panels work; with RedisBackend the same code runs unchanged.
2. **Sample keys truncated to first 3** — for tables; full key list could be added later.
3. **Refresh button uses `st.rerun()`** — re-reads all backend state from scratch; mid-load freshness only.
4. **Live verification reads through public API** — `get_circuit_state()`, `get_retry_telemetry()` etc. — so UI sees same view as production callers.
5. **No write actions in this surface** — operators read state; resets are in their respective sub-tabs (System Health for circuits etc.).

## Next: v9.10

G114 audit gate `state_backend_abstraction_contract` locking:
- `utils/state_backend.py` exists and importable
- StateBackend ABC has all required methods
- InMemoryBackend implements all abstract methods
- circuit/retry/latency/alert/dedup all use the abstraction (no direct dict mutation)

Pushes 113 → 114 gates → 11-gate defense-in-depth perimeter (G104-G114).
