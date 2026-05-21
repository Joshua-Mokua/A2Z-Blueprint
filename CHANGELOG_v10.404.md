# Changelog — v10.404 Regenerator Preserves Manual Allocations

**Date:** 2026-05-14
**Phase:** Cascade behavior alignment — Joshua F4 directive
**Audit:** G290 added
**Tests:** 11/11 PASSED in `test_v10404_preserve_manual_allocations.py`
**Verifier:** 570/570 checks pass
**G162 baseline:** 4022 (97 consecutive zero-drift batches)
**Master prompt:** v4.46 → v4.47 (lockstep — 48 consecutive batches)

---

## Joshua's directive (F4)

> "Regenerate Cascade button — preserve manual allocations"

## Critical bug resolved

**Before v10.404**: Admin clicked Regenerate Cascade (canonical admin UI) → entire `target_cascade.json` rebuilt with equal-split flat cascade. **Every manager's manual allocation work was silently erased.**

**Example case** (deep-test verified):
- CRBO Nicholas manually allocates: Head of Branches gets 60%, Head of Women Banking gets 40%
- Admin adds a new chief mapping in canonical UI, clicks Regenerate
- CRBO's 60/40 split → wiped → replaced with equal split (1/6 each across ALL 6 reports)

**After v10.404**: Manual allocations preserved. CRBO's tree is left alone; only canonical changes outside CRBO's subtree update.

## Architecture

### 1. Schema markers (CascadeManager.set_allocation)

Every UI write now stamps:
```python
{
  "_v10404_manual": True,
  "updated_by": "<username>",   # NEW
  "updated_at": "ISO timestamp",
  ...
}
```

### 2. Detection (cascade_regenerator)

Manual entries detected by either:
- `_v10404_manual: True` (explicit marker), OR
- `updated_by` field present (UI write trail)

### 3. Skip logic (new helper `_cascade_recursive_with_skip`)

```
For each (kpi, period):
  manual_managers = {staff_codes with manual allocation for this kpi+period}
  When recursing top-down from MD:
    If current manager is in manual_managers:
      Skip them (preserve their existing entry)
      Don't recurse below them (their subtree is their responsibility)
    Else:
      Generate equal-split allocation
      Recurse into reports
```

### 4. API surface

```python
# Default: preserve manual (per Joshua F4)
regenerate_target_cascade(write=True)

# Force rebuild (rare; explicit admin choice)
regenerate_target_cascade(write=True, preserve_manual=False)
```

### 5. Admin UI

Canonical admin → 🔄 Regenerate tab now shows:
- 🛡️ **Preserve manual allocations (recommended)** ← default
- 🔥 **Force full rebuild (overwrites all manual work)** ← with warning

When force mode chosen, UI shows red warning before allowing click.

### 6. Provenance

Change log records:
```json
{
  "who": "admin",
  "action": "regenerate_cascade",
  "new": {
    "count": 24024,
    "preserve_manual": true,
    "manual_preserved": 3
  }
}
```

## End-to-end test results

| Test | Result |
|---|---|
| CRBO sets 60/40 manual split | ✓ stamped with `_v10404_manual` + `updated_by` |
| Admin Regenerate (preserve mode) | ✓ CRBO's split preserved exactly |
| Admin Regenerate (force mode) | ✓ CRBO's split overwritten (expected) |
| Manager's subtree under manual entry | ✓ also preserved (recursion skipped) |
| Engine state | ✓ 0/0/0/0 |
| Existing cascade size | ✓ ~24K entries (no regression) |

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 289 → **290** |
| Tests | 305 → **316** (+11 new) |
| Verifier | 564 → **570 checks** |
| Master prompt lockstep | **48/48 consecutive batches** |
| G162 baseline | 4022 (**97 consecutive zero-drift batches**) |
| Engine state | 0/0/0/0 ✓ |

## 10 honest acknowledgements

1. **F4 directive honored verbatim.** Default behavior preserves manual; force mode available but gated behind explicit choice + warning.

2. **Critical silent bug fixed.** Before v10.404, managers could spend hours setting allocations, then lose it all to a single admin regen click.

3. **Subtree preservation included.** When a manager has manual allocation, their entire subtree downstream is preserved too (not regenerated below them). This matches the design: the manager owns their tree.

4. **Detection is dual-signal.** Either `_v10404_manual` marker OR `updated_by` field triggers preservation. Pre-v10.404 entries (no marker) get treated as fresh — safe default.

5. **Change log records mode + count.** Audit trail shows whether preserve or force was used + how many manuals were preserved. Visible in Canonical Admin → Change Log tab.

6. **Force mode kept available.** Some scenarios (test data, mass reset, post-mistake recovery) need force. UI gates it behind a warning and labeled clearly.

7. **set_allocation API extended backward-compat.** Old callers (no `updated_by` arg) still work — defaults to `from_code` as updated_by.

8. **Engine state preserved.** Adding the preservation logic didn't break canonical validation (0/0/0/0).

9. **Backward compat for legacy cascade entries.** Cascade entries pre-v10.404 (without markers) regenerate fresh on next regen — they're treated as canonical defaults, not manual work. Once a manager touches them via UI, they become preserved going forward.

10. **48 consecutive lockstep batches.** No drift.

## On your end

1. Close Streamlit
2. Extract `a2z_v10404_patch.zip` flat on top of v10.403 state
3. Run `python scripts\verify_local_state.py` → expect **570/570**
4. Engine: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Acceptance test scenario:
   - Login as Chief Nicholas (CRBO)
   - Open Cascade page → 'Set team targets'
   - Set custom allocation for PBT 2026 (e.g., one report gets 80%)
   - Logout, login as admin
   - Open Admin → Canonical Hierarchy → Regenerate
   - Should see "🛡️ Preserve manual allocations (recommended)" toggle selected by default
   - Click Regenerate
   - Logout, login as Nicholas again
   - Open Cascade → My targets — your 80% allocation should be intact
6. Tell me **"continue"** → v10.405 = per-layer buffer with MD per-KPI cap (your F2 design)

## v10.405 preview — what's coming next

Per your F2 answers:
1. Buffer applies at each layer (MD, chief, head, manager…)
2. MD sets **per-KPI max %** cap (different per KPI)
3. Each layer's stretch hidden from layers below
4. BSC shows **stretch as primary**, base as secondary aside

Implementation outline:
1. Schema: `buffer_pct`, `stretch_target` fields on cascade entries (per-layer)
2. New `data/buffer_caps.json`: `{kpi: max_buffer_pct}` set by MD via Cascade page
3. Cascade UI 'Set team targets': buffer input per KPI per direct report
4. Validation: `buffer_pct ≤ max_buffer_pct` per the cap
5. BSC primary: stretch from most-local layer; secondary: base target (small label aside)
6. Regenerator: respects buffer when set per layer; falls back to default

Continue?
