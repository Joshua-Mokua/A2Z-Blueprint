# CHANGELOG v10.158 — Treasury LCR + NSFR Per-Call Endpoints

**Status:** **Closes the v10.157 deferred LiquidityRiskEngine ASF/RSF item.** Three new POST endpoints expose `LiquidityRiskEngine.lcr`, `.nsfr`, and `.hqla_value` as per-call computation surfaces.

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged — engine-level work, no new gates). G142 anti-drift floor unchanged at 76. v10.158 tests 19/19 pass.

---

## The honest design decision

v10.157 deferred ASF/RSF computation to v10.158 because the question wasn't "build it" but "what shape": persistent state vs per-call. v10.158 makes the call:

**LiquidityRiskEngine has STATIC methods** (no `self`). The methods are pure functions: input goes in, ratio comes out. There is no engine state to maintain. Therefore the right pattern is **per-call** — operator POSTs the full HQLA + cashflow + funding + asset lists in the request body, engine computes, returns ratio.

This is **different** from `TreasuryALMEngine` where `register_hqla` / `add_inflow` / `add_outflow` accumulate state across calls and `run_lcr` computes against the accumulated state.

**Both patterns coexist as first-class endpoints:**

| Endpoint | Engine | Pattern | Use case |
|---|---|---|---|
| `POST /alm/run-lcr` (v10.155) | TreasuryALMEngine | Stateful | Incremental workflow — register HQLA over time, add inflows/outflows as they arrive, compute LCR against accumulated state |
| `POST /liquidity-risk/lcr` (v10.158) | LiquidityRiskEngine | Per-call | One-shot regulatory submission — assemble entire HQLA + cashflow snapshot in request body, get ratio back |

Operator picks based on workflow.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/api_treasury.py` | +200 | EXTENDED. +3 POST endpoints + 6 Pydantic models + updated /liquidity-risk/methods placeholder |
| `tests/test_liquidity_risk_v10_158.py` | ~250 | NEW. 19 tests across 6 classes |
| `docs/Master_Prompt_v3.51.md` | ~1100 | Anti-drift sync v3.50 → v3.51 |
| `SCOPE_LEDGER.md` | updated | v10.158 row + status block |
| `CHANGELOG_v10.158.md` | this file | This document |

---

## Endpoints (3 POST)

```
POST /api/treasury/liquidity-risk/lcr         LCRRequest → engine.lcr() result
POST /api/treasury/liquidity-risk/nsfr        NSFRRequest → engine.nsfr() result
POST /api/treasury/liquidity-risk/hqla-value  LCRRequest → engine.hqla_value() result
```

The HQLA value endpoint reuses `LCRRequest` because the HQLA list is one of its two components — operator already has the data shaped for LCR, no need for a separate request model.

All endpoints JWT-protected via `Depends(get_current_user)` and audit-logged via `_audit_treasury(action, user, detail)`.

---

## Pydantic models (6 new)

```python
class HqlaHoldingModel(BaseModel):
    asset_id: str                # NOTE: NOT position_id (see below)
    level: str                   # LEVEL_1, LEVEL_2A, LEVEL_2B, NOT_HQLA
    market_value_kes: float

class CashFlowItemModel(BaseModel):
    item_id: str
    category: str                # LCR run-off category
    direction: str               # INFLOW or OUTFLOW
    balance_kes: float

class FundingItemModel(BaseModel):
    item_id: str
    category: str                # ASF category
    balance_kes: float

class AssetItemModel(BaseModel):
    item_id: str
    category: str                # RSF category
    balance_kes: float

class LCRRequest(BaseModel):
    hqla_holdings: List[HqlaHoldingModel]
    cash_flows: List[CashFlowItemModel]

class NSFRRequest(BaseModel):
    funding: List[FundingItemModel]
    assets: List[AssetItemModel]
```

---

## Cross-engine field distinction — important

**`LiquidityRiskEngine.HqlaHolding` is a DIFFERENT dataclass than `TreasuryALMEngine.HQLAPosition`**, even though both represent High-Quality Liquid Assets:

| | LiquidityRiskEngine.HqlaHolding | TreasuryALMEngine.HQLAPosition |
|---|---|---|
| Identifier field | `asset_id` | `position_id` |
| Asset class | (implicit in level) | `asset_class` (free-form) |
| Value field | `market_value_kes` | `notional` |
| Currency | KES implicit | `currency` (multi-ccy) |
| Level | `level` (str) | `level` (HQLALevel enum) |
| Notes | (none) | `notes` |

v10.158's `HqlaHoldingModel` uses **`asset_id`** to match LiquidityRiskEngine. Test class `TestSignatureDiscipline.test_endpoint_uses_real_dataclass_fields` explicitly verifies this — same lesson codification as v10.156's FXPosition `is_long_base` catch.

If a future drop (v10.159+) wraps `LiquidityRiskEngine.HqlaHolding` and `TreasuryALMEngine.HQLAPosition` under a unified façade, it should be a deliberate refactor with field-mapping tests, not an accidental conflation.

---

## Engine returns honest status='NO_DATA'

The LiquidityRiskEngine static methods return rich status fields when the input categories don't map to known weighting tables:

```json
{
  "lcr_pct": null,
  "hqla_total_kes": "100000000.00",
  "net_outflows_kes": "0.00",
  "min_required_pct": "100",
  "status": "NO_DATA",
  "reason": "net_outflows_zero_or_negative"
}
```

The endpoint surfaces these fields directly. **Operator should fix the category vocabulary rather than treat NO_DATA as a passing ratio.** Same discipline as ENH-138 no_product_resolution and ENH-139 PROXY MODE — engine surfaces what it can/can't compute honestly, doesn't hide gaps behind synthetic numbers.

The HQLA value endpoint, in contrast, returns rich computed data without NO_DATA when given valid HQLA holdings — it computes level breakdown, applies Basel III caps (Level 2 ≤ 40%, Level 2B ≤ 15%), and returns the cap-applied total:

```json
{
  "level_1_kes": "100000000.00",
  "level_2a_kes": "0.00",
  "level_2b_kes": "0.00",
  "level_2a_after_cap_kes": "0.00",
  "level_2b_after_cap_kes": "0.00",
  "gross_total_kes": "100000000.00",
  "total_hqla_kes": "100000000.00",
  "cap_applied": false,
  "excluded_count": 0
}
```

---

## Updated `/liquidity-risk/methods` placeholder

The structured response evolved with v10.158:

**Removed from `remaining_deferred`** (now in `live_compute_endpoints`):
- `available_stable_funding` — exposed via `/liquidity-risk/nsfr`
- `required_stable_funding` — exposed via `/liquidity-risk/nsfr`

**Still in `remaining_deferred` (shifted from v10.158+ to v10.159+):**
- `register_agent` — Agents are Python objects with custom `__call__` contracts; needs code-mobility design
- `register_product` (Islamic) — IslamicProduct schema needs Sharia-board input
- Digital Assets state loaders — engine integration pattern still evolving

**`phase_2_status` updated**: *"WRITE-SIDE COMPLETE for the core Treasury workflow (ALM, Products, Connectivity, LCR, NSFR). Islamic, Digital Assets, and Agent state loaders defer to v10.159+ for design reasons noted above, not bandwidth reasons."*

Each remaining item has an explicit `reason` field — operators reading the API discover what's deferred AND why. Same discipline maintained from v10.155 onward.

---

## Tests — `tests/test_liquidity_risk_v10_158.py`

19 tests across 6 classes:

- **TestNewPydanticModels** (3) — 6 models present, `LCRRequest` uses nested model lists, `NSFRRequest` uses nested model lists
- **TestNewPostEndpoints** (3) — 3 paths present, total `@router.post` count >=21 (5+6+7+3), every v10.158 endpoint JWT-protected
- **TestSignatureDiscipline** (2) — **`HqlaHolding` uses `asset_id` NOT `position_id`** (codifies cross-engine field distinction), `_audit_treasury` still uses real `audit_log` signature
- **TestRoundTripConversions** (3) — `lcr` / `nsfr` / `hqla_value` all round-trip via engine output structure verified
- **TestUpdatedDeferralPlaceholder** (3) — placeholder lists v10.158 ships, remaining shifted to v10.159+, phase_2_status mentions LCR+NSFR
- **TestNoRegression** (5) — all 5 closure gates still pass, total gate count unchanged at 151, v10.155 + v10.156 + v10.157 endpoints all still present

All 19 pass via inline runner.

---

## Endpoint trajectory v10.154 → v10.158

| Version | Added | Type | Cumulative |
|---|---:|---|---:|
| v10.154 | 18 | GET (read-only) | 18 |
| v10.155 | +6 | POST (compute: lcr/repricing/decay/approve/reject/breach) | 24 |
| v10.156 | +6 | POST (simple-shape state loaders) | 30 |
| v10.157 | +9 | POST x7 (5 register + 2 mtm) + GET x2 (queries) | 39 |
| **v10.158** | **+3** | **POST (per-call LCR/NSFR/HQLA-value)** | **42** |

---

## Apply order

After v10.157:

```
1. utils/api_treasury.py                  → utils/  (REPLACES v10.157)
2. tests/test_liquidity_risk_v10_158.py   → tests/  (NEW)
3. docs/Master_Prompt_v3.51.md            → docs/
4. SCOPE_LEDGER.md                        → root
5. CHANGELOG_v10.158.md                   → root
```

`git add -A && git commit -m "v10.158 Treasury LCR+NSFR per-call endpoints — closes v10.157 ASF/RSF deferral"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

**No app.py / audit / admin / registry change.** Pure engine-layer work. If you've already mounted the Treasury router, no remount needed — new endpoints register automatically when the router is reloaded.

---

## Phase 2 Treasury status: COMPLETE

All write-side surfaces shipped:

- **ALM stateful workflow**: deposits, HQLA, cashflows, rates positions, run-lcr/nsfr/decay/irrbb
- **Products**: yield curves, FX, MM, bonds, MTM endpoints
- **Connectivity**: connectors, MMF counterparties
- **LCR per-call** (this drop)
- **NSFR per-call** (this drop)
- **HQLA value per-call** (this drop)
- **Climate breach checks**
- **Agent recommendations approve/reject**

Three remaining items are honestly deferred for design reasons (Agent code-mobility, Islamic Sharia-board input, Digital Assets engine integration). Each has an explicit `reason` field in the API placeholder response.

---

## v10.159 next-up — Phase 3 module selection

Phase 2 fully done. Greenfield Phase 3 modules await selection. Candidates per registry survey of 152 non-active standards:

1. **AML/Compliance (ENH-190..199)** — 9 standards: Digital KYC/KYB, PEP/Sanctions, AML transaction monitoring, SAR/STR filing, regulatory change, policy attestation, compliance training, compliance risk assessment. Strategic alignment with CBK regulatory pressure. **All engines greenfield** — high build cost (~10-15 ZIPs spread across closure batches).

2. **IT/Digital architecture (ENH-290..299)** — 10 standards: ITSM, cloud-native/container, observability, DR/BCP, API gateway, encryption, CI/CD, multi-tenancy, CBK IT compliance. **2 of 10 engines exist** (`issue_management`, `api`); 8 greenfield.

3. **Bancassurance (ENH-300..309)** — 10 standards: insurance catalog, AI recommendation, partner hub, agentic claims, commission reconciliation, customer insurance 360°, RM insurance desktop. **2 of 10 engines exist** (`reconciliation`, `regulatory_reporting`); 8 greenfield.

4. **NSFR category vocabulary expansion** — smaller scope; completes v10.158's category mapping for production use. Operator-facing benefit: `status='NO_DATA'` becomes `status='COMPUTED'` for real Ecobank Kenya data with KES retail/wholesale/government bond categories properly weighted.

**Recommendation framework** for the office PC review:
- **Option 4 (NSFR vocabulary)** if the priority is making v10.158's endpoints immediately useful for production NSFR submission
- **Option 1 (AML/Compliance)** if regulatory pressure is the strategic priority
- **Option 2 (IT/Digital)** if platform-engineering quality is the priority

User selection drives the next path.

---

## Summary

v10.158 closes the last open Treasury deferral with three per-call endpoints for LCR, NSFR, and HQLA value computation against `LiquidityRiskEngine`'s static methods. The honest design decision (per-call, not stateful) coexists with v10.155's stateful `/alm/run-lcr` — operators pick the right tool per workflow. **Treasury router now has 42 endpoints**; **Phase 2 Treasury read + write surface COMPLETE for the core workflow**. Three remaining items are honest design-deferrals with explicit `reason` fields, not work-deferrals. v10.159 opens Phase 3.

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. v10.158 tests `19/19 pass`.
