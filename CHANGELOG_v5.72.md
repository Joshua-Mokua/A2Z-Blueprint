# A2Z MIS 360 — CHANGELOG v5.72

**v5.72 Second Integration Batch — Capital & Risk Engines Studio**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (unchanged from v5.71)
**Engine batch tests:** 49 files / 2211 tests (unchanged from v5.71)
**Strategic milestone:** **Second daylight for the standards library** — 4 high-stakes regulatory engines (#74 IRRBB, #76 Investment Portfolio, #77 Capital Adequacy, #53 Credit Risk Scoring) now callable from the live Streamlit UI. **Cumulative: 7 of 116 standards integrated.**

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.71 demonstrated the integration pattern with the 3 most-frequently-used finance engines (Tax / Procurement / Close). v5.72 scales it to the 4 engines a regulator's first questions will land on:

| Engine | Why it matters for Ecobank Kenya |
|---|---|
| **#74 IRRBB** | BCBS 368 outlier flags — when EVE/Tier 1 ≥ 15% triggers CBK supervisory review |
| **#76 Investment Portfolio** | HQLA classification (LCR), CBK PG/04 concentration limits |
| **#77 Capital Adequacy** | Basel III + CBK PG/02 split (CBK is 6.5pp tougher than Basel) |
| **#53 Credit Risk Scoring** | Rule 7 PD/LGD/EAD with ML-disabled disclosure |

---

## What was built

### `pages/89_capital_risk_engines.py` — Capital & Risk Engines Studio (NEW)

**5 top-level tabs** with **12 sub-tabs**:

| Tab | Standard | Engine | Sub-tabs |
|---|---|---|---|
| 📈 IRRBB (#74) | BCBS 368 | `IrrbbEngine` | Repricing Gap · NII ±200bps · EVE Standardised Shocks |
| 💼 Investment Portfolio (#76) | Basel III LCR + CBK PG/04 | `InvestmentPortfolioEngine` | Bond Duration · HQLA Classification · Concentration Risk |
| 🏛️ Capital Adequacy (#77) | Basel III + CBK PG/02 | `CapitalAdequacyEngine` | CAR Ratios · Leverage Ratio · Capital Buffers |
| 📊 Credit Risk Scoring (#53) | Basel IRB + Rule 7 | `CreditRiskScoringEngine` | Score Borrower · Risk Grade Reference |
| ℹ️ About | — | — | Engine + audit gate linkage, integration tally |

### `app.py` — registered in 2 nav groups
- Finance group (line 928)
- Risk & Compliance group (line 951)

Surfaced as **"Capital & Risk Engines" 🏦** with `require_access("perform")` gating (these are bank-wide concerns, not just Risk team).

---

## How users interact with it

Every form on the page calls a real engine method with user-supplied inputs. **12 engine paths verified end-to-end** at the CLI:

| Tab | Input | Engine call | Output |
|---|---|---|---|
| Repricing Gap | 3 buckets {1M:500/400, 3M:300/200, 6M:200/150}M | `IrrbbEngine.repricing_gap()` | Total cumulative gap **200,000,000.00** |
| NII ±200bps | Tier 1 = 15B | `nii_sensitivity_200bps()` | Impact 4,219,178.08; outlier_pct **0.03%** (NOT outlier; 5% threshold) |
| EVE PARALLEL_UP | Tier 1 = 15B | `eve_sensitivity()` | ΔEVE -780,821.92; outlier_pct **0.01%** (NOT outlier; 15% threshold) |
| Bond Duration | 100M par, 11.5% coupon, 5y, YTM 12% | `bond_modified_duration()` | Macaulay **3.9269**, Modified **3.7046** |
| HQLA | 2 holdings (sovereign + BBB corp) | `hqla_classification()` | LEVEL_1 **98M**, LEVEL_2B **51M** |
| Concentration | 100M sovereign in 149M book | `concentration_risk()` | 1 sector breach: **SOVEREIGN at 65.77%** > 35% limit |
| CAR Ratios | 8B paid + 5B retained + AT1/T2 / 100B RWA | `car_ratios()` | CET1 **14.70%**, Tier1 **16.70%**, Total **19.70%**, status **GREEN**, compliant_basel + cbk = True |
| Leverage | 17B Tier1 / 130B exposures | `leverage_ratio()` | **13.08%** (vs 3% min, compliant) |
| Buffers | CET1 12.5%, ccyc 0.5%, dsib 1.0% | `capital_buffers()` | Required 8.5%, surplus **+4.00pp**, met=True |
| Credit Risk | DTI 0.35, payment 85, collateral 1.5, age 12mo, util 0.45, EAD 1M | `score_borrower()` | rule_based_grade **CCC**, rule_pd **0.16**, ml_pd **None** (Rule 7), EL **72,000.00** |

---

## Critical engine API discoveries during build

This batch surfaced several non-obvious engine signatures and return shapes that the v5.71 master prompt entry didn't catch. Documenting them so the next integration batch doesn't re-tread:

**IRRBB:**
- `IrrbbEngine.repricing_gap` returns `total_cumulative_gap_kes`, `bucket_count`, `excluded_count`, `buckets` (list of per-bucket dicts) — **no `total_gap` key**
- `IrrbbEngine.nii_sensitivity_200bps` returns `nii_impact_kes`, `outlier_pct`, `is_outlier`, `shock_bps`, `outlier_threshold_pct`
- `IrrbbEngine.eve_sensitivity` returns `eve_change_kes`, `outlier_pct`, `is_outlier`, `scenario`
- `RepricingBucket(bucket=, rate_sensitive_assets_kes=, rate_sensitive_liabilities_kes=, weighted_avg_rate_pct=)` — fields are `_kes` suffixed, **not** `asset_balance_kes`

**Investment Portfolio:**
- `BondHolding(holding_id=, instrument_type=, issuer=, sector=, par_value_kes=, market_price_pct=, coupon_rate_pct=, coupon_frequency_per_year=, maturity_date=, settlement_date=, credit_rating=, is_sovereign=)` — **maturity_date** + **settlement_date**, not `maturity_years`; **par_value_kes**, not `face_value`
- `hqla_classification` returns `by_level` (dict by HQLA level), `holdings` (list per holding), `excluded_count` — **no `total_hqla_kes`** (compute from `by_level` summing LEVEL_1 + LEVEL_2A + LEVEL_2B)
- `concentration_risk` returns `issuer_breaches` (list), `sector_breaches` (list), `issuer_count`, `sector_count`, `total_book_kes`, `core_capital_kes` — **not `single_issuer_breaches`**

**Capital Adequacy:**
- `CapitalComponents` has 16+ named per-line-item fields (`paid_up_capital_kes`, `share_premium_kes`, `retained_earnings_kes`, etc.) — **not** generic buckets like `cet1_capital`/`at1_capital`/`tier2_capital`
- `car_ratios` returns `status` (GREEN/AMBER/RED on Total CAR vs CBK + 2pp green buffer), `compliant_basel`, `compliant_cbk`, `cet1_ratio_pct`, etc. — **not `total_car_status`**
- `capital_buffers(cet1_ratio_pct, countercyclical_pct=, dsib_pct=)` — **kwargs are `countercyclical_pct` and `dsib_pct`**, not `countercyclical_buffer_pct`/`dsib_buffer_pct`
- `leverage_ratio(tier1_capital, total_exposures)` returns `leverage_ratio_pct`, `min_required_pct`, `compliant`, `tier1_kes`, `total_exposures_kes`

**Credit Risk Scoring:**
- `score_borrower` returns **separate `rule_based_grade` and `ml_grade`** keys per Rule 7 — **no single `grade` key**
- `score_borrower` features dict reads **`outstanding_balance`** for EAD (Basel IRB Foundation simplification) — **not `exposure_at_default`**
- Engine reads its own feature names: `debt_to_income`, `payment_history_score`, `collateral_coverage_ratio`, `loan_age_months`, `credit_utilization`, `outstanding_balance`

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "IRRBB #74: NII sensitivity tier1=15000000000, outlier=False")
audit_log("IFRS_ENGINE_USED", uname, "InvPortfolio #76: HQLA classification, total_hqla=149000000.00")
audit_log("IFRS_ENGINE_USED", uname, "CAR #77: Total CAR=19.70%, status=GREEN")
audit_log("IFRS_ENGINE_USED", uname, "CreditRisk #53: Borrower=B001, rule_grade=CCC, rule_pd=0.16")
```

This continues the v5.71 pattern — live regulatory computations are traceable by user, time, standard, and inputs.

---

## Honesty discipline preserved at the UI layer

- `_to_decimal()` returns `None` for empty/invalid input → engines return `None` per Rule 1
- Engine `{"computed": False, "reason": "..."}` responses surface the `reason` field
- **Rule 7 visually surfaced** — when credit risk engine returns `ml_pd=None` with `reason=no_ml_model_loaded`, the page shows a yellow disclosure banner explaining no silent ML substitution
- **CBK vs Basel split visualised** — separate `compliant_basel` and `compliant_cbk` flags on CAR page
- **BCBS 368 outlier thresholds visualised** — explicit pass/fail flag on NII (5%) and EVE (15%) per Tier 1
- Decimal precision 28 digits maintained throughout

---

## What didn't change

- All 4 engine source files — byte-for-byte unchanged
- `scripts/audit.py` — gates G72 / G62 / G75 / G19 / G44 still pass exactly as v5.66 verified them
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- v5.71 page (`88_ifrs_engines.py`) — unchanged, still works

---

## Comparison vs v5.71

| | v5.71 | v5.72 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **3** | **7** ⭐ |
| Audit gates | 103/103 | 103/103 (unchanged) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 88 numbered | **89 numbered** |
| Nav group entries (integration pages) | 3 | **5** (3 + 2) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** The page passes `python -m py_compile`, module-level import test in mocked-Streamlit, and 12-path engine call simulation at the CLI. What I **cannot** do is run `streamlit run app.py` to confirm browser rendering. User must do that locally to confirm visual layout, button behaviour, expanders, and tab navigation. Streamlit-specific issues like widget key conflicts or layout problems on small screens will only surface at runtime.

2. **7 of 116 integrated.** 109 standards remain library-only.

3. **CBK PG/02 minimums shown but not enforced.** The page displays compliance flags (`compliant_basel`, `compliant_cbk`) and visual status (GREEN/AMBER/RED), but does not block downstream actions when a bank is non-compliant. Enforcement is the integrating page's responsibility — e.g. management accounts page could refuse to publish if Total CAR < 14.5%.

4. **Page-passed credit risk features work for ad-hoc scoring**, but if the engine had a configured feature store (which it doesn't in this build), those values would be re-read from there. The page therefore demonstrates ad-hoc what-if scoring; production scoring would feed from a registered borrower feature store.

5. **`exposure_at_default` was renamed to `outstanding_balance`** in the page input field to match the engine's `_ead()` method which reads `features.get("outstanding_balance", 0)`. This is the engine's API, not a page bug. The label on the form mentions both.

6. **No 4th IFRS 9 ECL engine exists standalone in `utils/`.** IFRS 9 ECL logic lives inside `pages/32_ifrs9.py` directly. The 4th integration target was therefore **#53 Credit Risk Scoring** (which produces PD/LGD/EAD that feed into ECL) rather than a non-existent ECL engine. This was discovered during the build and is documented in the master prompt entry. A future batch could surface ECL by either (a) extracting the ECL logic from `pages/32_ifrs9.py` into a dedicated `utils/ifrs9_ecl.py` engine and integrating it, or (b) integrating directly with the existing IFRS 9 page.

7. **Some role roles will see 2 entries** — Finance and Risk & Compliance teams will both see "Capital & Risk Engines" in their nav groups. This is intentional (CAR matters to both Finance and Risk) but means the same page renders in 2 places. Acceptable; users who don't want it in both places can ask to drop one registration.

---

## Next batch options ranked by impact

| Priority | Batch | Standards | Strategy |
|---|---|---|---|
| **(1) Recommended** | BSC enhancement | #105 IAS 36 Impairment / #111 IAS 1 OCI recycling | Modify existing `pages/1_perform.py` + `pages/52_mgmt_accounts.py` |
| (2) | Vendor Risk | #96 Vendor Risk + #98 Procurement | Enhance `pages/64_vendors.py` |
| (3) | Customer & Disclosure | #95 CLV + #110 IFRS 7 + #116 IAS 24 | Enhance `pages/34_customer360.py` |
| (4) | Remaining IFRS Engines | #101-#108 (lease, IFRS 15, IFRS 16, IAS 19, IAS 21, IAS 28, IAS 33, IAS 36) | New consolidated page `pages/90_remaining_ifrs.py` |

Recommend **(1) BSC enhancement** for v5.73 because it modifies *existing* high-traffic pages rather than adding new ones — every user with `perform` access (i.e. virtually everyone) will see the IAS 36 impairment indicator and IAS 1 OCI recycling map without needing to navigate to a new page. After 2 batches that added new pages, modifying existing pages broadens the impact surface.

---

**Cumulative tally:** 116 standards delivered, **7 integrated into UI via 2 pages in 5 nav-group entries**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.
