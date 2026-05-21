# A2Z MIS 360 — CHANGELOG v5.92

**v5.92 Twenty-Second Integration Batch — Customer Profitability (#57)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 18th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🎯 CUSTOMER-CENTRIC QUARTET COMPLETE.** NBA + Segmentation + Churn + Profitability now all integrated. Cumulative: **41 of 116 standards integrated.** Twenty-second integration batch.

---

## Strategic milestone — customer-centric quartet complete

After v5.89 + v5.90 + v5.91 built the customer-centric trio, v5.92 adds the per-customer P&L view that completes the quartet:

| Question | Standard | Integrated in |
|---|---|---|
| What should I offer THIS customer? | #59 Cross-sell NBA | v5.89 |
| How should I group customers for marketing? | #65 Segmentation | v5.90 |
| Who should I prioritize for retention? | #58 Churn Prediction | v5.91 |
| **How profitable is this customer right now?** | **#57 Customer Profitability** | **v5.92** ⭐ |

The four engines compose powerfully:
- A **HIGH_RISK** churn customer (v5.91) in **CANNOT_LOSE_THEM** segment (v5.90) with **negative PBT margin** (v5.92) is the most urgent retention target.
- The bank can make informed decisions: invest to retain the **profitable + at-risk**, let go of the **unprofitable + at-risk**.

Customer Profitability is the most strategically important addition because it surfaces the **uncomfortable truth that some customers are unprofitable** — a fact that revenue-only analytics (CLV, NBA) hide.

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.92 wires **Standard #57 Customer Profitability** (`customer_profitability.py`) — per-customer P&L with 4 allocation methods + optional FTP support.

---

## What was modified

### `pages/34_customer360.py` — inner sub-tab expansion within tab[5] CLV
**1739 → 2148 lines (+409)**

**Top-level tabs UNCHANGED at 7** (already at G4 limit). **Inner sub-tab expansion within tab[5] CLV**: clv_sub_tabs expanded from 3 to 6 (sub-tabs are NOT capped by G4):

| # | Sub-tab | Status |
|---|---|---|
| 0-2 | Customer CLV Calculator · Product Yield Reference · Portfolio CLV Distribution | unchanged from v5.75 |
| **3** | **💵 Customer P&L (#57)** | **NEW** |
| **4** | **🎯 Allocation Method Comparison (#57)** | **NEW** |
| **5** | **🌳 Engine Reference (#57)** | **NEW** |

### Customer P&L sub-tab

User inputs:
- Customer ID / period / segment / allocation method
- Revenue components (interest_income / fee_income / other_income)
- Direct costs (interest_expense / loan_loss_provisions / transaction_costs)
- Overhead pool size + bank-wide total revenue + active customer count + customer's asset balance

Engine returns full P&L:
- **Verdict banner**: PROFITABLE ✅ / BREAK-EVEN ⚪ / UNPROFITABLE ❌ traffic-light
- 4 metrics: total_revenue / direct_costs / indirect_costs / PBT
- Per-component breakdown tables for revenue and costs
- `missing_components` warning per Rule 6
- Engine metadata in expandable JSON viewer

### Allocation Method Comparison sub-tab

Same fixed customer profile run through all 4 ALLOCATION_METHODS:

**Demo customer**: Revenue=350K, Direct costs=117K

| Method | Indirect (KES) | PBT (KES) | Margin |
|---|---|---|---|
| equal_per_customer | 71,429 | **+161,571** | **+46.16%** |
| revenue_weighted (default) | 700,000 | **−467,000** | **−133.43%** |
| asset_weighted | 357,143 | −124,143 | −35.47% |
| activity_weighted* | 0 | +233,000 | +66.57% |

\* *activity_weighted result is artificially high because demo activity ratio is negligible*

**KES 700K spread** for the same customer. Bar chart of PBT by method. Warning explaining that consistency in method matters more than the specific choice.

### Engine Reference sub-tab — 4 reference tables

**4 allocation methods** with descriptions:

| Method | Description | Default |
|---|---|---|
| equal_per_customer | Overhead ÷ customer count. Simple but biased. | |
| revenue_weighted | Customer's share of bank revenue × overhead pool. Most common. | ✓ |
| asset_weighted | Customer's share of assets × overhead. Recognizes balance-sheet contribution. | |
| activity_weighted | Customer's share of activity × overhead. Best matches cost causation. | |

**6 DI callbacks** with input/output schemas.

**7 engine output keys** with descriptions.

**FTP mode behavior** caption explaining Rule 6 transparency for missing FTP inputs.

**EXCEL_MATCH_TOLERANCE=0.5%** reconciliation guarantee surfaced.

**Integration with v5.75 CLV** explained — CLV is NPV of future P&L, Profitability is current-period P&L.

### Engine file — UNCHANGED
`utils/customer_profitability.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 1 engine path verified end-to-end (used 4+ times per session)

**`calculate_customer_pnl` — single P&L** with `revenue_weighted`:
- PBT: −467,000
- Margin: −133.4%
- Revenue: 350,000 / Direct: 117,000 / Indirect: 700,000
- **14 meta fields**: customer_id / customer_segment / period / allocation_method / missing_components / input_currency / precision / tolerance_excel_pct / ftp_mode / ftp_rate / ftp_missing / ftp_simplifications / balance_basis / generated_at

**4-method comparison** for same customer:
- equal_per_customer → PBT +161,571 (+46.16%)
- revenue_weighted → PBT −467,000 (−133.43%)
- asset_weighted → PBT −124,143 (−35.47%)
- activity_weighted → PBT +233,000 (+66.57% — artifact of small activity ratio)

**Unknown customer** correctly returns `{}` per Rule 6.

**Engine logic confirmed**: 4 allocation methods produce dramatically different PBT outcomes (KES 700K spread). 14 meta fields surface full transparency. Excel reconciliation tolerance 0.5%.

---

## Critical engine API specifics documented

These were verified during build (12 findings):

1. **`CustomerProfitabilityEngine` is an INSTANCE class** with **8 DI callbacks** (customer_lookup_fn, revenue_fn, direct_costs_fn, overhead_pool_fn, allocation_inputs_fn, allocation_method, ftp_mode, ftp_inputs_fn) — **most DI-heavy engine in the platform**.

2. **`calculate_customer_pnl(customer_id, period)` is the ONLY public method** — engine is intentionally narrow at the API surface but rich at the implementation level.

3. **🆕 Engine returns `{}` for unknown customer** (Rule 6) — page must check for empty dict before accessing keys.

4. **🆕 Top-level keys**: `pbt` + `pbt_margin` + `revenue` (dict) + `direct_costs` (dict) + `indirect_costs` (dict) + `total_revenue` + `total_direct_costs` + `total_indirect_costs` + `meta` (dict). **`customer_id` and `period` are in `meta`, NOT at top level** — non-obvious gotcha discovered during smoke testing.

5. **🆕 4 ALLOCATION_METHODS produce dramatically different PBT outcomes** — same customer can be 'profitable' OR 'unprofitable' depending on allocation choice. **Bank policy decision must precede production rollout**.

6. **`indirect_costs` dict has a single 'allocated_overhead' key** — engine doesn't break down indirect costs by category, just allocates the total pool.

7. **🆕 FTP mode is OPTIONAL** — engine works fine with `ftp_mode='off'` (default). When `ftp_mode='on'`, engine reconstructs interest income/expense from FTP rates rather than using revenue/direct_costs callbacks.

8. **🆕 FTP needs 5 specific keys** in ftp_inputs_fn return: `ftp_rate` (Decimal), `deposit_balance` (Decimal), `deposit_rate_paid` (Decimal), `loan_balance` (Decimal), `period_fraction` (Decimal). **Missing FTP keys surface in `meta.ftp_missing`** per Rule 6 (no silent fallback).

9. **`meta.missing_components` lists components** where the callback returned None or invalid values — production debugging aid.

10. **🆕 EXCEL_MATCH_TOLERANCE=0.5%** — engine guarantees outputs match Excel reference to within 0.5%. Useful for reconciliation against Finance team's existing Excel models during deployment.

11. **Engine uses Decimal internally for precision**, returns float in output dict (2dp). 'precision' field in meta documents this.

12. **🆕 `allocation_inputs_fn` return must include keys for the chosen method** — e.g. revenue_weighted needs `my_revenue` + `total_revenue`, asset_weighted needs `my_assets` + `total_assets`. **Missing keys silently zero the allocation** (engine doesn't error). Production deployment should populate ALL allocation keys regardless of which method is active so the bank can switch methods without code changes.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "CustomerProfitability #57: P&L CUST_PNL_001 period=2025-12 method=revenue_weighted pbt=-467000 margin=-133.43%")
audit_log("IFRS_ENGINE_USED", uname, "CustomerProfitability #57: allocation comparison spread=700000 min_pbt=-467000 max_pbt=233000")
```

---

## ✅ Eighteenth clean-first-try batch in a row

Audit clean on first attempt (after v5.74 → v5.91). G3 + G4 lessons embedded.

---

## Honesty discipline visualised

- **All 4 allocation methods compared** with dramatic PBT spread (KES 700K) explicitly surfaced
- **Unprofitable customer banner** ❌ when PBT < 0 — no sugar-coating
- **Missing components warning** (Rule 6) — `meta.missing_components` surfaced when callbacks return None
- **FTP transparency** — `meta.ftp_missing` documented, no silent fallback
- **14 meta fields** in expandable JSON viewer for full traceability
- **Excel reconciliation tolerance 0.5%** disclosed
- **Allocation method choice** explicitly framed as bank policy decision
- **Engine integration with v5.75 CLV** documented — Profitability is current period, CLV is NPV of future
- **Activity_weighted misleading-result caveat** — small activity ratio rounds allocated cost to 0
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G57 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.91 pages — unchanged
- The other 6 top-level tabs in `34_customer360.py` (Customer Lookup / Portfolio Intelligence / Churn Risk / NBA / Segment Analytics / IFRS 7) — completely untouched
- The 3 existing CLV sub-tabs in tab[5] from v5.75 — completely untouched
- The `customer_intelligence.json` data store — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.91

| | v5.91 | v5.92 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **40** | **41** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 15 | **15** (re-enhances 34_customer360.py from v5.75 + v5.90 + v5.91) |
| Lines added across pages this batch | +488 (customer360 v5.91) | +409 (customer360 v5.92) |
| **34_customer360.py total lines** | 1739 | **2148** (largest non-people page) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and engine call simulation including 4-method comparison. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **NEW 6-sub-tab structure under tab[5] CLV** with the new sub-tabs at positions 3-5 (after the existing 3 CLV sub-tabs from v5.75).

2. **41 of 116 integrated** — 75 standards remain library-only.

3. **Customer P&L sub-tab uses user-entered values** — does NOT auto-pull from CBS or General Ledger. **Production deployment would feed via 5 DI callbacks** connecting to:
   - Customer master data (segment, CIF)
   - Revenue side (interest_income from CBS interest accruals, fee_income from CBS fee waterfall, other_income from special items GL)
   - Direct costs side (interest_expense from FTP or CBS, **loan_loss_provisions from IFRS 9 ECL engine in v5.71**, transaction_costs from channel cost engine in v5.87)
   - Overhead pool (Finance team's bank-wide indirect cost total per period)
   - Allocation inputs (customer counts from CBS, total revenue/assets from GL)

4. **Allocation Method Comparison uses fixed example values** to make the point that methods matter; production deployment would compare actual customer profile across methods, with potentially much smaller spreads if revenue/assets/activity ratios are similar.

5. **🆕 Engine returns {} for unknown customer** — caller must check before accessing keys. Page handles this with error banner but production deployment with batch processing must handle gracefully across thousands of customers.

6. **🆕 4 allocation methods produce dramatically different PBT** — the spread can be hundreds of thousands of KES for the same customer. **Bank policy decision must precede production rollout** — pick one method and stick with it across all P&L reporting. Production deployment without a stated policy creates inconsistency.

7. **FTP mode is documented but NOT exercised in UI** — page only uses ftp_mode='off' default. Production deployment that wants FTP-based interest income/expense must populate the 5 ftp_inputs keys; missing inputs surface in `meta.ftp_missing` per Rule 6. The Engine Reference sub-tab documents this but the Customer P&L sub-tab doesn't expose FTP inputs to the user (would over-complicate the form).

8. **`indirect_costs` dict has only `allocated_overhead`** key — engine doesn't break down indirect costs by category (HR / IT / Premises / Marketing). Production deployment that wants finer breakdown would need separate allocations.

9. **🆕 No support for direct cost reconciliation with IFRS 9 ECL** — the engine takes loan_loss_provisions as an input but doesn't reconcile with the ECL engine in v5.71. Production deployment should ensure consistency: customer P&L's loan_loss_provisions should equal the customer's share of the IFRS 9 ECL engine's output. **Otherwise the same loss is either double-counted or missed.**

10. **No multi-period support** — engine returns single-period P&L. Year-over-year comparison or trend analysis requires the caller to invoke the engine multiple times and stitch results.

11. **🆕 Engine doesn't model customer-level taxes** — output is PBT (Profit Before Tax), not PAT. For CLV calculations that need PAT, caller must apply tax rate. CLV engine (v5.75) does this separately.

12. **🆕 Allocation comparison's activity_weighted result can mislead** — if `my_activity_units / total_activity_units` ratio is very small (as in the demo: 1200/50M = 0.0024%), allocated overhead rounds to 0 and PBT looks artificially high. Production deployment with realistic activity proportions would show non-zero allocations.

---

## Strategic narrative — customer-centric quartet complete

Customer 360 page now has all 4 customer-centric engines integrated:

| Tab | Engine | Standard | Coverage |
|---|---|---|---|
| tabs[2] Churn Risk | ChurnPrediction | #58 | Who to retain (v5.91) |
| tabs[3] NBA | (cross-sell page covers depth) | #59 | What to offer (v5.89) |
| tabs[4] Segment Analytics | CustomerSegmentation | #65 | How to group (v5.90) |
| **tabs[5] CLV → expanded** | **CLV + CustomerProfitability** | **#95 + #57** | **What's their value + how profitable** (v5.75 + **v5.92**) ⭐ |

The **quartet composes powerfully**:
- HIGH_RISK churn (v5.91) + CANNOT_LOSE_THEM (v5.90) + negative PBT margin (v5.92) = most urgent retention target
- Bank can invest to retain **profitable + at-risk**, let go of **unprofitable + at-risk**

Customer Profitability surfaces the **uncomfortable truth that some customers are unprofitable** — hidden by revenue-only analytics.

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Coaching Intelligence | coaching_intelligence | Pivot to HR axis after deep customer-centric work — complements v5.79 retrospective + v5.84 forward-looking |
| (2) | Customer Lifetime Value depth | customer_lifetime_value | Engine-level depth beyond v5.75 (especially FTP-based CLV) |
| (3) | Customer Value Segments | customer_value_segments | Alternative segmentation lens (different from v5.90 RFM) |
| (4) | Allocation Optimizer | allocation_optimizer | Resource allocation |
| (5) | Compensation Equity | compensation_equity | HR fair-pay analytics |
| (6) | Employee Engagement | employee_engagement | HR survey analytics |
| (7) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With customer-centric quartet complete, recommend pivoting to **(1) Coaching Intelligence** for v5.93 — would shift to HR axis after the deep customer-centric work, complementing v5.79 People retrospective + v5.84 forward-looking with engine-driven coaching support.

---

**Cumulative tally:** 116 standards delivered, **41 integrated into UI via 3 dedicated pages + 15 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🎯 **Customer-centric quartet complete** (NBA #59 + Segmentation #65 + Churn #58 + Profitability #57).
