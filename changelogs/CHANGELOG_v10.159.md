# CHANGELOG v10.159 — Treasury LCR/NSFR Category Vocabulary Discovery

**Status:** Closes the v10.158 production-readiness gap. The v10.158 endpoints (lcr, nsfr, hqla-value) work correctly, but operators couldn't discover which `category` strings to put in their request payloads without reading the engine source code. v10.159 publishes the engine's full Basel III standardised vocabulary as a discoverable JSON endpoint.

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged — engine-level work, no new gates). G142 anti-drift floor unchanged at 76. v10.159 tests 15/15 pass.

---

## The honest reframing

Initial framing was "category vocabulary expansion" — implying engine work to add new categories. After inspecting `utils/liquidity_risk.py`, the Basel III standardised vocabulary turned out to be **already complete**: 8 outflow categories, 4 inflow categories, 6 ASF categories, 11 RSF categories, 3 HQLA levels, all with proper Basel III weights.

The real gap wasn't engine capability — it was **discoverability**. Operators couldn't see what to use without reading the source code. Engine returned `status='NO_DATA'` for unknown categories — correct behaviour, but unhelpful for operators building their first request.

The honest fix is smaller and better: publish the existing vocabulary as a JSON endpoint.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/api_treasury.py` | +130 | EXTENDED. +1 GET endpoint publishing 29 Basel III categories |
| `tests/test_liquidity_risk_vocabulary_v10_159.py` | ~250 | NEW. 15 tests across 6 classes |
| `docs/Master_Prompt_v3.52.md` | ~1100 | Anti-drift sync v3.51 → v3.52 |
| `SCOPE_LEDGER.md` | updated | v10.159 row + status block |
| `CHANGELOG_v10.159.md` | this file | This document |

---

## The endpoint

```
GET /api/treasury/liquidity-risk/vocabulary
```

Returns structured JSON with **29 category entries** organised by table:

### HQLA levels (3)
| Level | Haircut |
|---|---:|
| LEVEL_1 | 0% |
| LEVEL_2A | 15% |
| LEVEL_2B | 50% |

Plus caps: Level 2 total ≤ 40% of HQLA, Level 2B alone ≤ 15%.

### LCR outflow categories (8)
| Category | Run-off rate |
|---|---:|
| RETAIL_DEPOSITS_STABLE | 5% |
| RETAIL_DEPOSITS_LESS_STABLE | 10% |
| SME_OPERATIONAL | 25% |
| CORPORATE_NON_FINANCIAL | 40% |
| FINANCIAL_COUNTERPARTY | 100% |
| UNDRAWN_CREDIT_FACILITIES | 10% |
| UNDRAWN_LIQUIDITY_FACILITIES | 30% |
| DERIVATIVES_NET_OUTFLOW | 100% |

### LCR inflow categories (4)
| Category | Inflow rate |
|---|---:|
| RETAIL_LOAN_INFLOWS | 50% |
| WHOLESALE_LOAN_INFLOWS | 50% |
| SECURED_LENDING | 100% |
| OPERATIONAL_DEPOSITS_HELD | 0% |

Plus inflow cap: total inflows ≤ 75% of total outflows (Basel III).

### NSFR ASF categories (6)
| Category | ASF factor |
|---|---:|
| TIER_1_CAPITAL | 100% |
| TIER_2_CAPITAL | 100% |
| RETAIL_DEPOSITS_LT_1Y | 90% |
| WHOLESALE_FUNDING_LT_1Y | 50% |
| OPERATIONAL_DEPOSITS | 50% |
| OTHER_LIABILITIES_LT_6M | 0% |

### NSFR RSF categories (11)
| Category | RSF factor |
|---|---:|
| CASH | 0% |
| CENTRAL_BANK_RESERVES | 0% |
| LEVEL_1_HQLA | 5% |
| LEVEL_2A_HQLA | 15% |
| LEVEL_2B_HQLA | 50% |
| RETAIL_LOANS_LT_1Y | 50% |
| RETAIL_LOANS_GTE_1Y | 65% |
| CORPORATE_LOANS_LT_1Y | 50% |
| CORPORATE_LOANS_GTE_1Y | 85% |
| MORTGAGE_LOANS | 65% |
| OTHER_ASSETS | 100% |

### Thresholds (5)
- LCR_MIN_PCT (default 100%, sourced from system_invariants registry)
- NSFR_MIN_PCT (default 100%, sourced from system_invariants registry)
- LEVEL_2_TOTAL_CAP_PCT (40%)
- LEVEL_2B_CAP_PCT (15%)
- INFLOW_CAP_PCT_OF_OUTFLOWS (75%)

### `endpoint_field` cross-references

Each table's response section includes an `endpoint_field` mapping the vocabulary back to the Pydantic request model field name. Example:

```json
"lcr_outflow_categories": {
  "endpoint_field": "category in CashFlowItemModel with direction=OUTFLOW",
  "valid_values": ["RETAIL_DEPOSITS_STABLE", ...],
  "run_off_rate_pct_by_category": {"RETAIL_DEPOSITS_STABLE": "5", ...}
}
```

Operators discover not just **what** the categories are but **which request field consumes them**.

---

## Live import from engine constants

The endpoint imports constants live from `utils/liquidity_risk.py` at request time:

```python
from utils.liquidity_risk import (
    HQLA_HAIRCUT_PCT, LEVEL_2_TOTAL_CAP_PCT, LEVEL_2B_CAP_PCT,
    LCR_MIN_PCT, NSFR_MIN_PCT,
    OUTFLOW_RATES_PCT, INFLOW_RATES_PCT,
    INFLOW_CAP_PCT_OF_OUTFLOWS,
    ASF_FACTORS_PCT, RSF_FACTORS_PCT,
)
```

If engine constants change (CBK adjusts run-off rates, LCR_MIN goes from 100% to 110%, etc.), the vocabulary endpoint reflects new values automatically — **no code change in api_treasury.py**. Same anti-drift discipline as the registry approach used for LCR_MIN/NSFR_MIN thresholds in v7.0.1+ (defensive fallback to hardcoded constants if registry import fails).

Test class `TestVocabularyMatchesEngine.test_endpoint_imports_constants_from_engine` explicitly verifies this — endpoint must use `from utils.liquidity_risk import` not hardcoded values.

---

## Honest design note in the response

The endpoint response includes a `honest_design_note` field:

> *"This vocabulary is the Basel III standardised approach. It does NOT yet include CBK-specific category extensions (e.g. KEPSS-settled wholesale, M-Pesa float deposits). Adding Kenya-specific categories is a deliberate extension that requires regulatory review and weight calibration — out of scope for v10.159; tracked as future work."*

Operators reading the API discover this limitation **explicitly**, not by surprise when their KEPSS-categorised data returns `status='NO_DATA'`. Same discipline as ENH-138 no_product_resolution and ENH-139 PROXY MODE — surface gaps honestly, don't hide them.

---

## Production readiness verified

`TestProductionReadinessLCR` + `TestProductionReadinessNSFR` assert that with categories from the published vocabulary, the engine produces COMPUTED ratios:

### Realistic Ecobank Kenya LCR snapshot (in test data)

```
HQLA:
  H1: LEVEL_1, 10,000,000,000 KES (CBK reserves + GOK bills)
  H2: LEVEL_2A, 5,000,000,000 KES (sovereign bonds)

Cash flows:
  O1: RETAIL_DEPOSITS_STABLE,    50,000,000,000 KES OUTFLOW (5% run-off)
  O2: RETAIL_DEPOSITS_LESS_STABLE, 30,000,000,000 KES OUTFLOW (10%)
  O3: SME_OPERATIONAL,            5,000,000,000 KES OUTFLOW (25%)
  O4: CORPORATE_NON_FINANCIAL,   10,000,000,000 KES OUTFLOW (40%)
  I1: RETAIL_LOAN_INFLOWS,        8,000,000,000 KES INFLOW (50%)
```

**Result:**
```
lcr_pct: 211.11
hqla_total_kes: 14,250,000,000.00
net_outflows_kes: 6,750,000,000.00
status: GREEN
compliant: true
hqla_breakdown: { level_1: 10B, level_2a_after_cap: 4.25B, ... }
nco_breakdown: { total_outflows: 10.75B, total_inflows: 4B (uncapped), capped_inflows: 4B, net: 6.75B }
```

### Realistic NSFR snapshot

```
Funding:
  F1: TIER_1_CAPITAL,           15,000,000,000 KES (100% ASF)
  F2: TIER_2_CAPITAL,            3,000,000,000 KES (100%)
  F3: RETAIL_DEPOSITS_LT_1Y,    80,000,000,000 KES (90%)
  F4: WHOLESALE_FUNDING_LT_1Y,  20,000,000,000 KES (50%)

Assets:
  A1: CASH,                      5,000,000,000 KES (0% RSF)
  A2: LEVEL_1_HQLA,             10,000,000,000 KES (5%)
  A3: RETAIL_LOANS_GTE_1Y,      60,000,000,000 KES (65%)
  A4: CORPORATE_LOANS_GTE_1Y,   30,000,000,000 KES (85%)
  A5: MORTGAGE_LOANS,           12,000,000,000 KES (65%)
```

**Result:**
```
nsfr_pct: 137.36
asf_kes: 100,000,000,000.00
rsf_kes:  72,800,000,000.00
status: GREEN
compliant: true
asf_breakdown: { TIER_1_CAPITAL: 15B, TIER_2_CAPITAL: 3B, RETAIL_DEPOSITS_LT_1Y: 72B, WHOLESALE_FUNDING_LT_1Y: 10B }
rsf_breakdown: { CASH: 0, LEVEL_1_HQLA: 0.5B, RETAIL_LOANS_GTE_1Y: 39B, CORPORATE_LOANS_GTE_1Y: 25.5B, MORTGAGE_LOANS: 7.8B }
```

**The v10.158 endpoints are now demonstrable standalone.** Operator GETs the vocabulary, builds a request, POSTs to /lcr or /nsfr, sees a real CBK-grade ratio. No longer "demoable when the operator reads the source code."

---

## Strategic value for the Ecobank Kenya MIS bid

v10.158 endpoints alone are a feature; with v10.159's vocabulary discovery, they're a **demonstrable workflow**. Vendor competitors typically show feature lists; A2Z MIS 360 now shows operational readiness — operator hits one GET, builds request payload from the discovered vocabulary, POSTs and gets a real CBK-grade LCR ratio back.

That's the qualitative jump from "capability claim" to "capability proof" in a vendor evaluation. The 3 incumbent vendors typically don't ship this kind of self-documenting API surface.

---

## Tests — `tests/test_liquidity_risk_vocabulary_v10_159.py`

15 tests across 6 classes:

- **TestVocabularyEndpointShape** (3) — path present, GET not POST, JWT-protected
- **TestVocabularyContent** (4) — publishes all 5 weight tables, publishes 5 thresholds, lists `endpoint_field` for each table, includes honest CBK design note
- **TestProductionReadinessLCR** (1) — LCR with Basel categories returns COMPUTED ratio not NO_DATA, validates categories are in published vocabulary
- **TestProductionReadinessNSFR** (1) — NSFR with Basel categories returns COMPUTED ratio
- **TestVocabularyMatchesEngine** (2) — engine has expected category minimums, **endpoint imports constants from engine** (not hardcodes them)
- **TestNoRegression** (4) — all 5 closure gates pass, gate count = 151, v10.158 endpoints still present, `_audit_treasury` still uses real signature

All 15 pass via inline runner.

---

## Endpoint trajectory v10.154 → v10.159

| Version | Added | Type | Cumulative |
|---|---:|---|---:|
| v10.154 | 18 | GET (read-only) | 18 |
| v10.155 | +6 | POST (compute: lcr/repricing/decay/approve/reject/breach) | 24 |
| v10.156 | +6 | POST (simple-shape state loaders) | 30 |
| v10.157 | +9 | POST x7 + GET x2 | 39 |
| v10.158 | +3 | POST (per-call LCR/NSFR/HQLA-value) | 42 |
| **v10.159** | **+1** | **GET (vocabulary discovery)** | **43** |

---

## Apply order

After v10.158:

```
1. utils/api_treasury.py                                → utils/  (REPLACES v10.158)
2. tests/test_liquidity_risk_vocabulary_v10_159.py      → tests/  (NEW)
3. docs/Master_Prompt_v3.52.md                          → docs/
4. SCOPE_LEDGER.md                                      → root
5. CHANGELOG_v10.159.md                                 → root
```

`git add -A && git commit -m "v10.159 Treasury vocabulary discovery — closes v10.158 production-readiness gap"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

**No app.py / audit / admin / registry change.** Pure engine-layer surface improvement. If you've already mounted the Treasury router, no remount needed.

---

## Try it after applying

Once mounted in your FastAPI app:

```bash
curl http://your-host/api/treasury/liquidity-risk/vocabulary \
  -H "Authorization: Bearer $YOUR_JWT" | jq .
```

The response shows you exactly which category strings to use in subsequent LCR/NSFR/HQLA-value requests. Build a payload using those categories, POST it to `/api/treasury/liquidity-risk/lcr`, get back a real ratio.

---

## v10.160 next-up — Phase 3 module selection

Phase 2 Treasury fully complete AND production-ready. Greenfield Phase 3 awaits selection. Candidates:

1. **AML/Compliance (ENH-190..199)** — 9 greenfield standards. Strategic CBK alignment.
2. **IT/Digital architecture (ENH-290..299)** — 10 standards, 2 engines exist.
3. **Bancassurance (ENH-300..309)** — 10 standards, 2 engines exist.
4. **CBK-specific category vocabulary extension** — extend v10.159 with M-Pesa float, KEPSS-settled wholesale, agent banking float. Needs regulatory weight calibration (CBK Risk-Based Supervision Framework or equivalent guidance docs). High Ecobank-Kenya-specific value, smaller scope than greenfield modules.

User selection drives the next path.

---

## Summary

v10.159 closes the v10.158 production-readiness gap with a single GET endpoint that publishes the engine's 29 Basel III category vocabulary entries with weights, thresholds, and Pydantic field cross-references. Live import from engine constants (no stale snapshot). Honest design note flags CBK-specific extensions as future work. Production readiness verified by tests that compute real LCR (211%) and NSFR (137%) ratios on realistic Ecobank Kenya snapshots using categories from the published vocabulary.

The strategic effect: v10.158's endpoints went from "demoable when the operator reads source code" to "demoable standalone" — qualitative jump from capability claim to capability proof for the Ecobank Kenya MIS vendor bid.

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. v10.159 tests `15/15 pass`.
