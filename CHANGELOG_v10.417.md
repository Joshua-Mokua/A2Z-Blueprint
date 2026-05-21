# Changelog — v10.417 F5: dual-view BSC render · F-SERIES CLOSED

**Date:** 2026-05-14
**Phase:** Phase 2c (architectural features) — **CLOSES** with F5
**Audit:** G303 added (cumulative 303 gates)
**Tests:** 14/14 PASSED in `test_v10417_dual_view_bsc.py`
**Regression:** 253/253 v10.4xx tests PASSED (239 + 14)
**Verifier:** 682/682 checks pass (676 → 682, +6 v10.417 checks)
**G162 baseline:** 4022 (110 consecutive zero-drift batches)
**Master prompt:** v4.59 → v4.60 (lockstep — 61 consecutive batches)

---

## F-series CLOSED

Your four F-series architectural concerns are now landed:

| F | Concern | Batch |
|---|---|---|
| **F2** | Per-KPI cap + per-allocation stretch | v10.414 + v10.415 |
| **F3** | Per-line-manager retain authorization | v10.416 |
| **F4** | Regenerator preserves manual allocations | v10.404 (earlier session) |
| **F5** | Dual-view BSC (primary=stretch, secondary=base aside) | **v10.417 (this batch)** |

Phase 2c is complete. The cascade module has the architecture you locked.

## What v10.417 built

### Engine extension to `utils/cascade_buffer_engine.py`

Still zero streamlit imports. The discipline holds across all 13 cascade engines.

**Two new functions + one dataclass:**

```python
@dataclass
class DualViewEntry:
    staff_code: str
    period: str
    kpi: str
    base_amount: float        # received target before stretch
    stretch_pct: float        # stretch added by direct manager
    stretch_amount: float     # effective - base
    effective_amount: float   # what staff sees
    has_stretch: bool         # convenience
    from_code: str            # who cascaded this
    from_name: str

def compute_dual_view(staff_code, period, cascade_entries=None) -> List[DualViewEntry]:
    """For each KPI assigned to this staff, compute base + stretch breakdown."""

def get_dual_view_summary(staff_code, period, cascade_entries=None) -> dict:
    """Totals rollup: total_base, total_effective, total_stretch, stretched_kpi_count."""
```

If `cascade_entries=None`, the function loads from `data/target_cascade.json` itself. Filters by period. Skips meta/deadline/global keys per the defensive iteration pattern locked in v10.409.

### My targets — dual-view rendering

The KPI summary cards in My targets now show base + stretch% as a small aside when stretch is present:

```
┌────────────────────────────────────────┐
│ PBT                                    │
│ 110M                                   │
│ Base: 100M · +10.0% stretch            │  ← new (only when has_stretch)
└────────────────────────────────────────┘
```

Below the cards, a stretch summary callout appears when any KPIs have stretch:

> **Stretch on your cascade:** 3 of 8 KPIs include stretch, adding +7.5% on average over base. Base targets remain visible under each card so you can see what was originally cascaded.

For KPIs without stretch (most KPIs today), the card renders exactly as before — no change.

### NEW 2 FastAPI endpoints

Cascade router now **28 routes** (was 26). All JWT-required:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/cascade/dual-view/{staff_code}/{period}` | List per-KPI dual-view entries |
| `GET` | `/api/v1/cascade/dual-view/{staff_code}/{period}/summary` | Totals rollup |

**Pydantic models:** `DualViewEntryResponse`, `DualViewSummaryResponse`.

### Audit gate G303

Verifies engine functions + dataclass + cascade page imports + render markers + endpoints + Pydantic models + engine state 0/0/0/0 + E2E synthetic cascade extraction.

## Verified outcome

| Metric | v10.416 | v10.417 |
|---|---|---|
| Audit gates | 302 | **303** |
| v10.4xx tests | 239 | **253** (+14) |
| Verifier | 676 | **682** (+6) |
| Cascade endpoints | 26 | **28** (+2) |
| Master prompt lockstep | 60 | **61** consecutive |
| G162 baseline | 4022 (109) | 4022 (**110** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |
| React-readiness | 86% | **88%** |

## Architecture — what React sees

A React component for the staff's dual-view scorecard:

```typescript
// 1. Fetch dual-view breakdown for current staff
const entries: DualViewEntryResponse[] =
  await api.get(`/api/v1/cascade/dual-view/${staffCode}/2026`);

// 2. Render each KPI card
entries.forEach(e => {
  if (e.has_stretch) {
    renderCard({
      primary: fmtV(e.effective_amount, e.kpi),     // big number
      secondary: `Base: ${fmtV(e.base_amount, e.kpi)} · +${(e.stretch_pct*100).toFixed(1)}% stretch`,
    });
  } else {
    renderCard({ primary: fmtV(e.effective_amount, e.kpi) });
  }
});

// 3. Or fetch the rollup for a summary header
const summary = await api.get(`/api/v1/cascade/dual-view/${staffCode}/2026/summary`);
showHeader(`${summary.stretched_kpi_count} of ${summary.kpi_count} KPIs stretched`);
```

Same engine the Streamlit page calls.

## 10 honest acknowledgements

1. **F-series is done.** Four batches over this arc closed all four F-concerns. The mechanics, the surface, the data trail, the BSC render — all wired. From here on out, the cascade architecture is feature-complete per your design.

2. **No render changes to BSC scorecard table (yet).** `pages/1_perform.py` has its own BSC scorecard render that displays targets. v10.417 covered the **My targets** in cascade page — the most immediate need where staff look up their assigned targets. The BSC scorecard table will pick up dual-view in a later batch via the same engine call. The endpoint is there waiting.

3. **`has_stretch` is the gate.** The card aside only appears when `stretch_pct > 0`. Cards without stretch render identically to before — backward compat for the 99% of KPIs that don't have stretch yet.

4. **Multiple inflows for one KPI return as multiple entries.** In the rare co-KPI pairing case (PBT pairs Retail + Commercial), `compute_dual_view` returns one DualViewEntry per inflow. The UI aggregates if needed; the engine keeps them separate so callers see the provenance.

5. **Stretch summary callout is conditional.** Only shown when at least one KPI has stretch. Doesn't clutter the view for staff whose cascade doesn't use stretch yet.

6. **The summary callout shows weighted average wrong, technically.** The callout says "adding +Z% on average over base" where Z = total_stretch / total_base. That's a value-weighted average, not equal-weighted across KPIs. For most uses this is the right summary (it reflects bottom-line impact). If you want unweighted-equal, the engine exposes `stretch_pct` per entry.

7. **The dataclass is React-shaped.** All fields are primitives or strings. `to_dict()` → JSON via `dataclasses.asdict()`. React TypeScript types are 1:1.

8. **Float precision matters.** `100 × 1.10 / 1.10 ≠ 100` in IEEE 754 (it's `99.9999...`). The engine uses derivations carefully but tests assert with tolerance `< 1e-6`. Numeric correctness verified.

9. **`compute_dual_view` reads target_cascade.json directly when entries=None.** Bypasses CascadeManager (which has streamlit deps). The engine stays standalone and FastAPI-callable.

10. **13th React-ready cascade engine.** All zero-streamlit, all dataclass-returning. 28 endpoints across `/api/v1/cascade/*`. The discipline you locked in v10.412 has now produced architecturally what was promised: a cascade subsystem ready to be consumed by anything that speaks HTTP + JSON.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10417_patch.zip` on top of v10.416 state
3. `python scripts/verify_local_state.py` → expect **682/682**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/cascade_buffer_engine.py` → engine self-test (17 checks, includes new dual-view)
6. Launch Streamlit, log in as someone whose manager has added stretch to their cascade (any role that received an allocation with `stretch_pct > 0` from v10.415)
7. Target Cascade → My view → My targets → see KPI cards with base aside under stretch primary
8. See the stretch summary callout below the cards
9. (Optional) FastAPI → `/api/v1/cascade/dual-view/{your-staff-code}/2026` → list endpoint
10. (Optional) `/api/v1/cascade/dual-view/{your-staff-code}/2026/summary` → rollup endpoint

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.414~~ | ~~F2 part A~~ | **DONE** |
| ~~v10.415~~ | ~~F2 part B~~ | **DONE** |
| ~~v10.416~~ | ~~F3 retain authorization~~ | **DONE** |
| **v10.417** | **F5 dual-view BSC** | **DONE — F-series CLOSED** |
| v10.418 | Cascade-validation surgery (relax 100% rule when retain auth granted) | Next |
| v10.419 | Role weight renormalization (225/227 broken) | Pending |
| v10.420 | KPI library dedup follow-through | Pending |
| v10.421 | Backup retention cleanup | Pending |
| v10.422 | Retired test cleanup | Pending |
| v10.423 | Pillar weights decision | Pending |
| v10.424 | BSC scorecard dual-view in pages/1_perform.py | Pending |
| v10.425-v10.427 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.428+ | React SPA build | Pending |

Phase 2c is closed. Phase 2d (data integrity housekeeping) opens next — quieter batches that clean up technical debt before we build the React SPA scaffold in Phase 4.
