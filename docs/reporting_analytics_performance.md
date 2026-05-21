# Reporting & Analytics Module — Performance Bottleneck Inventory

**Module key:** `reporting_analytics` · **Organ role:** Vital Signs Monitoring & Diagnostic Systems (reporting · analytics workbench · NLQ · anomaly · branch ranking · SBU drilldown · benchmarking · competitor intelligence)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Per Phase 1 Technical Health: performance bottlenecks inventory. Identifies known/suspected bottlenecks and remediation priorities.

---

## Suspected bottlenecks

| Source | Pattern | Risk |
|---|---|---|
| Pages | JSON file reads in render path | Slow on large files; cache |
| Pages | DataFrame .iterrows() | O(n) Python loop; vectorize |
| Caching | No st.cache_data hints | Recomputes every rerun |

## Mitigations

- Add `@st.cache_data(ttl=60)` to expensive computations
- Move large file reads behind a cached helper
- Vectorize DataFrame operations
- Index PostgreSQL tables on common filters (branch_id, period, role)
