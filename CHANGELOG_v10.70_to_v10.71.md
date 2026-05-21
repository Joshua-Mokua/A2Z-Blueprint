# CHANGELOG v10.70-v10.71 — trade_finance arc OPENING (dual batch)

**Status:** trade_finance arc opening, 2/12 standards active. ENH-269 + ENH-273 shipped together as the dual-batch opener.
**Audit:** **136/136 PASS** · **G117** 99.0% (193/195) · **G128** STABLE (336 modules · 864 imports · 3 HARD baseline)
**Active standards:** 139/260 (+2 vs v10.69)
**Scenario library:** 134 (+8 trade finance scenarios across TFI-* and TFL-*)
**Self-tests:** 374/374 PASS across 22 engines

---

## Why trade_finance is the next arc

With the finance arc closed at v10.69, two priority B subcategories with full standard sets remain as natural next-arc candidates: trade_finance (12 planned) and customer_360 (12 planned). Trade finance won this round for three reasons:

1. **Direct fit for Ecobank Kenya's corporate banking strength.** Trade finance is a major revenue line at the bank — letters of credit, bank guarantees, documentary collections. Modeling these instruments deterministically gives operational leverage to the corporate banking desk.

2. **Cleaner Rule 7 / Rule 1 patterns.** Trade finance is deterministic by nature — UCP 600, ISP98, URDG 758, URC 522, IFRS 9 contingent liabilities, Basel CCF. Document validation, state machines, exposure measurement all reduce to deterministic rules with explicit framework citations. Customer 360 leans heavier on ML (churn prediction, journey optimization, behavioral pattern detection) which would force more `ml_disabled` fallback patterns.

3. **Composes cleanly with existing engines.** ENH-273 limits compose with ENH-252 CBK SBL (bank-wide aggregate vs per-product allocation — distinct concerns). ENH-269 instrument exposure feeds Basel CCF computations the capital adequacy engine already does. SWIFT integration (ENH-272, deferred) will compose with the regulatory reporting layer.

## v10.70 — ENH-269 Trade Finance Core Instruments Engine

`utils/trade_finance_instruments.py` (~810 lines, 30/30 tests PASS)

Five capabilities, each surfacing full Rule 1 provenance with framework citations per instrument type:

**1. `validate_issuance`** — pre-issuance field-level + business-rule validation. LC requires `lc_type` + advising bank (warning if missing — UCP 600 §9 best practice) + description of goods + incoterms + tenor ≤365d hard / ≤270d warning; SBLC and BG more permissive (financial/standby instruments don't need shipped-goods discipline); DOC_COLLECTION requires goods + incoterms; CLEAN_COLLECTION minimal. 3 `ValidationOutcome` (VALID/WARNING/INVALID) scaled by violation severity — hard rule violations dominate over warnings.

**2. `validate_state_transition`** — `InstrumentState` machine with 9 states (DRAFT/APPROVED/ISSUED/AMENDED/ACTIVE/DRAWN/EXPIRED/CANCELLED/REJECTED) and explicit allowed-transitions matrix. DRAWN/EXPIRED/CANCELLED/REJECTED are terminal. Cannot skip states (e.g. DRAFT → ISSUED rejected — must approve first).

**3. `validate_amendment`** — amendments permitted only from ISSUED/AMENDED/ACTIVE states. **LC + SBLC require `beneficiary_consent` per UCP 600 §10 / ISP98 §2.06** — engine surfaces this requirement explicitly via `requires_beneficiary_consent` flag in the validation result; operator must capture consent before posting. >25% amount uplift raises soft warning to delegate to ENH-273 limits engine.

**4. `compute_exposure`** — IFRS 9 + IAS 37 contingent liability measurement. FUNDED vs UNFUNDED `ExposureClassification`. Drawn portion of LC = funded receivable from applicant; undrawn = unfunded contingent liability. SBLC + BG = full notional unfunded contingent until drawn. Clean Collection = zero contingent (bank handles documents only). Basel CCF noted in framework refs as caller's downstream concern.

**5. `age_pending_actions`** — surfaces 5 `AgingBucket` states for portfolio review. DRAFT_STALE (>7d in DRAFT — abandon or progress); APPROVED_NOT_ISSUED (>3d after approval — operator action required); EXPIRY_IMMINENT (≤7d to expiry — prepare drawdown or amendment); EXPIRED_OPEN (past expiry but state not closed — close to EXPIRED); NORMAL. Thresholds operator-configurable.

Enums: 5 `InstrumentType` × 9 `InstrumentState` × 7 `LcType` (SIGHT/USANCE/RED_CLAUSE/GREEN_CLAUSE/TRANSFERABLE/BACK_TO_BACK/REVOLVING) × 6 `BgType` (PAYMENT/PERFORMANCE/BID_BOND/ADVANCE_PAYMENT/RETENTION_MONEY/WARRANTY) × 2 `ExposureClassification` × 5 `AgingBucket` × 3 `ValidationOutcome`.

**Per Rule 7, engine NEVER:** issues instruments (operator approval workflow); amends (validate_amendment surfaces consent requirement, never applies); honors drawdowns; pays beneficiaries; books accounting entries; sends SWIFT messages (ENH-272 territory); auto-cancels or auto-expires aged instruments; mutates inputs.

**Bug fixed during build:** `FRAMEWORK_REFS` dict required trailing commas on single-element tuples for BG/DOC_COLLECTION/CLEAN_COLLECTION entries — Python's `("x")` is a string, `("x",)` is a single-element tuple. The trade finance arc joins the platform's pattern of explicit single-element tuple discipline (same gotcha that bit ENH-251 earlier).

## v10.71 — ENH-273 Trade Finance Limits & Risk Management

`utils/trade_finance_limits.py` (~720 lines, 16/16 tests PASS)

Diagnostic 4-dimensional pre-deal + post-deal limit utilization engine consuming `TradeInstrument` from ENH-269. Distinct from ENH-252 — that one tracks bank-wide single-borrower aggregate per CBK PG/05; ENH-273 operates at the trade-finance product level for per-instrument allocation decisions. Both compose: a deal can pass ENH-273 product limits but still trip ENH-252 bank-wide SBL.

**Four `LimitDimension`:**

- **COUNTRY** — foreign country sovereign + counterparty risk concentration. `CountryAttribution` maps beneficiary to ISO-3166-alpha-2 country code. Beneficiary-side attribution because country exposure tracks where the goods are flowing from / payment is being made to.
- **COUNTERPARTY** — per-corporate exposure aggregated by **APPLICANT** (not beneficiary). In trade finance, the applicant is the bank's customer and carries the default risk to the bank — they're the one who'd be unable to reimburse the bank if the LC draws. Beneficiary risk is more about delivery performance (commercial risk between parties) than credit risk to the bank.
- **PRODUCT** — concentration in a single `InstrumentType` (LC / SBLC / BG / Doc Collection / Clean Collection).
- **TENOR** — 4 buckets: SHORT ≤90d / MEDIUM 91-180d / LONG 181-365d / EXTRA_LONG >365d. Long-tenor concentration materially worsens liquidity profile under stress; engine surfaces this as a separate dimension from product/counterparty.

**Each dimension is opt-in.** If no limits configured for a dimension, engine returns nothing — caller has chosen not to track that dimension. If limits configured for a dimension but a specific bucket missing, engine surfaces "policy gap" BREACH for that bucket. This pattern was discovered during build — earlier behavior treated empty-limits as policy gap = BREACH for every observed bucket, which produced spurious BREACHes in test scenarios that only configured one dimension. Fix is in: **dimension opt-out preserves the principle that the engine never asserts what limits "should" be configured.**

**4-tier `UtilizationSeverity`** by % of limit consumed: HEALTHY ≤70%, ELEVATED 70-85%, HIGH 85-100%, BREACH >100%. Strict > comparison at boundaries — 0.70 stays HEALTHY, 1.00 stays HIGH. Closed instruments (EXPIRED/CANCELLED/REJECTED/DRAWN) excluded from exposure since they no longer consume limits.

**`check_pre_deal`** computes utilization both with and without the proposed deal; identifies `binding_dimension` (the tightest constraint affected by the proposed instrument); returns 4 `PreDealOutcome`:

- APPROVE_LIKELY (post-deal HEALTHY)
- REVIEW_NEEDED (post-deal ELEVATED)
- SENIOR_APPROVAL (post-deal HIGH)
- BLOCK_RECOMMENDED (post-deal BREACH)

**`build_portfolio_report`** orchestrates all 4 dimensions returning `PortfolioLimitReport` with by_severity + by_dimension aggregates + breached_count.

**Per Rule 7, engine NEVER:** approves or rejects deals (computes utilization only); blocks instrument issuance; posts limit allocations to source systems; amends operator-set limits; sources market data; auto-rebalances portfolio; mutates inputs.

## Composition between ENH-269 and ENH-273

ENH-273 imports `TradeInstrument`, `InstrumentType`, `InstrumentState` from ENH-269. The exposure-of-instrument helper checks state — closed instruments contribute zero. This means a deal flow looks like:

1. Caller proposes `TradeInstrument` in DRAFT state
2. ENH-269 `validate_issuance` confirms field-level + business-rule integrity
3. ENH-273 `check_pre_deal` evaluates against 4 limit dimensions; recommends outcome
4. Operator approves → state transitions DRAFT → APPROVED → ISSUED (each transition validated by ENH-269)
5. ENH-269 `compute_exposure` produces IFRS 9 contingent liability measurement
6. ENH-273 `build_portfolio_report` aggregates portfolio utilization across all instruments
7. As the instrument matures, ENH-269 `age_pending_actions` surfaces operational concerns (expiry imminent, draft stale)

Each step is diagnostic. Each step's output feeds operator decision-making. No engine in the chain auto-acts.

## Final platform state

| Metric | Value |
| --- | --- |
| Audit gates | **136/136 PASS** |
| G117 Engine Hub coverage | 99.0% (193/195) |
| G128 structural integrity | STABLE (336 modules · 864 imports · HARD=3 baseline) |
| Active standards | 139/260 (+2 vs v10.69) |
| Trade finance arc | **2/12 active (in flight)** |
| Scenario library | 134 (+8) |
| Trade finance scenarios | 8 (4 TFI-* + 4 TFL-*) |
| Self-tests | 374/374 across 22 engines |
| Closed arcs | 13 (unchanged — trade_finance opens but does not close) |

## What the next 5 drops look like

10 standards remain in the trade_finance arc (ENH-270, 271, 272, 274, 275, 276, 277, 278, 279, 280). At 2-per-drop cadence, that's 5 more drops to closure. Likely sequencing:

- **v10.72-v10.73** — ENH-272 SWIFT Integration (MT700/707/760/103 message validation) + ENH-274 Compliance (sanctions screening on parties/ports/vessels, dual-use goods detection)
- **v10.74-v10.75** — ENH-275 Accounting & Integration (IFRS 9 contingent liability journal templates + Basel CCF) + ENH-280 Reporting & Analytics (trade volumes, country exposure, sector concentration)
- **v10.76-v10.77** — ENH-278 Sustainable Trade Finance (green LC, ESG-screened counterparties) + ENH-270 AI-Powered Document Checking (with explicit `ml_disabled` flag per Rule 6 — the AI hook is injectable; engine works without it)
- **v10.78-v10.79** — ENH-271 Corporate Trade Portal (Streamlit; split-implementation likely — data layer ships, UI rolls into closure cockpit) + ENH-276 Multi-Bank Connectivity (we.trade, Marco Polo, Contour, Bolero — diagnostic adapter surface, never sends)
- **v10.80** — closure batch: G137 trade_finance_arc_closed + G138 trade_finance_arc_ui_integrated + pages/97_trade_finance_arc_cockpit.py + Tier 28 expanded to full descriptions + Master Prompt v3 line 108 update + CHANGELOG_v10.80.md

ENH-279 Trade Finance Mobile App is out of scope for the diagnostic engine pattern — a mobile app is a separate frontend project, not an engine. The closure narrative will document this honestly.

The G117 floor will need monitoring around v10.74-v10.76 when the in-flight engine count starts pressing the 95% boundary. The Tier 28 placeholder is in place from v10.71; descriptions for new engines added at each drop will keep coverage above floor through closure.

## Lean+Compact protocol — mid-arc update

The v10.46 amendment + v10.65 nuance hold for this arc. Specifically:

- **2 batches per drop** confirmed direction
- **Closure batches ship 5 things** together (G-gate ratchet pair + Engine Hub Tier expansion + Master Prompt update + UI cockpit + CHANGELOG)
- **G117 95% floor** preserved via Tier placeholders mid-arc (Tier 28 in place from v10.71; will expand at closure)
- **Audit + G128 + scenario library** non-negotiable per batch — both batches in this drop preserved this discipline
- **Rule 1** (full provenance) + **Rule 6** (ml_disabled flag) + **Rule 7** (diagnostic-only) maintained

The dimension opt-out pattern discovered during ENH-273 build is a new addition to the engine library — when an engine handles multiple dimensions and the caller opts out of some, the engine should produce no output for opted-out dimensions rather than asserting policy gaps. This pattern preserves the principle that the engine never asserts what limits "should" be configured. Future engines with optional dimensions should follow this pattern.

## Files changed in this drop

- **NEW** `utils/trade_finance_instruments.py` (~810 lines, 30 tests)
- **NEW** `utils/trade_finance_limits.py` (~720 lines, 16 tests)
- **MOD** `utils/standards_registry.py` (ENH-269 + ENH-273 activated with full descriptions)
- **MOD** `utils/scenario_simulator.py` (8 scenarios added: TFI-01..04 + TFL-01..04 + library wiring)
- **MOD** `pages/7_admin.py` (Tier 28 placeholder added with brief one-paragraph descriptions per engine)
- **NEW** `CHANGELOG_v10.70_to_v10.71.md` (this file)
