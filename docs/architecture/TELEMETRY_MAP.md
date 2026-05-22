# A2Z Blueprint MIS 360 — Telemetry Map

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md`)
**Status:** `canonical_with_transitional_subareas`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 4)
**Last updated:** 2026-05-22
**Owner:** Compliance / Audit + Platform / Observability
**Authoritative source:** `utils/api.py::_audit` (line 170) + observability module family
**Machine-readable equivalent:** `TELEMETRY_MAP.json`

---

## Purpose

This document is the canonical map of every telemetry signal the system emits — audit events, observability metrics, anomaly detections, alerts, notifications, and cross-organ events. For each it declares:

- **Emitter** — which module produces it
- **Sink** — where it goes (file, DB, queue, dashboard, downstream)
- **Schema** — the event/metric shape
- **Consumers** — who reads it
- **Retention** — how long it persists, whether replayable

Per Article VIII of `SYSTEM_CONSTITUTION.md`: every state change is audited; observability is a first-class concern; no silent operations.

---

## Doctrine

**T1 — Every state change emits a signal.** State changes without telemetry are violations of `gate_audit_coverage`.

**T2 — One canonical emitter per signal type.** API audit events have **one** emitter (`utils/api.py::_audit`); engine events have **one** event bus (`utils/event_bus.py`). Multiple emitters per signal type fragment the audit trail.

**T3 — Telemetry is the system's nervous system.** Per the body metaphor: signals flow from organs (sensors) through buses (nerves) to sinks (memory, dashboards). Loss of any signal degrades situational awareness.

**T4 — Signals must be queryable and replayable.** Append-only sinks allow reconstruction. Replay engines (`utils/workflow_replay.py`) consume sinks to re-derive state. This is regulator-grade audit capability.

**T5 — Sensitive signals are gitignored.** Audit logs, observability metrics, and anything containing user-identifying actions stays out of version control. PII protection per `DATA_DICTIONARY.md::DD5`.

---

## Signal categories

The system produces signals in 5 categories:

| Category | Examples | Emitter | Sink |
|---|---|---|---|
| 1. **API audit events** | `API_LOGIN_SUCCESS`, `API_BSC_SUMMARY` | `utils/api.py::_audit` | `data/audit_log.json` + `data/audit_trail.jsonl` |
| 2. **Cross-organ events** | `bsc.score.computed`, `pipeline.deal.won` | Engines via `utils/event_bus.py` | Subscribers; replayable via `workflow_replay` |
| 3. **Observability metrics** | latency, error rate, gauge values | `utils/observability_monitoring.py`, `utils/api_telemetry.py` | `data/observability_metrics.json` + dashboards |
| 4. **Anomaly detections** | unusual transactions, behavior patterns | `utils/anomaly_observer.py`, `utils/analytics_anomaly_detection.py`, `utils/behavioral_anomaly_detection.py` | Alert routing |
| 5. **Alerts & notifications** | wellness alerts, risk threshold breaches, smart alerts | `utils/notification_broadcaster.py`, `utils/smart_alerts.py`, `utils/nudge_engine.py` | Recipients (email, in-app, mobile) |

---

## Category 1 — API audit events

### Canonical emitter

`utils/api.py::_audit(action: str, user: dict, detail: str = "") -> None` at line 170 (per OI-7 verification output).

```python
def _audit(action: str, user: dict, detail: str = "") -> None:
    """Single canonical emitter for API audit events. Writes to data/audit_log.json."""
    # See utils/api.py:170 for implementation
```

### Sinks

1. **`data/audit_log.json`** — append-only structured JSON array; primary sink
2. **`data/audit_trail.jsonl`** — line-delimited JSON; high-volume-friendly variant
3. (Optional / future) PostgreSQL event table — per `gate_pg_*` migration tracking

Both sinks are **gitignored** per `DATA_DICTIONARY.md`.

### Event naming convention

`API_<DOMAIN>_<ACTION>[_<MODIFIER>]`

Where:
- `<DOMAIN>` ∈ {LOGIN, LOGOUT, BSC, PIPELINE, CREDIT, AML, USERS, DASHBOARD, CACHE, INTEGRATION, ROLE_WEIGHTS, KPI_DEDUP, BACKUP_RETENTION, TEST_CLEANUP, BSC_PILLAR, BSC_LIBRARY, BSC_COMPLETENESS, BSC_WEIGHTS, BSC_CODES, ADMIN_VALIDATION, CASCADE_360, HARMONIZE, ONBOARDING, EXIT_RISK, HR_AUDIT, PEER_LEARNING, COACHING, PREDICT, GAMIFICATION, EFFICIENCY, WELLNESS, HR_ACTUALS, VITALS}
- `<ACTION>` ∈ {SUCCESS, FAILED, DENIED, SUMMARY, READ, WRITE, MIGRATE, REPAIR, ARCHIVE, RUN, ALL, STAGE, ...}
- `<MODIFIER>` optional, qualifies further

### Complete event vocabulary (post v10.497 P1.3)

#### Auth (3 events)

| Event | Trigger | Detail field example |
|---|---|---|
| `API_LOGIN_SUCCESS` | Successful `/api/auth/login` | `username, role, mode (cookie/bearer)` |
| `API_LOGIN_FAILED` | Failed `/api/auth/login` | `username (if provided), reason` |
| `API_LOGOUT_SUCCESS` | Successful `/api/auth/logout` | `username, jti revoked` |

#### Resource summaries (9 events)

| Event | Trigger |
|---|---|
| `API_BSC_SUMMARY` | `GET /api/bsc/summary` |
| `API_BSC_STAFF` | `GET /api/bsc/staff/{username}` (success) |
| `API_BSC_STAFF_DENIED` | `GET /api/bsc/staff/{username}` (scope denial) |
| `API_PIPELINE_SUMMARY` | `GET /api/pipeline/summary` |
| `API_PIPELINE_DEALS` | `GET /api/pipeline/deals` |
| `API_CREDIT_SUMMARY` | `GET /api/credit/summary` |
| `API_CREDIT_WATCHLIST` | `GET /api/credit/watchlist` |
| `API_AML_SUMMARY` | `GET /api/aml/summary` |
| `API_USERS_SUMMARY` | `GET /api/users/summary` |

#### Dashboard + cache (3 events)

| Event | Trigger |
|---|---|
| `API_DASHBOARD_MD` | `GET /api/dashboard/md` |
| `API_CACHE_CLEAR` | `POST /api/cache/clear` |
| `API_CACHE_STATS` | `GET /api/cache/stats` |

#### Integration (6 events)

| Event | Trigger |
|---|---|
| `API_INTEGRATION_RULES` | `GET /api/integration/rules` |
| `API_INTEGRATION_ACTUALS` | `GET /api/integration/actuals/{period}` |
| `API_INTEGRATION_RESOLUTION_METRICS` | `GET /api/integration/resolution-metrics` |
| `API_INTEGRATION_RUN_PERIOD` | `POST /api/integration/run-period` |
| `API_INTEGRATION_COVERAGE` | `GET /api/integration/coverage` |
| `API_INTEGRATION_RULE_EXPLAIN` | `GET /api/integration/rule-explain/{kpi_id}` |

#### v1 admin governance writes (12 events)

| Event | Trigger |
|---|---|
| `API_ROLE_WEIGHTS_MIGRATE` | `POST /api/v1/role-weights/migrate` |
| `API_KPI_DEDUP_MIGRATE` | `POST /api/v1/kpi-dedup/migrate` |
| `API_BACKUP_RETENTION_APPLY` | `POST /api/v1/backup-retention/apply` |
| `API_TEST_CLEANUP_ARCHIVE` | `POST /api/v1/test-cleanup/archive` |
| `API_BSC_PILLAR_MIGRATE` | `POST /api/v1/bsc-pillar/migrate` |
| `API_BSC_LIBRARY_REGISTER` | `POST /api/v1/bsc-library/register` |
| `API_BSC_COMPLETENESS_REPAIR` | `POST /api/v1/bsc-completeness/repair` |
| `API_BSC_WEIGHTS_RENORMALIZE` | `POST /api/v1/bsc-weights/renormalize` |
| `API_BSC_CODES_FIX` | `POST /api/v1/bsc-codes/fix` |
| `API_ADMIN_VALIDATION_LEGACY_ALIASES` | `POST /api/v1/admin-validation/legacy-aliases` |
| `API_HARMONIZE_ALL` | `POST /api/v1/harmonize/all` |
| `API_HARMONIZE_STAGE` | `POST /api/v1/harmonize/stage/{stage}` |

#### HR write events (3 events, expected)

| Event | Trigger |
|---|---|
| `API_ONBOARDING_SIMULATE` | `POST /api/v1/onboarding/simulate` (OI-7 confirmed canonical) |
| `API_PEER_LEARNING_GENERATE` | `POST /api/v1/peer-learning/generate-cards` (OI-7 confirmed canonical) |
| `API_GAMIFICATION_EVALUATE` | `POST /api/v1/gamification/evaluate/{staff_code}` |

### Total API audit event count

**36 distinct event types** documented above. Additional events may exist in router modules (cascade, capacity feedback, branding, +17 unverified routers per OI-14 follow-up). Wave 4 amendment will enumerate router-emitted events.

### Audit event schema

```json
{
  "timestamp": "2026-05-22T13:15:30.123Z",
  "action": "API_BSC_SUMMARY",
  "username": "william001",
  "role": "Chief Executive & Managing Director",
  "detail": "summary requested for period 2026-Q1",
  "endpoint": "/api/bsc/summary",
  "method": "GET",
  "status_code": 200,
  "duration_ms": 42
}
```

(**OI-31** — exact schema may differ; needs verification from actual `_audit()` body. The shape above is the **target canonical schema**.)

### Audit gate enforcement

`gate_audit_coverage` (scripts/audit.py:251) verifies:
- Every state-changing endpoint (POST/PUT/PATCH/DELETE) has at least one `_audit()` call in its body
- The audit event name matches the endpoint domain (e.g. `/api/cache/clear` emits `API_CACHE_CLEAR`)

Severity: `CRITICAL`. A missing audit on a state-changing endpoint blocks certification.

---

## Category 2 — Cross-organ events (event bus)

### Canonical interface

`utils/event_bus.py` — single-process pub/sub
`utils/cross_organ_event_bus.py` — cross-organ coordination with persistence

(**OI-19 from Wave 3** — API surface still pending body verification. The contract below is the **declared canonical target**; actual signatures need confirmation in Stage C.)

### Expected publisher API

```python
from utils.event_bus import publish

publish(
    event_type="bsc.score.computed",
    payload={"staff_code": "300001", "score": 0.87, "period": "2026-Q1"},
    source_module="utils.bsc_score_computation"
)
```

### Expected subscriber API

```python
from utils.event_bus import subscribe

@subscribe("bsc.score.computed")
def handle_bsc_score(event):
    # event has: event_type, timestamp, actor (if known), payload, source_module
    ...
```

### Event categories (canonical namespace)

| Namespace | Owner organ | Purpose |
|---|---|---|
| `auth.*` | UserManager / auth modules | `auth.login.success`, `auth.login.failed`, `auth.logout`, `auth.token.revoked` |
| `bsc.*` | BSC engines | `bsc.score.computed`, `bsc.target.cascaded`, `bsc.actual.updated`, `bsc.weight.renormalized` |
| `cascade.*` | CascadeManager + cascade engines | `cascade.target.locked`, `cascade.harmonize.run` |
| `pipeline.*` | PipelineManager | `pipeline.deal.created`, `pipeline.deal.moved`, `pipeline.deal.won`, `pipeline.deal.lost` |
| `credit.*` | CreditAdminManager | `credit.application.submitted`, `credit.application.approved`, `credit.ews.flagged` |
| `risk.*` | Risk engines | `risk.threshold.breached`, `risk.limit.warning`, `risk.stress.completed` |
| `compliance.*` | ComplianceManager + screening | `compliance.case.escalated`, `compliance.aml.flagged`, `compliance.sanctions.hit` |
| `hr.*` | HRManager | `hr.staff.registered`, `hr.staff.transferred`, `hr.staff.terminated`, `hr.leave.requested` |
| `treasury.*` | TreasuryManager | `treasury.position.changed`, `treasury.limit.warning` |
| `cbs.*` | CBS modules | `cbs.baseline.refreshed`, `cbs.transaction.streamed`, `cbs.account.tagged` |
| `api.*` | API transports | `api.endpoint.called`, `api.audit.emitted` |
| `vitals.*` | Health monitoring | `vitals.organ.degraded`, `vitals.regression.detected`, `vitals.certification.advanced` |
| `mlops.*` | ML governance | `mlops.model.deployed`, `mlops.prediction.adjudicated`, `mlops.retrain.scheduled`, `mlops.drift.detected` |
| `system.*` | System-wide | `system.batch.started`, `system.batch.completed`, `system.gate.failed` |

### Publication rules (carried forward from `CANONICAL_DEPENDENCY_MAP.md`)

1. Only Managers and engines may publish events
2. Transports MUST NOT publish events directly (they call Managers, which publish)
3. Events MUST include `event_type`, `timestamp`, `actor` (if known), `payload`, `source_module`
4. Subscribers MUST be idempotent (events may be replayed)

### Replayability

`utils/workflow_replay.py` consumes the event stream to reconstruct state. This means:

- Event payloads must be self-contained (no live references to mutable state)
- Subscribers must produce the same effect when replayed
- Replay is the canonical disaster-recovery mechanism for derived state

---

## Category 3 — Observability metrics

### Canonical interfaces

| Module | Purpose |
|---|---|
| `utils/observability_monitoring.py` | Metrics collection + aggregation |
| `utils/api_telemetry.py` | API-specific latency, throughput, errors |
| `utils/it_observability.py` | Infrastructure-level observability |

### Sinks

- `data/observability_metrics.json` — short-lived rolling metrics
- (Future) external observability platform — Datadog/New Relic/Grafana via OTLP

### Metric categories

| Category | Examples |
|---|---|
| **API performance** | `api.endpoint.duration_ms` (per route, percentiles), `api.endpoint.error_rate`, `api.cors.rejected` |
| **Engine performance** | `engine.bsc.score_compute.duration_ms`, `engine.cascade.walk.duration_ms` |
| **Data freshness** | `data.kpi_library.last_updated`, `data.cbs_baseline.staleness_hours` |
| **Audit health** | `audit.gate.pass_rate`, `audit.gate.failures.count` |
| **Org health (vitals)** | `vitals.organ.<name>.status`, `vitals.regression.count` |
| **ML drift** | `mlops.model.<id>.accuracy_drift`, `mlops.adjudication.queue_depth` |

### Performance thresholds (`gate_performance_api_latency`)

Per audit gate at scripts/audit.py:2897:
- p50 latency target per endpoint declared
- p95 latency target declared
- p99 latency target declared
- Threshold breaches escalate severity

(**OI-32** — Document exact thresholds in Stage C amendment.)

---

## Category 4 — Anomaly detections

### Canonical interfaces

| Module | Purpose |
|---|---|
| `utils/anomaly_observer.py` | General anomaly observer |
| `utils/analytics_anomaly_detection.py` | Statistical anomaly detection |
| `utils/behavioral_anomaly_detection.py` | Behavioral pattern anomalies |
| `utils/revenue_anomaly_patterns.py` | Revenue anomaly patterns |

### Sinks

- Events published to `event_bus` namespace `anomaly.*`
- Alert routing via `utils/command_centre_alert_routing.py`

### Anomaly types

| Type | Detector | Example trigger |
|---|---|---|
| Transaction anomaly | `anomaly_observer` | Unusual transaction pattern for customer |
| AML anomaly | `aml_monitoring` + behavioral | Velocity, structuring, smurfing |
| Revenue anomaly | `revenue_anomaly_patterns` | Sudden revenue drop in a branch/SBU |
| Performance anomaly | `behavioral_anomaly_detection` | Staff productivity outside expected range |
| Risk threshold | Risk engines | VaR breach, limit utilization >100% |

---

## Category 5 — Alerts & notifications

### Canonical interfaces

| Module | Purpose |
|---|---|
| `utils/notification_broadcaster.py` | Broadcast notifications |
| `utils/notifications.py` | Notification helpers |
| `utils/smart_alerts.py` | Smart alert routing |
| `utils/smart_alerts_i18n.py` | Internationalization |
| `utils/nudge_engine.py` | Behavioral nudges |
| `utils/command_centre_alert_routing.py` | Command centre alert routing |
| `utils/command_centre_crisis.py` | Crisis-level alerts |
| `utils/command_centre_stakeholder_comms.py` | Stakeholder communication |

### Notification channels

| Channel | Implementation | Use case |
|---|---|---|
| Email | `utils/core.py` email helpers (lines 71-280: `send_milestone_alert_email`, `send_structural_delay_email`, `send_start_alert_email`, `send_welcome_email`) | Async escalations, welcome emails |
| In-app | Streamlit toasts, React sonner | Real-time UX feedback |
| WebSocket | `utils/websocket_manager.py` | Push to active sessions |
| Mobile | `utils/mobile_app_tracking.py`, `utils/command_centre_mobile_board.py` | Mobile devices |

### Wellness alert special handling

`utils/wellness.py` + `/api/v1/wellness/alerts/{manager_code}` requires special ethical handling per session memory. Wellness alerts:

- Go only to the staff's direct manager
- Never include speculative diagnoses
- Direct manager receives suggestions, not directives
- Subject staff has visibility into their own assessment

This is enforced by handler-level scope checks (per `RBAC_MATRIX.md`).

---

## Compliance & regulatory audit trail

### Canonical chain (regulator-grade)

```
Action happens
  ↓
_audit() called by transport → data/audit_log.json
  ↓
Engine publishes event → event_bus → subscribers + persistence
  ↓
Subscribers may write derived audit records (e.g. compliance case)
  ↓
audit_trail_certification consolidates → certification ledger
  ↓
gate_audit_trail_composer_wired verifies coverage
  ↓
Regulator reviews via /api/v1/vitals/* or compliance dashboards
```

### Key audit modules

| Module | Role |
|---|---|
| `utils/audit_log.py` | Audit log writer (lower-level than `_audit`) |
| `utils/audit_core.py` | Core audit helpers |
| `utils/audit_universe.py` | Audit universe definitions |
| `utils/audit_trail_certification.py` | Trail certification (canonical) |
| `utils/audit_trail_cert.py` | Trail cert (potential duplicate per OI-18) |
| `utils/audit_reporting.py` | Audit reporting |
| `utils/audit_dashboards_portal.py` | Audit dashboards |
| `utils/cbk_regulatory_reporting.py` | Central Bank of Kenya regulatory submissions |
| `utils/examiner_reporting.py` | Examiner-facing reports |

---

## Retention & purging

| Signal type | Retention | Mechanism |
|---|---|---|
| API audit events | Indefinite (append-only) | `data/audit_log.json` + `audit_trail.jsonl` |
| Cross-organ events | Indefinite (replayable) | event bus persistence |
| Observability metrics | Rolling window (~7-30 days) | Auto-purge in `observability_monitoring` |
| Anomaly detections | Indefinite (compliance) | Event bus + downstream sinks |
| Alerts | 90 days default | Notification broadcaster |
| JWT blocklist entries | Until natural token expiry | `auth_jwt.py` auto-prune |
| Backup directories | 3 most recent | `/api/v1/backup-retention/apply` |

---

## Privacy & PII in telemetry

Per `DATA_DICTIONARY.md::DD5` and `SYSTEM_CONSTITUTION.md::§5.5`:

- Username and role in audit events: OK
- Customer CIF or account number in audit events: OK (system context required for regulator)
- Customer PII (name, email, phone, ID number) in audit events: forbidden
- Staff PII beyond username: forbidden
- Passwords: NEVER (audit emits username, not credentials)
- JWT contents in audit detail: forbidden (use `jti` instead)

`gate_password_safety` (scripts/audit.py:741) enforces.

---

## Stage C gates planned

| Gate | Purpose | Severity |
|---|---|---|
| `gate_telemetry_event_naming` | Verify all `_audit()` event names match canonical vocabulary | HIGH |
| `gate_event_bus_publisher_purity` | Verify transports don't publish events directly | CRITICAL |
| `gate_event_bus_subscriber_idempotent` | Verify subscribers are decorated as idempotent | MEDIUM |
| `gate_observability_freshness` | Verify metrics are within freshness window | MEDIUM |
| `gate_audit_event_schema_compliance` | Verify audit events conform to canonical schema | HIGH |

---

## Open items

| ID | Title | Resolution wave |
|---|---|---|
| OI-19 | event_bus + cross_organ_event_bus actual API surface verification | Stage C |
| OI-31 | Audit event schema verification (compare to declared canonical) | Stage C |
| OI-32 | Document exact performance latency thresholds per endpoint | Stage C amendment |
| OI-33 | Enumerate audit events emitted by mounted routers (per OI-14 follow-up) | Wave 4 amendment |
| OI-34 | Event namespace registry (canonical list of allowed namespaces) | Stage C |

---

**End of TELEMETRY_MAP.md**
