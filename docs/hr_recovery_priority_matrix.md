# HR Module — Recovery Priority Matrix

**Module key:** `hr` · **Organ role:** Human Capital & Regenerative System
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 88.7%

Per Module Revival Framework Phase 2 QA4. Prioritized recovery actions ranked by impact x effort matrix. Drives v10.46x+ rescue batch sequencing.

---

## Recovery items ranked

| Priority | Item | Impact | Effort | Why this rank |
|---|---|---|---|---|
| 1 (P0) | Module-specific audit gates (QA1 >=3) | High | Low | Locks doctrine, prevents drift |
| 2 (P0) | Cascade roles aligned with users.json (WF1) | High | Low | Unblocks Phase 4 |
| 3 (P1) | risk_assessment + remediation_roadmap docs | High | Medium | Closes Phase 2 QA |
| 4 (P1) | Cross-organ event_bus wiring | Medium | Low | Already done v10.459 |
| 5 (P2) | Stress test scenarios specific to this organ | Medium | Medium | Phase 8 deepening |
| 6 (P2) | Auto-actuals engine per organ | High | High | Future v10.46x batch |
| 7 (P3) | module_revival.md certification doc | Medium | Low | Final cert criterion #12 |
| 8 (P3) | capacity_plan.md per organ tier | Medium | Low | Final cert criterion #14 |

## Effort vs Impact matrix

```
Impact ↑      | Stress tests      | Cascade roles
  HIGH        | risk_assessment   | Audit gates
              |                   |
  MEDIUM      | capacity_plan     | event_bus
              |                   |
  LOW         | module_revival    | (nothing)
              +-------------------+-------------------
              HIGH effort         LOW effort →
```
