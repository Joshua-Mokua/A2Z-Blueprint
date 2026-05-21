# Enterprise Capacity & Horizontal Scale Plan — v10.471

Per Joshua doctrine Phase 8: 'The objective is not temporary recovery.
The objective is permanent operational vitality.'

## Current Capacity Footprint

| Resource | Current | Headroom | 2× | 5× |
|---|---|---|---|---|
| Active staff | 1,438 | Yes | 2,876 | 7,190 |
| Customers | 700K | Yes | 1.4M | 3.5M |
| Accounts | 1.19M | Yes | 2.38M | 5.96M |
| Branches | 35 | Yes | 70 | 175 |
| Cascade entries | 5,069 | Yes | 10K | 25K |
| BSC entries | 2,948 | Yes | 6K | 15K |
| Audit log entries | ~5K | Yes | 10K | 25K |
| Daily transactions | 50K | Yes | 100K | 250K |

## Horizontal Scale Strategy

### Stateless Scaling
- All engines decoupled from Streamlit (zero `import streamlit as st` in `utils/*`)
- Engines stateless — every call carries its own context
- API surface (`utils/api.py`) exposes 105 engines for horizontal scaling

### Containerization (Phase 3 SM5)
- Multi-stage Python 3.11 Dockerfile
- Healthcheck on `/_stcore/health` every 30s
- Streamlit on 8501, FastAPI on 8000
- Override CMD to run uvicorn for pure-API deployment

### Caching Strategy
- `@st.cache_data` on hot reads (BSC scoring, cascade tree)
- `@st.cache_resource` on Flexcube adapter (one connection per worker)
- TTL: 5min for actuals; 1min for cascade; 0 for audit log

### Database Scaling Plan
- Current: JSON + Excel filesystem (dev/demo)
- Phase 1 migration: PostgreSQL with `utils.db` abstraction layer
- Phase 2 scale: Read replicas for reporting/analytics
- Phase 3 scale: Connection pooling via PgBouncer

### Worker Topology (production)
- 4× Streamlit workers behind Nginx for UI
- 8× FastAPI workers behind ALB for API
- 2× scheduled job workers (cascade refresh, BSC actuals)
- 1× audit log writer (single-writer for append safety)

## Auto-Scaling Triggers

| Metric | Threshold | Action |
|---|---|---|
| CPU utilization | >70% for 5min | scale_out +1 worker |
| Memory pressure | >80% for 5min | scale_out +1 worker |
| Request queue depth | >50 for 2min | scale_out +2 workers |
| Idle workers | >30% for 15min | scale_in -1 worker |

## Anti-Deterioration

- G330 catches silent organ-health degradation
- G331 catches honest-measurement drift
- G354 catches BSC/actuals/chief coverage regression
- G355 catches structural-integrity regression
- G356 catches cert-regression
- 164 consecutive zero-drift batches (G162 baseline)
