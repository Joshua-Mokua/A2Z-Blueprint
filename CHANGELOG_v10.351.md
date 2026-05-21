# Changelog — v10.351 Thin Redirect Signaling + UnboundLocalError Fix

**Date:** 2026-05-12
**Phase:** 4 (thirty-sixth arc — Option E closure batch)
**Audit:** 237/237 gates PASS = 100.0%
**Tests:** 13 new in `test_v10351_redirect_signaling.py`, all passing
**Page smoke:** 123/123 PASS at 100%
**Verifier:** 100/100 checks pass on a clean extract
**G162 Baseline:** 4022 (45 consecutive zero-drift batches)

---

## Your ask

> "continue with v10.351 — Convert all 16 consolidated originals to thin redirects after resolving UnboundLocalError: cannot access local variable 'get_stock_snapshot'"

Plus an observation: "on the unified cockpits we only did CIMS, Treasury, Credit, and Compliance" — that's correct, those four were the v10.345 inventory and the noted scope. No action item.

Two pieces of work in this batch.

## Part 1 — UnboundLocalError fix

### Root cause

`render_systems_view` in `utils/platform_hub_render.py` is a single function spanning 2,300 lines (lines 81-2360). The function uses `get_stock_snapshot` at line 444 — and the name IS imported at the module top (line 40).

But deep inside the function body (line 1150), there was a **redundant local re-import**:

```python
from utils.system_stocks import get_stock_snapshot
```

Python's scoping rule: any assignment to a name (including `from X import Y`) anywhere in a function makes that name **local for the entire function**. So at line 444, when `render_systems_view` tries to use `get_stock_snapshot`, Python looks for the local variable — which hasn't been assigned yet at that point. `UnboundLocalError`.

This is the same class as v10.350's `STREAMLIT_AVAILABLE` issue: latent bug in the original `pages/91_systems_view.py` that only surfaces when specific code paths execute.

### Fix

Removed the shadowing local import at line 1150. The top-level import at line 40 is sufficient and now flows correctly through the entire function.

```python
# Before (line 1147-1150)
from utils.composite_scores import (...)
from utils.system_stocks import get_stock_snapshot   # ← shadowing import

# After
from utils.composite_scores import (...)
# v10.351 — removed `from utils.system_stocks import get_stock_snapshot`
# here. The same import exists at module top (line 40); the local
# version shadowed it and made `get_stock_snapshot` a local variable
# in the entire 2,300-line render_systems_view function...
```

AST-level test (`test_v10351_render_systems_view_no_shadowing_imports`) walks the function body and flags any import of a top-level name. Locks the fix.

## Part 2 — Thin redirect signaling (Option E closure)

### What changed

All 16 originals consolidated in v10.345-v10.349 now carry a clear redirect banner at the top of the page. Each remains functional below the banner — bookmarks keep working.

The pattern per page:

```python
from pages._access import require_access
require_access("...")

from utils.<hub>_render import render_<area>

# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of <Hub Name>** — the unified entry point "
    "consolidates <area> alongside related views..."
)
try:
    st.page_link("pages/<hub>.py", label="Open <Hub Name> →", icon="🔗")
except Exception:
    st.markdown(f"[Open <Hub Name> →](pages/<hub>.py)")
st.markdown("---")

actor = st.session_state.get("user", {}).get("username", "anonymous")
render_<area>(actor)
```

### The 16 originals → 5 hubs

| Original | → Hub | Area |
|---|---|---|
| `109_cims_live.py` | `115_live_cockpits.py` | CIMS |
| `110_treasury_live.py` | `115_live_cockpits.py` | Treasury |
| `111_credit_live.py` | `115_live_cockpits.py` | Credit |
| `112_compliance_live.py` | `115_live_cockpits.py` | Compliance |
| `9_sbu.py` | `116_finance_hub.py` | SBU Performance |
| `10_opex.py` | `116_finance_hub.py` | OpEx & CIR |
| `52_mgmt_accounts.py` | `116_finance_hub.py` | Management Accounts |
| `114_sbu_drilldown.py` | `116_finance_hub.py` | SBU Drilldown |
| `27_propositions.py` | `117_propositions_hub.py` | Performance |
| `92_propositions_workbench.py` | `117_propositions_hub.py` | Workbench |
| `11_competitor.py` | `118_competitor_hub.py` | Market Overview |
| `93_competitor_intelligence.py` | `118_competitor_hub.py` | Workbench |
| `91_systems_view.py` | `119_platform_hub.py` | Systems View |
| `96_it_digital_pt1.py` | `119_platform_hub.py` | IT Digital Pt 1 |
| `97_it_digital_pt2.py` | `119_platform_hub.py` | IT Digital Pt 2 |
| `98_platform_health.py` | `119_platform_hub.py` | Platform Health |

### Line growth

Each page went from ~26 lines to 42-48 lines after adding the banner block. Still thin — the banner is ~14 lines of code.

### Threshold update across audit + verifier

Both the audit gates (G232-G236) and the verifier had `≤40 lines` thin-wrapper checks. The redirect banner pushes pages past 40. The threshold's purpose was to detect re-bloat (rendering logic moved back into the page), not to forbid intentional banner additions.

Raised to `≤55 lines` in:
- `scripts/audit.py` — 4 locations (G232-G235 use the threshold check; G236 already had the `>40` literal patched)
- `scripts/verify_local_state.py` — 5 locations
- New G237 enforces `≤55` for all 16 redirect pages

The semantic check (render function still called) is preserved.

### New audit gate G237 — `redirect_signaling`

Locks the v10.351 pattern across all 16 originals:

1. Each page contains the `v10.351 — Thin redirect` marker
2. Each links to the correct unified hub (115/116/117/118/119)
3. Each still calls its render function (backward-compat preserved)
4. Each is ≤55 lines

If any of the 16 originals loses its banner, links to the wrong hub, removes the render call, or grows past 55 lines, G237 fails. No silent regression possible.

### Backups (Pattern M)

`data/_v10351_backups/` contains the 16 pre-redirect thin wrappers (the v10.345-v10.349 state). Recovery path: copy them back over the redirect-pattern pages and rerun the audit.

## On the unified cockpits scope note

The Live Cockpits batch (v10.345) only covered CIMS, Treasury, Credit, Compliance — those were the four "live cockpit" pages in the original inventory:

| Page (original) | What it was |
|---|---|
| `109_cims_live.py` | CIMS live cockpit |
| `110_treasury_live.py` | Treasury live cockpit |
| `111_credit_live.py` | Credit live cockpit |
| `112_compliance_live.py` | Compliance live cockpit |

`pages/115_live_cockpits.py` consolidates exactly these four. If there's a need to add more cockpit areas later (e.g. a Risk Live cockpit, Operations Live, etc.), the helper module `utils/live_cockpit_render.py` is the place to add a new `render_*_cockpit()` function and `pages/115` adds a new pill. No new page file needed.

That's the architectural payoff of Pattern S: adding a new area is now a focused change inside the helper + selector, not a new top-level page.

## Files changed

| File | Change |
|---|---|
| `utils/platform_hub_render.py` | Removed shadowing local import of `get_stock_snapshot` (UnboundLocalError fix) |
| `pages/9_sbu.py`, `pages/10_opex.py`, `pages/11_competitor.py`, `pages/27_propositions.py`, `pages/52_mgmt_accounts.py`, `pages/91_systems_view.py`, `pages/92_propositions_workbench.py`, `pages/93_competitor_intelligence.py`, `pages/96_it_digital_pt1.py`, `pages/97_it_digital_pt2.py`, `pages/98_platform_health.py`, `pages/109_cims_live.py`, `pages/110_treasury_live.py`, `pages/111_credit_live.py`, `pages/112_compliance_live.py`, `pages/114_sbu_drilldown.py` | Redirect banner inserted between `require_access` and the render call |
| `scripts/audit.py` | Threshold raised from `> 40` to `> 55` in 4 places; new G237 `gate_redirect_signaling` |
| `scripts/v10351_apply_redirects.py` | NEW — repeatable transform that adds the banner |
| `scripts/verify_local_state.py` | 5 `<= 40` checks updated to `<= 55`; v10.351 section added |
| `tests/integration/test_v10351_redirect_signaling.py` | NEW — 13 tests |
| `data/_v10351_backups/*.py.before` | 16 pre-v10.351 thin wrappers preserved (Pattern M) |

## Verified outcome

| Metric | Before → After v10.351 |
|---|---|
| Audit gates | 236 → **237** (G237 added) |
| Page smoke | 123/123 PASS (unchanged) |
| Verifier | 96 → **100 checks** |
| UnboundLocalError on /119 | **resolved** |
| Originals with redirect signal | 0 → **16/16** |
| G162 baseline | 4022 (45 consecutive zero-drift batches) |

## On your end

1. Close Streamlit
2. Delete any leftover subfolder extracts
3. Extract `a2z_v10351_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 100 CHECKS PASSED**
5. Run `python scripts\audit.py` → expect **237/237 PASS**
6. Restart Streamlit
7. Test:
   - `/119_platform_hub` → Systems View tab — should load (UnboundLocalError fixed)
   - Any of the 16 originals (e.g. `/9_sbu`, `/27_propositions`, `/91_systems_view`) — should show a redirect banner at the top with a button to the unified hub, AND the original content below

## Suggested direction for v10.352

The Option E arc is fully closed: 5 unified hubs + 16 originals as thin redirects. Natural next directions:

1. **You verify v10.351 on localhost first** ← recommended
2. **v10.352 — Smoke test enhancement** — extend `utils/page_smoke.py` to actually CALL render functions, not just import them. Would catch the v10.350/v10.351 class of bugs (NameError / UnboundLocalError inside function bodies)
3. **v10.352 — Return to original roadmap** — partnerships P&L, B-027 tail, Strategic Initiative engine
4. **v10.352 — Address documented divergences** — `strategic_initiatives.rag_status` Title-vs-UPPER, `kpi.direction` short-vs-long

Which way?
