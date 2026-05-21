# Changelog — v10.388 Bank Identity Pillar Weights Form REMOVED (Deprecation Promise Kept)

**Date:** 2026-05-13
**Phase:** Phase C continues — Tier-1 fix sequence
**Phase 4 arc count:** seventy-second arc — second Phase C execution batch
**Audit:** G273 added (G270 widened forward-compatibly)
**Tests:** 8/8 PASSED in `test_v10388_bank_identity_pillar_removed.py`; 2 prior tests updated forward-compatibly
**Verifier:** 469/469 checks pass on clean extract
**G162 baseline:** 4022 (81 consecutive zero-drift batches)
**Master prompt:** v4.30 → v4.31 (lockstep — 32 consecutive batches)

---

## Your direction

> "continue" — proceed with v10.388 per Phase C Tier-1 sequence

The v10.384 deprecation notice promised: *"This section is preserved only for backward compatibility and will be removed in v10.388."* v10.388 keeps that promise.

## What v10.388 removed

### Bank Identity admin tab — dead form amputated

**Removed widgets:**
- `_pw1,_pw2,_pw3,_pw4 = st.columns(4)` (the 4 columns)
- `_fin_wt = _pw1.number_input("Financial %", ...)` and 3 siblings (Customer/Operations/People)
- `_wt_total = _fin_wt+_cust_wt+_ops_wt+_ppl_wt` (total calculation)
- The colored sum-validation badge HTML

**Removed validation:**
- `if _wt_total != 100: st.error("Pillar weights must total 100%")` form-submit gate

**Removed dead-branch write:**
- `_org["pillar_weights"] = {"Financial": _fin_wt/100, ...}` — wrote to org_config.json which no consumer reads

**Removed deprecation warning (v10.384):**
- The yellow `st.warning("⚠️ Deprecated. ... will be removed in v10.388.")` block

### Replaced with brief redirect

```python
st.info(
    "ℹ️ **Pillar weights moved.** Pillar weights are managed at "
    "**Admin → KPI Library → Pillar weights tab**. That tab "
    "writes to the canonical store with audit history. The form "
    "that lived here previously wrote to a legacy location no "
    "longer read by scoring — it has been removed in v10.388."
)
```

Brief, factual, informational. No yellow warning. No crisis tone. Just wayfinding.

## What was preserved

| Item | Why |
|---|---|
| Bank Identity tab itself | Still handles bank_name, bank_code, country, currency, regulator, etc. |
| All non-pillar-weight identity field saves | Unchanged |
| `org_config.json::pillar_weights` data on disk | Two-stage removal: stop writing v10.388, delete data v10.390 |
| KPI Library → Pillar weights tab | v10.386 contract unchanged |
| `pillars[].weight` shadow data | Scheduled for v10.389 removal (separate concern) |

## Forward-compatible test updates

v10.384's admin test and v10.386's admin test both asserted "Deprecated" was present in admin.py. v10.388 replaced that text. Both tests updated to accept EITHER:
- `"v10.384" + "Deprecated"` (pre-v10.388 state), OR
- `"v10.388" + "Pillar weights moved"` (post-v10.388 state)

G270 (canonical pillar weights gate) updated similarly. The original intent — "the silent failure is documented in admin UI" — is satisfied by either marker.

## Verified outcome

| Metric | Value |
|---|---|
| Dead Bank Identity form removed | ✅ |
| Redirect notice in place | ✅ |
| KPI Library Pillar Weights tab unchanged | ✅ |
| Admin parses cleanly (AST) | ✅ |
| 8 v10.388 tests | ✅ all pass |
| 2 forward-compatible test updates | ✅ |
| G270 widened forward-compatibly | ✅ |
| All 133 Phase B+C arc tests | ✅ pass |
| Audit gates | 272 → **273** |
| Verifier | 463 → **469 checks** |
| Master prompt lockstep | **32/32 consecutive batches** |
| G162 baseline | 4022 (**81 consecutive zero-drift batches**) |

## Phase C status

| Batch | Concern | Status |
|---|---|---|
| ~~v10.386~~ | KPI Library tab migration + History view | ✅ |
| ~~v10.387~~ | History view | ✅ bundled into v10.386 |
| **v10.388** | Remove Bank Identity deprecated form | ✅ **THIS BATCH** |
| v10.389 | Remove `pillars[].weight` shadow data | next |
| v10.390 | Remove org_config orphan + Tier 1 Class B KPIs | pending |
| v10.391 | Tier 2 Class B KPIs (DIGITAL_ACT + 5 LEGAL_*) | pending |

After v10.390: prioritization organ rescue **fully complete** (one canonical store, one admin UI, no shadow data, no orphan field, full audit history).

## 15 honest acknowledgements

1. **Easiest batch of Phase C so far.** ~30 LOC removed. Three lines needed re-indentation (the success/cache_clear/rerun lines after removing the `if/else` branch they sat in). Otherwise mechanical.

2. **The deprecation period worked exactly as intended.** v10.384 made the silent failure visible (warning text). v10.386 migrated the working UI. v10.388 amputates the dead branch. Four batches; clean sequence.

3. **`org_config.json::pillar_weights` data is preserved on disk.** This is the "data" part of the orphan — v10.388 stops writing to it, v10.390 deletes the field entirely. Two-stage removal is safer (allows operational rollback if anything unexpected breaks).

4. **The form-submit no longer requires pillar weight validation.** Pre-v10.388, saving bank identity required pillar weights to sum to 100 (even though those weights had no effect). Post-v10.388, the save just persists identity fields. Faster, cleaner.

5. **No operator data lost.** Canonical state preserved. KPI Library tab continues working. History continues populating.

6. **G273 uses Bank Identity section bounds detection.** Finds the next "elif Branches" block, asserts pillar widgets absent in the preceding span. Targeted, not broad.

7. **Forward-compatible test updates were the right call.** Strict "Deprecated must be present" assertions would have broken v10.388. Widened assertions accept either marker — both express the same intent.

8. **The two test updates touched ONE assertion each.** Minimal change. Both v10.384 and v10.386 tests were structurally unchanged.

9. **Rule N2 single concern held strictly.** Removed dead UI + dead-branch write + dead validation gate from ONE admin tab section. Did NOT touch the canonical accessor, the working tab, the data files, or any other organ.

10. **The body's phantom limb is gone.** Before v10.388: two admin UIs for the same concept, one of them silently broken. After v10.388: ONE admin UI, working.

11. **The redirect notice is unlikely to confuse anyone.** "Pillar weights moved — managed at KPI Library → Pillar weights tab" is unambiguous. No history-of-the-bug to explain.

12. **G270's widening is documented.** Future readers see G270 now accepts either marker. The why-it-was-widened is in the v10.388 design doc + this CHANGELOG.

13. **Operators using only the canonical tab were unaffected.** v10.388 changes the deprecated tab; the working tab is untouched. If someone has only ever used the canonical tab (as intended), they see no difference.

14. **The body's prioritization organ rescue is 3-of-5 done.** v10.384 (canonical accessor) → v10.386 (working UI migration) → v10.388 (dead form removal) ✓. Still pending: v10.389 (shadow data) + v10.390 (orphan field).

15. **Phase C is on schedule.** Tier-1 fix sequence has 6 batches; v10.388 is #3. Each batch addresses one specific diagnosis finding. Pace is sustainable.

## On your end

1. Close Streamlit
2. Extract `a2z_v10388_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **469/469**
4. Visit Admin → Bank Identity tab — see the brief redirect notice (no more form)
5. Visit Admin → KPI Library → Pillar weights tab — still works as before
6. Read `docs\BANK_IDENTITY_PILLAR_WEIGHTS_REMOVED_v10.388.md`
7. Tell me "continue" → v10.389 = remove `pillars[].weight` shadow data

## What's next — v10.389

Remove the shadow `weight` field from each pillar entry in `kpi_library.json::pillars[]`. This shadow data is read by some pillar-iteration consumers but `pillar_weights` dict (the canonical) overrides. v10.389 cleans up the shadow.

After v10.389: pillar structural data lives in one place (`pillars[]` for grouping, `pillar_weights` for weights). No shadow weights.

Continue with v10.389?
