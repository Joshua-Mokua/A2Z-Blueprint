# Changelog — v10.418 cascade-validation surgery (F3 integration)

**Date:** 2026-05-14
**Phase:** Phase 2c→2d bridge — F3 integration completes
**Audit:** G304 added (cumulative 304 gates)
**Tests:** 15/15 PASSED in `test_v10418_cascade_validation_surgery.py`
**Regression:** 268/268 v10.4xx tests PASSED (253 + 15)
**Verifier:** 689/689 checks pass (682 → 689, +7 v10.418 checks)
**G162 baseline:** 4022 (111 consecutive zero-drift batches)
**Master prompt:** v4.60 → v4.61 (lockstep — 62 consecutive batches)

---

## What this batch is

The F3 integration batch. v10.416 shipped the retain-authorization surface (boss grants/revokes per direct report) but explicitly deferred the cascade-validation rule change. v10.418 closes that gap.

**Key insight:** The "must total 100% cascade" rule was never a hard save-time validation. It was a soft display rule — coverage % shown in red when under 50%, orange when 50-95%, green when ≥95%. So the "surgery" is at the display + audit layer, not in the save logic. Cleaner than expected.

## What v10.418 built

### Engine extension to `utils/cascade_retain_engine.py`

Still zero streamlit imports.

**`compute_allocation_compliance(staff_code, kpi, period, total_target, allocated_sum)` → `AllocationCompliance`**

Returns one of 5 status values:

| Status | Meaning | compliance_ok |
|---|---|---|
| `fully_cascaded` | allocated == total (within 0.1% tolerance) | ✓ True |
| `retained_authorized` | allocated < total AND boss granted retain auth | ✓ True |
| `under_no_auth` | allocated < total AND no auth (or explicit revoke) | ✗ False |
| `over_allocated` | allocated > total (auth doesn't matter) | ✗ False |
| `no_target` | total ≤ 0 | ✗ False |

`AllocationCompliance` dataclass (JSON-serializable):

```python
@dataclass
class AllocationCompliance:
    staff_code: str
    kpi: str
    period: str
    total_target: float
    allocated_sum: float
    retained_amount: float        # max(0, total - allocated) — only set on retained_authorized
    retained_pct: float           # retained / total
    coverage_pct: float           # allocated / total
    has_retain_auth: bool
    status: str                   # one of the 5 above
    compliance_ok: bool
    note: str                     # explanatory text
```

### Cascade page — compliance-aware coverage display

The Health & coverage tab's coverage table now has a Status column:

- **"✓ Fully cascaded"** (green) — allocated == total
- **"✓ Retained X"** (green) — under-allocated WITH retain auth, X = retained amount
- **"⚠ Under-cascaded"** (red) — under-allocated WITHOUT auth (legit violation)
- **"✗ Over-allocated"** (red) — allocated > total
- **"— No target"** (grey) — total ≤ 0

The existing Coverage column still shows percentage; the Status column tells the manager **whether their coverage is acceptable** given their authorization. A BOM with retain auth at 70% coverage now sees a green "✓ Retained 30M", not a red flag.

### NEW FastAPI endpoint

`POST /api/v1/cascade/retain/compliance` — cascade router now **29 routes**.

Stateless: caller provides staff_code, kpi, period, total_target, allocated_sum. Engine looks up retain auth, returns compliance verdict.

Pydantic: `ComplianceCheckRequest`, `ComplianceCheckResponse`.

### What this batch did NOT change

- **No save-time validation change.** The cascade-save logic (`CascadeManager.set_allocation`) accepts whatever the UI submits. Always has. The "100% rule" was display-only.
- **No cascade health engine update.** `cascade_health_engine.py` from v10.411 still flags under-allocation as part of its rollup. A follow-up batch could update it to skip retained_authorized cascades — not in this batch's scope.
- **BSC scorecard table** still doesn't show compliance. v10.424 on the roadmap is the BSC dual-view + compliance refresh in `pages/1_perform.py`.

## Verified outcome

| Metric | v10.417 | v10.418 |
|---|---|---|
| Audit gates | 303 | **304** |
| v10.4xx tests | 253 | **268** (+15) |
| Verifier | 682 | **689** (+7) |
| Cascade endpoints | 28 | **29** (+1) |
| Master prompt lockstep | 61 | **62** consecutive |
| G162 baseline | 4022 (110) | 4022 (**111** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |
| React-readiness | 88% | **88%** (no engine count change) |

## Architecture — what React sees

For the boss's compliance dashboard view:

```typescript
const compliance = await api.post('/api/v1/cascade/retain/compliance', {
  staff_code: 'BOM001',
  kpi: 'PBT',
  period: '2026',
  total_target: 100_000_000,
  allocated_sum: 70_000_000
});

// compliance.status === 'retained_authorized' if BOM001 has auth
// compliance.compliance_ok === true
// compliance.retained_amount === 30_000_000
// compliance.note === "retained 30.0% under boss authorization"
```

Same engine the Streamlit page calls.

## 10 honest acknowledgements

1. **The surgery was lighter than expected.** I went looking for a hard save-time validation to relax. There wasn't one. The rule was always display-only via the coverage % colouring. Touch the display, the integration is done.

2. **`retained_authorized` is a positive status.** Green like `fully_cascaded`. This is the design intent: when the boss has authorized retention, under-allocation is *the expected outcome*, not a problem.

3. **`under_no_auth` is the actual violation.** Red. Shows up when manager didn't cascade everything AND doesn't have authorization to retain. This is what a CFO audit should care about.

4. **Over-allocation ignores retain auth.** If allocated > total, that's always a violation regardless of authorization. Auth is about retention, not over-cascade.

5. **0.1% tolerance band.** For floating-point rounding. 100.0 ~= 100.05 ~= 99.95 all count as fully_cascaded. Stops false positives from numeric noise.

6. **Explicit revoke is treated as no auth.** If boss set `can_retain=False`, the manager doesn't have authorization — under-allocation flags as `under_no_auth`. The auth record exists but its content denies retention.

7. **The display table grew a column.** The Health & coverage tab now has Manager, KPI, Coverage, Status (was 3 columns). Slightly wider, much more meaningful.

8. **`retained_amount` is only non-zero on `retained_authorized`.** Other statuses report retained_amount=0 even when allocated < total — they don't *deserve* to count it as legitimate retention.

9. **The FastAPI endpoint is stateless.** Doesn't read target_cascade.json. Caller provides the numbers. This keeps the engine clean and lets the React frontend compute compliance from rollups already in hand without re-fetching.

10. **F3 is now fully wired.** Surface (v10.416) + integration (v10.418). The other F-series concerns wire automatically as their UIs land. No deferred work for F3 anymore.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10418_patch.zip` on top of v10.417 state
3. `python scripts/verify_local_state.py` → expect **689/689**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/cascade_retain_engine.py` → engine self-test (16 checks)
6. Set up a test scenario:
   - Log in as Branch Manager → grant retain auth to a BOM (Step 4 expander)
   - Log in as that BOM → cascade some PBT but only 70% of what was allocated
   - Open Health & coverage → see "✓ Retained X" (green) in Status column
7. Compare: cascade that's under-allocated without auth shows "⚠ Under-cascaded" (red)
8. Tell me **"continue"** → v10.419 = role weight renormalization (225/227 broken roles) — Phase 2d data integrity housekeeping

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.414-v10.417~~ | ~~F-series~~ | **DONE** |
| **v10.418** | **Cascade-validation surgery (F3 integration)** | **DONE (this batch)** |
| v10.419 | Role weight renormalization (225/227 broken) | Next — opens Phase 2d |
| v10.420 | KPI library dedup follow-through | Pending |
| v10.421 | Backup retention cleanup (122 MB) | Pending |
| v10.422 | Retired test cleanup | Pending |
| v10.423 | Pillar weights decision (68/14/6/12 vs Kaplan-Norton 40/25/25/10) | Pending |
| v10.424 | BSC scorecard dual-view + compliance in pages/1_perform.py | Pending |
| v10.425-v10.427 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.428+ | React SPA build | Pending |
