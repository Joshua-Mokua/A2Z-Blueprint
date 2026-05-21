# Changelog — v10.356 Master Prompt Sync v4.0 + Cycle Break Correction

**Date:** 2026-05-12
**Phase:** 4 (forty-first arc — anti-drift recovery)
**Audit:** G242 added (passes in 0.0s isolated). G128 now PASS after cycle break.
**Tests:** 12/12 PASSED in `test_v10356_master_prompt_sync.py`
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 137/137 checks pass on a clean extract
**G162 Baseline:** 4022 (50 consecutive zero-drift batches — milestone)

---

## Your ask

> "Sync the master prompt to v4.0 then we work together to ensure we never drift and move to bring this system as is required"

Two parts in one batch (explicitly flagged per Rule N2):

1. **Master prompt sync** — 240 versions of accumulated drift between v3.9 (covering v10.115) and v4.0 (covering v10.355) reconciled. This is the constitutional layer. Operating from a stale prompt invites drift in the wrong direction.

2. **Cycle break correction** — discovered during the system review at session start. v10.355 placed `refresh_yoy()` INSIDE `actuals_engine.compute_actuals_from_cbs`, creating a `actuals_engine → live_actuals → cbs_baseline → actuals_engine` cycle that **G128 flagged as a structural regression**. The cycle wouldn't crash Python at runtime (all lazy-imported in function bodies) but the structure audit correctly flagged it architecturally. v10.356 inverts: callers (`pages/7_admin.py` admin refresh; `app.py` startup is next) call `refresh_yoy` AFTER `compute_actuals_from_cbs` returns. The lower data-extraction layer no longer depends on the higher orchestration layer.

These are normally separate concerns. They're combined here because:
- The cycle break is a v10.355 correction that should land immediately
- The master prompt sync is the anti-drift recovery the session explicitly asked for
- Both touch the same review surface — examining the system end-to-end before the virtual-bank live bring-up
- Splitting would have meant shipping v10.356 (cycle break) → v10.357 (master prompt) consecutively; the session naturally synthesized them

The CHANGELOG transparently flags this exception per Rule N2.

## Part 1 — Master Prompt v4.0

### What was lost during the drift

`docs/Master_Prompt_v3.9.md` covered v10.115 — written in the era of 143 audit gates, 16 utility modules, 89 numbered pages, ~56K LOC. By v10.355 we had 241 gates, 429 utility modules, 123 numbered pages, 5 consolidated hubs, the smoke trio, the CBS baseline + YoY mechanism. Operating from v3.9 meant:

- New batches couldn't cite their place in the platform's reality (which gates? which standards? which loops?)
- "Verified gaps" section listed gaps that closed 200 batches ago
- "Codebase metrics" line wrong by an order of magnitude
- No mention of the harmonization arc, smoke trio, CBS-wired actuals — major work invisible to anyone reading the prompt fresh
- The lockstep ratchet (v3.9 → v3.10 every batch) silently disabled

### What v4.0 establishes

**Master prompt is now `docs/Master_Prompt_v4.0.md`** (575 lines, 24KB). Structural changes from v3.9:

| Section | What changed |
|---|---|
| Header | Version v3.9 → v4.0. Explicit "anti-drift resync" framing in the opening paragraph. |
| Charter §1-§12 | Preserved verbatim (the constitution remains correct) |
| Charter §2 (Football Team Test) | Status updated: **"NOT YET PASSING. v10.354 + v10.355 laid the foundation that makes this test verifiable. The mechanical chain exists; end-to-end live verification is the next bring-up objective."** |
| Charter §3 (feedback loops) | Updated: **15/15 WIRED** at v10.355 (vs 5/15 at v3.9 baseline) |
| Charter §4 (system stocks) | Updated: **6/6 have snapshot accessors wired with demo defaults**. Next maturity: wire to live CBS/FLEXCUBE via baseline structure. |
| State of play (Current version) | v10.115 narrative replaced with v10.355 narrative covering the v10.116-v10.355 arc |
| Codebase metrics | Verified counts (429 utils, 123 pages, 36 scripts, 217 data files, 11 schemas, 106 integration tests, 272 CHANGELOGs, 55 docs) |
| Audit gates | 143 → **241** with key milestones (G128, G143, G162, G230, G231, G232-G236, G237, G238, G239, G240, G241) |
| Smoke trio | NEW section documenting G231 + G238 + G239 (didn't exist at v3.9) |
| Verifier | NEW reference (didn't exist at v3.9) |
| Standards | 265 → **330** across 27 categories with full breakdown |
| Mandatory standards | **11 standards** (was 11; preserved verbatim including #11 Financial accounting honesty) |
| Anti-drift discipline | NEW section codifying the lockstep ratchet that broke between v3.9 and v4.0 |
| Verified gaps | Updated: 9 closed gaps strikethrough; 7 open/partially-closed gaps listed honestly |
| Quality gates | Updated audit cadence and smoke trio integration |
| Conventions | Added: smoke trio details, dynamic mock modes, dated-archive pattern, KPI→baseline mapping |
| No-fly zones | Added: CBS baseline files, YoY sidecar, 5 consolidated hubs, smoke trio, master prompt sync discipline |
| Version history | Lockstep entries v3.0 → v3.9 preserved verbatim; **v4.0 entry explicitly documents the 240-version drift recovery** |

The constitutional layer (Charter §1 "One Question", Charter §2 Football Team Test, 11 mandatory standards, 13 bounded contexts, 6 stocks, 15 loops, 8 invariants) is preserved exactly. **Drift recovery is a state update, not a constitutional rewrite.**

### G242 — anti-drift lockstep gate

NEW audit gate `gate_master_prompt_sync`. Validates:

1. `docs/Master_Prompt_v<MAJOR>.<MINOR>.md` exists
2. The newest master prompt references the most recent CHANGELOG batch within a **5-batch tolerance window** (allows in-flight work to ship master prompt update last in the workflow)
3. Charter §1 "One Question" is present verbatim
4. All 11 mandatory standards present by heading

**G242 runs in 0.0s isolated.** Zero cost. Locks the lockstep — if a future batch ships without updating the master prompt, G242 fires once the drift exceeds 5 batches.

This is **Pattern R5 — Ratchets, not heroics** applied to anti-drift. The discipline that erodes silently between v3.9 and v4.0 now has a tripwire.

## Part 2 — Cycle Break Correction

### Why G128 was failing

At session start, G128 returned `passed=False` with 1 violation:

```
CIRCULAR_IMPORT @ utils.actuals_engine: Circular import detected through 3 modules
```

Tracing it:

```
actuals_engine.compute_actuals_from_cbs (line 321):
    from utils.live_actuals import refresh_yoy        ← cycle starts

live_actuals (anywhere it's imported):
    [pulls in cbs_baseline]

cbs_baseline.snapshot_baseline:
    from utils.actuals_engine import (
        aggregate_cbs_by_rm, aggregate_cbs_by_branch, ...  ← cycle closes
    )
```

All three imports were inside function bodies (lazy), so Python tolerated them at runtime. But the structure audit's static analysis correctly flags the cycle architecturally: **a lower data-extraction layer (actuals_engine) was depending on a higher orchestration layer (live_actuals)**. The dependency direction was wrong.

### The fix

`actuals_engine.compute_actuals_from_cbs` no longer imports `live_actuals.refresh_yoy`. The YoY refresh moved to the caller side:

`pages/7_admin.py` admin refresh button now calls:

```python
_result = _cac2(force=True)  # compute_actuals_from_cbs
if _result.get("success"):
    try:
        from utils.live_actuals import refresh_yoy
        _yoy = refresh_yoy(actuals_path=_result.get("path"))
        _result["yoy"] = {
            "mapped_count": _yoy.get("mapped_count", 0),
            "baseline_date": _yoy.get("baseline_date", "n/a"),
        }
    except Exception:
        pass  # YoY refresh is best-effort
```

`app.py` `_auto_load_cbs_data` is the next callsite that should orchestrate this — currently it reads pre-existing actuals rather than computing them, so the YoY refresh hook there is a v10.357+ addition.

**G128 now passes** (8.9s, 0 violations). Smoke trio still green. All 31 tests in v10.354 + v10.355 still pass (with one test updated to reflect the inverted wiring).

### Files changed in Part 2

| File | Change |
|---|---|
| `utils/actuals_engine.py` | Removed `from utils.live_actuals import refresh_yoy` block. Function ends with the original return statement; YoY summary is now caller-side. |
| `pages/7_admin.py` | Admin refresh button now calls `refresh_yoy` AFTER `compute_actuals_from_cbs` returns. |
| `tests/integration/test_v10355_live_actuals.py` | Updated `test_v10355_compute_actuals_calls_refresh_yoy` to assert the inverted wiring. |
| `scripts/verify_local_state.py` | Verifier check updated to assert the cycle break. |

## Verified outcome

| Metric | Before → After v10.356 |
|---|---|
| Audit gates | 241 → **242** (G242 added) |
| G128 (structure audit) | **FAIL → PASS** |
| Master prompt | v3.9 (covering v10.115) → **v4.0 (covering v10.355, drift acknowledged)** |
| Page smoke | 123/123 PASS (preserved) |
| Static AST | 0 findings (preserved) |
| Dynamic render | 14/14 effective PASS (preserved) |
| Tests | +12 in v10.356 file, all passing |
| Verifier | 130 → **137 checks** |
| G162 baseline | 4022 (**50 consecutive zero-drift batches** — milestone) |

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10356_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 137 CHECKS PASSED**
5. Read `docs\Master_Prompt_v4.0.md` — this is now THE canonical prompt. The v3.9 file in `docs/` stays for historical reference but should not be used as the active prompt.
6. (Optional, takes >5min) Run audit → expect **242/242 PASS**
7. Restart Streamlit — verify the BSC scorecard still shows the YoY expander after the header cards (the cycle break is internal; the user-facing behavior is unchanged)

## Honest acknowledgements

1. **Two concerns in one batch.** Rule N2 says single-purpose batches. This batch combines master prompt sync (Part 1) with the cycle break (Part 2). Both were discovered during the same system review and naturally synthesized. Splitting would have meant a v10.356 (cycle break only) + v10.357 (master prompt only) sequence; the synthesis here is cleaner. Flagged transparently per Rule N2.

2. **`app.py` _auto_load_cbs_data not yet wired for YoY refresh.** That call site reads pre-existing actuals rather than computing them. The hook there is a v10.357+ addition. For now, only the admin refresh button triggers YoY regeneration. CBS data changes that go through `app.py` startup will reflect in actuals but YoY won't automatically refresh until either (a) the admin button is clicked or (b) v10.357 adds the hook.

3. **G242 tolerance window is 5 batches.** This allows in-flight work to ship master prompt update LAST in the workflow without immediately failing the gate. The risk: a batch could ship without master prompt update, technically passing G242 if only 4 newer batches exist. The mitigation: G242 fires once drift exceeds 5, which is enough to catch sustained discipline erosion. Tighter tolerance (drift ≤ 1) would be possible but pedantic.

4. **Master prompt v3.9 still in `docs/`.** I kept it rather than deleting. Historical reference. The active prompt is v4.0. Future v4.x replaces v4.0 in the same directory; v3.x files remain as historical artifacts.

5. **240-version drift acknowledgment is honest but doesn't undo the past.** The v10.116-v10.355 batches shipped without master prompt sync. Their CHANGELOGs are individually correct; the constitutional record was incomplete. v4.0 captures the current state; the rebuild of "what was in each prompt version through v10.355" is not possible without rewriting history. Going forward, the lockstep holds.

6. **Football Team Test remains NOT YET PASSING.** v10.354 + v10.355 + v10.356 lay the foundation. The end-to-end live verification (teller action → MD ROE tile under load) is the v10.357+ virtual-bank live bring-up objective. The master prompt now states this explicitly rather than implying the test passes.

## Suggested direction for v10.357

You explicitly asked for "we work together to ensure we never drift and move to bring this system as is required" — the virtual-bank live bring-up.

The natural v10.357 candidate is **the first concrete step toward the live bring-up**. Options:

1. **v10.357 — Virtual bank module inventory + readiness audit** — scan the existing `utils/virtual_bank*.py` (3,207 lines combined) and produce an honest readiness report. Which modules work today? Which are scaffolding? What's the dependency graph between them? This is reconnaissance before action.

2. **v10.357 — Football Team Test end-to-end harness** — synthetic teller action → trace through CBS update → actuals refresh → YoY recompute → BSC tile change. One automated test that fires the entire vertical. If it passes, we know the chain works; if it fails, we have a concrete failing test to drive fixes.

3. **v10.357 — System stocks live wiring** — wire the 6 stock snapshot accessors from demo defaults to live CBS-baseline data. This is the architectural "next step" the v3.9 charter foreshadowed and v4.0 now explicitly calls out.

4. **v10.357 — CBS-wired actuals arc closure (item 4 / PBT from CBS)** — the originally-planned v10.356. Now bumped to v10.357 because v10.356 became the master-prompt-sync + cycle-break correction. PBT computation from CBS transactions closes the arc.

5. **v10.357 — Audit performance optimization** — full audit takes >5 min. Caching for slow gates, parallel execution. Not urgent but real.

My honest recommendation: **option 1** (virtual bank readiness audit) before action. Going straight to (2) the Football Team Test harness without knowing the virtual bank's actual state risks chasing a moving target. Reconnaissance is cheap; action without reconnaissance is expensive.

After option 1 we'd have a concrete picture of what works, what doesn't, and a roadmap with realistic batch boundaries. Then options 2-4 sequence naturally.

Which way?
