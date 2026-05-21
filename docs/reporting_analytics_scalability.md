# Reporting & Analytics Module — Scalability Limitations

**Module key:** `reporting_analytics` · **Organ role:** Vital Signs Monitoring & Diagnostic Systems (reporting · analytics workbench · NLQ · anomaly · branch ranking · SBU drilldown · benchmarking · competitor intelligence)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Per Phase 1 Technical Health: scalability limits and capacity planning.

---

## Current capacity assumptions

- 700K customers, 1.2M accounts, 35 branches, 232 RMs, 487 staff
- Streamlit single-instance deployment per environment
- PostgreSQL on managed instance (read replicas pending)

## Scaling concerns

- Single Streamlit instance: vertical-only scaling
- BSC computations done in-app: candidate for batch processing
- Large XLSX uploads cause memory pressure

## Horizontal scale plan

- Containerize (Dockerfile) and orchestrate via Kubernetes
- Move heavy computation to FastAPI workers behind queue
- Read replicas for BSC dashboards
