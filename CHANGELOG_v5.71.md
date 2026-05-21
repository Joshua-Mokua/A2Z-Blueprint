# A2Z MIS 360 — CHANGELOG v5.71

**v5.71 First Integration Batch — IFRS Engines Studio**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (unchanged from v5.70)
**Engine batch tests:** 49 files / 2211 tests (unchanged from v5.70)
**Strategic milestone:** **First daylight for the standards library** — 3 of the 116 deterministic engines are now callable from the live Streamlit UI.

---

## What this batch is — and what it isn't

**This is a pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

The 116 deterministic standards engines built in v5.53–v5.70 have lived as a callable library — comprehensively tested by 2211 unit tests, verified by 103/103 byte-for-byte audit gates, but **not actually wired into anything the deployed Streamlit app shows users.** This batch closes that gap for the first 3 standards, establishing the pattern that the remaining 113 will follow.

---

## What was built

### `pages/88_ifrs_engines.py` — IFRS Engines Studio (NEW)

A single consolidated entry point with **4 top-level tabs** and **13 sub-tabs**:

| Top-level tab | Standard | Engine | Sub-tabs |
|---|---|---|---|
| 🧾 Tax & VAT Compliance | #97 | `TaxComplianceEngine` | VAT Payable · Corporate Tax · Withholding Tax · Filing Deadlines · Late Penalty |
| 🛒 Procurement Workflow | #98 | `ProcurementWorkflowEngine` | Approval Authority · Procurement Method · 3-Way Match |
| 📑 Financial Close | #99 | `FinancialCloseEngine` | Recon Variance · Materiality Check · Close Calendar · Signoff Compliance |
| ℹ️ About | — | — | Page provenance + audit gate linkage |

### `app.py` — registered in 3 nav groups
- Finance group (line 927)
- Risk & Compliance group (line 949)
- Operations group (line 987)

Surfaced as **"IFRS Engines" 🧮** with `require_access("perform")` gating (broadly available across Finance/Operations/Risk roles).

---

## How users interact with it

Every form on the page calls a real engine method with user-supplied inputs. Examples verified end-to-end at the CLI:

| Input | Engine call | Output |
|---|---|---|
| Sales 1M, Input VAT 80K | `vat_output(STANDARD)` + `vat_payable()` | Output 160,000.00 / Payable 80,000.00 |
| Income 10M, Resident company | `corporate_tax()` | Tax 3,000,000.00 (30% rate) |
| Gross 100K, Professional Resident | `withholding_tax()` | WHT 5,000.00 / Net 95,000.00 |
| Period 31-Mar 2026, VAT | `filing_deadline()` | Deadline 20-Apr-2026 (20 days) |
| Period 31-Jan 2026, VAT, not filed | `filing_status()` | Status: **OVERDUE** |
| Tax due 100K, 2 months late | `late_filing_penalty()` | Penalty 10,000 (5% × 2mo = 10K = floor) |
| Amount 500K | `approval_authority()` | Tier: **MANAGER** |
| Amount 500K | `procurement_method()` | Method: **REQUEST_FOR_QUOTATION** (3 quotes) |
| PO 100K, GRN 102K, Inv 100K | `three_way_match()` | **MATCHED** (within ±2% tolerance) |
| GL 1M, Subledger 1.001M | `reconciliation_variance()` | 1,000.00 / 0.1000% |
| 0.05% on GL_TO_SUBLEDGER | `materiality_check()` | NOT MATERIAL (below 0.1% threshold) |
| Period 30-Apr, RECON_COMPLETE | `close_calendar_milestone()` | Target 10-May (T+10) |
| All 3 signoffs present | `signoff_complete()` | eligible_for_close: **True** |
| Missing APPROVER signoff | `signoff_complete()` | eligible_for_close: **False** (close blocked) |

**14 engine paths exercised; all return correct values matching the byte-for-byte audit gate fixtures.**

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event with the user, standard, and inputs:

```
audit_log("IFRS_ENGINE_USED", uname, "Tax #97: VAT payable computed (sales=1000000, input=80000)")
audit_log("IFRS_ENGINE_USED", uname, "Procurement #98: Approval tier for 500000")
audit_log("IFRS_ENGINE_USED", uname, "Close #99: Materiality 0.05% on GL_TO_SUBLEDGER")
```

This makes live usage traceable in the audit trail and provides the foundation for usage analytics in later releases.

---

## Honesty discipline preserved at the UI layer

The standards library's Rule 1 / Rule 6 honesty discipline (no silent defaults, fail-closed on missing or invalid inputs) is preserved in the UI:

- `_to_decimal()` helper returns `None` when input is empty/invalid — engines then return `None` per Rule 1 rather than substituting zero
- When an engine returns `{"computed": False, "reason": "..."}`, the page surfaces the `reason` field in an error message rather than masking it
- Decimal precision 28 digits maintained throughout (no float coercion)
- Unknown categories (Rule 6) surface their valid alternatives via the engine response

---

## Pattern established for the next 113 standards

The integration pattern this page establishes is the template for the remaining 113 library-only engines:

1. Page imports `EngineClass` + module-level constants directly from `utils/<engine>.py`
2. Streamlit forms collect inputs (number_input, selectbox, date_input, checkbox)
3. `_to_decimal()` helper coerces user input to `Decimal` (or `None` for empty/invalid)
4. Engine methods called with their exact audited signatures
5. Page-side display extracts response fields by their canonical names — never reformulates business logic
6. Every call audit-logged via `audit_log("IFRS_ENGINE_USED", uname, ...)`
7. Page calls `require_access("perform")` (or finer-grained module if needed)

---

## What didn't change

- `utils/tax_compliance.py` — byte-for-byte unchanged
- `utils/procurement_workflow.py` — byte-for-byte unchanged
- `utils/financial_close.py` — byte-for-byte unchanged
- `scripts/audit.py` — gates G89 / G90 / G91 still pass exactly as v5.66 verified them
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6

---

## Comparison vs v5.70

| | v5.70 | v5.71 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **0** | **3** ⭐ |
| Audit gates | 103/103 = 100% | 103/103 = 100% (unchanged) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 87 numbered + 12 admin | **88 numbered + 12 admin** |
| Nav group entries | (existing) | + 3 new entries for IFRS Engines |
| Spec deviations | 9 | 9 (unchanged) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** The page has been validated by:
   - Python `ast.parse` syntax pass
   - Module import test in mocked-Streamlit environment (all engine constants and methods accessible)
   - End-to-end engine call simulation at the CLI (14 engine paths, all producing expected values)
   
   What I **cannot** do is run `streamlit run app.py` to confirm the page renders correctly in a browser. The user must do that locally to confirm visual rendering, button behaviour, and tab navigation. If a Streamlit-specific issue exists (e.g. widget key conflicts, layout problems on small screens, dark/light theme contrast), it will only surface at runtime.

2. **3 of 116 integrated.** 113 standards remain library-only. This batch establishes the pattern; subsequent batches will scale it.

3. **Single-page approach chosen over 3 separate pages.** Earlier session notes referenced `pages/16_tax.py`, `pages/17_procurement.py`, `pages/18_close.py` — but those files did not exist on filesystem. The single-page approach is preferable because: (a) one nav entry is easier to discover; (b) tabs are easier to extend than new pages; (c) avoids namespace pollution in `pages/` directory which already has 87+ pages; (d) groups conceptually-related operations together (tax + procurement + close are all month-end-related operational tasks).

4. **`require_access("perform")` is broad.** Tax / Procurement / Close are useful across Finance / Operations / Risk roles, so the broadest existing module gate is used. For production deployment with finer-grained control, a dedicated `ifrs_engines` entry could be added to `MODULE_ACCESS` in `utils/core.py`. Recommended only if specific roles should be denied.

5. **Master Prompt entry from earlier session was aspirational.** The previous v5.71 entry described files (`pages/16_tax.py`, `pages/17_procurement.py`, `pages/18_close.py`, `utils/integration_helpers.py`, `tests/test_integration_smoke.py`, `CHANGELOG_v5.71.md`, `INTEGRATION_GUIDE_v5.71.md`) that **did not exist on the filesystem**. That entry has been replaced in this v5.71 with a description of what was actually built. This is exactly the kind of "deployed-vs-built gap" we flagged in v5.70's CHANGELOG — and now demonstrably closed for these 3 standards.

---

## Next batch options ranked by impact

Per the integration plan agreed at v5.70 close, integration batches continue before any further standards work. Options for v5.72:

| Priority | Batch | Standards integrated | Page strategy |
|---|---|---|---|
| **(1) Recommended** | Capital & Risk | #74 IRRBB / #76 Investment Portfolio / #29 ECL / #44 Capital Adequacy | New consolidated page (`pages/89_capital_risk_engines.py`) |
| (2) | BSC enhancement | #105 IAS 36 Impairment / #111 IAS 1 OCI recycling | Modify existing `pages/1_perform.py` and `pages/52_mgmt_accounts.py` |
| (3) | Vendor Risk | #96 Vendor Risk + #98 Procurement | New page or enhance `pages/64_vendors.py` |
| (4) | Customer & Disclosure | #95 CLV + #110 IFRS 7 + #116 IAS 24 | New page or enhance `pages/34_customer360.py` |

**Recommend (1) Capital & Risk for v5.72** — wires the highest-stakes regulatory standards (capital adequacy, IRRBB, ECL) which are CBK-mandated for every bank. After that, the remaining batches can scale at 4-5 standards each until full coverage.

---

**Cumulative tally:** 116 standards delivered, **3 integrated into UI via 1 page in 3 nav groups**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.
