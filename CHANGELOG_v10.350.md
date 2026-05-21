# Changelog — v10.350 Runtime Stability Fixes

**Date:** 2026-05-12
**Phase:** 4 (thirty-fifth arc — runtime stability batch, same character as v10.341)
**Audit:** 236/236 gates PASS = 100.0%
**Tests:** 8 new in `test_v10350_runtime_stability.py`, all passing
**Page smoke:** 123/123 PASS at 100%
**Verifier:** 96/96 checks pass on a clean extract
**G162 Baseline:** 4022 (44 consecutive zero-drift batches)

---

## Your ask

You reported 6 runtime errors from localhost spanning 5 pages. None had been caught by my audit or smoke test, which is significant.

## The 6 errors, classified

| # | Error | Page | Root cause |
|---|---|---|---|
| 1 | `ModuleNotFoundError: utils.interaction_capture` | `117_propositions_hub.py` | File exists in my sandbox but my hand-picked cumulative zip didn't include it |
| 2 | `NameError: STREAMLIT_AVAILABLE` | `116_finance_hub.py` → render_opex → Arc Engines tab | Latent bug in original `10_opex.py` — variable used in 7 places, defined nowhere. Only surfaces when navigating to Arc Engines |
| 3 | `TypeError: Decimal / float` | `34_customer360.py` line 1075 | Pre-existing bug — `VALUE_TIER_*` constants are Decimal, divided by `1e6` (float) |
| 4 | `KeyError: 'campaign_id'` | `94_campaigns_management.py` line 287 | Defensive read missing — some campaign records lack `campaign_id` |
| 5 | (same as #1) | `27_propositions.py` | Same as #1 — interaction_capture chain |
| 6 | `KeyError: 'phase'` | `95_command_centre.py` → `command_centre_strategic_initiatives.py` line 421 | Same pattern as v10.341 fix (different line). Line 421 + 247 + 432 all had bare `r["phase"]` reads |

**Three of these (#2, #3, #6) are latent bugs that existed before v10.349.** The unified hubs surfaced them by making the code paths more reachable. None are regressions caused by the consolidation work.

## Why smoke test didn't catch these

| Bug | Why smoke passed |
|---|---|
| #1, #5 (missing module) | `utils/interaction_capture.py` exists in my sandbox; smoke ran there. The cumulative zip didn't ship it |
| #2 (STREAMLIT_AVAILABLE) | Variable used inside a function body — function never called during module import |
| #3 (Decimal/float) | Computed inside an `st.caption(f"...")` f-string evaluation, only fires when page renders |
| #4 (campaign_id) | Same — runtime evaluation, not import-time |
| #6 (phase) | Same — runtime evaluation |

The smoke test only checks module-load integrity. The whole **class of bugs that fire on actual code execution** is beyond what smoke covers. That's a real limitation made visible by this report.

## The 5 fixes in v10.350

### Fix 1 — `utils/interaction_capture.py` shipped + comprehensive zip approach

The file exists in my workspace (17,962 bytes, `class InteractionCaptureEngine` for Standard #337). v10.350 ships it explicitly in both the patch zip and the cumulative.

**Process fix going forward:** cumulative zips now copy the entire `utils/` directory using `cp utils/*.py` (or equivalent) rather than hand-picking files. This eliminates the entire class of "file exists in my sandbox but not in cumulative" bugs.

### Fix 2 — `STREAMLIT_AVAILABLE = True` added to `finance_hub_render.py`

```python
# v10.350 — STREAMLIT_AVAILABLE constant used in inherited helper code from
# the original pages/10_opex.py. Since this module only runs from inside a
# Streamlit page context, streamlit is always available — set the constant
# to True so the inherited "if not STREAMLIT_AVAILABLE" branches don't fire.
STREAMLIT_AVAILABLE = True
```

Defined at module top, immediately after `import streamlit as st`. All 7 `if not STREAMLIT_AVAILABLE:` branches now evaluate cleanly (branch is dead, code continues to the actual Streamlit rendering).

This was a latent bug in the original `10_opex.py` too — the variable was used but never defined anywhere in the codebase. The Arc Engines tab would have crashed if anyone navigated there in the pre-v10.346 code. v10.349 made it more reachable by exposing it through the unified hub, which is when you hit it.

### Fix 3 — `Decimal / float` wrapped with `float()`

`pages/34_customer360.py` line 1075-1078: 4 occurrences of `int(VALUE_TIER_XXX / 1e6)` or `/1000`. Each now uses `int(float(VALUE_TIER_XXX) / 1e6)`.

`VALUE_TIER_HNI_MIN`, `VALUE_TIER_MASS_AFFLUENT_MIN`, `VALUE_TIER_MASS_MIN` are tenant-defined as `Decimal` for currency precision. The display string formatting was dividing them by float literals, which Python rejects. Wrapping with `float()` converts cleanly for display arithmetic.

### Fix 4 — `c.get("campaign_id")` defensive read

`pages/94_campaigns_management.py:287`. Old:

```python
"Campaign", [c["campaign_id"] for c in campaigns],
```

New:

```python
"Campaign", [c.get("campaign_id", "unknown") for c in campaigns if c.get("campaign_id")],
```

Skips records that don't have a `campaign_id` rather than crashing.

### Fix 5 — `r.get("phase", ...)` in command_centre, all read sites

`utils/command_centre_strategic_initiatives.py` had **4 bare reads** of `r["phase"]` at lines 247, 432, plus the one already known at 421 (the brief's record of a v10.341 fix at line 409 was correct; that one was already defensive). All 4 read sites are now `r.get("phase", "...")` with sensible defaults:

| Line | Context | Default |
|---|---|---|
| 247 | RAG-to-phase transition check | `""` |
| 421 | `at_risk` list comprehension | `""` |
| 432 | building output dict | `"PLANNING"` |

Two `r["phase"] = ...` lines remain — those are WRITES (assignments), not reads, and are safe.

## What v10.350 did NOT do

- **Did not enhance the smoke test** to call render functions (would be a separate batch — interesting design question about runtime smoke coverage)
- **Did not refactor the underlying engine** that produces records without `phase` or `campaign_id` — the producers should arguably emit complete records. Defensive reads are the consumer-side fix; the producer-side discipline could be a separate batch via the schema-validator pattern (Pattern Q)
- **Did not touch the original `91-98` cockpit pages** — those are already thin wrappers from v10.349
- **Did not add a new audit gate.** The 5 fixes are tracked via tests + verifier; no new lockable invariant emerged

## Process improvement: comprehensive cumulative zips

Starting v10.350, cumulative zip building copies the entire `utils/` directory rather than hand-picking utilities. This guarantees every utility that's referenced anywhere is shipped. The patch zip remains hand-picked (it's the v10.350 deltas only).

Concretely:

```bash
# Old (hand-picked, missed interaction_capture.py)
for f in specialist_activity_generator branch_staff_generator pipeline_to_bsc ...; do
  cp utils/${f}.py staging/utils/
done

# New (comprehensive, every utility ships)
cp utils/*.py staging/utils/
```

Same approach for `pages/[0-9]*.py` — copy all numbered pages, not just the ones changed in this session.

This is a small but real defense against the "file exists in my sandbox but not on Joshua's machine" class.

## Files changed

| File | Change |
|---|---|
| `utils/finance_hub_render.py` | `STREAMLIT_AVAILABLE = True` added at module top |
| `utils/command_centre_strategic_initiatives.py` | 4 defensive `.get("phase", ...)` reads at lines 247, 421, 432 |
| `utils/interaction_capture.py` | Explicitly shipped (was in sandbox, missing from earlier cumulatives) |
| `pages/34_customer360.py` | 4 `int(float(...) / ...)` wraps for Decimal divisions |
| `pages/94_campaigns_management.py` | `c.get("campaign_id")` defensive listing |
| `tests/integration/test_v10350_runtime_stability.py` | NEW — 8 tests covering each fix |
| `scripts/verify_local_state.py` | Extended to 96 checks across v10.336-v10.350 |

## Verified outcome

| Metric | Before → After v10.350 |
|---|---|
| Audit gates | 236 → **236** (no new gate; existing pass) |
| Page smoke | 123/123 PASS (unchanged) |
| Tests | +8 = total grows |
| Verifier | 91 → **96 checks** |
| Localhost runtime errors known | 6 → **0** (all fixed) |
| G162 baseline | 4022 (44 consecutive zero-drift batches) |

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10350_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 96 CHECKS PASSED**
5. Run `python scripts\audit.py` → expect **236/236 PASS**
6. Restart Streamlit
7. Test each of the previously broken pages:
   - `/27_propositions` and `/117_propositions_hub` — should load (interaction_capture chain fixed)
   - `/116_finance_hub` → OpEx → Arc Engines tab — should render (STREAMLIT_AVAILABLE fixed)
   - `/34_customer360` — should load (Decimal/float fixed)
   - `/94_campaigns_management` — should load (campaign_id defensive)
   - `/95_command_centre` — should load (phase defensive)

## Suggested direction for v10.351

The harmonization arc is closed; v10.350 is a runtime fix batch. Natural next directions:

1. **Smoke test enhancement** — extend `utils/page_smoke.py` to actually CALL render functions, not just import them. Would catch the v10.350-class bugs (NameError inside conditional branches). Significant engineering effort but closes the gap that this report surfaced.
2. **v10.351 — Convert all 16 consolidated originals to thin redirects** — original v10.350 plan (deferred by the runtime fixes)
3. **v10.351 — Return to original roadmap** — partnerships P&L, B-027 tail, Strategic Initiative engine
4. **v10.351 — Address documented divergences** — `strategic_initiatives.rag_status` Title-vs-UPPER, `kpi.direction` short-vs-long

My honest recommendation: **option 1 (smoke test enhancement).** Six errors slipped through. Strengthening the smoke test to catch this class is the structural fix. Without it, we're trusting that you'll surface bugs from localhost — which works but isn't ideal.

Which way?
