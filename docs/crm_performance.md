# CRM & Customer Functions Module — Performance Bottleneck Inventory

**Module key:** `crm` · **Organ role:** Sensory & Interaction Systems (pipeline · customer 360 · propositions · campaigns · cross-sell · channels · NPS · behavioral intelligence · onboarding · cards · bancassurance · merchant acquiring)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

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
