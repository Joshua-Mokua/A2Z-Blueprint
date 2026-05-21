# Credit Module — Synchronization Gaps

**Module key:** `credit` · **Organ role:** The heart of the bank
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 38.6%

Per Phase 1 Data Health: detect where data flows are out-of-sync or batch-delayed.

---

## Known sync gaps

- BSC scorecards: computed on demand, not real-time
- Actuals: refreshed only when actuals_*.xlsx uploaded
- Target cascade: changes propagate only on save, no event push

## Mitigations planned

- Build event bus so cascade saves publish updates downstream
- Schedule nightly BSC recompute job
- Auto-load actuals from CBS on app startup (already partial)
