# A2Z MIS 360 — CHANGELOG v5.73

**v5.73 Third Integration Batch — BSC Enhancement (IAS 36 + IAS 1 OCI)**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (unchanged from v5.72)
**Engine batch tests:** 49 files / 2211 tests (unchanged from v5.72)
**Strategic milestone:** **First "modify existing" integration batch** — 2 standards now reachable from existing high-traffic pages without users navigating to a new page. **Cumulative: 9 of 116 standards integrated.**

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.71 + v5.72 both added new dedicated pages (`88_ifrs_engines.py`, `89_capital_risk_engines.py`). v5.73 takes the opposite approach: **enhance existing pages** so standards work appears where users already are.

---

## What was modified

### `pages/19_credit_monitoring.py` — IFRS 9 tab restructured + IAS 36 added
**569 → 798 lines (+229)**

- **Existing tab "📐 IFRS 9 Provisions"** restructured into a 2-sub-tab container labelled **"📐 IFRS 9 / IAS 36 Provisions"**
- **Sub-tab 1: 📐 IFRS 9 (financial assets)** — original ECL staging logic preserved exactly (Stage 1/2/3 by NPL days, summary metrics, account-level table, CSV export)
- **Sub-tab 2: 🔻 IAS 36 (non-financial assets, integrated v5.73)** — new, with 4 inner tabs:
  - **🔍 Indicator check** — all 7 EXTERNAL + 5 INTERNAL indicators per IAS 36.12 with category surfaced via `validate_impairment_indicator()`
  - **🧮 Recoverable amount + impairment loss** — HIGHER OF (VIU, FVLCD) per IAS 36.18 with single-input fallback per IAS 36.20; impairment recognised when CA > RA
  - **📐 Value-in-use (DCF)** — up to 5-year explicit horizon per IAS 36.33 via `value_in_use_pv()`
  - **↻ Reversal eligibility** — goodwill-never-reversed per IAS 36.124 prominently flagged with red banner

### `pages/52_mgmt_accounts.py` — OCI Recycling tab added
**105 → 188 lines (+83)**

- **New tab "♻️ OCI Recycling"** (5th tab, between "📐 Ratios" and "📥 Export") with two sections:
  - **OCI Recycling Map** — full IAS 1 / IFRS 9 / IAS 19R catalogue rendered from the engine's authoritative `OCI_RECYCLING_MAP`:
    - REVALUATION_SURPLUS → **NEVER_RECYCLED** (IAS 16)
    - FVTOCI_DEBT → **RECYCLABLE_TO_PNL** (IFRS 9 — debt FVTOCI does recycle on disposal)
    - FVTOCI_EQUITY → **NEVER_RECYCLED** (IFRS 9 — equity FVTOCI does **NOT** recycle, ever)
    - CASH_FLOW_HEDGE → **RECYCLABLE_TO_PNL** (IFRS 9)
    - DB_REMEASUREMENT → **NEVER_RECYCLED** (IAS 19R post-2013)
  - **Materiality Test** (interactive) — IAS 1.7 thresholds (5% of equity, 5% of revenue, 1% of total assets) with default basis amounts pre-populated from the page's existing balance sheet + P&L data

### `app.py` — UNCHANGED
Both pages were already registered. No nav-group changes needed.

### Engine files — UNCHANGED
`utils/asset_impairment.py` and `utils/ias1_presentation.py` byte-for-byte unchanged.

---

## 21 engine paths verified end-to-end

| Page | Engine call | Output |
|---|---|---|
| mgmt_accounts | `oci_classification("REVALUATION_SURPLUS")` | NEVER_RECYCLED |
| mgmt_accounts | `oci_classification("FVTOCI_DEBT_FAIR_VALUE_CHANGES")` | RECYCLABLE_TO_PNL |
| mgmt_accounts | `oci_classification("FVTOCI_EQUITY_FAIR_VALUE_CHANGES")` | NEVER_RECYCLED |
| mgmt_accounts | `oci_classification("CASH_FLOW_HEDGE_RESERVE")` | RECYCLABLE_TO_PNL |
| mgmt_accounts | `oci_classification("DEFINED_BENEFIT_REMEASUREMENT")` | NEVER_RECYCLED |
| mgmt_accounts | `materiality_test(5M, EQUITY, 100M)` | 5% boundary, **NOT material** |
| mgmt_accounts | `materiality_test(6M, EQUITY, 100M)` | 6% > 5%, **MATERIAL** |
| credit_monitoring | `validate_impairment_indicator("MARKET_VALUE_DECLINE_SIGNIFICANT")` | valid=True, EXTERNAL |
| credit_monitoring | `validate_impairment_indicator("OBSOLESCENCE")` | valid=True, INTERNAL |
| credit_monitoring | `validate_impairment_indicator("INVALID_NAME")` | valid=False, surfaces valid list |
| credit_monitoring | `recoverable_amount(VIU=85M, FVLCD=80M)` | 85,000,000.00 (basis=VALUE_IN_USE) |
| credit_monitoring | `recoverable_amount(VIU=80M, FVLCD=85M)` | 85,000,000.00 (basis=FVLCD) |
| credit_monitoring | `recoverable_amount(VIU=None, FVLCD=80M)` | 80,000,000.00 (single input per 36.20) |
| credit_monitoring | `impairment_loss(CA=100M, RA=85M)` | loss 15,000,000.00, impaired=True |
| credit_monitoring | `impairment_loss(CA=85M, RA=100M)` | loss 0, impaired=False |
| credit_monitoring | `value_in_use_pv(5y CFs @ 12%)` | 43,675,032.11 |
| credit_monitoring | `reversal_eligibility("GOODWILL")` | **allowed=False** (IAS 36.124 banner) |
| credit_monitoring | `reversal_eligibility("TANGIBLE_ASSET")` | allowed=True (IAS 36.117 ceiling) |
| credit_monitoring | `reversal_eligibility("INTANGIBLE_ASSET")` | allowed=True |
| credit_monitoring | `reversal_eligibility("CASH_GENERATING_UNIT")` | allowed=True |
| credit_monitoring | `reversal_eligibility("INVESTMENT_PROPERTY")` | allowed=True |

---

## Critical guardrail caught at audit time

**The platform's G4 audit gate enforces a 7-tab-per-page limit.**

Initial v5.73 build added IAS 36 as an **8th top-level tab** on `credit_monitoring.py`, which dropped the audit from 103/103 to **102/103**:

```
❌ [G4] tab_counts               1 pages exceed 7-tab limit
       • 19_credit_monitoring.py: 8 tabs (top-level)
```

**This is exactly the kind of architectural drift the audit gates exist to catch.** The fix was not a workaround but the correct answer: restructure the existing "IFRS 9 Provisions" tab into a 2-sub-tab container holding both IFRS 9 (financial assets) and IAS 36 (non-financial assets). They conceptually belong together — both deal with asset impairment, just different asset classes — and grouping them is more useful for the user than keeping them as separate top-level tabs.

After the fix: **103/103 PASS** restored.

This validates that the audit gates catch real architectural issues, not just engine constants.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "IAS1 #111: OCI recycling map viewed on mgmt_accounts page")
audit_log("IFRS_ENGINE_USED", uname, "IAS1 #111: Materiality 6.0M vs 100.0M EQUITY → material=True")
audit_log("IFRS_ENGINE_USED", uname, "IAS36 #105: Indicators flagged ext=['MARKET_VALUE_DECLINE_SIGNIFICANT']")
audit_log("IFRS_ENGINE_USED", uname, "IAS36 #105: Impairment CA=100M RA=85M loss=15M impaired=True")
audit_log("IFRS_ENGINE_USED", uname, "IAS36 #105: Reversal check GOODWILL → allowed=False")
```

---

## Honesty discipline visualised

- **Goodwill non-reversal warning** — IAS 36.124 surfaced as a red banner, not a footnote
- **OCI recycling distinguishes equity vs debt FVTOCI** — the most common error in IFRS reporting
- **DB remeasurement explicitly NEVER recycled** per IAS 19R post-2013
- **Materiality thresholds bound byte-for-byte** to engine constants (no hardcoded percentages in page)
- Every engine call audit-logged

---

## What didn't change

- Both engine source files — byte-for-byte unchanged
- `scripts/audit.py` — gates G92 (asset_impairment) / G100 (ias1_ias8) still pass exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- v5.71 + v5.72 dedicated pages — unchanged

---

## Comparison vs v5.72

| | v5.72 | v5.73 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **7** | **9** ⭐ |
| Audit gates | 103/103 | 103/103 (unchanged) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 89 numbered | 89 numbered (unchanged) |
| **Modified existing pages** | 0 | **2** (first batch to do this) |
| Lines added across pages | — | +312 (+229 to credit_monitoring + +83 to mgmt_accounts) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Pages pass `python -m py_compile`, module-level import test in mocked-Streamlit, and 21-path engine call simulation at the CLI. What I **cannot** do is run `streamlit run app.py` to confirm browser rendering — particularly the new sub-tab nesting structure on `credit_monitoring.py`. User must do that locally.

2. **9 of 116 integrated.** 107 standards remain library-only.

3. **`pages/1_perform.py` (BSC main page) was NOT modified** despite the v5.72 changelog suggesting it would be. The BSC page is **1,908 lines** and modifying it carries higher regression risk than enhancing the more compact `mgmt_accounts.py` (105 → 188 lines) and `credit_monitoring.py` (569 → 798 lines). Both target standards (IAS 36 impairment, IAS 1 OCI) fit more naturally on these pages than on the BSC:
   - **IAS 36 in credit_monitoring** — impairment thinking already happens there for IFRS 9; users get IAS 36 one click away
   - **IAS 1 OCI in mgmt_accounts** — balance sheet + P&L are already shown; OCI recycling fits the same close-process flow
   The BSC will get attention in a future batch when there's a clear high-value standard to surface there.

4. **The 8th-tab attempt failing G4** was instructive — documented in detail above. The audit gates catch real architectural drift, not just engine constants. The fix (sub-tab restructuring) is the correct architectural answer.

5. **Page modifications increase regression risk.** Unlike v5.71/v5.72 which added entirely new pages, modifying existing pages means any bug introduced could break workflows users already depend on. The IFRS 9 sub-tab (sub-tab 0) preserves the original logic byte-for-byte; the IAS 36 sub-tab (sub-tab 1) is purely additive. The OCI Recycling tab on mgmt_accounts is purely additive (new tab between Ratios and Export).

6. **No changes to engine files.** This was deliberate — engine code drift is the highest-risk change. All modifications are at the page (UI) layer.

---

## Next batch options ranked by impact

| Priority | Batch | Standards | Strategy |
|---|---|---|---|
| **(1) Recommended** | Vendor Risk + Procurement | #96 + cross-ref to #98 | Enhance `pages/64_vendors.py` |
| (2) | Customer 360 + Disclosures | #95 CLV + #110 IFRS 7 + #116 IAS 24 | Enhance `pages/34_customer360.py` |
| (3) | Treasury / ALM | #75 FX + #71 LCR/NSFR | Enhance `pages/25_treasury.py` + `pages/81_alm.py` |
| (4) | Stress Testing | #79 | Enhance `pages/35_stress_testing.py` |
| (5) | HR Performance | #63 + #64 | Enhance `pages/2_people.py` |

Recommend **(1) Vendor Risk + Procurement** for v5.74 — closes the operational risk gap and complements the v5.71 procurement integration. Vendor risk scoring is high-stakes for any regulated bank (Ecobank Kenya in particular has CBK PG/06 third-party risk requirements).

---

**Cumulative tally:** 116 standards delivered, **9 integrated into UI via 2 dedicated pages + 2 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.
