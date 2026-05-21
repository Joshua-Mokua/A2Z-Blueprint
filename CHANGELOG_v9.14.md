# CHANGELOG v9.14 — Production-ops admin UI extensions

**Audit:** 114/114 PASS — **67th consecutive clean.**

## What

Extends the v9.9 "🗄️ State Backend" admin sub-tab with three v9.14 production-ops surfaces:

1. **🔌 Connection pool configuration** (collapsible expander)
   - Visible only when RedisBackend is active
   - Calls `RedisBackend.get_connection_config()` (v9.11)
   - Shows masked URL, key prefix, max connections, timeouts, TLS state, auth state
   - Caption notes the env-var tunables

2. **⚠️ Operator destructive actions** (collapsible expander)
   - 5 domain-specific clear buttons: circuit / retry / latency / dedup / alert_history
   - Each button requires explicit confirmation step (button → confirm step → action)
   - Per-domain description explains operational impact
   - Success/failure feedback inline

3. **📋 Command-line operations** (collapsible expander)
   - Reference card for v9.13 `scripts/redis_admin.py` CLI commands
   - Bash examples for health-check / config / inventory / live-state / verify-state / snapshot / restore / clear-domain
   - Pointer to `docs/REDIS_DEPLOYMENT_RUNBOOK.md` for deployment context

## Layout

The State Backend sub-tab now has 6 sections (v9.9 + v9.14 combined):

| Section | Source batch | Type |
|---|---|---|
| Active backend (3 metrics) | v9.9 | Read-only |
| Configuration table | v9.9 | Read-only |
| State by domain table | v9.9 | Read-only |
| Live state verification (5 metric tiles) | v9.9 | Read-only |
| Migration map markdown | v9.9 | Read-only |
| **Connection pool configuration** | **v9.14** | Read-only |
| **Operator destructive actions** | **v9.14** | Destructive (gated) |
| **Command-line operations reference** | **v9.14** | Read-only |

## Honest acknowledgements

1. **No live Redis test** — UI compile-tested only. With InMemoryBackend, the connection pool config expander is hidden (correct behavior).
2. **Confirmation flow uses `st.session_state`** — works for typical Streamlit but on full page rerun the confirm state could reset; acceptable for destructive ops where re-confirmation is fine.
3. **CLI examples panel is static markdown** — doesn't dynamically generate; if v9.13 commands change in v9.x+, this panel needs sync.
4. **5 destructive clear buttons in 2-column layout** — operator scrolls to see all 5; future could group by criticality (operational vs investigative).
5. **No bulk export from UI** — for full backups operators use `redis_admin.py snapshot` CLI; UI stays focused on live operations.
6. **Connection-pool stats (live in-flight count, queue depth) not surfaced** — redis-py exposes `pool._available_connections` but it's internal API; not stable enough to surface as production metric. Server-side `INFO clients` gives equivalent visibility.

## Next: v9.15

G115 audit gate `redis_production_artifacts_present` — locks the v9.11 production-config + v9.12 deployment runbook + v9.13 CLI as permanent invariants. Closes the v9.11-v9.15 5-batch arc with the **12-gate defense-in-depth perimeter** (G104-G115).
