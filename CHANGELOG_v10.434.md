# Changelog — v10.434 New Staff Onboarding Fit-In Test

**Date:** 2026-05-14
**Phase:** Verifying every staff fits the canonical onboarding pattern
**Audit:** G320 added (cumulative 320 gates)
**Tests:** 18/18 PASSED in `test_v10434_staff_onboarding.py`
**Combined regression:** 182 v10.4xx BSC arc tests PASSED (164 prior + 18 new)
**Verifier:** 787 → **793** (+6 v10.434 checks)
**G162 baseline:** 4022 (127 consecutive zero-drift batches)
**Master prompt:** v4.76 → v4.77 (lockstep — 78 consecutive batches)

**360 HARMONY: 100% preserved. BSC RESCUE: 100% preserved.**

---

## What you directed

> "Confirm that an addition of a new staff fits in so well — register → cascade → BSC auto-populates."

## What v10.434 built

### `utils/staff_onboarding_engine.py` (~600 LOC, **27th React-ready engine**)

Zero streamlit. Four public functions cover the full lifecycle:

| Function | Returns | Purpose |
|---|---|---|
| `validate_new_staff(staff_dict)` | `ValidationResult` | Pre-add checks: required fields, duplicate codes, role configured in `role_kpis`, manager exists, etc. |
| `simulate_onboarding(staff_dict, dry_run)` | `OnboardingResult` | Project what would happen: how many BSC rows, weight sum, pillar coverage, cascade reception, score viability |
| `audit_staff_completeness(staff_code)` | `CompletenessAudit` | One staff's full fit: register + role_kpis + BSC + weights + pillars + score + cascade |
| `audit_all_staff_completeness()` | `FullCompletenessAudit` | Bank-wide rollup across all 1,437 staff |

**5 JSON-serializable dataclasses.** Constants: `CANONICAL_PILLARS`, `WEIGHT_TOLERANCE = 0.001`, `DEFAULT_NEW_KPI_WEIGHT = 0.05`, `DEFAULT_NEW_ACHIEVEMENT = 0.80`.

Helper: `_resolve_canonical_names(lib, kpi_ids)` resolves cascade IDs, names, and aliases to canonical library names (so `PRODUCT_BOOK_ACHIEVEMENT` → `"Product Book Achievement"`).

### Admin panel — `render_onboarding_fit_panel()`

Bank-wide audit dashboard with:
- 8 metrics: fully fit count + percentage, partial, failing, role_kpi coverage, weight invariant, score computable, pillar coverage, failing samples count
- Pass/info/warn banner based on fit percentage
- Failing staff samples expander
- **Interactive simulator**: pick any role, set a unit, run a hypothetical onboarding → see projected BSC rows, weight sum, pillar coverage, score viability

### 3 new FastAPI endpoints
- `GET  /api/v1/onboarding/audit` — bank-wide rollup
- `GET  /api/v1/onboarding/audit/{staff_code}` — one staff
- `POST /api/v1/onboarding/simulate` — dry-run for a payload

### Audit gate G320
Verifies engine API, zero streamlit, 5 dataclasses, admin panel + page wiring, 3 endpoints, `Body` imported, 360 harmony preserved, BSC rescue preserved, engine state preserved.

## Bank-wide fit-in audit findings

This is the **truthful state of onboarding readiness** across the existing 1,437 staff:

| Metric | Value | Note |
|---|---|---|
| Total staff | 1,437 | per register |
| **Fully fit** | **1,176 (81.8%)** | passes all 6 checks |
| Partial fit (1-2 minor issues) | 261 | role_kpis configuration drift |
| Failing (3+ issues) | **0** | no broken staff |
| Avg role_kpi coverage | **91.61%** | BSC mostly matches role_kpis |
| Weight sum = 1.0 (invariant) | **100%** ✓ | v10.428 + v10.433 work pays off |
| Score computable | **100%** ✓ | v10.433 work pays off |
| All 4 pillars represented | **99.51%** ✓ | very close to universal |

## Why 18.2% are "partial fit" — and what to do about it

The partial-fit bucket reflects **role_kpis configuration drift**, not data brokenness. Two main patterns:

### Pattern 1: Senior leadership role_kpis are stale

The MD ("Chief Executive & Managing Director") has 12 KPIs in `role_kpis`:
> 360 Feedback Score, Budget Achievement — OpEx (%), Cost-to-Income Ratio (%), …

But MD's BSC has 15 KPIs (PBT, Total NFI, Retail & MSME Deposits, Commercial Deposits, Loan Book Growth, NPL Ratio, etc.) — the actual bank-wide metrics MD owns.

**Diagnosis:** `role_kpis["Chief Executive & Managing Director"]` was set with support-role KPIs at some prior point. The BSC reflects the real measure of accountability. Fix: admin updates `role_kpis` via the KPI Library editor.

### Pattern 2: Roles missing from `role_kpis` entirely

"Senior Relationship Officer Corporate" returned 0 KPIs in the simulator — that role isn't keyed in `role_kpis`. A new hire into that role would join with no BSC. Fix: admin adds the role to `role_kpis` with appropriate KPI set.

**Both patterns are admin-fixable via the existing KPI Library editor + the validation engine (v10.431).** The fit-in test surfaces them; v10.434 doesn't auto-fix because they need product/HR judgment on the right KPI set per role.

## The simulator in action

```
Role: Branch Operations Manager
  → 21 KPIs assigned
  → Pillar coverage: F:12 CF:4 OE:4 PL:1
  → Score computable: ✓

Role: Senior Relationship Officer Corporate
  → 0 KPIs (role not in role_kpis)
  → Warning surfaced to admin

Role: Teller
  → 21 KPIs assigned
  → Score computable: ✓

Role: Branch Manager
  → 21 KPIs assigned
  → Score computable: ✓
```

## Verified outcome

| Metric | v10.433 | v10.434 |
|---|---|---|
| Audit gates | 319 | **320** |
| BSC arc tests | 164 | **182** (+18) |
| Verifier | 787 | **793** (+6) |
| API endpoints | 63 | **66** (+3) |
| React-ready engines | 26 | **27** |
| Lockstep batches | 77 | **78** consecutive |
| G162 baseline | 4022 (126) | 4022 (**127** zero-drift) |
| 360 harmony | 100% | **100%** ✓ |
| BSC rescue | 100% | **100%** ✓ |
| **Fully-fit staff** | n/a | **81.8% (1176/1437)** |

## Admin panel — now 6 stacked sections

```
📊 Performance → 🩺 BSC Health
   ├ 🩺 BSC Health Dashboard          (v10.430)
   ├ 🔍 KPI Library Validation         (v10.431)
   ├ 🔄 Cascade ↔ BSC 360° Harmony    (v10.432) — 100% ✓
   ├ 🛠️ Cascade-BSC Harmonization     (v10.433) — idempotent on clean state
   ├ 👥 Staff Onboarding Fit-In Audit (v10.434) — 81.8% fully fit (NEW)
   └ BSC Admin Actions
```

## 10 honest acknowledgements

1. **The fit-in audit is read-only.** No data writes; just the diagnostic. Surfaces issues; admin chooses what to fix.

2. **81.8% fully fit is the honest current state.** Could be 100% if I auto-rewrote `role_kpis` for senior leaders, but that's a judgment call on what each role SHOULD track — not a mechanical fix.

3. **The 100% weight invariant is the win from v10.428+v10.433.** Every staff's weight sum is exactly 1.0 — this is the "100% catch" you insisted on.

4. **100% score computability is the win from v10.433.** Every staff can be scored end-to-end. No NaN, no orphans, no broken paths.

5. **The simulator is the real value-add.** Admin can preview what a new hire's BSC will look like BEFORE adding them. If 0 KPIs come back, the role needs `role_kpis` configuration first.

6. **`_resolve_canonical_names` is reused.** Same helper pattern as v10.433. Single source of truth for the cascade↔BSC↔library naming mismatch problem.

7. **Bank-wide audit is fast.** Initial implementation was per-staff JSON reload (timed out); refactored to load once + iterate with in-memory lookups. Now runs in ~3s for all 1437 staff.

8. **No `onboard_new_staff` live-write yet.** Validation + simulation + audit are this batch's scope. Actual register writes + cascade integration would be v10.436+ alongside HR module.

9. **The MD `role_kpis` mismatch is the most striking find.** The BSC has the right metrics; `role_kpis` has stale ones. Fix is to align `role_kpis[Chief Executive & Managing Director]` to the canonical 15 bank-wide KPIs.

10. **Pattern 2 (roles missing from `role_kpis`) is the higher-risk one.** A new hire into "Senior Relationship Officer Corporate" today would get zero BSC rows. The simulator catches this; admin updates `role_kpis` before onboarding.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10434_patch.zip` on top of v10.433 state
3. `python scripts/verify_local_state.py` → expect **793/793**
4. `python utils/staff_onboarding_engine.py` → self-test runs bank-wide audit (~5s)
5. **Open Streamlit → Admin → 📊 Performance → 🩺 BSC Health → scroll to "👥 Staff Onboarding Fit-In Audit"**
6. See the 81.8% fully fit + 261 partial samples
7. Try the simulator: pick "Senior Relationship Officer Corporate" → see 0 KPIs warning → confirms role needs `role_kpis` config
8. Tell me **"continue"** → v10.435 = staff exit + target gap risk detection

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.424–v10.429~~ | BSC Rescue (6 batches) | **DONE** (100% health) |
| ~~v10.430–v10.431~~ | Admin UI + validation engine | **DONE** |
| ~~v10.432–v10.433~~ | 360 audit + harmonization to 100% | **DONE** |
| ~~**v10.434**~~ | **New staff onboarding fit-in test** | **DONE (this batch)** |
| v10.435 | Staff exit + target gap risk detection | **Next** |
| v10.436+ | HR / People module (incl. live onboard_new_staff write path) | After exit flow |
| (later) | Per-role-category pillar weight overrides for support roles | Flagged |
| (later) | role_kpis admin editor with config audit for senior roles | Flagged |
