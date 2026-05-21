# Treasury Module Refresh Plan (v10.152 — opening drop)

**Phase 2 module selection:** Treasury Arc.

**Why a plan-only opening drop:** the Treasury module already has 12 engines + 18 active standards + 2 cockpit pages — it's a substantial existing footprint that predates the v10.46 Lean+Compact protocol amendment. Before writing any code, this drop establishes what's there, what the v10.46 gaps are, and the sequenced trajectory to closure-readiness. Disciplined opening: inventory first, code after the trajectory is confirmed.

**No code changes in v10.152.** No registry flips, no audit gate additions, no engine modifications, no cockpit refactors. Single deliverable: this document.

---

## 1. Current state — what's already there

### 1.1 Engines (12 in `utils/`, ~10,143 LOC total)

| File | LOC | Main class | Notable methods |
|---|---:|---|---|
| `treasury_intelligence.py` | 481 | `TreasuryIntelligenceEngine` | income_by_instrument, liquidity_metrics, alm_dashboard_data, yield_curve |
| `treasury_alm.py` | 1,221 | `TreasuryALMEngine` | register_deposit, run_decay_analysis, register_hqla, run_lcr, run_nsfr |
| `treasury_dashboard.py` | 755 | `TreasuryDashboardEngine` | generate_daily_treasury, generate_board_pack, generate_regulatory_pack, board_summary |
| `treasury_products.py` | 930 | `TreasuryProductsEngine` | register_yield_curve, register_fx_position, mtm_fx_position, register_mm_position, register_bond_position |
| `treasury_agents.py` | 862 | `AgentOrchestrator` + 5 agents | register_agent, run_all, approve, reject, mark_executed |
| `treasury_connectivity.py` | 723 | `TreasuryConnectivityEngine` | register_connector, activate_connector, register_mmf, best_yielding_mmf |
| `treasury_digital_assets.py` | 704 | `DigitalAssetTreasuryEngine` | register_wallet, whitelist_wallet, add_holding, set_spot_rate, value_holding |
| `treasury_unified_platform.py` | 497 | `UnifiedTreasuryPlatform` | n_engines_wired, positions, cross_asset_rollup, board_summary |
| `liquidity_risk.py` | 609 | `LiquidityRiskEngine` | hqla_value, net_cash_outflows_30d, lcr, available_stable_funding, nsfr |
| `liquidity_stress.py` | 744 | `LiquidityStressEngine` | compute |
| `islamic_treasury.py` | 804 | `IslamicTreasuryEngine` | register_product, value_product, value_all, non_compliant_products, board_summary |
| `climate_treasury_limits.py` | 577 | `ClimateTreasuryLimitsEngine` | has_climate_engine, compute_adjusted_limit, compute_all_limits, check_breach, board_summary |

Every engine has a clean public API surface. None is a black box. The engine layer is **rich and consumable** — the only thing missing is the unified UI/API that consumes it.

The `UnifiedTreasuryPlatform` (ENH-TRS-R4) and `TreasuryDashboardEngine` (ENH-238) are already aggregators in spirit — both have `board_summary()` methods that compose outputs from companion engines. The new cockpit doesn't need to invent an aggregator; it can call these existing ones.

### 1.2 Standards (18 active, all in registry)

| ID | Name | Affected engines |
|---|---|---|
| CBK-PG-05-LCR | CBK Liquidity Coverage Ratio | liquidity_risk, treasury_intelligence |
| ENH-231 | NMD Behavioral Modeling & Deposit Analytics | treasury_intelligence, deposit_intelligence, treasury_alm |
| ENH-232 | Intraday Liquidity & Real-Time Monitoring | treasury_intelligence, treasury_alm |
| ENH-233 | IRRBB Management & Dynamic ALM | treasury_intelligence, treasury_alm |
| ENH-234 | Treasury Products Suite (Oracle/Temenos-class) | treasury_intelligence, treasury_products |
| ENH-235 | RWA Optimization & Capital Management | risk_weighted_assets, capital_adequacy, rwa_optimization |
| ENH-236 | Fund Transfer Pricing (FTP) Enhancement | treasury_intelligence, fund_transfer_pricing |
| ENH-237 | AI-Powered Cash Forecasting | treasury_intelligence, cash_forecasting |
| ENH-238 | Treasury Dashboard & Reporting | treasury_intelligence, treasury_dashboard |
| ENH-239 | Islamic Treasury Products | treasury_intelligence, islamic_treasury |
| ENH-240 | Agentic Treasury Orchestration (Kyriba TAI-class) | treasury_intelligence, treasury_agents |
| ENH-LR-001 | Stressed LCR with Severity Calibration | liquidity_stress |
| ENH-TRS-R1 | 9900+ Bank Connection Capability | treasury_intelligence, flexcube_adapter, treasury_connectivity |
| ENH-TRS-R2 | Stablecoin & Digital Asset Treasury Integration | treasury_intelligence, treasury_digital_assets |
| ENH-TRS-R3 | Money Market Fund (MMF) Direct Access | treasury_intelligence, treasury_connectivity |
| ENH-TRS-R4 | MX.3 Cross-Asset Trading + Treasury + Risk Platform | treasury_intelligence, market_risk, treasury_unified_platform |
| ENH-TRS-R5 | Real-Time API ERP-to-Bank Payment Journey | treasury_intelligence, treasury_connectivity |
| ENH-TRS-R6 | Climate-Adjusted Treasury Risk Limits | treasury_intelligence, market_risk, climate_treasury_limits |

All 18 are already `status='active'`. The Treasury closure gate (G149 — to be added) will verify all 18 active + each engine present.

Worth noting: ENH-235 (RWA Optimization), ENH-236 (FTP), and ENH-237 (Cash Forecasting) reference engines (`risk_weighted_assets`, `capital_adequacy`, `rwa_optimization`, `fund_transfer_pricing`, `cash_forecasting`) that aren't in the file inventory above. These are likely either elsewhere in `utils/` (separate non-treasury engines that Treasury standards reference) or stubs. **Inventory verification needed in v10.153** — closure can't proceed until every affected_engine in the 18 standards is confirmed present.

### 1.3 Cockpit pages (existing, pre-v10.46)

| File | LOC | What it does |
|---|---:|---|
| `pages/25_treasury.py` | 779 | Main treasury operations page — FD, FX, MM, government securities. Hand-built, queries DB directly. **Imports ZERO engines.** |
| `pages/81_alm.py` | 457 | ALM-specific operational page. **Imports ZERO engines.** |

Both pages are operational (transaction-oriented: FD queue, FX deal register, MM placements). They predate the engine layer. The v10.46 gap: engines exist, pages don't consume them.

### 1.4 FastAPI router

`utils/api_treasury.py` **does not exist**. No React-ready surface for the Treasury module.

---

## 2. v10.46 gap analysis

The v10.46 Lean+Compact protocol amendment codified the closure norm: every closed module ships engines + tests + registry flips + closure gate + cockpit + UI gate + FastAPI router. Treasury was closed before this norm existed. The gaps:

1. **No FastAPI router** (`utils/api_treasury.py` missing) — gap vs v10.46 React-ready surface requirement
2. **Cockpit doesn't consume engines** — `25_treasury.py` and `81_alm.py` don't import a single Treasury engine; they query the DB directly. v10.46 norm: cockpit imports engines as the unified abstraction
3. **No closure gates** — there's no G149/G150 equivalent verifying Treasury module completeness or UI integration. The 18 standards are active in registry but no audit gate locks them against regression
4. **No engine self-test verification** for the 12 engines as a coherent module — the existing test suite has per-engine tests but not the closure-level tests that v10.151 introduced (TestPhase1EClosure, TestNoRegression patterns)

Note: the existing pages don't need to be DELETED. Path A (additive) is the disciplined approach — build a new strategic/analytical cockpit (`pages/26_treasury_arc_cockpit.py`) that consumes engines, leave the operational pages 25_treasury.py + 81_alm.py as-is. This mirrors what v10.151 did for Product (built `16_product_arc_cockpit.py` as the new strategic view; the operational `5_products.py` stayed put).

---

## 3. Refresh trajectory — sequenced drops

| drop | scope | size | status |
|---|---|---|---|
| **v10.152** (this drop) | Inventory + plan only — single TREASURY_REFRESH_PLAN.md document | small | **PLAN ONLY** |
| **v10.153** | Verify all 18 standards' affected_engines exist; build `utils/api_treasury.py` FastAPI router (24+ endpoints across 12 engines, JWT auth, mirrors api_product.py pattern from v10.151) | substantial single artifact | NEXT |
| **v10.154** | Build `pages/26_treasury_arc_cockpit.py` Streamlit cockpit (≤7 thematic tabs grouping the 12 engines per workflow logic) | substantial single artifact | planned |
| **v10.155** | Closure batch — G149 `gate_treasury_module_closed` (verifies 18/18 active + each engine file exists) + G150 `gate_treasury_arc_ui_integrated` (verifies cockpit imports + API exists with JWT) + tests/test_treasury_v10_155.py + registry flips not needed (already active) + admin Tier section update + master prompt sync + scope ledger + changelog | closure batch | planned |

Three engine-level drops + one closure batch. Closure batch consolidates per the v10.141 standing norm.

### 3.1 Why this sequence

- **v10.153 first (API router):** the most isolated artifact. Doesn't change cockpit, doesn't add audit gates. If Treasury QA team or React frontend devs want to start consuming endpoints, they can immediately. Also forces a verification of every engine's public method shape before any cockpit work.
- **v10.154 (cockpit):** depends on having confirmed the engine surfaces are coherent (which v10.153 forces). The cockpit can call the same methods the API exposes.
- **v10.155 (closure):** can only meaningfully run after both API and cockpit exist — G150 verifies both.

### 3.2 What v10.153 specifically must verify

The 18 Treasury standards reference these `affected_engines` (deduped):
```
treasury_intelligence, treasury_alm, treasury_dashboard, treasury_products,
treasury_agents, treasury_connectivity, treasury_digital_assets,
treasury_unified_platform, liquidity_risk, liquidity_stress,
islamic_treasury, climate_treasury_limits, deposit_intelligence,
risk_weighted_assets, capital_adequacy, rwa_optimization,
fund_transfer_pricing, cash_forecasting, flexcube_adapter, market_risk
```

20 unique engine references. The 12 confirmed are listed in §1.1. The remaining 8 (`deposit_intelligence`, `risk_weighted_assets`, `capital_adequacy`, `rwa_optimization`, `fund_transfer_pricing`, `cash_forecasting`, `flexcube_adapter`, `market_risk`) need verification — they may exist elsewhere in `utils/` (non-treasury engines that Treasury standards reference for cross-cutting capabilities like RWA or FTP) or they may be missing. **v10.153's first action: run `ls utils/ | grep -E '^(deposit_intelligence|risk_weighted_assets|capital_adequacy|rwa_optimization|fund_transfer_pricing|cash_forecasting|flexcube_adapter|market_risk)\.py$'` and audit the results.** If any are missing, the closure plan is blocked until they're built — that becomes a Phase 2 sub-track.

If all 20 engines exist, v10.153 proceeds with the API router covering the 12 Treasury-named engines (the 8 cross-cutting engines have or will have their own routers under their own modules — Risk Arc already has `api_risk.py` etc.).

### 3.3 Cockpit thematic grouping (preview for v10.154)

Following the v10.151 7-tab convention, the 12 engines map to ~7 thematic tabs along workflow lines:

| Tab | Engines |
|---|---|
| 📊 Dashboard | `treasury_intelligence` + `treasury_dashboard` (board summary + daily reports) |
| 💧 Liquidity & ALM | `liquidity_risk` + `liquidity_stress` + `treasury_alm` (LCR/NSFR/IRRBB/stress) |
| 💰 Products | `treasury_products` (FD/FX/MM/Bonds with MTM and yield curves) |
| 🤖 Agents | `treasury_agents` (AgentOrchestrator + 5 agents + recommendations lifecycle) |
| 🔌 Connectivity | `treasury_connectivity` (connectors + MMF counterparties) |
| 🌐 Digital & Climate | `treasury_digital_assets` + `climate_treasury_limits` |
| 🕌 Islamic & Unified | `islamic_treasury` + `treasury_unified_platform` (cross-asset rollup) |

Pairings reflect operational adjacency. Subject to refinement once API + engine consumption is concrete. UX choice, not a structural constraint.

---

## 4. Out-of-scope for this Phase 2 refresh

- **Pages 25_treasury.py + 81_alm.py:** intentionally left as-is. These are operational pages (transaction-oriented). The new strategic cockpit is additive. Migration of operational pages is a separate, larger initiative — outside Phase 2 closure scope.
- **Cross-cutting engines (RWA, FTP, Capital Adequacy, etc.):** referenced by Treasury standards but belong to other modules. They're already covered by their own module closures (Risk, Capital, etc.). The Treasury cockpit will display their relevant outputs but won't own them.
- **Database schema changes:** none expected. Engines already read from existing tables.
- **New regulatory standards:** if Continuation.docx or QA spec has Treasury standards beyond the 18 already active, those are post-closure additions — out of scope for refresh.

---

## 5. Risks & dependencies

### 5.1 Risk: missing cross-cutting engines

If `risk_weighted_assets.py`, `capital_adequacy.py`, etc. don't actually exist in `utils/`, the closure gate G149 will fail because affected_engines points to missing files. **Mitigation:** v10.153 starts by running the inventory check and surfaces honestly which engines are missing. If any are missing, we either (a) build stubs with explicit `is_estimate=True` and `fallback_reason="engine_not_yet_built"` returns, or (b) update the registry to remove the missing engine from affected_engines and document the deferral.

### 5.2 Risk: cockpit complexity from 12 engines

Strategy module had 15 engines and managed 7 tabs successfully. Product module had 10 engines, 7 tabs. Treasury at 12 fits the same envelope. No technical concern; UX risk is real (information density).

### 5.3 Dependency: existing tests

The 12 engines presumably have existing test coverage (per pattern, `tests/test_treasury_*.py`). v10.155 closure tests will be ADDITIVE — module-level closure verification, not duplicating per-engine tests.

---

## 6. What this drop actually ships

This drop ships ONE artifact: this document, `TREASURY_REFRESH_PLAN.md`, at the repo root.

No code changes. No registry changes. No audit changes. Audit score remains **148/148 PASS**.

The discipline of starting Phase 2 with a plan rather than code is the same discipline that caught the v10.150 scope error mid-drop (where I'd built the wrong engine for ENH-139 and corrected it). For a module the size of Treasury — 12 engines, 18 standards, 10K LOC of existing code — jumping straight to building the API would skip the verification that all 20 referenced engines actually exist. v10.152 establishes the trajectory and the verification protocol; v10.153 begins execution.

---

## 7. Execution checklist for v10.153 (next drop)

When v10.153 starts:

1. ☐ Verify 20 affected_engines exist in utils/ (the 12 confirmed + 8 cross-cutting). Document any missing.
2. ☐ Build `utils/api_treasury.py` FastAPI router covering the 12 Treasury-named engines:
   - One endpoint per main public method per engine (~24-30 endpoints)
   - JWT auth via `Depends(get_current_user)` on every endpoint
   - Audit logging via `_audit_treasury(action, user, detail)` after every call
   - Pydantic models for request payloads
   - FASTAPI_AVAILABLE flag pattern (so module loads in environments without FastAPI)
3. ☐ Test the router shape with the same inline runner pattern used for v10.151's TestAPIRouter
4. ☐ Update master prompt v3.44 → v3.45
5. ☐ Update SCOPE_LEDGER with v10.153 row + status block
6. ☐ Apply the standing rule of one artifact per zip (the API router is the single deliverable; the engine-existence verification is a prerequisite documented in the changelog, not a separate artifact)

---

**Audit (this drop):** `Score: 148/148 gates = 100.0% — PASS` (unchanged — no audit-relevant changes).

**Phase 2 status:** OPENED. Treasury arc selected. Trajectory documented. v10.153 next.
