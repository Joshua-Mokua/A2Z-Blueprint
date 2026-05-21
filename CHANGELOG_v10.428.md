# Changelog — v10.428 BSC Weight Renormalization (BSC Rescue batch 4)

**Date:** 2026-05-14
**Phase:** BSC Rescue (batch 4 of ~5)
**Audit:** G314 added (cumulative 314 gates)
**Tests:** 13/13 PASSED in `test_v10428_weight_normalize.py`
**Combined regression:** 81 BSC Rescue tests PASSED (68 prior + 13 new)
**Verifier:** 750 → **755** (+5 v10.428 checks)
**G162 baseline:** 4022 (121 consecutive zero-drift batches)
**Master prompt:** v4.70 → v4.71 (lockstep — 72 consecutive batches)

**BSC HEALTH: 71.4% → 85.7% (+14.3 points)** — fourth rescue batch lands. **6 of 7 categories now clean. Only cascade linkage remains.**

---

## What this batch is

Closes finding #4 from the v10.424 audit: **491 staff with weight sums ≠ 1.0** (range 1.0-4.28).

The root cause was structural, not drift: when chiefs/managers received KPI assignments via the simulate_v2.py generator, each row got the **library default_weight** (e.g. Compliance Score = 0.50). Staff with many KPIs accumulated weights summing to 2.0–4.28 — not normalized to per-staff = 1.0.

**Aaron Lagat** (Central Processing Manager) example, pre-v10.428:
- 27 KPI rows, weights from 0.05 to 0.50
- Total weight: **3.18** (should be 1.0)
- Breakdown: Compliance Score 0.50, Diligence Score 0.50, Reconciliation Rate 0.25, …
- Post-v10.428: same KPIs, weights rescaled by 1/3.18 ≈ 0.314 → all weights smaller proportionally, sum = 1.0

## Strategy: per-staff proportional rescale

For each staff with `weight_sum != 1.0` (within 1% tolerance):

```
new_weight[i] = old_weight[i] / sum(old_weights_for_staff)
```

**Why proportional rescale instead of using library `role_normalized_weights`?**

The actuals authored relative weights per row (some KPIs given more emphasis for the specific staff than others). Proportional scaling preserves that authorial intent while making the sum mathematically valid for BSC score aggregation.

Using library `role_normalized_weights` (from v10.419) would override per-staff customization. The rescue is more conservative: respect existing relative weights, fix the totals.

## Live migration result

**Pre-migration:**
- 491 staff with weight sums ≠ 1.0
- Range: 1.0 – 4.28
- Distribution: 136 staff [1.01-1.50), 155 staff [1.50-2.00), 141 staff [2.00-3.00), 59 staff [3.00-4.30)

**Post-migration:**
- 491 staff renormalized
- 10,945 BSC rows touched (rows × per-staff weight rescale)
- Post sum range: **1.0 – 1.0** exactly
- Average rescale factor: 0.606 (sum 1.65 → 1.0)

## What v10.428 built

### NEW `utils/bsc_weight_normalize_engine.py` (~350 LOC)

Zero streamlit imports. **22nd React-ready engine.**

**Constants:**
- `WEIGHT_TOLERANCE = 0.01` (1%) — anything within 1% of 1.0 is treated as already-normalized

**Public API:**

| Function | Returns | Purpose |
|---|---|---|
| `audit_actuals_weights(actuals_path)` | `WeightAuditResult` | Per-staff weight sum + which need renorm |
| `renormalize_actuals_weights(dry_run=True)` | `WeightNormResult` | Apply rescale; idempotent |

**Dataclasses (JSON-serializable):**
- `StaffWeightProfile` — single staff weight state (current_sum, after_renorm, rescale_factor)
- `WeightAuditResult` — bank-wide
- `WeightNormResult` — migration outcome

### NEW `scripts/renormalize_bsc_weights.py` runner with `--confirm`

### NEW 2 FastAPI endpoints

- `GET /api/v1/bsc-weights/audit`
- `POST /api/v1/bsc-weights/renormalize?confirm=true`

### Audit gate G314

Verifies engine API + zero streamlit + `WEIGHT_TOLERANCE` + `dry_run=True` default + runner `--confirm` + 2 endpoints + **weight_normalization audit = 0 not normalized** + engine state 0/0/0/0.

### Forward-compat test patches

- `test_v10424_weight_normalization_finds_not_normalized` — accepts pre or post v10.428 state
- `test_v10424_full_audit_health_calculated` — no longer asserts health < 100% (it can reach 100% as rescue completes)

## Verified outcome

| Metric | v10.427 | v10.428 |
|---|---|---|
| Audit gates | 313 | **314** |
| BSC Rescue tests | 68 | **81** (+13) |
| Verifier | 750 | **755** (+5) |
| API endpoints | 53 | **55** (+2) |
| React-ready engines | 21 | **22** |
| Lockstep batches | 71 | **72** consecutive |
| G162 baseline | 4022 (120) | 4022 (**121** zero-drift) |
| **BSC health** | **71.4%** | **85.7%** (+14.3 points) |
| **Categories clean** | **5/7** | **6/7** |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |

## 10 honest acknowledgements

1. **Proportional rescale is the right tool here.** Each staff's weights were authored with intent — relative importance is meaningful. Scaling preserves that. Replacing with library defaults would overwrite manual customization without consent.

2. **The 1% tolerance is generous.** Some staff had weight sums like 0.9997 from floating-point rounding — those are "already normalized" and get a no-op rescale of ≈1.0. Avoids unnecessary churn.

3. **10,945 rows touched in one migration.** Every cell in the Weight column for the 491 affected staff was recomputed. The Excel write took ~5 seconds, well within tolerable single-batch latency.

4. **Idempotent by design.** Re-running on clean state: every staff's sum is already within tolerance, so 0 staff get rescaled. Verified in the test suite.

5. **Library `role_normalized_weights` (v10.419) wasn't used.** That dataset was correctly computed but the actuals file diverged. Future generations of actuals should consume `role_normalized_weights` directly. Until then, v10.428's rescale is the bridge.

6. **The 27-KPI staff like Aaron Lagat are interesting.** Their weights post-rescale are all small (avg 1/27 ≈ 0.037). This is correct — many small contributions to the total score. The BSC engine handles this naturally.

7. **No KPI weights became zero.** All original weights were positive, so the rescale only changes magnitudes, never signs or zeros.

8. **The audit and renormalize functions are decoupled.** You can audit without running the migration. The dry-run pattern lets you preview the rescale factors before committing.

9. **6/7 categories clean.** Only cascade linkage remains (10 cascade staff missing from BSC). After v10.429, BSC health should hit 100% for the first time since the audit was built.

10. **22 React-ready engines.** Counting from v10.412's discipline lock-in: bsc_audit (v10.424), bsc_pillar_normalize (v10.425), bsc_library_register (v10.426), bsc_completeness (v10.427), bsc_weight_normalize (v10.428). Five BSC engines, all FastAPI-accessible, all dataclass-returning. v10.430+ will start consuming them in the Streamlit pages and React frontend.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10428_patch.zip` on top of v10.427 state
3. `python scripts/verify_local_state.py` → expect **755/755**
4. `python utils/bsc_weight_normalize_engine.py` → engine self-test (7 checks)
5. `python scripts/audit_bsc.py` → confirm Weight normalization = ✓ **0 not normalized**
6. (Optional, idempotent) `python scripts/renormalize_bsc_weights.py` → audit shows 0 to renormalize
7. Tell me **"continue"** → v10.429 = cascade-BSC linkage (10 missing staff) — expected to close the rescue at **100% BSC health**

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.424~~ | ~~BSC Deep Audit Engine~~ | **DONE** |
| ~~v10.425~~ | ~~Pillar canonical merge~~ | **DONE** |
| ~~v10.426~~ | ~~BSC Library register~~ | **DONE** |
| ~~v10.427~~ | ~~Chief BSC completeness~~ | **DONE** |
| **v10.428** | **Weight normalization** | **DONE (this batch)** |
| v10.429 | Cascade-BSC linkage (10 missing) | **Next — closes the arc** |
| v10.430+ | BSC scorecard + admin config wiring | After 100% audit health |
