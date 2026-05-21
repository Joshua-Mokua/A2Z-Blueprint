# CHANGELOG v9.18 — Observability dashboard runbook + Grafana JSON

**Audit:** 115/115 PASS — **71st consecutive clean.**

## What

Operationalizes A2Z's existing telemetry into Prometheus + Grafana stack. Three artifacts ship in this batch:

1. **`docs/OBSERVABILITY_DASHBOARD_RUNBOOK.md`** (~367 lines)
   - Telemetry source inventory (5 public APIs)
   - Prometheus exporter pattern + skeleton example
   - Recommended metrics + thresholds (4 categories: circuit/retry/latency/alerts)
   - Sample alert rules with severity tiers
   - Operational triage flow
   - Multi-instance deployment guidance

2. **`scripts/observability/grafana_dashboard.json`** (~208 lines)
   - Importable Grafana 9.x+ dashboard
   - 7 panels: circuit state stat, consecutive failures timeseries, recovery rate timeseries, latency p95/p99 timeseries, unacked stat, alert volume bars
   - Color-coded thresholds matching runbook recommendations
   - Africa/Nairobi default timezone

3. **`scripts/observability/prometheus_alerts.yml`** (~120 lines)
   - 4 alert rule groups with 8 alerts total
   - Severity tiers (warning/critical) + team labels (a2z-ops)
   - Linked to runbook URLs in annotations
   - Recovery rate / latency p95+p99 / unacked alerts

## What v9.18 does NOT ship

1. **No actual Prometheus exporter** — runbook describes the pattern + skeleton; ops team writes the deployable script
2. **No Grafana installation guide** — assumes stack exists
3. **No bank-specific configuration** — generic recommendations
4. **No log aggregation guidance** — separate concern (structured logging is v10.x candidate)
5. **No OpenTelemetry tracing** — A2Z doesn't emit traces yet

## Honest acknowledgements

1. **Threshold values are starting points** — first 30 days production should refine.
2. **Grafana dashboard JSON tested with `json.loads()` only** — actual import into Grafana not exercised.
3. **No prometheus_exporter.py shipped** — deliberate scope choice (avoid Prometheus dependency); runbook §2.2 has skeleton.
4. **Multi-instance metric deduplication noted but not fully solved** — operators may need to scrape only one instance or use `topk(1)` to avoid duplicate values when running with shared Redis.
5. **Cost / cardinality not exhaustively analyzed** — current label cardinality is bounded (5 endpoints + 3 alert tiers); future per-customer labels would explode.
6. **Mobile/pager integration deferred** — runbook ends at Prometheus alerts; bank's existing on-call infra carries it forward.
7. **JSON dashboard hard-codes Africa/Nairobi** — operator changes per deployment region.

## Next: v9.19

Admin UI extensions surfacing v9.17 load test results + linking to the v9.18 observability stack from within the State Backend sub-tab.
