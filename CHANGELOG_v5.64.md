# A2Z MIS 360 — CHANGELOG v5.64

**Volume Eighteen — Performance Management & Sustainability**
**Released:** April 2026
**Audit gates:** 85/85 = 100% PASS (was 82/82)
**Test count:** 43 files / 1491 tests (was 42/1407 — added 84 in `tests/test_volume_eighteen_batch.py`)

---

## Standards delivered (4 — all Cat B)

### #89 Funds Transfer Pricing (FTP) Engine (Cat B)
**Module:** `utils/funds_transfer_pricing.py` (~280 LOC)
**Engine:** `FtpEngine`

4 entries: `matched_maturity_ftp_rate`, `single_pool_ftp_rate`, `liquidity_premium`, `net_interest_margin_split`.

**2 FTP_METHODOLOGIES byte-for-byte:** SINGLE_POOL, MATCHED_MATURITY

**11 FTP_CURVE_TENORS_MONTHS byte-for-byte:** 1, 3, 6, 12, 24, 36, 60, 84, 120, 240, 360

**5 LIQUIDITY_PREMIUM_TIERS_BPS byte-for-byte:**

| Tier | Tenor band (months) | Premium (bps) |
|---|---|---|
| SHORT_TERM | 0–12 | 10 |
| MEDIUM_TERM | 13–60 | 25 |
| LONG_TERM | 61–120 | 50 |
| VERY_LONG_TERM | 121–240 | 100 |
| EXTRA_LONG_TERM | 241+ | 150 |

**MMFTP behaviour:** linear interpolation between curve points; below shortest → use shortest; above longest → use longest (anchor extrapolation, not extension).

**NIM split:** asset → lending_spread = customer_rate − ftp_rate; liability → funding_spread = ftp_rate − customer_rate.

**Rule 1**: empty curve, missing tenor, zero pool balance → None (no silent fallback).
**Rule 6**: mismatched input lengths surfaced. Self-test: 20/20.

---

### #90 Product RAROC & Hurdle-Rate Tiering (Cat B)
**Module:** `utils/product_raroc.py` (~310 LOC)
**Engine:** `ProductRarocEngine`

Note: separate from existing `utils/product_profitability.py` (Std #47, Volume Seven, v5.52) which covers cross-sell/lifecycle/FTP propagation. #90 adds RAROC formula, hurdle-rate tiering, and cost allocation methodologies — the two are complementary.

6 entries: `net_interest_income`, `total_opex`, `operating_profit`, `raroc`, `profitability_tier`, `allocate_costs`.

**6 PRODUCT_GROUPS byte-for-byte:** TRANSACTION_BANKING, CONSUMER_LENDING, CORPORATE_LENDING, TRADE_FINANCE, TREASURY, BANCASSURANCE

**4 COST_CATEGORIES byte-for-byte:** DIRECT_PRODUCT_COSTS, ALLOCATED_OPERATIONS, ALLOCATED_TECHNOLOGY, ALLOCATED_OVERHEAD

**3 ALLOCATION_METHODOLOGIES byte-for-byte:** ABC, FULL_COST, MARGINAL

**HURDLE_RATE_PCT = Decimal("15")** byte-for-byte (typical bank target).

**Tier multipliers byte-for-byte:**
- GREEN_MULTIPLIER = 1.0 (≥ hurdle)
- AMBER_MULTIPLIER = 0.8 (≥ 80% of hurdle)

**RAROC formula:** (Operating Profit − Expected Loss) / Economic Capital × 100

**Tier classification:**
- GREEN: RAROC ≥ 15%
- AMBER: 12% ≤ RAROC < 15%
- RED: RAROC < 12%

**Runtime example:** Mortgage product with NII 60M, +10M non-interest, -14M opex, -8M EL, 200M EC → 24% RAROC → GREEN.

**Rule 1**: zero EC, missing components → RAROC=None.
**Rule 6**: tier=None when raroc=None. Self-test: 24/24.

---

### #91 Channel Performance Analytics (Cat B)
**Module:** `utils/channel_performance.py` (~270 LOC)
**Engine:** `ChannelPerformanceEngine`

5 entries: `cost_per_transaction`, `channel_mix_pct`, `self_service_ratio`, `channel_availability_compliance`, `blended_cost_per_transaction`.

**10 CHANNELS byte-for-byte:** BRANCH, ATM, AGENT, MOBILE, INTERNET, USSD, CALL_CENTER, POS, RTGS, SWIFT

**CHANNEL_COST_PER_TXN_KES byte-for-byte (KES per transaction):**

| Channel | Cost | Tier |
|---|---|---|
| BRANCH | 200 | PHYSICAL |
| CALL_CENTER | 80 | PHYSICAL |
| ATM | 50 | PHYSICAL |
| AGENT | 30 | PHYSICAL |
| POS | 15 | PHYSICAL |
| INTERNET | 5 | DIGITAL |
| MOBILE | 2 | DIGITAL |
| USSD | 2 | DIGITAL |
| RTGS | 1500 | INTERBANK |
| SWIFT | 2500 | INTERBANK |

The 100× spread between BRANCH (200) and MOBILE (2) is the central digital-migration business case captured byte-for-byte.

**3 SELF_SERVICE_CHANNELS byte-for-byte:** MOBILE, INTERNET, USSD

**CHANNEL_AVAILABILITY_TARGET_PCT = Decimal("99.5")** byte-for-byte.

**3 CHANNEL_TIERS byte-for-byte:** PHYSICAL, DIGITAL, INTERBANK

**CHANNEL_TIER_MAP** byte-for-byte (every channel → exactly one tier).

**Self-service ratio = (MOBILE + INTERNET + USSD) / total_volume × 100**

**Runtime example:** 800 self-service of 1000 total → 80% self-service ratio. 500 BRANCH + 500 MOBILE blended cost = (500*200 + 500*2)/1000 = 101 KES/txn.

**Rule 1**: zero count, missing cost → None.
**Rule 6**: unknown channel surfaced. Self-test: 20/20.

---

### #92 ESG / Sustainability Reporting (Cat B)
**Module:** `utils/esg_reporting.py` (~320 LOC)
**Engine:** `EsgReportingEngine`

Per **TCFD** (Task Force on Climate-related Financial Disclosures) + **IFRS S2** (ISSB Climate-related Disclosures) + **GHG Protocol** + **CBK Climate Risk Management Framework** (April 2021).

4 entries: `validate_tcfd_disclosure`, `ghg_emissions_total`, `climate_risk_classification`, `generate_tcfd_pack`.

**4 TCFD_PILLARS byte-for-byte:** GOVERNANCE, STRATEGY, RISK_MANAGEMENT, METRICS_AND_TARGETS

**11 TCFD_RECOMMENDED_DISCLOSURES byte-for-byte (per-pillar count GOV=2, STR=3, RISK=3, MET=3):**
GOV_A, GOV_B, STR_A, STR_B, STR_C, RISK_A, RISK_B, RISK_C, MET_A, MET_B, MET_C

**3 GHG_SCOPES byte-for-byte (GHG Protocol):** SCOPE_1 (direct), SCOPE_2 (purchased electricity), SCOPE_3 (value chain)

**15 SCOPE_3_CATEGORIES byte-for-byte (GHG Protocol Scope 3 standard):**

| # | Category |
|---|---|
| 1 | PURCHASED_GOODS_AND_SERVICES |
| 2 | CAPITAL_GOODS |
| 3 | FUEL_AND_ENERGY_RELATED |
| 4 | UPSTREAM_TRANSPORTATION |
| 5 | WASTE_GENERATED_IN_OPERATIONS |
| 6 | BUSINESS_TRAVEL |
| 7 | EMPLOYEE_COMMUTING |
| 8 | UPSTREAM_LEASED_ASSETS |
| 9 | DOWNSTREAM_TRANSPORTATION |
| 10 | PROCESSING_OF_SOLD_PRODUCTS |
| 11 | USE_OF_SOLD_PRODUCTS |
| 12 | END_OF_LIFE_TREATMENT |
| 13 | DOWNSTREAM_LEASED_ASSETS |
| 14 | FRANCHISES |
| 15 | **INVESTMENTS** (financed emissions — most material category for banks) |

**6 CLIMATE_RISK_TYPES byte-for-byte:**
- 2 physical: ACUTE_PHYSICAL, CHRONIC_PHYSICAL
- 4 transition: TRANSITION_POLICY, TRANSITION_TECHNOLOGY, TRANSITION_MARKET, TRANSITION_REPUTATION

**3 ISSB_DISCLOSURE_TOPICS byte-for-byte (IFRS S2):** CLIMATE_GOVERNANCE, CLIMATE_STRATEGY, CLIMATE_METRICS

**TCFD_MIN_COMPLETE_PCT = Decimal("100")** byte-for-byte (zero tolerance for TCFD pack distribution).

**Runtime example:** 1500 + 8000 + 250000 = 259,500 tCO2e total emissions. 11/11 disclosures populated → eligible for distribution.

**Rule 1**: total emissions = None when ANY scope missing (cannot silently extrapolate financed emissions — Scope 3 category 15 is typically 90%+ of a bank's footprint, so missing it would dramatically understate exposure).
**Rule 6**: missing disclosures surfaced; pack ineligible if incomplete. Self-test: 20/20.

---

## Audit gates added (3)

### G83 — `gate_ftp_correct`
Inline programmatic gate verifying:
- 2 FTP_METHODOLOGIES byte-for-byte
- 11 FTP_CURVE_TENORS_MONTHS byte-for-byte
- 5 LIQUIDITY_PREMIUM_TIERS_BPS byte-for-byte
- LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS byte-for-byte
- Runtime: MMFTP exact match 12mo → 9.5%
- Runtime: linear interpolation 18mo (between 12 at 9.5% and 24 at 10.0%) → 9.7500%
- Runtime: single pool 50M@8% + 50M@12% → 10.0000% weighted average
- Runtime: liquidity premium 84mo → LONG_TERM = 50bps
- Rule 1: empty curve / missing tenor / zero balance → None
- NIM split: asset 14%-9% = 5% lending; liability 9%-5% = 4% funding

**Tampering test:** LIQUIDITY_PREMIUM_TIERS_BPS["EXTRA_LONG_TERM"] (150→1) caught.

---

### G84 — `gate_product_raroc_correct`
Inline programmatic gate verifying:
- 6 PRODUCT_GROUPS byte-for-byte
- 4 COST_CATEGORIES byte-for-byte
- 3 ALLOCATION_METHODOLOGIES byte-for-byte
- HURDLE_RATE_PCT=15 byte-for-byte
- GREEN_MULTIPLIER=1.0 / AMBER_MULTIPLIER=0.8 byte-for-byte
- Runtime: full RAROC chain — NII 60M + 10M - 14M opex = 56M operating profit; (56M - 8M EL) / 200M EC = 24% RAROC
- Tier classification: 24%=GREEN, 13%=AMBER, 5%=RED
- Boundary cases: 15% (at hurdle) = GREEN; 12% (at amber threshold) = AMBER
- Rule 1: zero EC → RAROC=None
- Rule 6: tier=None when raroc=None
- ABC allocation: 60/40 split of 1M → 600K/400K
- Unknown method rejected

**Tampering test:** HURDLE_RATE_PCT (15→1) caught.

---

### G85 — `gate_channel_esg_correct`
Combined inline programmatic gate for #91 + #92.

**CHANNEL (#91):**
- 10 CHANNELS byte-for-byte
- CHANNEL_COST_PER_TXN_KES byte-for-byte (BRANCH=200, MOBILE=2, etc.)
- 3 SELF_SERVICE_CHANNELS byte-for-byte
- CHANNEL_AVAILABILITY_TARGET_PCT=99.5 byte-for-byte
- 3 CHANNEL_TIERS + tier map byte-for-byte
- Runtime: cost-per-txn 1M/100K = 10; self-service 80%; blended 101; availability 1.50pp shortfall
- Rule 1: zero count / missing cost → None
- Rule 6: unknown channel surfaced

**ESG (#92 TCFD + IFRS S2 + GHG Protocol):**
- 4 TCFD_PILLARS byte-for-byte
- 11 TCFD_RECOMMENDED_DISCLOSURES byte-for-byte
- Per-pillar counts GOV=2, STR=3, RISK=3, MET=3 byte-for-byte
- 3 GHG_SCOPES byte-for-byte
- 15 SCOPE_3_CATEGORIES byte-for-byte (incl. INVESTMENTS for financed emissions)
- 6 CLIMATE_RISK_TYPES byte-for-byte
- 3 ISSB_DISCLOSURE_TOPICS byte-for-byte
- TCFD_MIN_COMPLETE_PCT=100 byte-for-byte
- Runtime: full pack complete + eligible; GHG total 259,500 tCO2e
- Rule 1: missing scope → total=None
- Rule 6: missing disclosure surfaced
- Climate risk classification: PHYSICAL vs TRANSITION family

**Tampering tests:** CHANNEL_COST_PER_TXN_KES["MOBILE"] (2→500) caught; len(SCOPE_3_CATEGORIES) drop FRANCHISES (15→14) caught.

---

## Spec deviations through v5.64

**Cumulative count UNCHANGED at 9** — no new spec deviations introduced (all 4 standards Cat B with full deterministic implementation).

## Rule 7 application count

**UNCHANGED at 6** — no ML branches in v5.64 (all 4 standards Cat B performance/sustainability).

---

## Comparison v5.63 → v5.64

| Metric | v5.63 | v5.64 |
|---|---|---|
| Standards delivered | 88 | **92** |
| Audit gates | 82/82 = 100% | **85/85 = 100%** |
| Test files | 42 | **43** |
| Total tests | 1407 | **1491** |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |
| New utility modules | 4 | **4** (~1,180 LOC) |

---

## Why Volume Eighteen matters

Volume Eighteen adds the **Performance & Sustainability layer** that sits above the reporting superstructure (Vol 17), the three lines of defence (Vols 9-10, 16), Treasury/Capital (Vols 14-15), and the operational disciplines (Vols 11-13).

**The four standards together let CFO + COO + Board judge their own work against economic and sustainability standards:**

- **#89 FTP** — separates lending margin from funding margin. The CFO can finally see whether a 14% mortgage at 9% FTP is making **5% lending spread** or whether the bank is cross-subsidising loan products from cheap deposits. NIM alone hides this.

- **#90 Product RAROC** — turns operating profit + expected loss + economic capital into a single comparable hurdle-rate-adjusted return. Board Strategy Committee can rank every product line against the 15% return target. RAROC of 24% (Mortgage) vs 8% (Personal Loans) makes the capital allocation decision unambiguous.

- **#91 Channel Performance** — quantifies the 100× cost spread between BRANCH (200 KES/txn) and MOBILE (2 KES/txn). The COO can see exactly how much margin is being left on the table by every transaction that goes through a branch instead of a digital channel. The 80% self-service ratio target is the operational North Star.

- **#92 ESG/TCFD** — delivers the Board's regulator-mandated climate disclosure pack to TCFD + IFRS S2 + GHG Protocol standard. Critically, **Scope 3 category 15 (INVESTMENTS = financed emissions)** is encoded byte-for-byte — for a bank, this is typically 90%+ of total emissions and the central focus of climate risk management. The 11-disclosure TCFD framework with 100% completeness threshold means the Board cannot accidentally publish a partial disclosure pack.

**Key engineering invariants encoded byte-for-byte:**

- **FTP linear interpolation** between curve points (Decimal precision 28); below shortest → anchor to shortest (no extrapolation), above longest → anchor to longest
- **RAROC formula** (Operating Profit − EL) / EC × 100 with explicit 15% hurdle and tiered GREEN/AMBER/RED classification
- **Channel cost benchmarks** (200/50/30/2/5/2/80/15/1500/2500 KES) matching industry practice
- **TCFD 11 disclosures** with strict per-pillar count (2/3/3/3) — drift in any of these would make the disclosure non-compliant
- **GHG Protocol 15 Scope 3 categories** including INVESTMENTS (#15) — banks' largest single emissions category
- **Rule 1 fail-closed**: missing GHG scope → total=None (cannot silently extrapolate financed emissions)
- **Rule 6 surface**: missing TCFD disclosure → pack `eligible_for_distribution=False`

When the CFO presents quarterly product RAROC of 24% (GREEN), the COO presents Q3 self-service ratio of 78%, and the Board Sustainability Committee approves the annual TCFD pack with total Scope 1+2+3 emissions of 259,500 tCO2e — those numbers, those classifications, those disclosures are **independently verifiable, drift-detected, audit-trail-enforced, and tamper-evident**.

**The Performance & Sustainability layer is now complete on top of the Reporting Superstructure.**

The platform now spans the **complete CFO + COO + Board governance + Sustainability stack** — every major banking discipline supported with byte-for-byte regulatory fidelity to TCFD, IFRS S2, GHG Protocol, BCBS 309/356, CMA Code, and CBK BSD requirements.
