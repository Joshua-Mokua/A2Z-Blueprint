# CHANGELOG v10.77 — trade_finance arc batch 7 (7/12)

**Status:** Single-batch drop by deliberate choice. Per the v10.76 ML-strategy review, ENH-270 AI-Powered Document Checking gets paired with the reference training script as a v10.78 dual batch — splitting the cadence so that the ML reference implementation gets proper attention rather than being squeezed into v10.77 alongside ENH-278. The trade finance arc still closes at v10.80.

**Audit:** 136/136 PASS (unchanged — closure-batch ratchets batched at v10.80)
**G117:** 99.0% (195/197) (unchanged)
**G128:** STABLE (343 modules · 877 imports · HARD=3) (+1 module, +2 imports from new engine)
**Active standards:** 144/260 (was 143; +1 from this drop)
**Scenario library:** 154 (was 150; +4 from this drop — SUS-01..04)
**Engine self-tests:** 143/143 via orchestrator (was 142; +1 from this drop)

---

## v10.77 — ENH-278 Sustainable Trade Finance (deterministic)

**Module:** `utils/trade_finance_sustainability.py` (~880 lines, 23/23 tests pass)

Diagnostic ESG + climate + sustainability screening engine for trade finance instruments. Five capabilities, all deterministic — sustainability classification is rules-based when caller supplies a taxonomy, and PCAF-aligned emissions attribution is arithmetic. ML doesn't add accuracy here; the operationally-meaningful improvements come from better taxonomy data, refined emission factors, and faster ESG rating updates — none of which the engine should bundle.

The engine follows the **ENH-274 caller-supplied data discipline** — it bundles no taxonomy, no exclusion list, no emission factors, no ESG ratings. All four data types are operationally maintained and update on independent cadences:

- **KGFT** (Kenya Green Finance Taxonomy 2025) updates annually as CBK refines sector definitions
- **KBA SFI** prohibited-sector list updates as the bank association revises industry-level commitments
- **PCAF** emission factors update per sector as data hierarchy improves (Score 1 directly reported through Score 5 estimated proxies)
- **ESG ratings** flow continuously from MSCI / Sustainalytics / ISS ESG / internal screening

Bundling any of these into the engine would freeze data that needs to refresh independently of the platform deployment. Operations layer maintains the feeds; the engine consumes them at call time.

### The five capabilities

**1. `classify_instrument_sustainability`** — Word-boundary regex match against caller-supplied `TaxonomyEntry` sequence (keyword + tier + source + justification). 4-tier `SustainabilityTier`: GREEN / TRANSITION / BROWN / UNCLASSIFIED. UNCLASSIFIED is the no-match outcome; `TaxonomyEntry` rejects UNCLASSIFIED at construction so callers can't accidentally inject an "unclassified" rule.

Per Rule 1, ALL matches surface in the result — operator sees every signal, not just the engine's pick. The `primary_tier` field is mechanically derived as the most-conservative-tier-present (BROWN > TRANSITION > GREEN > UNCLASSIFIED), so a deal that mentions both solar panels and a coal-fired backup boiler shows `primary_tier=BROWN` plus `conflicting=True` plus both matches in `all_matches`. Operator adjudicates the conflict; engine doesn't make the call.

3-character `MIN_KEYWORD_LENGTH` floor on taxonomy keywords, rejected at construction. Same discipline as ENH-274 — prevents `oil` from matching `topsoil` via substring.

**2. `screen_exclusion_list`** — Word-boundary match against caller-supplied `ExclusionEntry` sequence (KBA SFI prohibited sectors, internal policy, regulator-mandated exclusions). 4-tier `ExclusionSeverity`: CRITICAL (absolute prohibition, e.g. weapons) / HIGH (bank-level exclusion, e.g. thermal coal) / MEDIUM (senior-approval required) / LOW (review-only). 5-tier `SustainabilityScreeningOutcome` ladder: ELIGIBLE_GREEN / ELIGIBLE_TRANSITION / REVIEW_NEEDED / SENIOR_APPROVAL / EXCLUDED — driven by highest-severity hit per Rule 7 (engine surfaces; operator decides).

**3. `compute_ghg_attribution`** — PCAF Global GHG Accounting & Reporting Standard for Financed Emissions: `amount_kes × emission_factor_kgco2e_per_kes`. Caller supplies `sector_attribution` (applicant_id → sector_code) and `emission_factors` (sector_code → kg CO2e per KES). 3-tier `GhgAttributionStatus`: ATTRIBUTED / SECTOR_UNKNOWN / FACTOR_UNKNOWN — surfaces the gap rather than fabricating zero. This matters because zero-emissions financing is a categorically different state from unknown-emissions financing, and conflating them undermines the disclosure quality TCFD expects.

**4. `assess_counterparty_esg_risk`** — Per-counterparty risk lookup against caller-supplied `esg_attribution` map (MSCI / Sustainalytics / internal feed). 5-tier `EsgRiskTier`: LOW / MEDIUM / HIGH / SEVERE / UNRATED. UNRATED treated as least severe in the worst-of-pair calculation so the rating gap stays visible — masking unrated counterparties as low-risk would hide the data quality problem.

**5. `build_sustainability_report`** — Portfolio orchestrator. Tier shares (notional-weighted) + total attributed emissions + unattributed_count + top-5 emitting sectors + exclusion hit counts (total + critical) + ESG risk distribution. Active states only (ISSUED / AMENDED / ACTIVE) — closed instruments excluded from current portfolio snapshot, consistent with ENH-275 disclosure discipline.

### Why this is the right deterministic shape

A sustainability classifier that "guesses" green vs brown without the operator seeing exactly which keyword fired and where it came from is a compliance failure waiting to happen. The same applies to PCAF emissions — fabricated zero emissions because the engine couldn't find a sector factor would breach the disclosure principles PCAF and TCFD both require. Surfacing the gap (`SECTOR_UNKNOWN` / `FACTOR_UNKNOWN` / `UNRATED`) is the honest reporting posture and the only one that defends well in audit.

ML could plausibly help with sector inference from goods descriptions (e.g. "what sector is 'industrial cement clinker' in") but that's a different engine — sector classification, not sustainability screening. If/when that becomes a separate ENH-* engine, it will plug into the v10.76 ML hook contract and feed `sector_attribution` upstream of this engine. ENH-278 stays deterministic by design.

**Per Rule 7, engine NEVER:** sets sustainability classifications (taxonomy is caller-supplied; engine looks up only); blocks transactions (operator adjudicates per outcome ladder); amends taxonomy or exclusion list (operationally separate); reports to CBK / regulators (climate disclosure flows through ENH-CLIM-* engines); adjusts pricing or terms (RM / pricing system territory); sources emission factors or ESG ratings (caller supplies); mutates inputs.

## 4 new scenarios (SUS-01..04)

All 4 pass with 16/16 assertions:

- **SUS-01** — solar PV equipment LC against KGFT taxonomy → primary_tier GREEN, single match, no conflict, KGFT cited in framework_refs
- **SUS-02** — thermal coal LC: classification BROWN (2 matches: 'thermal coal' + 'coal' both BROWN), exclusion HIGH severity hit, outcome SENIOR_APPROVAL
- **SUS-03** — PCAF GHG attribution: 10m KES × 0.50 kg CO2e/KES = 5m kg CO2e attributed; pair test for FACTOR_UNKNOWN gap surfacing
- **SUS-04** — portfolio sustainability report: 3-LC portfolio (5m green + 3m brown + 2m unclassified), tier shares 0.5/0.3/0.2, total emissions 2.15m kg CO2e (250k + 1.5m + 400k), top sector ENERGY_FOSSIL, 1 HIGH exclusion hit, 0 critical

## Tier 28 expansion (`pages/7_admin.py`)

Tier 28 label updated to `(v10.70-v10.77, in flight, closes vTBD)`. New entry appended after `trade_finance_reporting`:
- `trade_finance_sustainability` / `TradeFinanceSustainabilityEngine` — full description with 5-capability summary, caller-supplied data discipline noted, all enums and dataclass count surfaced

Tier 28 now has **7 of 12 expected entries** (instruments / limits / SWIFT / compliance / accounting / reporting / sustainability). Closure batch v10.80 adds the remaining 5 entries (ENH-270 + ENH-271 + ENH-276 + ENH-279 scope-resolution note + closure cockpit page).

## Why single-batch this drop

The Lean+Compact protocol's two-per-drop cadence is a discipline, not a quota. ENH-270 AI-Powered Document Checking is the natural pair for v10.77, but it requires real attention to the ML hook contract integration, the deterministic UCP 600 fallback, AND the reference training script. Compressing all three into v10.77 alongside ENH-278 would force corner-cutting on the ML reference implementation — exactly the part that needs the most rigor. The single-batch decision protects v10.78 from a quality compromise that would be hard to roll back.

The trade finance arc still closes at v10.80 on schedule:
- v10.77 (this drop) — ENH-278
- v10.78 (next) — ENH-270 + reference training script
- v10.79 — ENH-271 Corporate Trade Portal + ENH-276 Multi-Bank Connectivity
- v10.80 — closure batch (G137 + G138 + cockpit + Tier 28 full descriptions + Master Prompt update)

## Files changed in this drop

- **NEW** `utils/trade_finance_sustainability.py` (~880 lines, 23 tests)
- **MOD** `utils/standards_registry.py` (ENH-278 activated, comprehensive description)
- **MOD** `utils/scenario_simulator.py` (4 new SUS scenarios + library wiring)
- **MOD** `pages/7_admin.py` (Tier 28 +1 entry, label v10.70-v10.77)
- **NEW** `CHANGELOG_v10.77.md` (this file)

## Trade finance arc state

| Standard | Engine | Drop | Status |
|---|---|---|---|
| ENH-269 | trade_finance_instruments | v10.70 | active |
| ENH-273 | trade_finance_limits | v10.71 | active |
| ENH-272 | trade_finance_swift | v10.72 | active |
| ENH-274 | trade_finance_compliance | v10.73 | active |
| ENH-275 | trade_finance_accounting | v10.75 | active |
| ENH-280 | trade_finance_reporting | v10.76 | active |
| ENH-278 | trade_finance_sustainability | **v10.77** | **active** |
| ENH-270 | (AI document checking) | v10.78 | next — ML hook contract + reference training script |
| ENH-271 | (corporate trade portal) | v10.79 | queued |
| ENH-276 | (multi-bank connectivity) | v10.79 | queued |
| ENH-279 | (mobile app) | v10.80 closure | scope-resolution note in closure batch |
| (closure) | trade_finance_arc_cockpit | v10.80 | closure batch |

**7 of 12 active.** Three drops to closure. Trade finance becomes the 14th closed arc at v10.80.

## What's next — v10.78 dual batch

ENH-270 AI-Powered Document Checking + reference training script. ENH-270 is where the v10.76 ML hook contract proves itself in production-realistic conditions. Engine ships with a deterministic UCP 600 rule-based fallback (field-mismatch checks, expiry verification, amount tolerance, party-name consistency); injected ML classifier raises accuracy on the long tail of nuanced discrepancies that rules can't catch — non-conforming presentations where shipping documents technically meet UCP 600 but fail real-world examiner scrutiny.

The training script (`scripts/training/train_document_classifier.py`, ~250 lines target) demonstrates end-to-end pipeline:

1. Data extraction from `cbs_data/` virtual bank instrument descriptions
2. Feature engineering (UCP 600 field expectations, anomaly indicators)
3. Train/test split with stratification, deterministic seed
4. Model training (sklearn baseline, swappable)
5. Evaluation against held-out scenario library cases (ENH-274 SCR-* + new DOC-* scenarios)
6. Model artifact persistence with metadata JSON (training date, data hash, evaluation metrics, version)

The script ships as a reference implementation. The model it produces is acknowledged as synthetic-trained; `ml_disabled` continues to surface that fact in every production prediction. The selling point to Ecobank shifts from "we have ML accuracy 92-95%" to "we have a documented, reproducible training pipeline; here is the script that trains the document classifier; when you provide labeled discrepancy data we retrain on your distribution."
