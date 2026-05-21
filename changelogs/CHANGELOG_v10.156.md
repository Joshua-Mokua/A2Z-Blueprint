# CHANGELOG v10.156 — Treasury State-Loading Endpoints

**Status:** **Treasury state-loading POST endpoints — completes Phase 2 write-side surface.** Per the v10.155 deferral commitment, v10.156 ships POST endpoints for the simple-shape state-loading methods that v10.155 honestly deferred.

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged — engine-level work, no new module closure, no new audit gates). G142 anti-drift floor unchanged at 76. v10.156 tests 18/18 pass.

---

## What v10.155 vs v10.156 ship

The v10.155 closure batch shipped 6 POST endpoints for state-mutating **computations** (run_lcr, run_repricing_gap, run_decay, agents.approve/reject, climate.check_breach). Those compute against engine state — but the state had to come from somewhere.

v10.156 ships the 6 POST endpoints for state **loading** — populating the engine state that those computations need:

```
POST /api/treasury/alm/register-deposit          NMDDeposit
POST /api/treasury/alm/register-hqla             HQLAPosition
POST /api/treasury/alm/add-inflow                CashFlow (direction=INFLOW)
POST /api/treasury/alm/add-outflow               CashFlow (direction=OUTFLOW)
POST /api/treasury/alm/register-rates-position   RatesGapPosition
POST /api/treasury/products/register-fx-position FXPosition
```

**Total router endpoints now 30** (18 GET from v10.154 + 6 POST from v10.155 + 6 POST from v10.156). All JWT-protected via `Depends(get_current_user)`; all audit-logged via `_audit_treasury(action, user, detail)` using the real `audit_log` signature.

---

## Pre-ship bug catch — v10.153.1 discipline applied

My initial v10.156 draft used `is_asset=True` for FXPosition — carrying over the field name from RatesGapPosition. The round-trip probe surfaced:

```
TypeError: FXPosition.__init__() got an unexpected keyword argument 'is_asset'
```

The real field on FXPosition is `is_long_base`. Fixed before shipping. **This is exactly the v10.153.1 bug class** — inventing field names without verifying against the actual frozen dataclass. The probe discipline (run the Pydantic→engine conversion in a Python REPL before writing the endpoint) caught it; user testing didn't have to.

Now codified into the `TestRoundTripConversions` test class which exercises each of the 6 conversions end-to-end. Future state-loading endpoints that invent field names will fail this test before reaching user testing — same pattern as G149 (nav registration), G150/G151 (Treasury closure), and TestCockpitSignatureDiscipline (require_access/audit_log kwargs).

---

## Pydantic model design

Each request model maps 1:1 to the engine's `@dataclass(frozen=True)` constructor arguments:

### RegisterDepositRequest → NMDDeposit
- `category` is a string from a controlled vocabulary (RETAIL_STABLE, RETAIL_LESS_STABLE, SME_OPERATIONAL, CORPORATE_OPERATIONAL, CORPORATE_NON_OPERATIONAL, INSTITUTIONAL_NON_OPERATIONAL, PUBLIC_SECTOR). Endpoint converts via `NMDDepositCategory(req.category)`. Bad string → HTTP 400 with valid values listed.
- `balance` is `float` in the Pydantic model, converted to `Decimal(str(balance))` for the engine (Decimal-internal precision per the platform's no-float-on-money rule).

### RegisterHQLARequest → HQLAPosition
- `level` is one of LEVEL_1, LEVEL_2A, LEVEL_2B, NOT_HQLA. Same conversion + 400 pattern.
- `asset_class` is free-form string label (e.g. "CBK_BILL", "GOK_BOND", "CORPORATE_BOND_AAA").

### CashFlowRequest → CashFlow
- One Pydantic model serves both `add-inflow` and `add-outflow`. The endpoint forces `direction="INFLOW"` or `direction="OUTFLOW"` regardless of what's in the request — operator can't accidentally route an outflow to the inflow endpoint.
- `bucket_days: int` — LCR uses 0..30; engine accepts arbitrary integer.

### RegisterRatesPositionRequest → RatesGapPosition
- `bucket` is one of OVERNIGHT, 2D_7D, 8D_1M, 1M_3M, 3M_6M, 6M_1Y, 1Y_2Y, 2Y_5Y, 5Y+. Same enum conversion pattern.
- `is_asset: bool` — True for assets, False for liabilities (real field name on this dataclass).

### RegisterFXPositionRequest → FXPosition
- `instrument_type` constrained to FX_SPOT / FX_FORWARD / FX_SWAP. Endpoint validates that the instrument_type is FX-family even though the engine's InstrumentType enum has more values (MM, CD, BOND, etc.) — wouldn't make sense to register a Money Market position via the FX endpoint.
- **`is_long_base: bool`** (NOT `is_asset` — the v10.156 pre-ship bug).

---

## Honest deferral surfaces — what defers to v10.157

Updated GET `/api/treasury/liquidity-risk/methods` placeholder enumerates two structured fields:

**`live_state_loaders`** — 6 endpoints with `shipped_in: 'v10.156'` tags listing path + Pydantic model name.

**`deferred_methods`** — 7 entries with `deferred_to: 'v10.157'` tags:
- `register_yield_curve` (YieldCurve with nested `points: Tuple[YieldCurvePoint, ...]` — needs nested Pydantic model)
- `register_bond_position` (BondPosition with full coupon/maturity/rating shape)
- `register_mm_position` (MoneyMarketPosition)
- `register_connector` (Connector with `FrozenSet[MessageFormat]`)
- `register_mmf` (MmfCounterparty)
- `available_stable_funding` / `required_stable_funding` (List[FundingItem] / List[AssetItem] for NSFR ASF/RSF computation)

Operators reading the API discover both what's shipped and what's explicitly deferred — same discipline as ENH-139 PROXY MODE and ENH-138 no_product_resolution.

---

## Tests — `tests/test_treasury_state_loaders_v10_156.py`

18 tests across 6 classes:

- **TestNewPydanticModels** (2) — 5 models present (RegisterDepositRequest, RegisterHQLARequest, CashFlowRequest, RegisterRatesPositionRequest, RegisterFXPositionRequest) + all inherit `BaseModel`
- **TestNewPostEndpoints** (3) — 6 endpoint paths present + 11+ `@router.post` decorators total (5 from v10.155 + 6 from v10.156) + every POST JWT-protected
- **TestSignatureDiscipline** (2) — **FXPosition uses `is_long_base` NOT `is_asset`** (codifies the pre-ship catch), `_audit_treasury` still uses real `audit_log` signature carrying forward v10.155 enforcement
- **TestRoundTripConversions** (6) — each of 6 endpoints exercises Pydantic→dataclass→register conversion end-to-end; engine state changes verified via `board_summary` counters (`n_deposits`, `n_hqla_positions`, `n_rates_positions`, `n_fx_positions`)
- **TestUpdatedDeferralPlaceholder** (2) — placeholder reflects v10.156 ships + remaining defers to v10.157
- **TestNoRegression** (3) — G147+G148+G149+G150+G151 still pass / total gate count unchanged at 151 / api module still loads

All 18 pass via inline runner.

---

## Apply order

After v10.155:

```
1. utils/api_treasury.py                           → utils/  (REPLACES v10.155)
2. tests/test_treasury_state_loaders_v10_156.py    → tests/  (NEW)
3. docs/Master_Prompt_v3.49.md                     → docs/
4. SCOPE_LEDGER.md                                 → root
5. CHANGELOG_v10.156.md                            → root
```

`git add -A && git commit -m "v10.156 Treasury state-loading endpoints — Pydantic→engine conversion verified"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

**No app.py change, no scripts/audit.py change, no admin/registry change. Pure engine-layer work.** If you've already mounted the Treasury router in your FastAPI app per v10.155, no remount needed — the new endpoints register automatically when the router is reloaded.

---

## What users gain

The Treasury arc API now supports the full state-load → compute workflow end-to-end:

```
1. POST /api/treasury/alm/register-hqla       (HQLA Level 1, KES 100M)
2. POST /api/treasury/alm/add-outflow          (KES 50M outflow, 30-day bucket)
3. POST /api/treasury/alm/add-inflow           (KES 20M inflow, 30-day bucket)
4. POST /api/treasury/alm/run-lcr              (compute LCR against the loaded state)
   → Returns LCR ratio, compliant flag, per-bucket details
```

Same pattern for IRRBB:

```
1. POST /api/treasury/alm/register-rates-position  (asset, 3M_6M, KES 50M)
2. POST /api/treasury/alm/run-repricing-gap        (compute gap against loaded positions)
```

And for FX:

```
1. POST /api/treasury/products/register-fx-position  (USD/KES SPOT, $1M long)
   → Available for net exposure / MTM via /api/treasury/products/board endpoint
   → mtm_fx_position compute endpoint defers to v10.157 (needs spot rate state)
```

The React frontend can drive end-to-end LCR / NSFR / IRRBB workflows without going through the Streamlit cockpit. Streamlit cockpit's Liquidity & ALM tab will gain "Load HQLA / Load Cashflows" form widgets in a future drop that wires the cockpit to these POST endpoints.

---

## What this drop does NOT change

- No engine modifications. Treasury engines were already implemented; v10.156 just exposes their existing state-loading methods over JSON.
- No registry changes. All 18 Treasury standards remain `status='active'`.
- No `app.py` changes. The router is the same one mounted in v10.155.
- No new audit gates. v10.156 is engine-level work between closure milestones.
- No closure status changes. Phase 2 Treasury remains closed (G150/G151 still pass).

---

## v10.157 next-up

Complete the remaining Treasury state-loading endpoints (the complex-shape ones that deferred from v10.156):

- `register_yield_curve` — needs nested `YieldCurvePoint` Pydantic model with `tenor_years: Decimal`, `rate_pct: Decimal`. Endpoint accepts list of points, converts to tuple of frozen YieldCurvePoint, wraps in YieldCurve.
- `register_bond_position` — full BondPosition shape: position_id, instrument_type (GOVT_BOND / CORPORATE_BOND), isin, issuer, currency, face_value, coupon_pct, coupon_freq_per_year, plus maturity/rating fields.
- `register_mm_position` — MoneyMarketPosition (similar shape to FXPosition but for term deposits / borrowings / CDs / commercial paper).
- `register_connector`, `register_mmf` — for the connectivity engine.
- Compute endpoints: `set_spot_rate`, `mtm_fx_position`, `mtm_bond`.

After v10.157, Phase 2 Treasury is fully complete on both read AND write sides. Phase 3 module selection (Cards / Customer Behavioral Intelligence / Continuation.docx Phase 3) opens — user picks the next module to close.

---

## Summary

v10.156 honors the v10.155 deferral by shipping POST endpoints for the simple-shape state-loading methods. 30 total endpoints in the Treasury router, all JWT-protected. Pre-ship round-trip probe caught a real bug (FXPosition `is_asset` → `is_long_base`) before user testing — codified into TestRoundTripConversions class so the same bug class can't recur silently. Honest deferral surfaces enumerate what shipped (`live_state_loaders`) vs what's deferred (`deferred_methods` with `deferred_to: 'v10.157'` tags). Total active 147/264 (55.7%).

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. v10.156 tests `18/18 pass`.
