# Changelog — v10.389 Pillar Shadow Weights Removed (Body Sheds Dead Weight)

**Date:** 2026-05-13
**Phase:** Phase C continues — Tier-1 fix sequence
**Phase 4 arc count:** seventy-third arc — third Phase C execution batch
**Audit:** G274 added
**Tests:** 9/9 PASSED in `test_v10389_pillar_shadow_removed.py`
**Verifier:** 475/475 checks pass on clean extract
**G162 baseline:** 4022 (82 consecutive zero-drift batches)
**Master prompt:** v4.31 → v4.32 (lockstep — 33 consecutive batches)

---

## Your direction

> "continue" — proceed with v10.389 per Phase C Tier-1 sequence

## What was removed

Inside `data/kpi_library.json::pillars[]` — the `weight` field on each of the 4 pillar entries.

### Before v10.389
```json
"pillars": [
  {"id": "Financial",              "name": "Financial Performance",   "weight": 0.4,  "color": "#0F6E56"},
  {"id": "Customer Focus",         "name": "Customer Focus",          "weight": 0.25, "color": "#185FA5"},
  {"id": "Operational Excellence", "name": "Operational Excellence",  "weight": 0.25, "color": "#854F0B"},
  {"id": "People & Learning",      "name": "People & Learning",       "weight": 0.1,  "color": "#3C3489"}
]
```

### After v10.389
```json
"pillars": [
  {"id": "Financial",              "name": "Financial Performance",   "color": "#0F6E56"},
  {"id": "Customer Focus",         "name": "Customer Focus",          "color": "#185FA5"},
  {"id": "Operational Excellence", "name": "Operational Excellence",  "color": "#854F0B"},
  {"id": "People & Learning",      "name": "People & Learning",       "color": "#3C3489"}
]
```

## Why this mattered

The shadow `weight` values (40/25/25/10) DIFFERED from the canonical `pillar_weights` dict (68/14/6/12). Two parallel values for the same concept inside the same file. Anyone inspecting the library JSON saw inconsistent answers depending on which field they read.

Health check confirms the shadow is gone:

```python
>>> health_check()
{
  'canonical_weights': {Financial: 0.68, ...},
  'shadow_pillars_field': False,     # ← flipped from True ✓
  'orphan_detected': {Financial: 0.40, ...},  # still present, v10.390 removes
  ...
}
```

## Discovered along the way — Finding N7 (NOT bundled)

While verifying consumers, found a **pre-existing bug**:

```python
# utils/core.py:1467
def get_active_kpis() -> list:
    for pillar, kpis in lib.get("pillars", DEFAULT_KPI_LIBRARY).items():
        ...
```

`lib.get("pillars")` returns a **list** (the actual data shape). `.items()` is called on it → **AttributeError**.

This bug has existed in `utils/core.py` for a long time. v10.385 body diagnosis surveyed consumers by grep, not by execution, so it didn't catch this. v10.389 caught it through manual verification.

**Per Rule N2 (single concern): v10.389 logs Finding N7 but does NOT fix the bug.** That's a separate batch.

### Finding N7 added to body diagnosis backlog

| Finding | Description | Severity | Suggested fix |
|---|---|---|---|
| **N7** | `get_active_kpis()` AttributeError on pillars list | MEDIUM | v10.392 or earlier |

## Verified outcome

| Metric | Value |
|---|---|
| Shadow weight field removed from all 4 pillar entries | ✅ |
| Structural fields (id, name, color) preserved | ✅ |
| Canonical pillar_weights dict unchanged | ✅ |
| Backup preserved at `data/_v10389_backups/kpi_library.json.before` | ✅ |
| `health_check.shadow_pillars_field` flips to False | ✅ |
| 9 v10.389 tests pass | ✅ |
| All 142 Phase B+C arc tests pass | ✅ |
| Finding N7 documented in design doc Part 5 | ✅ |
| Audit gates | 273 → **274** |
| Verifier | 469 → **475 checks** |
| Master prompt lockstep | **33/33 consecutive batches** |
| G162 baseline | 4022 (**82 consecutive zero-drift batches**) |

## Phase C progress

| Batch | Concern | Status |
|---|---|---|
| ~~v10.386~~ | KPI Library tab canonical save + History view | ✅ |
| ~~v10.387~~ | History view | ✅ bundled |
| ~~v10.388~~ | Remove Bank Identity dead form | ✅ |
| ~~**v10.389**~~ | **Remove pillars[].weight shadow data** | ✅ **DONE** |
| v10.390 | Remove org_config.json orphan field + start Tier-1 Class B KPIs | next |
| v10.391 | Tier-2 Class B KPIs (DIGITAL_ACT + 5 LEGAL_*) | pending |

**4 of Tier-1 closed. 2 to go. Prioritization organ rescue is 4-of-5 complete.**

## 15 honest acknowledgements

1. **Smallest batch of Phase C.** Four field deletions. No code changes.

2. **Discovered a pre-existing bug.** `get_active_kpis()` crashes on list-vs-dict. Logged as Finding N7. Not bundled.

3. **The shadow had wrong values for an unknown duration.** Pillars[] had 40/25/25/10; canonical had 68/14/6/12. Drift was silent.

4. **Backup pattern preserved.** `data/_v10389_backups/kpi_library.json.before` allows rollback.

5. **No code changes means low risk.** Five canonical pillar_weights consumers untouched. Other consumers read id/name/color — never weight. Nobody used the shadow for scoring.

6. **Rule N2 single concern held strictly** even when Finding N7 was tempting to bundle. Discipline matters.

7. **Finding N7 reveals v10.385 diagnosis had a coverage gap.** The diagnosis surveyed consumers by grep, not by running code. Some bugs only show up when consumers execute. A future diagnosis enhancement could include runtime probe of each consumer.

8. **The body's prioritization organ now speaks with ONE voice inside kpi_library.json.** No shadow. One canonical dict. Structural metadata in pillars[].

9. **v10.390 finishes the rescue.** Remove the `org_config.json::pillar_weights` orphan field. After that, the prioritization organ is fully canonical: one store, one admin UI, no shadows, no orphans, full audit history.

10. **Phase C is on pace.** Four batches in (v10.386, v10.388, v10.389), two to go (v10.390, v10.391). Each batch addresses one diagnosis finding. Sustainable rhythm.

11. **Health check diagnostic earned its keep.** v10.384 added `shadow_pillars_field` to health_check. v10.389 made it flip. Future diagnostics see the shadow was removed, when.

12. **Two-stage removal pattern continues.** v10.388 stopped writing to org_config; v10.390 removes the data. v10.389 removed pillars[].weight; the canonical dict was always authoritative — no data preservation needed since there was nothing depending on the shadow.

13. **The 4 pillar entries are now smaller.** Pre-v10.389: 4 fields per entry. Post-v10.389: 3 fields per entry. JSON file is slightly smaller. Cleanup adds up.

14. **AST/regex/data-shape verification all three patterns used.** G272 (regex on admin UI), G273 (text-finding on admin section), G274 (JSON shape check on data). Each gate uses the right tool for its concern.

15. **Constitution §12 Flow Principle is the architectural anchor.** Body should have one source of truth per concern. Each rescue batch (v10.384/386/388/389, soon v10.390) gets closer to that ideal.

## On your end

1. Close Streamlit
2. Extract `a2z_v10389_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **475/475**
4. **Confirm the shadow is gone**: open `data/kpi_library.json` in an editor, search for `"pillars": [` — see entries no longer have `weight` field
5. **Confirm canonical still intact**: search for `"pillar_weights":` — still has 4 keys with current values
6. Read `docs\PILLAR_SHADOW_WEIGHTS_REMOVED_v10.389.md`
7. Tell me "continue" → v10.390 = remove org_config orphan field + start Tier-1 Class B KPIs

## What's next — v10.390

Two concerns in one batch (final rescue step + KPI work start):

**Concern A — Remove `org_config.json::pillar_weights` orphan field.** The two-stage cleanup completes (v10.388 stopped writing; v10.390 deletes data). After this, NO shadow data and NO orphan field anywhere — the prioritization organ rescue is fully complete.

**Concern B — Start Tier-1 Class B KPIs.** v10.390 lays the foundation: build `utils/financial_ratios_engine.py` as a leaf module exposing `compute_nim`, `compute_cir`, `compute_roe`, `compute_total_deposit_growth`. v10.391 adds the customer-focus engine (NPS, DIGITAL_ACT) and the library entries.

Two concerns in one batch is a deliberate exception to Rule N2 because:
- Concern A is the final rescue cleanup (small)
- Concern B starts a new workstream (foundation)
- They're sequenced naturally (rescue ends → new work begins)

Or if you'd prefer strict single-concern: v10.390 = orphan removal only, v10.391 = financial ratios engine, v10.392 = customer focus engine, etc. Your call.

Continue with v10.390?
