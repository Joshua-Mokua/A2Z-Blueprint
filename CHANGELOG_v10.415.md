# Changelog — v10.415 F2 part B: per-allocation stretch tuner

**Date:** 2026-05-14
**Phase:** Phase 2c (architectural features) — F2 part B
**Audit:** G301 added (cumulative 301 gates)
**Tests:** 15/15 PASSED in `test_v10415_per_allocation_stretch.py`
**Regression:** 221/221 v10.4xx tests PASSED (206 + 15)
**Verifier:** 666/666 checks pass (660 → 666, +6 v10.415 checks)
**G162 baseline:** 4022 (108 consecutive zero-drift batches)
**Master prompt:** v4.57 → v4.58 (lockstep — 59 consecutive batches)

---

## What this batch is

Second of three batches landing your F2 architectural concern. v10.414 shipped the cap-setting surface (MD configures max stretch % per KPI). v10.415 wires the per-allocation slider so managers can actually use that cap when cascading downward.

The mechanics are complete after this batch. Only the BSC dual-view render (primary=stretch, secondary=base aside) remains — that's v10.417 (F5).

## What v10.415 built

### Engine extensions to `utils/cascade_buffer_engine.py`

Three new functions and one new dataclass. Module still ZERO streamlit imports (AST-verified by G300 + new G301 check). Discipline holds.

| Function | Signature | Purpose |
|---|---|---|
| `apply_stretch_to_allocations` | `(allocations, stretch_map, kpi) → StretchApplicationResult` | Apply per-allocation stretch with validation |
| `derive_base_for_allocation` | `(alloc) → float` | Back-derive base from amount + stretch_pct |
| `cascade_stretch_breakdown` | `(entries) → dict` | Cross-cascade base/effective/stretch rollup |

**`StretchApplicationResult` dataclass** (JSON-serializable):
```python
@dataclass
class StretchApplicationResult:
    kpi: str
    cap_pct: float
    total_allocations: int
    updated_count: int
    new_allocations: List[Dict[str, Any]]
    violations: List[Dict[str, Any]]
    new_total_amount: float
```

`apply_stretch_to_allocations` semantics:
- Walks each allocation; if `to_code` is in stretch_map, validates the new pct against MD's cap via `validate_buffer` from v10.414 (single source of truth)
- Valid entries: re-derives base via existing `amount / (1 + existing_stretch_pct)`, computes new `amount = base × (1 + new_stretch_pct)`, persists `stretch_pct` + `base_amount` fields
- Invalid entries: passthrough unchanged + appended to `violations` list with reason
- Untouched entries (no map entry): passthrough unchanged
- Atomic in spirit: violations don't poison the rest; caller chooses to save partial or reject all

### Set team targets — NEW expander `🛡️ Step 3 (optional) · F2 stretch tuning`

Sits **after** all base-save sections (per-report, per-group, per-branch, global). Operates on already-saved cascades. Lightweight; doesn't touch the complex data editor.

Flow:
1. Manager picks a KPI they've cascaded for
2. UI shows MD's cap for that KPI (if set)
3. For each direct report in the cascade: row with name + base amount + stretch slider (0% to cap%) + live-preview final amount
4. Apply button → calls `apply_stretch_to_allocations` → on success, persists via `casc.set_allocation(my_code, kpi, period, new_allocations, new_total_amount)` + logs `STRETCH_APPLIED` audit event

Edge cases handled:
- No cap set → warning shown ("ask MD to set one")
- No allocations yet → info shown ("save base cascade first")
- Single allocation over cap → row-level error shown; valid rows hold for re-apply

### NEW FastAPI endpoint

`POST /api/v1/cascade/buffer/apply` — cascade router now **22 routes** (was 21).

Request:
```json
{
  "kpi": "PBT",
  "allocations": [
    {"to_code": "100001", "to_name": "Alice", "amount": 100.0}
  ],
  "stretch_map": {"100001": 0.10}
}
```

Response (JSON-serializable):
```json
{
  "kpi": "PBT",
  "cap_pct": 0.20,
  "total_allocations": 1,
  "updated_count": 1,
  "new_allocations": [
    {"to_code": "100001", "to_name": "Alice", "amount": 110.0, "stretch_pct": 0.10, "base_amount": 100.0}
  ],
  "violations": [],
  "new_total_amount": 110.0
}
```

Same pattern: stateless. The endpoint validates and computes; caller persists.

### Allocation schema extension

Allocation records gain two **optional** fields:
- `stretch_pct: float` (0.0 default; what THIS allocation has on top of base)
- `base_amount: float` (the amount before stretch was applied)

Backward compatibility: absent fields mean no stretch. All v10.414-and-prior cascades continue to work — `derive_base_for_allocation` returns `amount` itself when `stretch_pct` is missing.

## Verified outcome

| Metric | v10.414 | v10.415 |
|---|---|---|
| Audit gates | 300 | **301** |
| v10.4xx tests | 206 | **221** (+15) |
| Verifier | 660 | **666** (+6) |
| Cascade endpoints | 21 | **22** |
| Master prompt lockstep | 58 | **59** consecutive |
| G162 baseline | 4022 (107) | 4022 (**108** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |
| React-readiness | 82% | **84%** |

## Architecture — what React sees

A React component implementing the stretch tuner:

```typescript
// 1. Get current cascade allocations from cascade engine
const cascade = await api.get(`/api/v1/cascade/rollup/${myCode}/2026`);

// 2. User adjusts sliders → build stretch_map
const stretchMap = { "100001": 0.10, "100002": 0.05 };

// 3. Validate + compute (does NOT persist)
const result = await api.post('/api/v1/cascade/buffer/apply', {
  kpi: 'PBT',
  allocations: cascade.allocations,
  stretch_map: stretchMap
});

// 4. Surface violations to user
if (result.violations.length > 0) {
  result.violations.forEach(v => showError(`${v.to_name}: ${v.reason}`));
}

// 5. On clean result, the caller persists (via a separate save endpoint
//    in a future batch, or via CascadeManager-like REST in v10.426+)
```

Same engine the Streamlit UI calls.

## 10 honest acknowledgements

1. **The expander pattern dodges the data editor complexity.** Set team targets has 5+ save mechanisms (per-report, per-group, per-branch, branch-bulk, global). Adding a stretch column to each would have been brittle. The Step 3 expander sits OUTSIDE all those save flows, operates on already-saved cascades. Cleaner separation.

2. **`apply_stretch_to_allocations` is stateless.** It computes, returns the updated list, returns violations. The caller (Streamlit page, or future React app, or batch script) decides whether to persist. Matches the API-first discipline locked in v10.412.

3. **Re-derivation handles re-tuning.** If an allocation already has stretch (say 10%), re-tuning to 5% correctly reverses out the 10% before applying the new 5%. The math is `new_amount = (existing_amount / (1 + existing_stretch)) × (1 + new_stretch)`.

4. **Violations don't poison the batch.** If 3 of 5 stretches are valid and 2 violate, the 3 valid ones return updated, the 2 violators return unchanged. The UI can show errors AND let the user fix and re-apply.

5. **No backward incompat.** Old allocations without `stretch_pct` work unchanged — `derive_base_for_allocation` falls back to returning the amount itself. v10.405-and-prior cascades continue to flow through everything.

6. **The UI is a slim wrapper.** ~120 lines added to cascade.py for the entire stretch tuning UI. All math lives in the engine.

7. **`base_amount` is persisted explicitly.** Even though it's derivable from `amount / (1 + stretch_pct)`, storing it explicitly aids debugging and prevents floating-point drift across re-tunings.

8. **The v10.414 test had to be relaxed.** It expected exactly 6 buffer routes; v10.415 added a 7th (/buffer/apply). Test now asserts `>= 6` with the originally-required 4 paths still verified. Pattern for future buffer expansion.

9. **OpenAPI spec is two batches behind.** Shipped at v10.413 (19 endpoints). New buffer endpoints from v10.414 (6) and v10.415 (1) not in the JSON file yet. Refresh planned alongside another batch.

10. **F2 mechanics are now done.** v10.414 cap-setting + v10.415 stretch tuning = full F2 capability minus the dual-view BSC render. The dual-view is essentially display logic — the data exists in `base_amount` and `stretch_pct` per allocation, ready for v10.417 to read.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10415_patch.zip` on top of v10.414 state
3. `python scripts/verify_local_state.py` → expect **666/666**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/cascade_buffer_engine.py` → engine self-test (14 checks, includes new stretch logic)
6. Launch Streamlit → Target Cascade → Cascade & allocate → Set team targets
7. Save a base cascade for some KPI (existing flow)
8. Scroll to bottom → see `🛡️ Step 3 (optional) · F2 stretch tuning` expander
9. Pick KPI → adjust stretch sliders per report → see live final amounts → Apply
10. (Optional) Start FastAPI → `http://localhost:8502/api/docs` → see new `/buffer/apply` endpoint
11. Tell me **"continue"** → v10.416 = F3 per-line-manager retain authorization

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.414~~ | ~~F2 part A: Buffer engine + MD cap~~ | **DONE** |
| **v10.415** | **F2 part B: Per-allocation stretch tuner** | **DONE (this batch)** |
| v10.416 | F3: Per-line-manager retain authorization | Next |
| v10.417 | F5: Dual-view BSC (primary=stretch, secondary=base aside) | After |
| v10.418 | Role weight renormalization (225/227 broken) | Pending |
| v10.419 | KPI library dedup follow-through | Pending |
| v10.420 | Backup retention cleanup | Pending |
| v10.421 | Retired test cleanup | Pending |
| v10.422 | Pillar weights decision | Pending |
| v10.423-v10.425 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.426+ | React SPA build | Pending |
