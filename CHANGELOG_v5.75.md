# A2Z MIS 360 — CHANGELOG v5.75

**v5.75 Fifth Integration Batch — Customer 360 + Disclosures (3 standards in one batch)**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (unchanged from v5.74; restored after G3 fix during build)
**Engine batch tests:** 49 files / 2211 tests (unchanged from v5.74)
**Strategic milestone:** **Largest single-batch integration so far — 3 standards on one existing page.** Cumulative: **13 of 116 standards integrated.**

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.71/72/74 each integrated 3-4 standards across separate engines on dedicated/single pages. v5.75 packs **3 standards onto ONE existing page** where they belong together strategically:

- **#95 Customer Lifetime Value** — operationally useful for RM teams understanding individual customer value
- **#110 IFRS 7 Financial Instruments Disclosures** — statutory year-end + interim disclosure
- **#116 IAS 24 Related Party Disclosures** — statutory year-end + interim disclosure

All three sit naturally on Customer 360 because the data context (the customer being viewed) is the natural anchor for each.

---

## What was modified

### `pages/34_customer360.py` — CLV + Disclosures tabs added
**256 → 850 lines (+594)**

**Tab list expanded from 5 to 7** (within G4's 7-tab limit):

| # | Tab | Status |
|---|---|---|
| 0-4 | Customer Lookup · Portfolio Intelligence · Churn Risk · Next Best Action · Segment Analytics | unchanged |
| **5** | **💰 Customer Lifetime Value** | **NEW (Standard #95)** |
| **6** | **📄 IFRS 7 / IAS 24 Disclosures** | **NEW (Standards #110 + #116)** |

### Customer Lifetime Value tab — 3 sub-tabs (Standard #95)

- **💰 Customer CLV Calculator** — interactive single-customer CLV with up to 4 product holdings. Configurable horizon / discount rate / margin (defaulting to engine constants `DEFAULT_HORIZON_YEARS=5` / `DEFAULT_DISCOUNT_RATE_PCT=12%` / `DEFAULT_CONTRIBUTION_MARGIN_PCT=60%`). Surfaces CLV NPV + annual revenue + annual contribution + profitability segment with color-coded badge (HIGH_VALUE green / MEDIUM blue / LOW amber / UNPROFITABLE red) at engine-bound boundaries `CLV_HIGH_VALUE_MIN=500K` / `CLV_MEDIUM_MIN=50K`. Per-holding revenue breakdown table.

- **🌳 Product Yield Reference** — renders the 8 `PRODUCT_YIELDS_PCT` byte-for-byte (SAVINGS=0.5%, CURRENT=3%, TERM_DEPOSIT=1%, PERSONAL_LOAN=12%, MORTGAGE=4.5%, CREDIT_CARD=18%, TRADE_FINANCE=6%, INVESTMENT=1%) — single source of truth from engine.

- **📊 Portfolio CLV Distribution** — auto-bins all customers from `customer_intelligence.json` into the 4 `PROFITABILITY_SEGMENTS` using engine's static `profitability_segment()` method. 4 KPI metrics (counts + total CLV per segment) + summary table.

### Disclosures tab — 2-level nested tabs (Standards #110 + #116)

**Top-level**: 📊 IFRS 7 vs 👥 IAS 24

**📊 IFRS 7 — Financial Instruments** (4 inner tabs):
- **🪣 Maturity Bucket Classifier** — 5 buckets per IFRS 7.39: ON_DEMAND → UP_TO_3_MONTHS → THREE_TO_12_MONTHS → ONE_TO_5_YEARS → OVER_5_YEARS
- **⚠️ Concentration Check** — single-counterparty 10% / industry 25% thresholds
- **📈 Market Risk Sensitivity** — INTEREST_RATE / FOREIGN_EXCHANGE / EQUITY_PRICE risk variables per IFRS 7.40
- **✅ Disclosure Completeness** — 7 required IFRS 7 disclosures with missing-list surfacing

**👥 IAS 24 — Related Parties** (5 inner tabs):
- **👤 KMP Identification** — IAS 24.9 requires **BOTH** authority criterion AND role criterion (single criterion is INSUFFICIENT)
- **🏷️ Category Classifier** — validates against 7 `RELATED_PARTY_CATEGORIES`
- **👨‍👩‍👧 Close Family Check** — validates against 4 IFRS-defined `CLOSE_FAMILY_MEMBERS`, distinguishing IFRS narrow definition from colloquial sense
- **✅ Disclosure Completeness** — IAS 24.18 requires **ALL 5** of NATURE_OF_RELATIONSHIP / AMOUNT_OF_TRANSACTIONS / OUTSTANDING_BALANCES_AND_TERMS / PROVISIONS_FOR_DOUBTFUL_DEBTS / EXPENSE_RECOGNISED_FOR_BAD_DEBTS
- **🏛️ Government Relief** — IAS 24.25-27 partial exemption for government-related entities

### Engine files — UNCHANGED
`utils/customer_lifetime_value.py`, `utils/ifrs7_disclosures.py`, and `utils/related_party.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 19 engine paths verified end-to-end

**CLV (6 paths):**

| Input | Engine call | Output |
|---|---|---|
| C001 with SAVINGS 500K + MORTGAGE 3M, 5y@12% margin 60% | `clv_npv()` | NPV **288,742.57**, annual_rev 137,500 |
| 600K | `profitability_segment()` | HIGH_VALUE |
| 100K | `profitability_segment()` | MEDIUM |
| 10K | `profitability_segment()` | LOW |
| -5K | `profitability_segment()` | UNPROFITABLE |
| 2 holdings | `product_revenue()` | total 137,500, 2 per-holding rows |

**IFRS 7 (8 paths):**

| Input | Engine call | Output |
|---|---|---|
| 30 days | `classify_maturity_bucket()` | UP_TO_3_MONTHS |
| 180 days | `classify_maturity_bucket()` | THREE_TO_12_MONTHS |
| 730 days | `classify_maturity_bucket()` | ONE_TO_5_YEARS |
| 2000 days | `classify_maturity_bucket()` | OVER_5_YEARS |
| on_demand=True | `classify_maturity_bucket()` | ON_DEMAND |
| Single 10% boundary | `credit_risk_concentration()` | NOT concentrated (=10% threshold not >) |
| Industry 16.67% | `credit_risk_concentration()` | NOT concentrated (<25%) |
| 10B IR @ 1% | `market_risk_sensitivity()` | impact 100M |
| 2 of 4 disclosures | `disclosure_completeness()` | complete=False, 50%, 2 missing surfaced |

**IAS 24 (5 paths):**

| Input | Engine call | Output |
|---|---|---|
| Authority + Role | `identify_kmp()` | **is_kmp=True** |
| Authority only | `identify_kmp()` | **is_kmp=False** (correct AND logic) |
| KMP_OR_FAMILY category | `classify_related_party()` | valid=True |
| INVALID category | `classify_related_party()` | valid=False with valid_categories list |
| SPOUSE_OR_DOMESTIC_PARTNER | `close_family_member_check()` | is_close_family=True |
| UNCLE | `close_family_member_check()` | is_close_family=False (IFRS narrow) |
| All 5 disclosures | `validate_disclosure_completeness()` | compliant=True |
| 2/5 disclosures | `validate_disclosure_completeness()` | NON_COMPLIANT, 3 missing surfaced |
| is_government_controlled=True | `government_related_entity_relief()` | applies=True, level=FULL |
| is_government_controlled=False | `government_related_entity_relief()` | applies=False |

---

## Critical guardrails caught at audit time

**Two issues caught by the audit framework during this build:**

### Issue 1: G3 audit_coverage — aliased imports broke detection

Initial build had aliased `audit_log` imports:

```python
from utils.core_audit import audit_log as _audit_log_clv
from utils.core_audit import audit_log as _audit_log_disc
# ...
_audit_log_clv("IFRS_ENGINE_USED", uname, "...")
_audit_log_disc("IFRS_ENGINE_USED", uname, "...")
```

**The G3 gate scans for the literal string `audit_log(`** — aliased calls don't match. Audit dropped 103/103 → 102/103:

```
❌ [G3] audit_coverage    71 writer pages, 70 with audit
       • 34_customer360.py
```

**Fix**: use canonical name `audit_log` directly. **This validates that G3 catches not just missing audit calls but also obfuscated audit calls** — a more sophisticated check than I'd appreciated.

### Issue 2: G4 tab counts (preempted)

Page had 5 tabs; adding 2 brings to exactly 7, well within G4's limit. Avoided the v5.73 G4 mistake. (5 + 2 ≤ 7 ✓)

After fixes: **103/103 PASS** restored.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "CLV #95: Customer=C001 CLV=288742.57 segment=MEDIUM")
audit_log("IFRS_ENGINE_USED", uname, "CLV #95: Portfolio scan 1247 customers")
audit_log("IFRS_ENGINE_USED", uname, "IFRS7 #110: Maturity 180d / on_demand=False → THREE_TO_12_MONTHS")
audit_log("IFRS_ENGINE_USED", uname, "IFRS7 #110: Concentration SINGLE_COUNTERPARTY 300M/3000M = 10.00%, conc=False")
audit_log("IFRS_ENGINE_USED", uname, "IFRS7 #110: Disclosure check 2/4 complete=False")
audit_log("IFRS_ENGINE_USED", uname, "IAS24 #116: KMP test → is_kmp=True")
audit_log("IFRS_ENGINE_USED", uname, "IAS24 #116: Disclosure completeness complete=True compliant=True")
audit_log("IFRS_ENGINE_USED", uname, "IAS24 #116: Gov relief is_gov=True → applies=True")
```

---

## Honesty discipline visualised

- **CLV NEVER auto-prefills from customer JSON** — calculator is self-contained, user must enter holdings explicitly. No silent assumptions.
- **Profitability segment colour-coded** at engine boundaries (not page-defined)
- **KMP requires BOTH authority AND role** — single criterion shows is_kmp=False with explicit rationale
- **IAS 24 close family is the IFRS narrow list** — UI explicitly notes "this is the IFRS-defined narrow list, the colloquial sense of 'family' is wider"
- **Government relief returns disclosure_level=FULL** even when applied — partial exemption only on collectively-significant; individually-significant still requires full disclosure (engine surfaces this correctly)
- **5 of 5 disclosure rule** for IAS 24.18 — missing any one is NON-COMPLIANT, no override
- Every engine call audit-logged

---

## What didn't change

- All 3 engine source files — byte-for-byte unchanged
- `scripts/audit.py` — gates G69 (CLV) / G98 (IFRS 7) / G103 (IAS 24) still pass exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- v5.71 IFRS Engines Studio (88_ifrs_engines.py) — unchanged
- v5.72 Capital & Risk page (89_capital_risk_engines.py) — unchanged
- v5.73 modified pages (19_credit_monitoring, 52_mgmt_accounts) — unchanged
- v5.74 modified page (64_vendors) — unchanged
- `app.py` — unchanged

---

## Comparison vs v5.74

| | v5.74 | v5.75 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **10** | **13** ⭐ (+3 in one batch) |
| Audit gates | 103/103 | 103/103 (unchanged after G3 fix) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 89 numbered | 89 numbered (unchanged) |
| **Modified existing pages cumulative** | 3 | **4** |
| Lines added across pages this batch | +461 (vendors) | +594 (customer360) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level import test, and 19-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering — especially the new 2-level nested tabs in the Disclosures tab (top-level IFRS 7 vs IAS 24, then 4-9 inner tabs). Streamlit nested tabs are well-supported but visually denser; user should validate that the layout is usable on their typical screen size.

2. **13 of 116 integrated.** 103 standards remain library-only.

3. **Customer 360 page line count grew significantly** (256 → 850, **+232% larger**). The new tabs are clearly bounded at the bottom of the file via `with tabs[5]:` and `with tabs[6]:` blocks; existing tabs[0-4] are byte-for-byte unchanged. Risk of regression on existing functionality is therefore minimal but non-zero.

4. **CLV calculator is a standalone tool** — it does NOT pre-fill from `customer_intelligence.json` even when a customer is selected in the Customer Lookup tab. This was deliberate to keep the calculator self-contained and avoid cross-tab state synchronisation, which is fragile in Streamlit. Power users who want to apply CLV to a real customer must enter the holdings manually. The Portfolio CLV Distribution tab uses `clv_estimate` from the JSON without re-computing per-customer (uses engine's static `profitability_segment()` only for binning).

5. **The IAS 24 KMP test requires the user to be honest** — if they tick "INCLUDES_DIRECTORS" without actually being a director, the engine returns `is_kmp=True`. The engine binds the criteria; the user binds the truth value. This is a correct separation of concerns but worth noting.

6. **Government relief `disclosure_level` returns FULL** even when relief applies — this is a documented IAS 24 quirk, not an engine bug. Per IAS 24.25-27, government-related entities have *partial* exemption from disclosing **collectively** significant transactions but must still fully disclose **individually** significant transactions. The engine surfaces this correctly via the rationale field.

7. **The IFRS 7 concentration boundary at exactly 10%** is NOT flagged as concentrated. The engine uses strictly-greater-than (`>`) not greater-or-equal — at exactly 10.00%, `is_concentrated=False`. This matches the engine's conservative interpretation of IFRS 7 (disclose when *exceeding* threshold). User-facing message clarifies this.

8. **`disclosure_required` field in concentration response** triggers when concentration is detected, not when it's at threshold. The wording in the page makes this clear.

---

## Next batch options ranked by impact

| Priority | Batch | Standards | Strategy |
|---|---|---|---|
| **(1) Recommended** | Treasury / ALM | #75 FX + #71 LCR/NSFR | Enhance `pages/25_treasury.py` + `pages/81_alm.py` |
| (2) | Stress Testing | #79 | Enhance `pages/35_stress_testing.py` |
| (3) | HR Performance | #63 + #64 | Enhance `pages/2_people.py` |
| (4) | Remaining IFRS Engines | #101-#108 | New consolidated page `pages/90_remaining_ifrs.py` |
| (5) | BSC Main Page | various | Enhance `pages/1_perform.py` (1908 lines, higher risk) |

Recommend **(1) Treasury / ALM** for v5.76 — high regulatory urgency (FX limits and LCR/NSFR are CBK-supervised daily) and complementary to v5.72's Capital & Risk integration.

Alternative: **(4) Remaining IFRS Engines** if scaling integration breadth is the priority over depth — this would consolidate 8 engines (#101-108) onto a new page, taking integrated-standards count from 13 to 21 in a single batch.

---

**Cumulative tally:** 116 standards delivered, **13 integrated into UI via 2 dedicated pages + 4 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.
