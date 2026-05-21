# Target Cascade — 7 QA-Standards Enhancements Audit

**Date:** 2026-05-14
**Per Joshua's QA standards document:** 7 enhancements expected on target cascade
**Method:** Direct code inspection — file presence + wiring + scope check
**Result:** **3 partially built, 4 missing**, plus 1 "built for wrong purpose"

---

## Audit summary at a glance

| # | Enhancement | Engine | UI wired | Scope match | Status |
|---|---|---|---|---|---|
| **E1** | Real-Time Progress Rollup | ✓ Built (`manager_rollup.py` 544 LOC) | ✗ Not in cascade page | ✓ Right scope | **ENGINE READY, UI DISCONNECTED** |
| **E2** | Target Visualization & Impact (strategic pillar linkage) | Partial (`Cascade tree` tab) | ✓ Wired | ✗ No strategic-pillar viz | **PARTIAL — TREE ONLY** |
| **E3** | Target Scenario Simulator | ✗ Wrong scope | N/A | ✗ Risk scenarios, not target | **MISSING** |
| **E4** | Target Negotiation Workflow | ✓ Built | ✓ Wired (Review tab) | ⚠ Basic approve/reject | **BASIC ONLY — no escalation chain** |
| **E5** | Cascade Health Dashboard | ✓ Built (`cascade_coverage()`) | ✓ Wired (Coverage tab + Cascade tree) | ⚠ Per-user only, no exec dashboard | **PARTIAL — NEEDS EXEC ROLLUP** |
| **E6** | Bottom-Up Capacity Feedback | ✗ Not built | ✗ Not in UI | N/A | **MISSING** |
| **E7** | Cascade API & Integration | ✗ Not built | ✗ No download buttons in cascade | N/A | **MISSING** |

**Verdict: 3 partial, 3 fully missing, 1 mis-scoped.** The body has the skeleton in place but several muscles aren't connected and a few organs were never installed.

---

## Detailed findings

### 🟡 E1 — Real-Time Progress Rollup

**Solution requested**: Live aggregation of actuals from BSC engine with variance analysis per manager.

**What exists**:
- `utils/manager_rollup.py` — 544 LOC, fully functional
- Key functions:
  - `compute_team_rollup(manager_code)` — direct reports actuals aggregation
  - `compute_recursive_score(staff_code)` — recursive subtree rollup
  - `cascade_score_tree(...)` — tree of rollup scores
  - `_direct_actuals_for_kpi()` — KPI-specific actual extraction
- `utils/live_actuals.py` — 458 LOC, YoY tracking, sidecar persistence

**What's MISSING**: 
- Cascade page (`pages/12_cascade.py`) imports neither
- Currently wired ONLY into `pages/7_admin.py` line 9: `from utils.manager_rollup import compute_recursive_score as _bsc_recursive_score`
- BSC scorecard (`pages/1_perform.py`) doesn't surface team rollup per manager
- No "🔥 Live team progress" view on cascade page

**Fix scope**: Wire `compute_team_rollup` into cascade page Cascade Tree tab OR new "📊 Team progress" tab. Show each manager's team aggregate vs target in real-time with variance %.

---

### 🟡 E2 — Target Visualization & Impact (Strategic Pillar Linkage)

**Solution requested**: Interactive visualization linking individual targets to strategic pillars.

**What exists**:
- 🌳 Cascade tree tab (lines 2821-2870) — recursive tree showing target/actual/% per cascaded staff
- Per-KPI selection
- Color-coded by depth + achievement
- Cascade coverage badge per row

**What's MISSING**:
- No pillar-grouping visualization
- No "strategic pillar → KPI → target → staff" sankey/impact chart
- No way for a staff member to see "my PBT target supports the bank's Financial pillar (40% weight)"
- Pillar context only appears in admin (lines 803, 843), not cascade page
- No `utils/*visual*`, `utils/*sankey*`, `utils/*diagram*` helpers exist

**Fix scope**: Add new tab "🎯 Strategic impact" showing pillar-rolled view: how each staff's targets contribute to bank's 4 pillars (Financial / Customer / OpEx / People). Sankey-style or pillar-strip-tiled.

---

### 🔴 E3 — Target Scenario Simulator

**Solution requested**: Interactive simulator for target ALLOCATION scenarios (what-if).

**What exists**:
- `utils/scenario_simulator.py` — 18,026 LOC! But wrong scope.
- `ScenarioCategory` enum: `CUSTOMER_LIFECYCLE`, `CREDIT_LENDING`, `DEPOSIT_LIQUIDITY`, `PERFORMANCE_MGMT`, `RISK_COMPLIANCE`, `OPERATIONS_TREASURY`, `STRATEGY_CAMPAIGNS`, `FRAUD_SECURITY`, `RECOVERY_DISASTER`, `COMPETITOR_MARKET`
- This is the v10.36 framework risk-scenario engine (LCR compliance, fraud cascade, etc.) — NOT target cascade what-if
- Used only by `pages/7_admin.py`

**What's MISSING**:
- No target-allocation what-if module
- No "if I give Branch A 60% and Branch B 40% vs equal split, what's the BSC impact?" simulator
- No revision-and-compare flow

**Fix scope**: Build NEW `utils/target_scenario_simulator.py` — pure what-if for allocations. Given current cascade + a candidate split, project: (a) team coverage %, (b) likelihood-of-hit per historical achievement, (c) BSC impact projection. Wire as new tab "🧪 What-if simulator".

---

### 🟡 E4 — Target Negotiation Workflow

**Solution requested**: Structured negotiation workflow with escalation path.

**What exists**:
- `CascadeManager.request_review` (core.py:3072)
- `CascadeManager.resolve_review` (core.py:3108) — accepts Approved / Rejected
- `CascadeManager.get_review_requests` (core.py:3097)
- 🔍 Review requests tab (line 3014) — staff raise request, manager approves/rejects
- Buffer is called "negotiation space" (line 2605) — staff can request review within buffer
- Audit log records resolutions
- Note: separate `case_management` module has `escalate_to` parameter (core.py:5326) for compliance cases — not wired to target reviews

**What's MISSING**:
- No multi-step escalation when manager rejects (no path to skip-level)
- No SLA/deadline on resolution (manager can leave it pending indefinitely)
- No counter-proposal from manager (resolve = accept/reject the original ask only)
- No view "if rejected, what's the recourse?"

**Fix scope**: Extend `resolve_review` to accept `Counter-Proposed`, `Escalated` statuses. Add `escalate_to` field — auto-resolves to skip-level manager. Add resolution SLA (e.g., 7 days then auto-escalate).

---

### 🟡 E5 — Cascade Health Dashboard

**Solution requested**: Executive dashboard showing cascade health (completeness, gaps).

**What exists**:
- `CascadeManager.cascade_coverage(staff_code, kpi, period)` → (target_set, num_reports, coverage_pct, allocated_sum)
- 🌳 Cascade tree tab — per-row coverage badges (✓ ≥95%, ⚠ partial, ✗ none)
- ✅ Coverage & deadlines tab (lines 2927+) — exists but is user-scoped
- Metrics shown: "In cascade", "🔒 Targets locked", "✅ Coverage ≥90%", "⚠️ No target set"
- Each user sees their tree only (Branch Manager sees their branch, not bank-wide)

**What's MISSING**:
- No bank-wide cascade health view (MD's executive overview)
- No "by SBU / by branch / by KPI" cross-tab heatmap
- No drill-down to "where are the gaps" (specific KPIs with missing targets)
- No "stalest cascade entries" (allocated but never confirmed by recipient)

**Fix scope**: Add new tab "🩺 Cascade health" (MD/admin only). Bank-wide rollup: % cascade complete per pillar, per SBU, per branch. Heatmap of KPI × org-unit coverage. List of "broken cascade chains" (gaps, stale entries, locked-too-early, etc.).

---

### 🔴 E6 — Bottom-Up Capacity Feedback

**Solution requested**: Capacity feedback from staff BEFORE targets are finalized.

**What exists**:
- ❌ Nothing. Zero references to `capacity_feedback`, `capacity_constraint`, `bottom_up`, `local_capacity`, `capacity_input` across pages or utils.

**What's MISSING**:
- No way for staff to flag "this target is unrealistic given local capacity (e.g., only 3 RMs in our branch)"
- No pre-finalization staff input loop
- The review_request mechanism (E4) only fires AFTER cascade — not BEFORE finalization

**Fix scope**: New module `utils/capacity_feedback.py`. Schema: `{staff_code, period, kpi, capacity_constraint, suggested_target_max, rationale}`. Cascade-page tab "💬 Capacity feedback" (staff-facing): each staff can flag constraints before manager finalizes. Manager sees constraints when allocating (in Set team targets tab).

---

### 🔴 E7 — Cascade API & Integration

**Solution requested**: API for target data export and integration (HRIS, payroll, bonus calculation).

**What exists**:
- `utils/api.py` and ~30 other `api_*.py` files (cockpit, compliance, CRUD, product, etc.) — none for cascade
- No `utils/cascade_export*`, no `utils/cascade_api*`
- No `st.download_button` in cascade page
- BSC/finance modules have CSV exports, cascade does not

**What's MISSING**:
- No `GET /api/v1/cascade/{period}` endpoint
- No CSV/XLSX download of target_cascade.json
- No HRIS-shaped export (e.g., `staff_code, kpi, target, period, weight, pillar` flat)
- No bonus-calc-ready export (e.g., `staff_code, achievement_pct, weighted_score`)

**Fix scope**: New module `utils/cascade_export.py`:
- `export_cascade_to_xlsx(period, scope=None)` → file
- `export_cascade_to_hris(period)` → HRIS-shaped CSV
- `export_cascade_to_bonus(period)` → bonus-calc shape with weights resolved
- FastAPI route `/api/v1/cascade/{period}` for programmatic access
- Admin UI download buttons in cascade page

---

## Phase C2 status before tackling these 7

| Metric | Value |
|---|---|
| Phase C2 rescue arc | ✅ Complete (v10.391-v10.405) |
| Cascade engine state | 0/0/0/0 ✓ |
| Audit gates | 291 |
| Integration tests | ~434 |
| Verifier | 576/576 |
| Master prompt | v4.48 (49 consecutive lockstep batches) |
| G162 baseline | 4022 (98 consecutive zero-drift) |

The body has clean structural integrity. Now we're adding/connecting muscles.

---

## Recommended batch sequence — one concern per batch

### v10.406 — Wire `manager_rollup` into cascade UI (E1 fix)
**Touches**: `pages/12_cascade.py` (new "📊 Team progress" tab or wire into Cascade tree).
- No new engine code (manager_rollup.py already complete)
- Pure UI wiring — like v10.405 was for suggest_target
- Shows live team rollup with variance vs target per manager
- Low risk; high value

### v10.407 — Strategic pillar visualization (E2 fix)
**Touches**: New `utils/pillar_impact_engine.py` + new cascade tab.
- Build pillar-aggregation helper (sum of weighted targets per pillar per staff)
- New tab "🎯 Strategic impact" showing how individual targets roll into bank pillars
- Sankey or pillar-strip layout

### v10.408 — Target what-if simulator (E3 build)
**Touches**: New `utils/target_scenario_simulator.py` + new cascade tab.
- Pure what-if for allocations (not LCR-style scenarios)
- Manager picks alternative split, sees projected coverage + achievement likelihood
- Side-by-side comparison with current

### v10.409 — Negotiation escalation chain (E4 enhancement)
**Touches**: `utils/core.py::resolve_review` + Review Requests tab UI.
- Add `Counter-Proposed`, `Escalated` resolution statuses
- Add `escalate_to` parameter routing to skip-level manager
- 7-day SLA with auto-escalation

### v10.410 — Executive Cascade Health Dashboard (E5 enhancement)
**Touches**: New "🩺 Cascade health" tab (MD/admin only).
- Bank-wide rollup of cascade completeness
- KPI × SBU × branch coverage heatmap
- Gap-list with drill-down

### v10.411 — Bottom-up capacity feedback (E6 build)
**Touches**: New `utils/capacity_feedback.py` + new staff-facing tab.
- Schema for staff to flag constraints pre-finalization
- Surface in manager's "Set team targets" view when reading constraints

### v10.412 — Cascade API & Integration (E7 build)
**Touches**: New `utils/cascade_export.py` + admin UI download buttons + optional FastAPI route.
- XLSX export
- HRIS-shaped CSV
- Bonus-calc-shaped export

### Then the original pending design batches
- v10.413 — Per-layer buffer + MD per-KPI cap (Joshua F2)
- v10.414 — Per-line-manager retain auth (F3)
- v10.415 — Dual-view BSC (F5)
- v10.416 — Role weight renormalization (225/227 broken)
- v10.417 — KPI library dedup
- v10.418 — Backup retention cleanup

---

## Question for Joshua before v10.406

**Order**: Should I tackle E1-E7 first (in numbered order) THEN go back to F2-F5 architectural items? OR interleave them?

My recommendation: **E1-E7 first** because:
1. E1 (rollup wiring) is small, isolated, low-risk — easy win
2. E5 (cascade health dashboard) builds on existing engine — also low risk
3. E6 (capacity feedback) needs to land BEFORE F2 (per-layer buffer) makes sense — staff need to flag constraints first
4. E7 (export API) is independent — anytime
5. F2-F5 are architectural — best landed once E1-E7 give us the visibility tools to confirm the buffer mechanism is working correctly

If you agree, I'll proceed with v10.406 = Wire `manager_rollup` into cascade UI (E1 fix). Tell me **"continue"** and I'll ship it.

Or if you want a different order, tell me which enhancement to tackle first.
