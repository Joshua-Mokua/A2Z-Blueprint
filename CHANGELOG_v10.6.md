# CHANGELOG v10.6 — Phase 2 batch 1: Climate/ESG Core Intelligence Engine

**Audit:** 119/119 PASS — **90th consecutive clean.**

## Phase 2 begins

Phase 1 (v10.2–v10.5) registered 246 standards across 20 modules. Phase 2 begins
deep implementation. Per strategic plan §"Post-Phase-1 outlook," the first
arc is **Climate/ESG (v10.6–v10.10)**, prioritized for the **IFRS S1/S2
mandatory disclosure deadline of January 2027**.

## What ships in v10.6

`utils/esg_intelligence.py` — 1,164 lines, the core ESG intelligence engine
that 5 of the 13 Climate/ESG standards now run on:

| Standard | Name | Implemented as |
|---|---|---|
| ENH-CLI-01 | IFRS S1 General Sustainability Disclosures | `IFRSS1Disclosure`, `assess_ifrs_s1_compliance()`, 9 topic categories × 4 core content areas |
| ENH-CLI-02 | IFRS S2 Climate-Related Disclosures | `IFRSS2Disclosure`, `assess_ifrs_s2_compliance()`, 21 mandatory disclosures + Year-1 Scope-3 transition relief |
| ENH-CLI-08 | Scope 1/2/3 Emissions Tracking (portfolio attribution) | `PortfolioEmissionsRecord`, `compute_portfolio_emissions()`, GHG Protocol + PCAF Cat 15 financed emissions |
| ENH-CLI-09 | Green Asset Classification & Tagging | `GreenAssetClassification`, `classify_green_asset()`, KGFT 8 categories × 4 alignment levels × 6 eligibility dimensions + DNSH |
| ENH-CLI-11 | Climate Governance (Board Oversight + Roles) | `ClimateGovernanceAssessment`, `validate_climate_governance()`, IFRS S2 §6-§7 + CBK CRMF Pillar 1 |

## Engine architecture

```
ESGIntelligenceEngine (orchestrator)
├── add_ifrs_s1(IFRSS1Disclosure) ────────────────► assess_ifrs_s1_compliance()
├── add_ifrs_s2(IFRSS2Disclosure) ────────────────► assess_ifrs_s2_compliance()
├── add_green_asset(GreenAssetClassification) ───► green_book_share_pct()
├── add_emissions(PortfolioEmissionsRecord) ─────► (computed on add)
├── add_governance(ClimateGovernanceAssessment) ─► validate_climate_governance()
│
├── assess_all_frameworks() — full multi-framework compliance pass
└── board_summary() — one-pager view (IFRS S2 readiness status, green book share, governance compliance, deadline)
```

## Frameworks supported (`ESGFramework` enum)

- **IFRS S1** — General Sustainability Disclosures (June 2023)
- **IFRS S2** — Climate-related Disclosures (June 2023)
- **TCFD** — delegates to existing `utils/esg_reporting.py`
- **KGFT_CBK** — Kenya Green Finance Taxonomy (CBK April 2025)
- **CRDF_CBK** — Climate Risk Disclosure Framework (CBK April 2025)
- **CBK_CRMF** — CBK Climate Risk Management Framework (April 2021)

## Constants registered

| Constant | Count | Source |
|---|---|---|
| `IFRS_S1_TOPIC_CATEGORIES` | 9 | IFRS S1 §B5-§B7 |
| `IFRS_S1_CORE_CONTENT_AREAS` | 4 | IFRS S1 §27-§51 |
| `IFRS_S2_DISCLOSURES` | 21 | IFRS S2 §6-§37 |
| `KGFT_GREEN_CATEGORIES` | 8 | CBK KGFT April 2025 |
| `KGFT_ELIGIBILITY_DIMENSIONS` | 6 | CBK KGFT April 2025 |
| `KGFT_ALIGNMENT_LEVELS` | 4 | CBK KGFT April 2025 |
| `CLIMATE_GOVERNANCE_REQUIRED_ROLES` | 5 | IFRS S2 §6-§7 + CBK CRMF |
| `CLIMATE_GOVERNANCE_REQUIRED_PRACTICES` | 6 | IFRS S2 §6-§7 + CBK CRMF |

## Key features

- **Decimal-pure** throughout — 28-digit precision for tCO2e calculations
- **Honesty Rule 1 enforced** — `total_tco2e()` returns `None` if any scope missing (cannot infer)
- **DNSH (Do No Significant Harm)** — required for KGFT ALIGNED status; not optional
- **Year-1 Scope-3 transition relief** — IFRS S2 §B58 supported via `scope_3_required=False`
- **Materiality-aware** — `assess_ifrs_s1_compliance(required_topics=...)` honors materiality assessments
- **Deadline-aware** — engine surfaces `IFRS_S1_S2_MANDATORY_DEADLINE = "2027-01-01"` on every assessment
- **Board readiness status** — `board_summary()` returns `READY` / `ON_TRACK` / `AT_RISK` / `URGENT_ACTION_REQUIRED`

## Tests added (21 new integration tests)

`tests/integration/test_v10_6_esg_intelligence.py`:

- 7 classes covering: imports, self-test passing, registry alignment, KGFT classification, scope emissions, IFRS compliance, governance, engine orchestration, deadline awareness
- Plus 30 module-level self-tests (run on `python -m utils.esg_intelligence`)

## Verified output

```
✓ esg_intelligence self-test passed (30 tests)

Ran 21 tests in 0.049s
OK

Full integration suite: 99 tests, all pass
Audit: 119/119 gates PASS
```

## Standards registry update

5 Climate/ESG standards switched from `status='planned'` → `status='active'`:

```
Climate/ESG active: 5 (ENH-CLI-01, 02, 08, 09, 11)
Climate/ESG still planned: 8 (ENH-CLI-03, 04, 05, 06, 07, 10, 12, 13) — v10.7-v10.10
```

## Honest acknowledgements

1. **5 of 13 implemented**, not all 13. ENH-CLI-03 (KGFT report generation), ENH-CLI-04 (CRDF reporting), ENH-CLI-05/06 (physical/transition risk modeling), ENH-CLI-07 (climate scenario stress testing), ENH-CLI-10 (TNFD biodiversity), ENH-CLI-12 (climate-adjusted ECL), ENH-CLI-13 (greenwashing controls) remain `planned` for v10.7–v10.10.
2. **No persistence layer yet** — engine is in-memory. Persistence integrates with v8.x Postgres infrastructure in v10.7+ as needed.
3. **No UI surface yet** — Streamlit page lives in v10.9 per the 5-batch arc plan.
4. **No audit gate locking these 5 standards yet** — G120 gates the full Climate/ESG arc when v10.10 closes. Until then, the standards-registry `status='active'` flag and integration tests are the assurance mechanism.
5. **Existing `utils/esg_reporting.py` (TCFD foundation) preserved unchanged.** v10.6 engine imports its constants where helpful (graceful import fallback if missing).
6. **Materiality assessment is the user's responsibility** — engine accepts `required_topics` parameter for IFRS S1 but does not itself perform materiality assessment.
7. **PCAF financed emissions methodology mentioned in metadata only** — full PCAF computation (loan book × sector emission intensity) is part of ENH-CLI-12 climate-adjusted ECL work in v10.8.

## What v10.7 ships next

**Climate Risk Modeling** — physical risk (acute + chronic) and transition risk (policy + technology + market + reputation), plus TNFD biodiversity:

- ENH-CLI-05: Physical climate risk modeling (`assess_physical_risk()`)
- ENH-CLI-06: Transition climate risk modeling (`assess_transition_risk()`)
- ENH-CLI-10: Biodiversity & Nature-Related Risks (TNFD framework)

Will plug into the v10.6 engine via composition. Risk-adjusted scenario data flows into v10.8 climate-adjusted ECL.

## Phase 2 progress

| Arc | Standards | Cumulative active |
|---|---|---|
| **v10.6 ✅** | **Climate/ESG core (5 standards)** | **5/246 active** |
| v10.7 (next) | Climate risk modeling (3 standards) | 8/246 |
| v10.8 | Climate-adjusted ECL + scenarios (2 standards) | 10/246 |
| v10.9 | UI + KGFT/CRDF reporting (3 standards) | 13/246 |
| v10.10 | Audit gate G120 + arc closure | 13/246 (locked) |
| v10.11+ | Phase 2 batch 2: Credit deep impl | … |
