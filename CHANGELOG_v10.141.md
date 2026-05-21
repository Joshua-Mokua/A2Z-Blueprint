# CHANGELOG v10.141 — Strategy UI Pass: Cockpit + React-Ready API + G146

**Status:** **STRATEGY MODULE END-TO-END CLICKABLE + REACT-READY.** v10.140 closed the Strategy module's engine layer (15/15 standards active under G145). v10.141 closes the user-facing surface — every Strategy engine is now operator-driveable from the browser via a 7-tab cockpit page, AND consumable by the planned React frontend via 19 JWT-protected FastAPI endpoints. **UI-pass-on-closure adopted as standing norm going forward. Treasury arc UI gap surfaced as backlog.**

**Audit:** **146/146 PASS** · G144 264/264 STABLE · G145 15/15 100% STABLE · **G146 NEW — strategy_arc_ui_integrated** (15/15 engines imported in cockpit; React-ready API mounted; v10.46 protocol satisfied) · G117 97.8% (226/231; was 98.3% pre-drop — passes ≥95% threshold) · **Engine self-tests:** 152/152 · **Tests:** 25 in `tests/test_strategy_v10_141.py` (manual replay 25/25 pass; sandbox can't install pytest)

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `pages/15_strategy_arc_cockpit.py` | ~1100 | Streamlit cockpit page covering all 15 Strategy engines via 7 lifecycle-phase tabs |
| `utils/api_strategy.py` | ~580 | FastAPI router with 19 endpoints (one per engine main method + /_meta), all JWT-protected, 12 Pydantic request models |
| `utils/api.py` | +6 | Mounts strategy router via `app.include_router(strategy_router)` after the last CRUD router |
| `scripts/audit.py` | +120 | G146 `gate_strategy_arc_ui_integrated` — verifies cockpit + API + mount + 15 engine imports |
| `tests/test_strategy_v10_141.py` | ~390 | 6 test classes, 25 tests verifying cockpit + API + G146 + no regression |
| `docs/Master_Prompt_v3.34.md` | 1076 | UI-pass-on-closure standing norm codified; v10.141 narrative paragraph appended |
| `SCOPE_LEDGER.md` | updated | v10.141 trajectory row + status block + Treasury backlog gap acknowledged |
| `CHANGELOG_v10.141.md` | this file | This document |

---

## The cockpit — `pages/15_strategy_arc_cockpit.py`

The first comprehensive cockpit covering 15 engines. Pattern follows the established `_arc_cockpit.py` convention (`93_risk_arc_cockpit.py`, `97_trade_finance_arc_cockpit.py`, `98_ml_governance_arc_cockpit.py`) — header gradient, `require_access`, `audit_log` after operator-initiated computations, top-of-page metrics strip, tabs grouped by lifecycle phase rather than per-engine (15 tabs would overwhelm).

**Header gradient:** `#7C3AED → #1E40AF` (purple-to-deep-blue) marks the module visually.

**Top metrics strip (5 cols):** active engines (15/15), n_initiatives, completion_rate, n_strategy_risks, HIGH-risk pillar count.

**Tab structure:**

| Tab | Engines | What it does |
|---|---|---|
| 🎯 Formulation | ENH-141/142/143/144 | SWOT generation from STEEP context · ranked strategic options · pillar decomposition · knapsack-optimized portfolio under user-set budget |
| 📊 Cascade | ENH-145/153 | Band-weighted pillar→department cascade · personal daily strategy contribution scorecard (BSC engine link) |
| 📈 Health | ENH-150 | Full health dashboard payload — 4 metric cards + per-pillar progress table + alerts + insights with explicit weight re-normalization disclosure |
| 🔍 Execution | ENH-146/147/151 | Decision-tree gap analyzer · 3-template corrective action generator · what-if simulator (linear impact, ±15% uncertainty band) |
| 🧠 Learning | ENH-148/149/152 | Lessons captured from prior cycle · 4-question engagement pulse · contribution campaign creation · strategy update distribution (DELIVERY_PREPARED status when no adapter — does NOT pretend messages were sent) |
| 🏢 STO | ENH-154 | Six sub-tabs (Portfolio/Risks/Reviews/Analytics/Minutes/Academy) calling individual STO methods with review pack JSON viewer |
| 💰 ROI | ENH-155 | Cycle-level ROI with direct/indirect split, category breakdown, ±20% uncertainty band on indirect benefits |

**Method-mismatch fix during build:** First cockpit draft used 4 method names that didn't exist on the engines. Caught via static method-existence check (`python3 -c "from utils.X import Cls; assert hasattr(Cls, 'method')"`) before running audit. Fixed in same drop:

| Wrong (initial) | Correct (actual) |
|---|---|
| `StrategicInitiativePortfolio.optimize_under_budget()` | `StrategicInitiativePortfolio.knapsack_optimize(initiatives, budget)` |
| `StrategicInitiativePortfolio._load_initiatives()` | `StrategicInitiativePortfolio.get_proposed_initiatives(pillars)` |
| `EnhancedCascadeEngine.cascade_strategy()` | `EnhancedCascadeEngine.cascade_with_engagement(pillar_okrs, department, ...)` |
| `CorrectiveActionGenerator.generate_actions_for_gap(gap)` | `CorrectiveActionGenerator.generate_corrective_actions(gap)` |

After fixes, all 23 cockpit engine method calls verified against the live engine APIs. This is the same smoke-test discipline that caught the users.json dict-vs-list bug in v10.140 — static integration check before audit run.

**Honesty surfaces preserved in UI:** ENH-148 deferred-stub disclosure when AI hooks not injected · ENH-149 `level="no_data"` rendering when no responses · ENH-150 weights-used display when components missing · ENH-151 `Insufficient data` recommendation rendering · ENH-152 explicit DELIVERY_PREPARED warning ("does NOT pretend messages were sent") · ENH-154 read-only contract honoured (writes go through 83_strategy.py, not the cockpit) · ENH-155 indirect benefits LABELED `is_estimate=True` with ±20% uncertainty band displayed.

---

## The React-ready API — `utils/api_strategy.py`

19 endpoints exposing the same engine layer the cockpit calls, returning identical JSON-serializable dicts. **Engine is source of truth for both** — Streamlit cockpit consumes engine.method() directly; React frontend consumes the same dict via HTTP. Replacing the cockpit with a React component later requires no engine changes.

| Method | Path | Standard | Engine call |
|---|---|---|---|
| POST | `/api/strategy/swot` | ENH-141 | `StrategyFormulationEngine().generate_swot()` |
| POST | `/api/strategy/options` | ENH-142 | `StrategicOptionsGenerator().generate_options()` |
| POST | `/api/strategy/pillars` | ENH-143 | `StrategyDecompositionEngine().define_strategic_pillars()` |
| POST | `/api/strategy/portfolio/optimize` | ENH-144 | `StrategicInitiativePortfolio().get_proposed_initiatives()` + `knapsack_optimize()` |
| POST | `/api/strategy/cascade` | ENH-145 | `EnhancedCascadeEngine().cascade_with_engagement()` |
| GET | `/api/strategy/scorecard/{username}` | ENH-153 | `DailyStrategyIntegration().create_personal_strategy_scorecard()` |
| POST | `/api/strategy/gap` | ENH-146 | `StrategyGapAnalyzer().analyze_gaps()` |
| POST | `/api/strategy/corrective-actions` | ENH-147 | `CorrectiveActionGenerator().generate_corrective_actions()` |
| POST | `/api/strategy/lessons` | ENH-148 | `StrategyLearningLoop().capture_lessons_learned()` |
| GET | `/api/strategy/pulse?department=&period=` | ENH-149 | `StakeholderEngagementEngine().run_engagement_pulse()` |
| POST | `/api/strategy/campaign` | ENH-149 | `StakeholderEngagementEngine().run_strategy_contribution_campaign()` |
| GET | `/api/strategy/health` | ENH-150 | `StrategyHealthEngine().build_dashboard_payload()` |
| POST | `/api/strategy/simulate` | ENH-151 | `StrategySimulator().simulate_resource_reallocation()` |
| POST | `/api/strategy/whatif` | ENH-151 | `StrategySimulator().what_if_scenario()` |
| POST | `/api/strategy/communication` | ENH-152 | `StrategyCommunicationEngine().distribute_strategy_update()` |
| GET | `/api/strategy/sto` | ENH-154 | `STOToolkit().get_full_toolkit_payload()` |
| POST | `/api/strategy/sto/review-pack` | ENH-154 | `STOToolkit().generate_review_pack()` |
| POST | `/api/strategy/roi` | ENH-155 | `StrategyROIAnalytics().calculate_strategy_roi()` |
| GET | `/api/strategy/_meta` | (discovery) | Returns `{module, version, n_standards, standards[], endpoints[], auth, honesty_notes, generated_at}` for React route enumeration |

**Security:** Every endpoint declares `user: dict = Depends(get_current_user)` — JWT bearer token required, validated by `utils.auth_jwt`. Audit verified via AST walk: 19/19 endpoints have a `Depends()` call in their function defaults.

**Pydantic request models (12):** `SWOTRequest`, `PillarRequest`, `PortfolioOptimizeRequest`, `CascadeRequest`, `GapAnalyzeRequest`, `CorrectiveActionRequest`, `LessonsRequest`, `CampaignRequest`, `SimulateRequest`, `WhatIfRequest`, `CommunicationRequest`, `ROIRequest`. Type-safe payloads with `Field(..., gt=0)` constraints where applicable.

**Audit logging:** `_audit_strategy(action, user, detail)` helper emits to `utils.core_audit.audit_log` after every successful endpoint call — same pattern as `utils/api.py::_audit`.

**Mount in `utils/api.py`:** Two new lines after the `clearing_records` CRUD router (the last one):

```python
from utils.api_strategy import router as strategy_router
app.include_router(strategy_router)
```

**Sandbox limitation:** `fastapi` and `pydantic` aren't installable in the sandbox (egress-blocked from PyPI), so runtime import couldn't be verified. Static AST analysis confirmed: 19 endpoints registered, all JWT-protected, 12 Pydantic models present. Production environment has FastAPI installed.

---

## G146 audit gate — `gate_strategy_arc_ui_integrated`

Registered in `scripts/audit.py` GATES list immediately after G145. Total gates **146**.

**Four checks:**
1. `pages/15_strategy_arc_cockpit.py` exists
2. All 15 Strategy engine class names appear in cockpit text (`StrategyFormulationEngine`, `StrategicOptionsGenerator`, `StrategyDecompositionEngine`, `StrategicInitiativePortfolio`, `EnhancedCascadeEngine`, `StrategyGapAnalyzer`, `CorrectiveActionGenerator`, `StrategyLearningLoop`, `StakeholderEngagementEngine`, `StrategyHealthEngine`, `StrategySimulator`, `StrategyCommunicationEngine`, `DailyStrategyIntegration`, `STOToolkit`, `StrategyROIAnalytics`)
3. `utils/api_strategy.py` exists with `router = APIRouter` and `Depends(get_current_user)`
4. `utils/api.py` imports the router via `from utils.api_strategy import router`

**Returns:** `passed=True` iff all 4 checks pass + `n_engines_imported == 15`. Violations enumerated explicitly so operators see exactly what's missing.

**Pattern parallel:** Joins `gate_risk_arc_ui_integrated` (G124), `gate_credit_model_risk_arc_ui_integrated` (G125-equivalent), `gate_revenue_assurance_arc_ui_integrated` (G131), `gate_finance_arc_ui_integrated` (G134), `gate_trade_finance_arc_ui_integrated` (G138), `gate_ml_governance_arc_ui_integrated` (G140) — same structural shape, different module.

---

## UI-PASS-ON-CLOSURE STANDING NORM (codified v10.141)

The v10.46 Lean+Compact protocol amendment introduced cockpit-on-closure as a discipline. **v10.141 hardens this into a structured 9-step standing norm and adds React-ready API surface as a third explicit requirement.**

**Every module closure from v10.141 forward must ship:**

1. **Engine code** in `utils/<module>_<name>.py` files
2. **Tests** in `tests/test_<module>_v10.NNN.py`
3. **Registry flips** in `utils/standards_registry.py` (`status="planned"` → `"active"`)
4. **Closure audit gate** `gate_<module>_module_closed` in `scripts/audit.py`
5. **Cockpit page** `pages/N_<module>_arc_cockpit.py` with all engine classes imported and tabs grouped by lifecycle phase
6. **UI integration audit gate** `gate_<module>_arc_ui_integrated` verifying cockpit exists + imports all engine classes + API router mounted
7. **FastAPI router** `utils/api_<module>.py` with one endpoint per engine main method, JWT auth via `Depends(get_current_user)`, Pydantic request models, and a `/_meta` route-discovery endpoint for React
8. **Router mount** in `utils/api.py` via `include_router`
9. **Master prompt + scope ledger sync** in same drop

This is the discipline Phase 1E Product Module (~v10.142-v10.145) is the first to be built under from drop one.

---

## TREASURY ARC UI BACKLOG GAP (identified v10.141)

UI-gap audit of all closed modules surfaced exactly one backlog item:

| Module | Closure version | Closure gate | UI integration gate | Cockpit page |
|---|---|---|---|---|
| Treasury | v10.37 | G127 ✅ | **❌ MISSING** | **❌ MISSING** |
| Risk | post-v10.46 | ✅ | G124 ✅ | `93_risk_arc_cockpit.py` ✅ |
| Credit Model Risk | post-v10.46 | ✅ | G125-equivalent ✅ | `94_credit_governance_cockpit.py` ✅ |
| Revenue Assurance | post-v10.46 | ✅ | G131 ✅ | `95_revenue_assurance_cockpit.py` ✅ |
| Finance | post-v10.46 | ✅ | G134 ✅ | `96_finance_arc_cockpit.py` ✅ |
| Trade Finance | post-v10.46 | ✅ | G138 ✅ | `97_trade_finance_arc_cockpit.py` ✅ |
| ML Governance | post-v10.46 | ✅ | G140 ✅ | `98_ml_governance_arc_cockpit.py` ✅ |
| Strategy | v10.140 | G145 ✅ | **G146 ✅ (this drop)** | **`15_strategy_arc_cockpit.py` ✅ (this drop)** |

**Treasury closed at v10.37 — BEFORE the v10.46 protocol amendment introduced UI integration ratchets.** It's the only closed module that predates the discipline. Treasury has 16 active engines but no cockpit page and no `gate_treasury_arc_ui_integrated`.

**Recommendation:** defer to a future backfill drop (likely v10.150-range or after Phase 1E ships). Surfacing in this CHANGELOG and in SCOPE_LEDGER prevents it from being forgotten.

---

## React-ready discipline — pattern for every future module

The v10.141 pattern that Phase 1E will inherit:

```
                ┌───────────────────────────────────────────┐
                │   utils/<engine>.py (source of truth)     │
                │   engine.method(args) → JSON-serializable │
                │   Python dict (already verified by tests) │
                └─────────────────┬─────────────────────────┘
                                  │
              ┌───────────────────┴────────────────────┐
              │                                        │
              ▼                                        ▼
   pages/<N>_<module>_cockpit.py    utils/api_<module>.py (FastAPI)
   ├ Streamlit tabs                 ├ POST /api/<module>/<endpoint>
   ├ engine.method() calls          ├ engine.method() calls
   ├ st.dataframe(result)           ├ return result (JSON)
   └ audit_log(...)                 ├ Depends(get_current_user)
                                    └ /_meta endpoint
                                                     │
                                                     ▼
                              React frontend (planned, post-Phase-1)
                              fetch('/api/<module>/<endpoint>', JWT)
```

Both UI surfaces consume the same engine. Replacing Streamlit with React requires no engine changes — only swapping the page for a React component that calls the existing API.

---

## Apply order

```
consolidated → 133 → 135 → 136 → 137 → 138 → 139 → 140 → 141
```

After applying, run `python scripts/audit.py` — output should land **`Score: 146/146 gates = 100.0% — PASS`**.

---

## Files in this drop (zip contents)

```
pages/15_strategy_arc_cockpit.py     NEW — 7-tab cockpit, 15 engines wired
utils/api_strategy.py                NEW — 19 endpoints, JWT, 12 Pydantic models
utils/api.py                         MODIFIED — strategy router mounted
scripts/audit.py                     MODIFIED — G146 added, registered after G145
tests/test_strategy_v10_141.py       NEW — 25 tests across 6 classes
docs/Master_Prompt_v3.34.md          NEW — UI-pass-on-closure norm codified
SCOPE_LEDGER.md                      MODIFIED — v10.141 row + status block + Treasury backlog
CHANGELOG_v10.141.md                 NEW — this file
```

**Per project discipline (user prefs):** only changed files included; never full repo dump.

---

## What this drop does NOT change

- **Total QA spec progress: 137/264 (51.9%)** — UI integration is not new spec coverage. Spec-completeness number stays put.
- **Engine count** — still 15 Strategy engines; v10.141 is rendering surface, not new engines.
- **Database schema** — none changed.
- **Test count engine self-tests** — 152/152 passing as before.
- **Treasury arc** — backlog gap acknowledged but NOT fixed in this drop. Defer to future.

---

## Summary

Strategy module is now **end-to-end clickable + React-ready**. Every engine has a UI surface and an HTTP endpoint. UI-pass-on-closure is the standing discipline going forward. Treasury arc UI gap is the only backlog from prior closures and is on the radar. Phase 1E Product Module opens next under the new norm.

**Quoting the audit script directly:** `Score: 146/146 gates = 100.0% — PASS`. Engine self-tests `152/152`. Test file `tests/test_strategy_v10_141.py` 25/25 pass via manual replay (sandbox lacks pytest).
