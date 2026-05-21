# Reporting & Analytics Module — Security Gap Analysis

**Module key:** `reporting_analytics` · **Organ role:** Vital Signs Monitoring & Diagnostic Systems (reporting · analytics workbench · NLQ · anomaly · branch ranking · SBU drilldown · benchmarking · competitor intelligence)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Per Phase 1 Technical Health: security gaps and RBAC coverage.

---

## RBAC coverage

- Pages with `require_access`: **9/9 (100.0%)**
- Audit log calls: **24**

## Known security considerations

- Session-based authentication via Streamlit session_state
- Role checks at page entry via `require_access(roles_list)`
- Sensitive writes wrapped in audit_log for traceability

## Gaps

- ⚠️ No security_event monitoring in this module
- ⚠️ No failed-access tracking surfaced
