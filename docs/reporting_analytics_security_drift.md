# Reporting & Analytics Module — Security Drift Scan

**Module key:** `reporting_analytics` · **Organ role:** Vital Signs Monitoring & Diagnostic Systems (reporting · analytics workbench · NLQ · anomaly · branch ranking · SBU drilldown · benchmarking · competitor intelligence)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Per Phase 8 Anti-Deterioration: detect security configuration drift over time (RBAC gates removed, audit_log calls dropped).

---

## Current state

- Pages with require_access: 9/9
- audit_log calls in engines: 0

## Drift indicators

- No baseline yet — establish in this batch
- Future audits should compare against this snapshot

## Recommended baselines

- RBAC coverage must not drop below current level
- audit_log count must not decrease
