# Changelog — v10.410 Tab Consolidation (10→6) + Co-KPI Chief Pairing

**Date:** 2026-05-14
**Phase:** UX restructure + missing feature build
**Audit:** G296 added
**Tests:** 13/13 PASSED in `test_v10410_tab_consolidation_and_pairing.py`
**Verifier:** 614/614 checks pass
**G162 baseline:** 4022 (103 consecutive zero-drift batches)
**Master prompt:** v4.52 → v4.53 (lockstep — 54 consecutive batches)

---

## Joshua's two directives

> "the tabs are now more than 6 and still continuing and we had a rule that after six we start a new"

> "on the target cascade we had a drop down where for instance the MD could select the chief to cascade to or pair with another chief who shares same KPI e.g Commercial and retail chief could be paired"

> "on the road map i note we are not consistent with remaining batches"

## What v10.410 did

### Concern 1 — Tab consolidation (10→6)

**Before** (post-v10.409): 10 top-level tabs in cascade page
- 🏦 Bank targets & timeline | 🔒 Fixed KPIs | 🎯 Set team targets | 📊 My targets | 📈 Team progress | 🎯 Strategic impact | 🧪 What-if simulator | 🌳 Cascade tree | ✅ Coverage & deadlines | 🔍 Review requests

**After** (v10.410): 6 top-level tabs with sub-tabs inside

| Top-level | Sub-tabs |
|---|---|
| 📂 Bank setup (MD) | 🏦 Bank targets & timeline · 🔒 Fixed KPIs |
| 🎯 Cascade & allocate (mgr) | 🎯 Set team targets · 🤝 Co-KPI pairing **NEW** |
| 📊 My view (all) | 📊 My targets · 🎯 Strategic impact |
| 📈 Team analytics (mgr) | 📈 Team progress · 🧪 What-if simulator · 🌳 Cascade tree |
| ✅ Health & coverage (mgr) | ✅ Coverage & deadlines · (E5 dashboard arrives in v10.411) |
| 🔍 Negotiation (mgr) | 🔍 Review requests (with E4 escalation) |

**How it works:**
1. `_tab_defs` now has 6 entries
2. `_SUBTAB_MAP` is a dict mapping each old key → `(parent_key, sub_label, sub_idx)`
3. `_build_sub_tabs()` creates `st.tabs([...])` inside each parent, returning containers
4. `_in_tab(key)` now returns `(visible, container)` instead of `(visible, index)`
5. All 10 existing handler blocks updated: `with tabs[_tab_idx_xxx]:` → `with _tab_idx_xxx:` (the container itself)
6. `tab_visible_cascade` gets new top-level keys + retains legacy keys for backward compat

### Concern 2 — Co-KPI chief pairing

**Pre-v10.410**: Feature didn't exist. Manager assigns targets one-to-one with their direct reports. No way for MD to say "this PBT target is shared between Retail and Commercial — split 60/40".

**v10.410 builds:**

NEW `data/kpi_ownership_map.json` — 12 shared KPIs (PBT, LOAN_GROWTH, NPL_RATIO, FEES_COMM, NEW_CUST, DILIGENCE, Total NFI, Total Deposits, K001, K002, K003, K007) with:
- `primary_owners`: chiefs checked by default
- `secondary_owners`: optional co-contributors
- `default_pairing`: equal_split / by_prior_year / manual
- `note`: context

NEW `utils/kpi_ownership_pairing.py` (~280 LOC):
- `get_co_owners(kpi)` → `CoOwnership` dataclass
- `is_shared_kpi(kpi)` → bool
- `list_shared_kpis()` → list of shared KPI ids
- `apply_pairing_strategy(kpi, total, recipients, strategy, manual_shares=None)` → `PairingResult`
- 3 strategies:
  - `equal_split`: `total / N`
  - `by_prior_year`: proportional to each role's prior-year actual sum (falls back to equal if no data)
  - `manual`: caller provides `{role: pct}` dict; normalized to `total`

NEW `🤝 Co-KPI pairing` sub-tab inside Cascade & Allocate (MD-only):
1. Select shared KPI → see co-ownership info
2. Check/uncheck chiefs to include
3. Pick pairing strategy (3-option radio)
4. If manual: enter % shares per chief
5. Click 🚀 Compute pairing
6. See result table with per-chief amounts + percentages
7. Reminder: pairing is a planning aid; each chief then cascades via Set team targets

### Concern 3 — Roadmap reconciliation

Confirmed in `docs/V10_410_PLAN.md`:

| Batch | What |
|---|---|
| ~~v10.410~~ | Tab consolidation + Co-KPI pairing ✅ |
| v10.411 | E5: Executive cascade health dashboard (inside Health & coverage) |
| v10.412 | E6: Bottom-up capacity feedback (sub-tab in Cascade & allocate) |
| v10.413 | E7: Cascade API & exports (admin-side, no new tab) |
| v10.414 | F2: Per-layer buffer + MD per-KPI cap |
| v10.415 | F3: Per-line-manager retain authorization |
| v10.416 | F5: Dual-view BSC (primary=stretch, secondary=base) |
| v10.417 | Role weight renormalization (225/227 broken) |
| v10.418 | KPI library dedup follow-through |
| v10.419 | Backup retention cleanup |
| v10.420 | Retired test cleanup |
| v10.421 | Archived bank_target reconciliation (decision pending) |
| v10.422 | Pillar weights decision (68/14/6/12 vs 40/25/25/10) (decision pending) |
| v10.423 | CBS baseline computation (live data dep) |
| v10.424 | PBT live actuals integration (live data dep) |
| v10.425 | MD BSC integration verification |

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 296 → **297** |
| Tests | 376 → **389** (+13 new) |
| Verifier | 606 → **614 checks** |
| Master prompt lockstep | **54/54 consecutive batches** |
| G162 baseline | 4022 (**103 consecutive zero-drift batches**) |
| Engine state | 0/0/0/0 ✓ |
| Tabs | 10 → **6** top-level ✓ |
| Shared KPIs mapped | 12 (PBT, LOAN_GROWTH, NPL_RATIO, etc.) ✓ |

## 10 honest acknowledgements

1. **Tab overflow happened gradually.** v10.405 added 0, v10.406 added Team progress, v10.407 added Strategic impact, v10.408 added What-if simulator. Each batch was single-concern but cumulatively we landed at 10. Joshua's rule caught it.

2. **Sub-tabs preserve all functionality.** Zero feature lost; just reorganized. Users find the same 10+1 features inside 6 logical containers.

3. **Co-KPI pairing was a real gap.** Joshua remembered a feature that didn't exist — the assumption that PBT split happens automatically between Retail and Commercial was implicit, not coded.

4. **Pairing is a PLANNING aid, not execution.** Producing the per-chief split is half the work — each chief still needs to commit via Set team targets. Future: auto-apply button.

5. **3 strategies cover common cases.** Equal (no history), Prior year (data-driven), Manual (override). by_prior_year falls back to equal when actuals are missing.

6. **Static MD_CLUSTERS preserved.** The role-cluster grouping inside Set team targets ('Business Directors', 'Finance & Risk', etc.) stays — it's still useful for visual scorecard layout. Pairing is the new feature on top.

7. **Handler refactor was mechanical.** 10 `sed` substitutions changed `tabs[_tab_idx_xxx]` → `_tab_idx_xxx`. Container interface preserves the `with` statement semantics.

8. **Backward-compat keys retained.** Legacy callers (audit gates, page_access checks elsewhere) still get expected answers from `tab_visible_cascade("bank_targets")` etc.

9. **Roadmap re-numbered.** Original v10.410 (E5 health dashboard) becomes v10.411. All downstream batches shift +1.

10. **54 consecutive lockstep batches. 103 consecutive zero-drift G162.**

## What you'll see when you reload

**Cascade page top bar** now shows only 6 tabs:

```
📂 Bank setup | 🎯 Cascade & allocate | 📊 My view | 📈 Team analytics | ✅ Health & coverage | 🔍 Negotiation
```

**Inside 🎯 Cascade & allocate** (MD only):
```
[ 🎯 Set team targets ] [ 🤝 Co-KPI pairing ]
```

**Co-KPI pairing example flow:**

```
Shared KPI: [PBT v]    Period: [2026 v]

PBT — co-owned by 2 primary chiefs + 1 secondary
Profit before tax — main shared bank-wide KPI

Bank target (PBT, 2026): 65B

👥 Select chiefs to receive
☑ Director Retail Banking (primary)
☑ Director Commercial Banking (primary)
☐ Chief Financial Officer (secondary)

🎚️ Pairing strategy
⚖️ Equal split    📊 By prior year actuals    ✏️ Manual shares (%)

[🚀 Compute pairing]

📊 Allocation result
Chief role                       Amount    % of total
Director Retail Banking          32.5B     50.0%
Director Commercial Banking      32.5B     50.0%
```

## On your end

1. Close Streamlit
2. Extract `a2z_v10410_patch.zip` on top of v10.409 state
3. Run `python scripts\verify_local_state.py` → expect **614/614**
4. Engine: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Login as MD → Cascade page → see **6 tabs** at top
6. Open **🎯 Cascade & allocate** → see two sub-tabs: Set team targets · 🤝 Co-KPI pairing
7. Try Co-KPI pairing: pick PBT → see Retail+Commercial pre-checked → pick strategy → compute
8. Tell me **"continue"** → v10.411 = E5 Executive Cascade Health Dashboard

## Roadmap (reconciled)

| Batch | Concern | Status |
|---|---|---|
| ~~v10.410~~ | Tab consolidation + Co-KPI pairing | ✅ **DONE** |
| **v10.411** | E5: Executive cascade health dashboard | **next** |
| v10.412 | E6: Bottom-up capacity feedback |
| v10.413 | E7: Cascade API & exports |
| v10.414 | F2: Per-layer buffer + MD per-KPI cap |
| v10.415 | F3: Per-line-manager retain auth |
| v10.416 | F5: Dual-view BSC |
| v10.417 | Role weight renormalization |
| v10.418 | KPI library dedup |
| v10.419 | Backup retention cleanup |
| v10.420 | Retired test cleanup |
| v10.421 | Archived bank_target reconciliation |
| v10.422 | Pillar weights decision |
| v10.423 | CBS baseline computation (data dep) |
| v10.424 | PBT live actuals integration (data dep) |
| v10.425 | MD BSC integration verification |
