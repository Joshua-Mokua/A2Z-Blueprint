# CHANGELOG v9.19 — Admin UI panels for load test + observability

**Audit:** 115/115 PASS — **72nd consecutive clean.**

## What

Extends the v9.9+v9.14 "🗄️ State Backend" admin sub-tab with two v9.19 production-validation panels:

1. **🧪 Recent load test results** (collapsible expander)
   - Auto-discovers `loadtest*.json` files in `load_test_results/` and `/tmp/`
   - Selectbox to pick which run to display
   - 4 metric tiles: total calls / success rate / throughput / latency p95
   - Per-endpoint summary table
   - Empty state with command-line instructions

2. **📊 Observability stack (Prometheus + Grafana)** (collapsible expander)
   - 3-row table showing v9.18 artifact status (runbook + dashboard JSON + alerts YAML)
   - File sizes + presence indicators
   - Markdown documentation of exposed Prometheus metrics
   - Pointer to `docs/OBSERVABILITY_DASHBOARD_RUNBOOK.md` §2.2

## Sub-tab structure (now 10 sections)

The State Backend sub-tab grew across v9.9 → v9.14 → v9.19:

| Section | Source batch |
|---|---|
| Active backend (3 metrics) | v9.9 |
| Configuration table | v9.9 |
| State by domain table | v9.9 |
| Live state verification (5 metric tiles) | v9.9 |
| Migration map markdown | v9.9 |
| Connection pool configuration | v9.14 |
| Operator destructive actions | v9.14 |
| Command-line operations reference | v9.14 |
| **Recent load test results** | **v9.19** |
| **Observability stack** | **v9.19** |

## Honest acknowledgements

1. **Load test result discovery is heuristic** — searches `load_test_results/` then `/tmp/` for `loadtest*.json` glob; bank-specific log paths may need adjustment.
2. **Most-recent-5 cap** — for usability; older results require CLI access.
3. **No load test trigger from UI** — operator runs `scripts/load_test_multi_instance.py` from terminal; UI is read-only viewer. Triggering load tests from a production admin UI is intentionally not surfaced (safety).
4. **Observability stack panel is informational** — verifies artifacts exist with sizes; doesn't actually invoke Prometheus or Grafana from UI.
5. **No real-time metric scraping** — admin UI shows current state via Python APIs; for time-series + history, operators use the Grafana dashboard.

## Next: v9.20

G116 audit gate `final_unification_artifacts_present` — locks v9.16 event-bus migration + v9.17 load test + v9.18 observability artifacts. Closes the v9.16-v9.20 final-unification arc with the **13-gate defense-in-depth perimeter** (G104-G116).
