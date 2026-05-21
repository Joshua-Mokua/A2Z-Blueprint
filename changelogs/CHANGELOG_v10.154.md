# CHANGELOG v10.154 — Treasury FastAPI Router (read-only GET surface)

**Status:** **TREASURY API ROUTER + ENGINE-EXISTENCE VERIFICATION COMPLETE.** Resumes Phase 2 Treasury per the v10.152 plan after the v10.153 navigation hotfix and v10.153.1 cockpit signature hotfix.

**Audit:** `Score: 149/149 gates = 100.0% — PASS` (unchanged — no new audit gate). G142 anti-drift floor unchanged at 76. v10.154 tests 19/19 pass.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/api_treasury.py` | ~360 | NEW. FastAPI router with 18 GET endpoints, JWT auth, audit logging |
| `tests/test_api_treasury_v10_154.py` | ~200 | NEW. 19 tests across 5 classes |
| `docs/Master_Prompt_v3.47.md` | ~1100 | Anti-drift sync v3.46 → v3.47 |
| `SCOPE_LEDGER.md` | updated | v10.154 row + status block |
| `CHANGELOG_v10.154.md` | this file | This document |

---

## Engine-existence verification (v10.152 plan §3.2 first action)

The v10.152 plan's first execution checklist item was: verify the 8 cross-cutting engines exist in `utils/`. **They all exist.** Substantial implementations, not stubs:

| Engine | LOC | Belongs to module |
|---|---:|---|
| `deposit_intelligence` | 413 | NMD modeling (referenced by ENH-231) |
| `risk_weighted_assets` | 543 | Risk arc (referenced by ENH-235) |
| `capital_adequacy` | 696 | Capital arc (referenced by ENH-235) |
| `rwa_optimization` | 788 | Risk arc (referenced by ENH-235) |
| `fund_transfer_pricing` | 652 | Finance arc (referenced by ENH-236) |
| `cash_forecasting` | 870 | Treasury intelligence (referenced by ENH-237) |
| `flexcube_adapter` | 1,547 | Integration (referenced by ENH-TRS-R1) |
| `market_risk` | 354 | Risk arc (referenced by ENH-TRS-R4, ENH-TRS-R6) |

Total ~5,863 LOC across the 8 cross-cutting engines, plus 8,907 LOC for the 12 Treasury-named engines confirmed in v10.152. Combined ~14,770 LOC across the 20 engines covering 18 Treasury standards.

**v10.154 builds API endpoints only for the 12 Treasury-named engines** per the v10.152 plan. The 8 cross-cutting engines are read by Treasury's cockpit + API but live in their own module routers (Risk arc has its own `api_risk.py`, Capital has its own router, etc.). The Treasury cockpit in v10.155 will display relevant outputs from cross-cutting engines but won't own them — proper module boundaries.

---

## API endpoint inventory (18 GET endpoints)

All endpoints under `/api/treasury/*`, all JWT-protected via `Depends(get_current_user)`, all audit-logged.

```
GET /api/treasury/board                          # cross-engine board pack with engine_status map
GET /api/treasury/intelligence/yield-curve       ENH-231 yield_curve(as_of_date, currency)
GET /api/treasury/intelligence/liquidity         ENH-232 liquidity_metrics(as_of_date)
GET /api/treasury/intelligence/income            ENH-234/236 income_by_instrument(period)
GET /api/treasury/intelligence/alm-dashboard     ENH-233 alm_dashboard_data(as_of_date)
GET /api/treasury/alm/board                      ENH-233 board_summary
GET /api/treasury/alm/outlier-scenarios          ENH-233 outlier_scenarios
GET /api/treasury/products/board                 ENH-234 board_summary
GET /api/treasury/agents/board                   ENH-240 board_summary
GET /api/treasury/connectivity/board             ENH-TRS-R1 board_summary
GET /api/treasury/digital-assets/board           ENH-TRS-R2 board_summary
GET /api/treasury/dashboard/board                ENH-238 board_summary
GET /api/treasury/unified/board                  ENH-TRS-R4 board_summary
GET /api/treasury/unified/positions              ENH-TRS-R4 positions
GET /api/treasury/liquidity-risk/methods         CBK-PG-05-LCR (placeholder, deferred to v10.155)
GET /api/treasury/islamic/board                  ENH-239 board_summary
GET /api/treasury/islamic/non-compliant          ENH-239 non_compliant_products
GET /api/treasury/climate/board                  ENH-TRS-R6 board_summary
GET /api/treasury/climate/all-limits             ENH-TRS-R6 compute_all_limits
```

The `/api/treasury/board` cross-engine endpoint composes board_summary from every engine that exposes it, with an `engine_status` map (mirrors the v10.151 ProductAnalyticsDashboard pattern) so partial failure surfaces with reason rather than blanking the response.

---

## Honest scope decision — v10.154 is read-only GET only

State-changing engine methods (register_*, run_*, mark_executed) are NOT exposed as endpoints in v10.154 because:

1. **Typed payload validation needed.** The engines accept frozen dataclass tuples like `Tuple[HQLAHolding, ...]`, `Tuple[OutflowCategory, ...]`, etc. Exposing these as POST endpoints requires Pydantic models that match the dataclass shapes precisely. Inventing approximate shapes risks the same v10.153.1-style runtime errors that only surface in real testing.

2. **Multi-step workflows.** Many state-changing methods need prior `register_*` calls to populate engine state before the query method works. Request → engine state → query is a multi-step interaction that needs careful session/persistence design.

3. **Discipline from v10.153.1.** The Product cockpit hotfix taught the lesson: don't write against signatures you haven't verified. v10.154 verified every GET-endpoint method's signature via `inspect.signature` before writing the endpoint. POST endpoints with placeholder validation would be the inverse — writing first, hoping signatures align.

The `/api/treasury/liquidity-risk/methods` endpoint **honestly surfaces** what's deferred:

```json
{
  "engine": "LiquidityRiskEngine",
  "methods": [
    {"name": "hqla_value", "input": "List[HqlaHolding]", "deferred_to": "v10.155"},
    {"name": "net_cash_outflows_30d", "input": "List[CashFlowItem]", "deferred_to": "v10.155"},
    {"name": "available_stable_funding", "input": "List[FundingItem]", "deferred_to": "v10.155"},
    {"name": "required_stable_funding", "input": "List[AssetItem]", "deferred_to": "v10.155"}
  ],
  "note": "v10.154 exposes read-only GET endpoints. POST endpoints for LCR/NSFR computation ship in v10.155 closure batch with typed Pydantic request models matching the engine's frozen input dataclasses."
}
```

Operators reading the API discover both what's available now AND what's explicitly deferred. **Honest deferral surfaces are the same discipline used in ENH-139 PROXY MODE (analysis_basis tag) and ENH-138 no_product_resolution.**

---

## Discipline carried forward from v10.153.1

The Product cockpit hotfix taught two lessons that v10.154 codifies:

### Lesson 1: verify signatures before writing

Every method exposed as an endpoint had its signature verified via `inspect.signature` before the endpoint was written. The v10.154 development sequence:

1. Smoke-test instantiation on all 12 engines (all OK)
2. Probe `board_summary()` on the 4 engines that have it (all return dict)
3. Catalog public method signatures via `inspect.signature` (caught: some methods take dataclass tuples, some are static-style on LiquidityRiskEngine — informed the deferral decision)
4. Write endpoints only for methods whose signatures I verified

### Lesson 2: audit_log signature is real, not invented

`_audit_treasury(action, user, detail)` calls `audit_log(action, username, detail, module, ...)` — using `username=` (not `actor=`) and `detail=` (not `payload=`). Test class `TestModuleShape.test_audit_treasury_uses_real_audit_log_kwargs` explicitly asserts:

```python
assert "username=" in block
assert "detail=" in block
assert "actor=" not in block      # the v10.153.1 bug
assert "payload=" not in block    # the v10.153.1 bug
```

This codifies the v10.153.1 lesson into the test suite. Future API routers that invent kwargs will fail this test.

---

## Tests — `tests/test_api_treasury_v10_154.py`

19 tests across 5 classes:

- **TestModuleShape** (5) — exists / parses / loads without FastAPI installed / audit helper present / `_audit_treasury` kwargs match real `audit_log` signature
- **TestEngineSurfaceVerified** (7) — all 12 engines importable / intelligence methods exist / alm methods exist / 7 board_summary methods present / unified+islamic+climate specific methods exist
- **TestEndpointsCallable** (3) — yield_curve callable with right args / liquidity_metrics callable / 4 board_summaries return dicts
- **TestNoRegression** (3) — G149 still passes / G147+G148 still pass / total gate count unchanged at 149
- **TestLiquidityRiskDeferred** (1) — placeholder documents v10.155 deferral

All 19 pass via inline runner in the sandbox (where FastAPI is not installed; the graceful fallback path is exercised).

---

## Apply order

After v10.153.1:

```
1. utils/api_treasury.py                     → utils/  (NEW)
2. tests/test_api_treasury_v10_154.py        → tests/  (NEW)
3. docs/Master_Prompt_v3.47.md               → docs/
4. SCOPE_LEDGER.md                           → root
5. CHANGELOG_v10.154.md                      → root
```

`git add -A && git commit -m "v10.154 Treasury API router — read-only GET surface, engine-existence verified"`. Then `python scripts/audit.py` should print `Score: 149/149 gates = 100.0% — PASS`.

**Important deployment step:** mount the FastAPI router in the parent app (typically `utils/api.py` or wherever the parent FastAPI app is assembled):

```python
from utils.api_treasury import router as treasury_router
app.include_router(treasury_router)
```

If the FastAPI side isn't currently running, this can wait — Streamlit doesn't depend on it. The router activates when FastAPI is mounted.

---

## What this drop does NOT change

- No engine modifications. None of the 20 engines were touched.
- No registry changes. All 18 Treasury standards were already `status='active'`.
- No `app.py` changes. v10.154 is API-only; cockpit registration happens in v10.155.
- No audit gate additions. Closure gate G150 comes in v10.155 alongside the cockpit.
- No data file changes.

The only files added are `utils/api_treasury.py` and `tests/test_api_treasury_v10_154.py`. Plus the four documentation files.

---

## v10.155 next-up — closure batch

Per the v10.152 plan and the v10.153 G149 ratchet:

1. `pages/26_treasury_arc_cockpit.py` Streamlit cockpit (~7 thematic tabs grouping the 12 engines per workflow logic per the v10.152 cockpit thematic preview)
2. POST endpoints in `utils/api_treasury.py` for state-changing engine methods with typed Pydantic request models (LCR computation, NSFR computation, IRRBB scenarios, deposit registration, FX position registration, agent recommendations approve/reject)
3. **`app.py` registration of 26_treasury_arc_cockpit.py in `_treasury_grp`** — without this, G149 will fail. The discipline is now codified.
4. Admin Tier section update for Treasury arc
5. G150 `gate_treasury_module_closed` (verifies 18/18 standards active + each engine file exists)
6. G151 `gate_treasury_arc_ui_integrated` (verifies cockpit imports all 12 engines + API exists with JWT auth)
7. `tests/test_treasury_v10_155.py` — closure verification
8. Master prompt sync v3.47 → v3.48 + scope ledger + changelog

Per the v10.141 standing norm, the closure batch is consolidated. After v10.155, Phase 2 Treasury closes — 10th module closure in platform history.

---

## Summary

v10.154 ships the Treasury FastAPI router as a read-only GET surface, verified against the actual engine signatures. Engine-existence verification cleared the v10.152 risk item: all 20 affected_engines exist with substantial implementations. POST endpoints with typed Pydantic models defer to v10.155 closure batch. The v10.153.1 lesson on signature verification is codified into the test suite via the explicit `_audit_treasury` kwargs assertion. v10.155 closure next.

**Quoting the audit script directly:** `Score: 149/149 gates = 100.0% — PASS`. v10.154 tests `19/19 pass`.
