# Observability Dashboard Runbook — A2Z MIS 360

> **Status**: PRODUCTION OPERATIONAL DOCUMENT
> **Shipped in**: v9.18 (May 2026)
> **Companion to**: `utils/state_backend.py` (v9.6) + `docs/REDIS_DEPLOYMENT_RUNBOOK.md` (v9.12)
> **Audience**: DevOps engineer + bank IT operations + Joshua

---

## What this runbook is

Operationalizes A2Z's existing telemetry surfaces (`get_circuit_state()`, `get_retry_telemetry()`, `get_latency_state()`, `get_alert_history_stats()`, `get_dedup_stats()`) into a Prometheus + Grafana monitoring stack suitable for production deployment.

Pairs with:
- `scripts/observability/grafana_dashboard.json` (v9.18) — importable Grafana dashboard
- `scripts/observability/prometheus_alerts.yml` (v9.18) — alert rules
- The admin "🗄️ State Backend" sub-tab — operator-facing view of same metrics

---

## What this runbook is NOT

1. **Not a Prometheus/Grafana installation guide** — assumes the stack already exists or is being provisioned per bank IT standards
2. **Not bank-specific** — generic recommendations; bank's CISO + ops team adapt
3. **Not exhaustive** — covers the v8.x telemetry surfaces; future v10.x additions need dashboard updates
4. **Not load-testing methodology** — see `scripts/load_test_multi_instance.py` (v9.17)
5. **Not an SLA contract** — provides metrics + thresholds; SLA negotiation is commercial matter

---

## 1. Telemetry sources

A2Z exposes 5 telemetry surfaces via Python public APIs:

| API | Source batch | Purpose |
|---|---|---|
| `flexcube_adapter.get_circuit_state()` | v8.1+v8.17+v9.6 | Per-endpoint circuit breaker state |
| `flexcube_adapter.get_retry_telemetry()` | v8.19+v9.7 | Per-endpoint retry success/recovery rates |
| `flexcube_adapter.get_latency_state()` | v8.2+v8.24+v9.8 | Per-endpoint p50/p95/p99 latency |
| `smart_alerts.get_alert_history_stats()` | v8.25+v9.8 | Alert volume + acknowledgement rates |
| `event_bus.get_dedup_stats()` | v8.23+v9.8 | Per-topic publish/dedup rates |

These return Python dicts with structured fields. Production exposure requires a Prometheus exporter (next section).

---

## 2. Prometheus exporter pattern

A2Z does not ship a built-in Prometheus exporter (deliberate scope choice — would add Prometheus dependency to core platform). Instead, recommend a thin sidecar pattern:

### 2.1 Recommended exporter

`scripts/observability/prometheus_exporter.py` (operator-implemented; example shown in §2.2). Runs as a separate process on each Streamlit host, polling A2Z's public APIs and exposing metrics on `/metrics` HTTP endpoint.

### 2.2 Example exporter (skeleton)

```python
#!/usr/bin/env python3
"""Minimal Prometheus exporter for A2Z telemetry."""
from prometheus_client import start_http_server, Gauge, Counter
from utils import flexcube_adapter as fc
from utils import smart_alerts as sa
from utils import event_bus as eb
import time

# Define metrics
circuit_open = Gauge(
    'a2z_circuit_open',
    'Circuit breaker is_open per endpoint',
    ['endpoint'])
circuit_failures = Gauge(
    'a2z_circuit_consecutive_failures',
    'Circuit breaker consecutive_failures per endpoint',
    ['endpoint'])
retry_recovery = Gauge(
    'a2z_retry_recovery_rate_pct',
    'Retry recovery rate per endpoint',
    ['endpoint'])
latency_p95 = Gauge(
    'a2z_latency_p95_ms',
    'Latency p95 per endpoint',
    ['endpoint'])
latency_p99 = Gauge(
    'a2z_latency_p99_ms',
    'Latency p99 per endpoint',
    ['endpoint'])
alert_unacked = Gauge(
    'a2z_alerts_unacknowledged',
    'Unacknowledged alert count')
alert_total = Counter(
    'a2z_alerts_total',
    'Total alerts recorded',
    ['tier'])

def update_metrics():
    # Circuit
    cs = fc.get_circuit_state()
    for ep, state in cs.get('per_endpoint', {}).items():
        circuit_open.labels(endpoint=ep).set(
            1 if state['is_open'] else 0)
        circuit_failures.labels(endpoint=ep).set(
            state['consecutive_failures'])
    
    # Retry
    rt = fc.get_retry_telemetry()
    for ep, s in rt.get('per_endpoint', {}).items():
        if s.get('retry_recovery_rate_pct') is not None:
            retry_recovery.labels(endpoint=ep).set(
                s['retry_recovery_rate_pct'])
    
    # Latency
    ls = fc.get_latency_state()
    for ep, s in ls.get('endpoints', {}).items():
        latency_p95.labels(endpoint=ep).set(s['p95_ms'])
        latency_p99.labels(endpoint=ep).set(s['p99_ms'])
    
    # Alerts
    ahs = sa.get_alert_history_stats()
    alert_unacked.set(ahs['unacknowledged'])

if __name__ == '__main__':
    start_http_server(9100)
    while True:
        try:
            update_metrics()
        except Exception as e:
            print(f"Update failed: {e}")
        time.sleep(15)
```

Operator deploys this as a systemd service on each Streamlit host alongside the Streamlit process.

### 2.3 Prometheus scrape config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'a2z'
    scrape_interval: 15s
    static_configs:
      - targets:
          - 'streamlit-host-1:9100'
          - 'streamlit-host-2:9100'
          - 'streamlit-host-3:9100'
```

When using RedisBackend (v9.6+), all instances expose the same metrics (state is shared via Redis); when using InMemoryBackend, each instance has independent state and Prometheus aggregates them.

---

## 3. Recommended metrics + thresholds

### 3.1 Circuit breaker metrics

| Metric | Type | Threshold | Severity |
|---|---|---|---|
| `a2z_circuit_open{endpoint}` | Gauge (0/1) | == 1 for > 5 min | WARNING |
| `a2z_circuit_open{endpoint}` | Gauge (0/1) | == 1 for > 30 min | CRITICAL |
| `a2z_circuit_consecutive_failures{endpoint}` | Gauge | > 3 (close to threshold of 5) | WARNING |

**Why**: An open circuit means FLEXCUBE endpoint is being skipped; A2Z falls back to synthetic data. Prolonged outage erodes user trust.

### 3.2 Retry telemetry metrics

| Metric | Type | Threshold | Severity |
|---|---|---|---|
| `a2z_retry_recovery_rate_pct{endpoint}` | Gauge | < 50% over 1 hr | WARNING |
| `a2z_retry_recovery_rate_pct{endpoint}` | Gauge | < 25% over 1 hr | CRITICAL |
| `rate(a2z_retry_total{endpoint}[5m])` | Rate | > 10/sec | WARNING (spike) |

**Why**: Recovery rate < 50% means transient retries aren't recovering; the underlying issue may be persistent (not transient).

### 3.3 Latency metrics

| Metric | Type | Threshold | Severity |
|---|---|---|---|
| `a2z_latency_p95_ms{endpoint}` | Gauge | > 1000 ms | WARNING |
| `a2z_latency_p95_ms{endpoint}` | Gauge | > 5000 ms | CRITICAL |
| `a2z_latency_p99_ms{endpoint}` | Gauge | > 10000 ms (= 10s) | CRITICAL |

**Why**: A2Z's per-endpoint timeouts (v8.20) are 120-600 seconds depending on endpoint; p95 above 1 second suggests degraded FLEXCUBE backend.

### 3.4 Alert metrics

| Metric | Type | Threshold | Severity |
|---|---|---|---|
| `a2z_alerts_unacknowledged` | Gauge | > 10 sustained 1 hr | WARNING |
| `a2z_alerts_unacknowledged` | Gauge | > 50 sustained 1 hr | CRITICAL |
| `rate(a2z_alerts_total{tier="URGENT"}[15m])` | Rate | > 1/min | INFO |

**Why**: Mounting unacknowledged alerts indicate operators aren't responding; URGENT alert spike indicates infrastructure issue.

### 3.5 Backend health metrics (Redis-only)

If RedisBackend is in use:

| Metric | Source | Threshold |
|---|---|---|
| `redis_up` | redis_exporter | == 0 → CRITICAL |
| `redis_connected_clients` | redis_exporter | > 80% of maxclients → WARNING |
| `redis_used_memory` | redis_exporter | > 80% of maxmemory → WARNING |

See `docs/REDIS_DEPLOYMENT_RUNBOOK.md` §4 for full Redis monitoring.

---

## 4. Sample alert rules

`scripts/observability/prometheus_alerts.yml` (v9.18 ships this):

```yaml
groups:
  - name: a2z_circuit_breaker
    interval: 30s
    rules:
      - alert: A2ZCircuitOpenSustained
        expr: a2z_circuit_open == 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "A2Z circuit open for {{ $labels.endpoint }}"
          description: "Circuit has been open for 5+ minutes. Check FLEXCUBE health."
      
      - alert: A2ZCircuitOpenCritical
        expr: a2z_circuit_open == 1
        for: 30m
        labels:
          severity: critical
        annotations:
          summary: "A2Z circuit STILL open for {{ $labels.endpoint }}"
          description: "Circuit has been open for 30+ minutes. Likely persistent FLEXCUBE outage."
  
  - name: a2z_retry_telemetry
    interval: 30s
    rules:
      - alert: A2ZRecoveryRateLow
        expr: a2z_retry_recovery_rate_pct < 50
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Retry recovery rate below 50% for {{ $labels.endpoint }}"
  
  - name: a2z_latency
    interval: 30s
    rules:
      - alert: A2ZLatencyP95High
        expr: a2z_latency_p95_ms > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "p95 latency > 1s for {{ $labels.endpoint }}"
      
      - alert: A2ZLatencyP99Critical
        expr: a2z_latency_p99_ms > 10000
        for: 5m
        labels:
          severity: critical
  
  - name: a2z_alerts
    interval: 1m
    rules:
      - alert: A2ZAlertsUnackedHigh
        expr: a2z_alerts_unacknowledged > 10
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "10+ alerts unacknowledged for 1 hour"
          description: "Operator hasn't acknowledged alerts; check operator availability."
```

---

## 5. Grafana dashboard

`scripts/observability/grafana_dashboard.json` (v9.18 ships) — importable into Grafana 9.x+.

Panels:

1. **Circuit breaker overview** — per-endpoint open/closed state (red/green stat panels)
2. **Recovery rate** — line graph of `a2z_retry_recovery_rate_pct` per endpoint
3. **Latency percentiles** — heatmap of p50/p95/p99 per endpoint over time
4. **Alert volume** — bar chart of alerts by tier per hour
5. **Unacknowledged backlog** — single-stat with threshold colors
6. **Backend health** — Redis connection state, memory usage (when RedisBackend in use)

Import procedure:
1. Grafana → Dashboards → Import
2. Upload `scripts/observability/grafana_dashboard.json`
3. Select Prometheus datasource
4. Save

---

## 6. Operational procedures

### 6.1 Triage flow (alert fires)

```
ALERT: A2ZCircuitOpenSustained
    │
    ├─ Check Grafana A2Z dashboard
    │   - Which endpoint?
    │   - When did it open?
    │   - Is it just one or multiple?
    ├─ Check FLEXCUBE backend
    │   - Is FLEXCUBE itself reachable?
    │   - Check FLEXCUBE side metrics if available
    ├─ Check A2Z admin UI → System Health → FLEXCUBE
    │   - Detailed per-endpoint state
    │   - Recent retry telemetry
    ├─ If FLEXCUBE recovered:
    │   - Wait CIRCUIT_BREAKER_OPEN_SECONDS=60s for half-open probe
    │   - Or manually reset via admin UI / redis_admin.py
    └─ If sustained:
        - Acknowledge alert
        - Open incident with FLEXCUBE team
```

### 6.2 Dashboard upkeep

When v10.x adds new state surfaces:
1. Add new metric to Prometheus exporter (`scripts/observability/prometheus_exporter.py`)
2. Add new panel to Grafana dashboard JSON
3. Update this runbook

### 6.3 Multi-instance Streamlit + shared Redis topology

When running with RedisBackend, all Streamlit processes report identical metrics (since state is shared). Prometheus scrapes them all but the values match. This is correct: aggregation happens at the state layer, not at the Prometheus layer.

For deduplication in Grafana, either:
- Configure Prometheus to scrape only one Streamlit instance (preferred for redundancy)
- Use `topk(1)` in PromQL to pick a single sample

---

## 7. Honest acknowledgements

1. **No exporter shipped in this batch** — runbook describes the pattern; ops team writes the actual exporter (or uses an existing one). Future v9.x candidate: ship `scripts/observability/prometheus_exporter.py` as a reference implementation.
2. **Threshold values are starting points** — first 30 days of operation should refine based on actual baseline.
3. **Grafana dashboard JSON is a template** — operator likely customizes panels for bank's visual standards.
4. **No log aggregation guidance** — A2Z uses Python `print()` to stderr for diagnostic logging. Production deployment would use structured logging (e.g. `structlog` or `python-json-logger`); separate from this metrics-focused runbook.
5. **No tracing guidance** — A2Z doesn't emit OpenTelemetry traces; future v10.x candidate.
6. **Cost considerations not addressed** — Prometheus retention (30d default) for 5+ endpoint × 5+ metric streams = manageable; sustained high-cardinality (per-customer labels) would need Thanos/Cortex.
7. **No mobile alerting recommendation** — bank's existing pager / on-call infrastructure handles this; runbook ends at Prometheus alerts.

---

## 8. Companion artifacts

| Artifact | Status | Path |
|---|---|---|
| RedisBackend production config | ✅ v9.11 | `utils/state_backend.py` |
| Redis deployment runbook | ✅ v9.12 | `docs/REDIS_DEPLOYMENT_RUNBOOK.md` |
| Operations CLI | ✅ v9.13 | `scripts/redis_admin.py` |
| Production-ops admin UI | ✅ v9.14 | `pages/7_admin.py` State Backend sub-tab |
| Load test harness | ✅ v9.17 | `scripts/load_test_multi_instance.py` |
| **This runbook** | ✅ v9.18 | `docs/OBSERVABILITY_DASHBOARD_RUNBOOK.md` |
| Grafana dashboard JSON | ✅ v9.18 | `scripts/observability/grafana_dashboard.json` |
| Prometheus alert rules | ✅ v9.18 | `scripts/observability/prometheus_alerts.yml` |

---

*v9.18 — Observability Dashboard Runbook. Companion to v9.6-v9.17 architecture; the operational discipline that makes telemetry visible to operators in production.*
