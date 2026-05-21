# CHANGELOG v10.152 — Phase 2 Opened, Treasury Module Refresh Plan

**Status:** **PHASE 2 OPENED — TREASURY MODULE SELECTED. PLAN-ONLY DROP. NO CODE CHANGES.**

This drop opens Phase 2 of the build. User selected Treasury as the Phase 2 module after the v10.151 closure of Phase 1E Product. Treasury is an existing arc that predates the v10.46 Lean+Compact protocol amendment — 12 engines + 18 active standards + 2 cockpit pages are already in place, but the v10.46 UI integration ratchet is missing.

**This is a plan-only drop.** Single deliverable: `TREASURY_REFRESH_PLAN.md` at repo root. No code changes. No registry flips. No audit gate additions.

**Audit:** `Score: 148/148 gates = 100.0% — PASS` (unchanged — no audit-relevant changes). G142 anti-drift floor unchanged at 76.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `TREASURY_REFRESH_PLAN.md` | ~290 | NEW. Phase 2 opening inventory + trajectory + v10.46 gap analysis |
| `docs/Master_Prompt_v3.45.md` | ~1100 | Anti-drift sync v3.44 → v3.45 |
| `SCOPE_LEDGER.md` | updated | v10.152 row + status block |
| `CHANGELOG_v10.152.md` | this file | This document |

**No code changes.** No engines modified. No tests added. No registry changes. No audit gates added.

---

## Why a plan-only opening drop

For a module the size of Treasury (10,143 LOC across 12 engines, 18 standards, ~10K LOC of existing code), establishing inventory and trajectory before code is the disciplined opening. Same discipline that caught the v10.150 scope error mid-drop — verifying registry contents before committing.

Plan-only drops are a **new pattern in this build**. They're appropriate for module openings where the existing footprint is substantial and the closure trajectory needs confirmation before code begins. The discipline mirrors what closure batches do (consolidated final-state); the opening is the symmetrical artifact (consolidated initial-state plan).

For greenfield modules (e.g. Phase 1E Product, which started with 0 engines), a plan-only drop wouldn't be needed. For refresh modules with substantial existing footprint, it is.

---

## What the plan documents

### 1. Engine inventory (12 engines, ~10K LOC)

Every Treasury engine cataloged with main class + public method names + LOC count. All 12 have clean public API surfaces — none is a black box. The engine layer is rich and consumable; the v10.46 gap is purely the missing UI integration.

The `UnifiedTreasuryPlatform` (ENH-TRS-R4) and `TreasuryDashboardEngine` (ENH-238) are already aggregators in spirit — both have `board_summary()` methods composing outputs from companion engines. The new cockpit doesn't need to invent an aggregator; it can call these existing ones.

### 2. 18 active Treasury standards (full registry catalog)

CBK-PG-05-LCR, ENH-231..240, ENH-LR-001, ENH-TRS-R1..R6 — all status='active' in registry. Closure gate G149 (to be added in v10.155) will verify all 18 active + each engine present.

### 3. v10.46 gap analysis

Four specific gaps:
1. **No `utils/api_treasury.py`** — no FastAPI router / React-ready surface
2. **Cockpit doesn't consume engines** — both `pages/25_treasury.py` and `pages/81_alm.py` query DB directly, import zero Treasury engines
3. **No G149/G150 equivalent closure gates** — 18 standards active but no audit gate locking against regression
4. **No closure-level tests** — per-engine tests presumably exist but no Phase-1E-style closure verification (TestPhase1EClosure, TestNoRegression patterns)

### 4. Sequenced refresh trajectory

```
v10.152 (THIS) → v10.153             → v10.154             → v10.155
plan-only       FastAPI router         Streamlit cockpit     closure batch
                + engine verify        (~7 thematic tabs)    G149 + G150 + tests
```

Three engine-level drops + one closure batch. Closure batch consolidates per the v10.141 standing norm.

### 5. Cockpit thematic grouping preview (for v10.154)

12 engines mapped to 7 thematic tabs along workflow lines: Dashboard / Liquidity & ALM / Products / Agents / Connectivity / Digital & Climate / Islamic & Unified. UX choice, not structural. Subject to refinement when API + engine consumption is concrete.

### 6. Out-of-scope items

- Legacy operational pages 25_treasury.py + 81_alm.py left as-is (additive Path A, mirroring v10.151's choice not to refactor 5_products.py for Product)
- Cross-cutting engines (RWA, FTP, Capital Adequacy) belong to other modules — Treasury cockpit displays their relevant outputs but doesn't own them
- Database schema unchanged
- New regulatory standards out of scope

### 7. Risk: missing cross-cutting engines

8 of 20 affected_engines across the 18 Treasury standards (`deposit_intelligence`, `risk_weighted_assets`, `capital_adequacy`, `rwa_optimization`, `fund_transfer_pricing`, `cash_forecasting`, `flexcube_adapter`, `market_risk`) aren't in the visible Treasury engine inventory. They may be elsewhere in `utils/` or may be missing.

**v10.153's first action:** verify each of the 20 engines exists. If any are missing, surface honestly — either build stubs with `is_estimate=True` and `fallback_reason="engine_not_yet_built"`, or update the registry to remove the missing engine reference and document the deferral in changelog.

### 8. v10.153 execution checklist

The plan ends with an explicit checklist for the next drop, so v10.153 starts with a clear action sequence rather than re-deriving scope.

---

## Honesty discipline (v10.152)

**No code is being shipped.** The plan is the entire drop. Audit score remains 148/148; nothing changed.

The plan explicitly flags the cross-cutting engine existence question — 8 engines may or may not exist, and v10.153 will verify and surface the answer honestly. The plan does NOT pretend the engines exist; it documents the uncertainty and the verification protocol.

Path A (additive) is the disciplined choice — leave the existing operational pages as-is, build a new strategic cockpit alongside them. Mirrors v10.151's Product Module choice. Refactoring the 779-line `25_treasury.py` to consume engines would be a significantly larger initiative with regression risk; building `26_treasury_arc_cockpit.py` as a new strategic view alongside it is non-destructive and additive.

---

## Apply order

After v10.151:

```
1. TREASURY_REFRESH_PLAN.md                 → root
2. docs/Master_Prompt_v3.45.md              → docs/
3. SCOPE_LEDGER.md                          → root
4. CHANGELOG_v10.152.md                     → root
```

Four documentation files. No code. `git add -A && git commit -m "v10.152 Phase 2 opened — Treasury Module Refresh Plan"`. Then `python scripts/audit.py` should print `Score: 148/148 gates = 100.0% — PASS` (unchanged).

---

## What's next — v10.153

Per the plan's execution checklist:

1. Verify 20 affected_engines exist in `utils/`. Document any missing.
2. Build `utils/api_treasury.py` FastAPI router covering the 12 Treasury-named engines:
   - One endpoint per main public method per engine (~24-30 endpoints)
   - JWT auth via `Depends(get_current_user)` on every endpoint
   - Audit logging via `_audit_treasury(action, user, detail)` after every call
   - Pydantic models for request payloads
   - FASTAPI_AVAILABLE flag pattern
3. Test the router shape with the same inline runner pattern used for v10.151's TestAPIRouter
4. Update master prompt v3.45 → v3.46
5. Update SCOPE_LEDGER with v10.153 row + status block
6. One artifact per zip — the API router is the single deliverable

---

## Summary

v10.152 opens Phase 2 with a plan, not code. Treasury Module is the selected refresh target. The plan documents what's there (12 engines + 18 active standards + 2 legacy pages), what's missing (FastAPI router + engine-aware cockpit + closure gates), and the sequenced trajectory to closure-readiness (v10.153 API → v10.154 cockpit → v10.155 closure batch). Path A additive — legacy pages stay, new strategic cockpit gets built alongside.

**Quoting the audit script directly:** `Score: 148/148 gates = 100.0% — PASS` (unchanged from v10.151).
