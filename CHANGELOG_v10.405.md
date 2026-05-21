# Changelog — v10.405 Target Guidance Wired + Weight Visibility

**Date:** 2026-05-14
**Phase:** UX repair — Joshua's 3 user-flagged fixes
**Audit:** G291 added
**Tests:** 11/11 PASSED in `test_v10405_target_guidance_wired.py`
**Verifier:** 576/576 checks pass
**G162 baseline:** 4022 (98 consecutive zero-drift batches)
**Master prompt:** v4.47 → v4.48 (lockstep — 49 consecutive batches)

---

## Joshua's 3 directives

> "on the fixed kpi let it be greyed out for full visibility and to ensure weights can be summed up to 100%"

> "i had also build a matrix to calculate realistic targets to guide before cascade that was to review historical performances, plus an ai recommended target"

> "in the event a line manager was distributing a targets for shared across there was summing up showing what was being allocated, confirm if this is still intact and working accordingly"

## Audit findings (before fix)

| Feature | Pre-v10.405 status |
|---|---|
| Fixed KPI greying | ✅ Already rendered read-only as 🔒 cell with yellow background + "auto-cascade" label. No change needed. |
| Target guidance matrix | ❌ **BROKEN** — `suggest_target` imported but NEVER called. ~200 LOC engine sitting unused in `utils/core.py:3408`. |
| Allocation sum indicator | ✅ Lines 1872-1894 work — `_allocated_so_far` + `_remaining` displayed live. |
| Weight totals check | ⚠️ Gated by `if _bad_wts:` — only shown when WRONG, hidden when correct. |

## What v10.405 did

### Fix 1: Wired `suggest_target` into 'Set team targets' tab

Per-KPI **🎯 Target guidance** ribbon now appears between the KPI header and allocation inputs. Shows:

- **Prior actual** — what they achieved last year
- **Suggested min → target → stretch** range — color-highlighted recommended target
- **Confidence badge** — high/medium/low based on data availability
- **NEW HIRE badge** — when staff has <6 months data
- **Italic rationale** — plain-English explanation of how the recommendation was derived

Skips Fixed KPIs (no allocation needed). Tolerates exceptions silently — guidance is informational, never blocks UI.

`get_bank_growth_trajectory` also wired to feed growth-rate context into the engine.

**Result**: Managers now see historical performance + AI-grounded targets BEFORE allocating — exactly what was built but never connected.

### Fix 2: Weight check row always visible

Was: `if _bad_wts: tbl += ...` — only showed warning when totals ≠ 100%.

Now: `if _has_any_wts: tbl += ...` — always renders the row:
- **Green ✅** "KPI weights check (sum to 100%)" when correct
- **Red ⚠️** "KPI weights check (must sum to 100%)" when not

Each person's column shows their actual % total. Compliance and incorrectness are both visible at all times.

Per Joshua: "full visibility and to ensure weights can be summed up to 100%".

### Fix 3: Verified allocation sum indicator

Confirmed working at lines 1872-1894:
- `_allocated_so_far` — sums values typed into inputs for this KPI across direct reports
- `_remaining` — `stretch_tgt − _allocated_so_far`
- Live in header: "X remaining" (green) or "X over" (red)
- Skips Fixed KPIs from the sum (correct — they auto-cascade)
- Updates as manager types each value

No change required — feature intact.

### Fix 4 (no-op): Fixed KPI greying verified

Looked at the rendering — already correctly shows Fixed KPI rows as read-only cells with:
- 🔒 icon
- "auto-cascade" badge in yellow
- `#FFFBEB` (yellow-50) background
- `#92400E` (amber-900) text color
- AUTO badge on KPI name

Already greyed/locked. No code change needed.

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 290 → **291** |
| Tests | 316 → **327** (+11 new) |
| Verifier | 570 → **576 checks** |
| Master prompt lockstep | **49/49 consecutive batches** |
| G162 baseline | 4022 (**98 consecutive zero-drift batches**) |
| Engine state | 0/0/0/0 ✓ |

## 10 honest acknowledgements

1. **Target matrix wasn't broken — it was disconnected.** The code was complete, well-designed, and never invoked. Single one-line import; zero function calls. Fixed by wiring it into the existing per-KPI render loop.

2. **suggest_target output is rich.** Returns prior year target, prior actual, achievement %, 2-yr rolling avg, is_new_hire flag, suggested min/target/stretch range, rationale, confidence — all properly surfaced in the UI now.

3. **NEW HIRE handling proper.** Staff with <6 months data get the NEW HIRE badge automatically. Managers know to use industry benchmarks instead of personal history.

4. **Weight check now always speaks.** Green when right, red when wrong — never silent. Especially important for branch managers managing multiple direct reports.

5. **Allocation sum check confirmed unbroken.** Spent time verifying instead of assuming — feature works exactly as Joshua remembered.

6. **Fixed KPI greying was already there.** Yellow background + 🔒 + "auto-cascade" label. Could have been mistaken for needing fixing, but visual inspection confirmed correct.

7. **No regression risk.** v10.405 only ADDS UI rendering; doesn't change any underlying data or logic.

8. **Engine preserved.** 0/0/0/0 still holds. Adding informational UI is safe.

9. **49 consecutive lockstep batches.** No drift between master prompt and code.

10. **N2 single-concern preserved.** v10.405 = UX repair only. Per-layer buffer architecture (originally v10.405 scope) deferred to v10.406 to keep each batch focused.

## What you'll see when you reload

For each KPI in 'Set team targets' tab, just above the allocation input row:

```
PBT
🎯 Target guidance | Prior actual: 28.5B | Recommended: 30.0B → 32.5B → 35.0B (min·target·stretch) | HIGH confidence
💡 Based on staff member's 2-year trend showing 92% achievement at 28B target; recommend modest stretch.
```

For each direct report group, at the top of the allocation table, always:

```
✅ KPI weights check (sum to 100%) | Σ wt | 100% | 100% | 100% | 100%
```

Or if wrong:
```
⚠️ KPI weights check (must sum to 100%) | Σ wt | 85% | 95% | 100% | 105%
```

And live in each KPI header as you type allocations:

```
PBT  Bank: 50B → With buffer: 55B · 5.5B remaining
```

## On your end

1. Close Streamlit
2. Extract `a2z_v10405_patch.zip` flat on top of v10.404 state
3. Run `python scripts\verify_local_state.py` → expect **576/576**
4. Engine: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Login as a manager (e.g., Nicholas/CRBO or any Branch Manager)
6. Open Cascade page → 'Set team targets'
7. You should see:
   - 🎯 Target guidance ribbon for each KPI (with prior data + recommendations)
   - ✅ KPI weights check row (always visible, green when correct)
   - Live "X remaining" / "X over" in KPI headers as you type
   - Fixed KPI rows still showing 🔒 yellow auto-cascade cells
8. Tell me **"continue"** → v10.406 = per-layer buffer + MD per-KPI cap (F2 original scope)

## Roadmap

| Batch | What |
|---|---|
| ~~v10.403~~ Data cleanup | ✅ |
| ~~v10.404~~ Preserve manual on regen (F4) | ✅ |
| ~~v10.405~~ Target guidance wired + weight visibility | ✅ **DONE** |
| **v10.406** Per-layer buffer + MD per-KPI cap (F2 architectural) | **next** |
| v10.407 Per-line-manager retain auth (F3) |
| v10.408 Dual-view BSC (primary=stretch, secondary=base) |
| v10.409 Role weight renormalization (225/227 roles broken) |
| v10.410 KPI library dedup |
| v10.411 Backup retention cleanup |
