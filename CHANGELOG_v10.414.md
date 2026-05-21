# Changelog — v10.414 F2 part A: Cascade buffer engine + MD per-KPI cap

**Date:** 2026-05-14
**Phase:** Phase 2c (architectural features) — F2 part A
**Audit:** G300 added (cumulative 300 gates)
**Tests:** 15/15 PASSED in `test_v10414_cascade_buffer_and_md_cap.py`
**Regression:** 206/206 v10.4xx tests PASSED (191 + 15)
**Verifier:** 660/660 checks pass (651 → 660, +9 v10.414 checks)
**G162 baseline:** 4022 (107 consecutive zero-drift batches)
**Master prompt:** v4.56 → v4.57 (lockstep — 58 consecutive batches)

---

## What this batch is

The first of three batches landing your F2 architectural concern. F2 = per-layer buffer + MD per-KPI cap, with stretch hidden from layers below, BSC dual-view (primary=stretch, secondary=base aside).

v10.414 covers **part A**: the engine, the cap-setting MD surface, and the FastAPI endpoints. Per-allocation stretch slider (part B) is v10.415; dual-view BSC display is v10.417 (F5 in your numbering).

This is also the **11th cascade engine** built API-first (zero streamlit imports). The discipline you set in v10.412 is paying off — adding F2 to the codebase took one engine module plus six endpoints, with the same module servicing both Streamlit and FastAPI without modification.

## What v10.414 built

### NEW `utils/cascade_buffer_engine.py` (~360 LOC)

API-first per v10.412 discipline. **Zero streamlit imports (AST-verified).**

**Public API:**

| Function | Returns | Purpose |
|---|---|---|
| `set_buffer_cap(kpi, max_stretch_pct, set_by, note='')` | `BufferCapConfig` or `None` | MD sets cap (validates: 0.0 ≤ pct ≤ 0.50) |
| `get_buffer_cap(kpi)` | `BufferCapConfig` or `None` | Single cap lookup |
| `get_all_buffer_caps()` | `list[BufferCapConfig]` | All configured caps |
| `remove_buffer_cap(kpi, removed_by)` | `bool` | Clear cap (returns False if absent) |
| `validate_buffer(kpi, proposed_pct)` | `BufferValidation` | Check proposed stretch against cap |
| `is_within_cap(kpi, proposed_pct)` | `bool` | Convenience wrapper |
| `compute_effective_amount(base, stretch_pct)` | `float` | `base × (1 + stretch_pct)` |
| `extract_base_from_amount(amount, stretch_pct)` | `float` | Reverse math (for back-derivation) |
| `summarize_cascade_buffer(kpi, period, entries=None)` | `BufferSummary` | Bank-wide rollup with violation detection |

**3 dataclasses** all JSON-serializable via `asdict()`:

- `BufferCapConfig(kpi, max_stretch_pct, set_by, set_at, note)` — full audit trail
- `BufferValidation(kpi, proposed_pct, cap_pct, ok, reason)` — clear deny reasons
- `BufferSummary(kpi, period, cap_pct, cap_set_by, total_allocations, allocations_with_stretch, max_stretch_observed_pct, avg_stretch_pct, cap_utilization_pct, notes)` — rollup + violations

**Constants:**
- `MAX_REASONABLE_STRETCH_PCT = 0.50` — absolute cap on the cap (sanity bound)
- `MIN_STRETCH_PCT = 0.0`

**Persistence:** `data/buffer_caps.json` (dict keyed by KPI).

### Bank targets page — NEW MD-only expander

`🛡️ F2: Per-KPI stretch caps (MD only)` expander appears for MD users in Bank targets sub-tab. Contains:

- **Summary metrics**: KPIs with cap, avg cap %, max cap set
- **Set/update form**: KPI selector + stretch slider (0% to 50%, default 10%) + rationale text field + Set button → calls `set_buffer_cap()` with audit trail
- **Current caps table**: All caps with KPI, max stretch %, set by, set at, note
- **Remove control**: Select KPI + Remove button → calls `remove_buffer_cap()`

Logged via `audit_log("BUFFER_CAP_SET", uname, ...)` and `audit_log("BUFFER_CAP_REMOVED", uname, ...)`.

### NEW 6 FastAPI endpoints in `utils/api_cascade.py`

Cascade router now has **21 routes** (was 15). New buffer endpoints, all JWT-required via `Depends(get_current_user)`:

| Method | Path | Purpose |
|---|---|---|
| `GET`    | `/api/v1/cascade/buffer/caps`                       | All KPI caps |
| `GET`    | `/api/v1/cascade/buffer/cap/{kpi}`                  | Single cap |
| `PUT`    | `/api/v1/cascade/buffer/cap/{kpi}`                  | MD sets/updates cap |
| `DELETE` | `/api/v1/cascade/buffer/cap/{kpi}`                  | Remove cap |
| `POST`   | `/api/v1/cascade/buffer/validate`                   | Check proposed pct |
| `GET`    | `/api/v1/cascade/buffer/summary/{kpi}/{period}`     | Cascade-wide rollup |

**Pydantic models:** `BufferCapResponse`, `BufferCapSetRequest`, `BufferValidationRequest`, `BufferValidationResponse`, `BufferSummaryResponse`.

### Audit gate G300

Verifies engine API surface + AST zero-streamlit + data file present + cascade page UI integration + endpoints registered + Pydantic models defined + engine state 0/0/0/0 + end-to-end set/validate cycle works.

## What's deferred to v10.415+

- **F2 part B**: per-allocation stretch slider in `Set team targets` (so each cascade layer can actually use the cap when allocating downward, with the layer-hiding semantics)
- **F2 part C / F5 v10.417**: dual-view BSC render — primary metric shows stretch target, base shown aside in smaller font

The engine APIs (`compute_effective_amount`, `extract_base_from_amount`, `summarize_cascade_buffer`) are ready for both — v10.415 and v10.417 wire UI to the engine.

## Verified outcome

| Metric | v10.413 | v10.414 |
|---|---|---|
| Audit gates | 299 | **300** |
| v10.4xx tests | 191 | **206** (+15) |
| Verifier | 651 | **660** (+9) |
| Cascade endpoints exposed | 19 | **21** (+6 in router; 19 in shipped OpenAPI spec — refresh in v10.415) |
| React-ready cascade engines | 10 | **11** |
| Master prompt lockstep | 57 | **58** consecutive |
| G162 baseline | 4022 (106) | 4022 (**107** consecutive zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |
| React-readiness | 80% | **82%** |

## Architecture — what React sees

For a React component handling the MD's cap setting:

```typescript
// 1. Fetch all caps
const caps: BufferCapResponse[] = await api.get('/api/v1/cascade/buffer/caps');

// 2. MD sets a new cap
const newCap = await api.put('/api/v1/cascade/buffer/cap/PBT', {
  max_stretch_pct: 0.20,
  note: 'Q1 review allows 20% stretch buffer'
});

// 3. Manager-side: validate proposed stretch before submitting cascade
const validation = await api.post('/api/v1/cascade/buffer/validate', {
  kpi: 'PBT',
  proposed_pct: 0.15
});
if (!validation.ok) showError(validation.reason);
```

The same engine the Streamlit UI calls is the engine the React UI will call. No business logic divergence.

## 10 honest acknowledgements

1. **F2 is a multi-batch concern.** Setting it up properly (engine first, cap-setting UI, then allocation UI, then BSC display) keeps each batch single-concern. v10.414 ships the foundation that the next two batches build on.

2. **Existing `buffer_pct` in `bank_targets.json` was a stub.** The previous schema had `buffer_pct` on each bank target entry but nothing read or enforced it. The new engine canonicalizes the concept with full audit trail. Legacy data stays compatible (the new engine reads from `data/buffer_caps.json`; old `buffer_pct` in `bank_targets.json` is left untouched for now).

3. **The 50% absolute max is editorial.** No KPI cap can exceed 50% even if MD tries. This sanity bound prevents accidents (e.g., MD types 200 thinking it's 2%). Adjustable later if you want a higher ceiling.

4. **Uncapped KPIs deny non-zero stretch.** If MD hasn't set a cap, the engine refuses any stretch > 0 with reason "no cap configured; ask MD to set one". This forces explicit configuration before stretch can be added in v10.415.

5. **The validation API is reusable.** Same `validate_buffer()` will gate the per-allocation slider in v10.415 — slider locks if proposed_pct exceeds cap, with reason shown.

6. **The summary engine detects violations across the cascade.** Useful for v10.415+ when allocations have stretch_pct: `summarize_cascade_buffer` returns a `notes` list flagging any allocation that exceeds the cap, which can surface in a health dashboard view.

7. **AST guard enforces the discipline.** G300 specifically uses regex (not substring) to find actual import statements, so the docstring's mention of "import streamlit" doesn't false-trigger the gate.

8. **OpenAPI spec is one batch behind.** The shipped `docs/openapi_cascade_v10413.json` doesn't yet include the 6 new buffer endpoints. v10.415 will refresh the spec.

9. **No CascadeManager changes.** The engine reads `target_cascade.json` directly when needed (via `summarize_cascade_buffer`). `CascadeManager` is untouched — keeping single-concern and avoiding the central module's complexity.

10. **F4 was already done (v10.404).** Per your locked F-series numbering: F2=buffer, F3=retain auth, F4=regen preserve (DONE), F5=fixed greyed (DONE) and/or dual-view BSC. v10.414 = F2 part A. Next: v10.415 = F2 part B. Then v10.416 = F3. Then v10.417 = F5 (dual-view BSC) — or interleaved differently if you'd rather.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10414_patch.zip` on top of v10.413 state
3. Run `python scripts/verify_local_state.py` → expect **660/660**
4. Engine: `python utils/cascade_structure_engine.py` → **0/0/0/0**
5. Self-test the buffer engine directly: `python utils/cascade_buffer_engine.py` (runs 12 checks)
6. Launch Streamlit, navigate to Target Cascade → Bank setup → Bank targets, scroll past the metrics → see the **🛡️ F2: Per-KPI stretch caps** expander as MD
7. Set a cap (e.g., PBT at 15%) → confirms via toast → re-opens to show the caps table
8. (Optional) Start FastAPI: `python -m utils.api` → `http://localhost:8502/api/docs` → see new `/buffer/*` endpoints in Swagger UI
9. Tell me **"continue"** → v10.415 = F2 part B per-allocation stretch slider in Set team targets

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.406-v10.413~~ | ~~E1-E7 QA-Standards enhancements~~ | **DONE** |
| **v10.414** | **F2 part A: Cascade buffer engine + MD cap** | **DONE (this batch)** |
| v10.415 | F2 part B: per-allocation stretch slider in Set team targets | Next |
| v10.416 | F3: Per-line-manager retain authorization | Pending |
| v10.417 | F5: Dual-view BSC (primary=stretch, secondary=base aside) | Pending |
| v10.418 | Role weight renormalization (225/227 broken) | Pending |
| v10.419 | KPI library dedup follow-through | Pending |
| v10.420 | Backup retention cleanup | Pending |
| v10.421 | Retired test cleanup | Pending |
| v10.422 | Archived bank_target reconciliation | Pending |
| v10.423 | Pillar weights decision | Pending |
| v10.424-v10.426 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.427+ | React SPA build (CascadeManager split, CORS, WebSocket, Vite+TS+Tailwind, page-by-page port) | Pending |
