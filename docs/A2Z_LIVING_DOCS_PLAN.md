# A2Z MIS 360 — Living Documentation & Sales Enablement System

> **Status**: Planning document — to be implemented as a v8.11+ batch sequence
> **Audience**: Future engineers + sales engineers + the engineer reviewing the next campaign
> **Companion to**: `docs/A2Z_SYSTEMS_CHARTER.md`, `docs/A2Z_V7_RETROSPECTIVE.md`, `docs/A2Z_V8_RETROSPECTIVE.md`
> **Discipline**: Per Charter §6 (every claim traceable) + the 36-batch honest-acknowledgement convention

---

## Foreword — Why this matters for A2Z specifically

Most banking platforms have a documentation problem: the slide decks the sales team uses describe one product; the codebase implements another. The drift compounds. Six months in, no one trusts either source.

A2Z does not have that problem yet — and the Living Documentation System is the discipline that prevents it from developing.

We have already built the hard part: a structured content layer that mirrors the codebase reality. `utils/system_stocks.py` declares 6 stocks with status and data_source. `utils/system_flows.py` declares 15 loops with pattern + status + notes. `utils/system_invariants.py` declares hard constraints. `data/kpi_library.json` declares 35 KPIs across 4 BSC pillars. `scripts/audit.py` reports 109 gates. `docs/A2Z_SYSTEMS_CHARTER.md` describes the architecture in 14 sections. Two retrospectives capture the v7.x + v8.x arcs. Thirty-two CHANGELOG files narrate every batch.

**The Living Documentation System does not invent content. It renders what already exists in machine-checkable form.**

This means three things, in order of strategic importance:

1. **Sales claims are audit-locked.** A magazine that says "15 of 15 feedback loops are wired" must fail the build if `system_flows.py` reports anything else. The same gates that prove engineering integrity prove marketing accuracy.

2. **The 36-batch clean streak becomes the proof point.** Our credibility is not "we promise"; it is "we have shipped 36 consecutive batches clean on first try, every batch landed 100% audit pass, here is the audit script — run it." Documentation rendered from that audit becomes self-verifying.

3. **Honest acknowledgements migrate from CHANGELOG to collateral.** Every batch ends with 12 things we deliberately did not ship. Every retrospective has a "what didn't ship" section. The magazine and brochure inherit this discipline. Sales collateral that never says "this is roadmap, not shipped" is the kind banks have learned to mistrust.

The original draft of this plan was excellent in structure but generic in voice — it could have been written for any platform. This enriched version aligns it with the campaign discipline that built A2Z in the first place.

---

## Part 0 — Architectural Mapping (where this fits)

The Living Documentation System adds a new layer to an architecture that already exists. It does not replace anything.

```
┌────────────────────────────────────────────────────────────────────┐
│  EXISTING — built v7.0 → v8.10 (36 batches)                         │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  TIER 1 — Domain engines (116 standards in utils/)                 │
│           Pure deterministic logic. Zero presentation.             │
│                                                                     │
│  TIER 2 — Systems-layer registries                                 │
│           system_stocks.py + system_flows.py +                     │
│           system_invariants.py + composite_scores.py +             │
│           kpi_library.json                                          │
│           This is where claims live.                                │
│                                                                     │
│  TIER 3 — Audit perimeter (scripts/audit.py)                       │
│           109 gates. Single command verifies the platform's        │
│           every cross-cutting invariant. Truth-source.              │
│                                                                     │
│  TIER 4 — Technical-grade documentation                            │
│           A2Z_SYSTEMS_CHARTER.md (288 lines, 14 sections) +        │
│           A2Z_V7_RETROSPECTIVE.md (282 lines) +                    │
│           A2Z_V8_RETROSPECTIVE.md (364 lines) +                    │
│           32 × CHANGELOG_v*.md files                                │
│           Audience: engineers, auditors, future implementers.       │
│                                                                     │
│  TIER 5 — UI surfaces (62 standards rendered today)                │
│           4 dedicated pages + 16 enhanced pages + page 91          │
│           systems-view operator dashboard.                          │
│                                                                     │
├────────────────────────────────────────────────────────────────────┤
│  NEW — Living Documentation System (planned v8.11+)                 │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  TIER 6 — Sales-grade rendering                                    │
│           Generators that READ tiers 1-5 and produce:               │
│           • A2Z_MIS_360_Brochure.pptx (executive)                   │
│           • A2Z_MIS_360_Magazine.pdf (deep-dive, 100+ pages)        │
│           • A2Z_MIS_360_Security_Whitepaper.pdf (CISO)              │
│           • A2Z_MIS_360_Compliance_Pack.pdf (regulator)             │
│           Audience: bank executives, procurement, regulators.       │
│                                                                     │
│  TIER 7 — Audit-locked claim verification                          │
│           New gate G110 (proposed): every numeric claim in          │
│           rendered collateral has a registry citation; build       │
│           fails if any claim cannot be traced.                      │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

**The key insight**: tiers 1-5 already exist. Tier 6 is pure rendering. Tier 7 makes the rendering trustworthy.

---

## Part 1 — Source of Truth (already built — do not duplicate)

### What sales collateral can read FROM, today

| Source file | What it provides | Status |
|---|---|---|
| `utils/system_stocks.py` | 6 system stocks: name, status, data_source, value, unit | ✅ shipped v7.0 |
| `utils/system_flows.py` | 15 feedback loops: from/to context, engine, payload, pattern, status, notes, learning_loop flag | ✅ shipped v7.0 + closed L14 in v8.4 |
| `utils/system_invariants.py` | Hard non-linear constraints: name, formula, threshold, severity | ✅ shipped v7.0 |
| `utils/composite_scores.py` | 4 health composites with definitions | ✅ shipped v7.6 |
| `utils/flexcube_aggregator.py` | ACL contracts: payload schemas for 5 stocks (loans, deposits, NPL, customers, dormant) | ✅ shipped v7.10/v7.11 |
| `data/kpi_library.json` | 35 KPIs across 4 BSC pillars (Financial 40%, Customer 25%, Operational 25%, People 10%) with formulas + targets | ✅ shipped (A2Z Blueprint) |
| `data/staff_register.xlsx` | 487 staff, 35 branches, hierarchy MD → Director → Head → Regional → Branch Manager | ✅ shipped (A2Z Blueprint) |
| `cbs_data/*.json` | 700K customers, 1.2M accounts, 50K transactions (synthetic) + 5 ACL aggregates | ✅ shipped v7.14 + v8.10 |
| `docs/A2Z_SYSTEMS_CHARTER.md` | Architecture ground truth — 14 sections, 288 lines | ✅ shipped v7.0 |
| `docs/A2Z_V7_RETROSPECTIVE.md` | v7.x campaign retrospective — 282 lines | ✅ shipped v7.16 |
| `docs/A2Z_V8_RETROSPECTIVE.md` | v8.x campaign retrospective — 364 lines | ✅ shipped v8.6 |
| `CHANGELOG_v*.md` × 32 files | Per-batch narratives, each with 12 honest acknowledgements | ✅ shipped per batch |
| `scripts/audit.py` | 109 gates including G104-G109 defense-in-depth perimeter | ✅ shipped per batch |

**The Living Doc generators read all 13 sources.** They build no new source of truth.

### What is NOT yet in machine-readable form (and must be added in v8.11)

These are the genuinely new JSON repositories the Living Doc system needs:

```
docs/sales_content/
├── gap_analysis.json           # Market gaps + a2z solutions per module
├── security_architecture.json  # CISO-grade summary (auth, encryption, audit)
├── integrations_roadmap.json   # What's shipped vs what's planned per integration
├── case_studies.json           # Reference deployments + cited external case studies
├── pricing_models.json         # Deployment options + ROI calculator inputs
└── competitive_positioning.json # Honest comparison vs alternatives
```

These six files are the only NEW content. Everything else flows from the existing tier 1-5 sources.

**Critical discipline:** every claim in these six files must include either:
- A registry citation (`source: utils/system_flows.py:L14`) for facts about A2Z, OR
- A public citation (`source_url: ...`) for external case studies, with `verification_date` and `relationship: cited|partner|reference`

Claims without citations get rejected by G110 (proposed).

---

## Part 2 — The Generation Engine (Tier 6)

### Three generators, one shared rendering core

```
scripts/
├── docgen/
│   ├── __init__.py
│   ├── _registry_loader.py    # Reads tiers 1-5; produces unified content dict
│   ├── _claim_validator.py    # Verifies every claim has a registry citation
│   ├── _theme.py              # Banking theme (blue/gold), professional restraint
│   ├── _honest_section.py     # Auto-generates the "what's not shipped" panel
│   ├── ppt_generator.py       # python-pptx → Brochure.pptx (15 slides)
│   ├── magazine_generator.py  # WeasyPrint → Magazine.pdf (100+ pages)
│   ├── whitepaper_generator.py # WeasyPrint → Security/Compliance .pdf
│   └── _orchestrator.py       # generate_all_docs.py entry point
└── generate_all_docs.py       # CLI wrapper
```

### `_registry_loader.py` — the heart

This is the only module that knows about tier 1-5 file structures. Everything else consumes its output, which is a single dict:

```python
{
  "platform": {
    "version": "v8.10",
    "audit_gates": 109,
    "audit_pass_rate": "100.0%",
    "consecutive_clean_first_try": 36,
    "build_timestamp_iso": "2026-05-01T16:09:00+00:00",
    "audit_command": "python scripts/audit.py",
  },
  "stocks": [ ... 6 entries from system_stocks.py ... ],
  "loops": [ ... 15 entries from system_flows.py ... ],
  "invariants": [ ... entries from system_invariants.py ... ],
  "composites": [ ... 4 entries from composite_scores.py ... ],
  "kpi_library": { ... 35 KPIs from kpi_library.json ... },
  "branches": 35,
  "staff": 487,
  "customers_simulated": 700_000,
  "accounts_simulated": 1_200_000,
  "engines_count": 116,
  "loops_wired_pct": 100.0,
  "stocks_wired_pct": 100.0,
  "stocks_acl_wired": 5,
  "ifrs_compliance": ["IFRS 9", "IFRS 7", "IFRS 16", "IFRS 15"],  # from engine registry
  "regulatory": ["CBK Operations Resilience Guidelines", "CBK Prudential Guidelines",
                 "Data Protection Act 2019", "Basel III"],  # from charter §11
  "retrospectives": [ ... v7 + v8 doc paths ... ],
  "changelogs": [ ... per-batch markdown paths ... ],
  "honest_acknowledgements": [
    # Aggregated from all CHANGELOGs — what's deferred + why
    ...
  ],
}
```

If this dict cannot be assembled (e.g. a registry is missing a field), the loader **raises** rather than falling back to defaults. We will not silently render stale or guessed numbers.

### `_claim_validator.py` — the audit-lock

Every numeric or factual claim in the rendered output passes through this validator. The pattern matches our existing G108/G109 introspection style:

```python
class Claim:
    text: str            # "15 of 15 feedback loops wired (100%)"
    numeric_value: any   # 15
    registry_path: str   # "loops_wired_pct"
    source_file: str     # "utils/system_flows.py"

def validate(claim: Claim, registry_dict: dict) -> bool:
    actual = _resolve_path(registry_dict, claim.registry_path)
    return actual == claim.numeric_value
```

**If validation fails, generation aborts.** The collateral is never written. Sales gets a clean error: "Brochure.pptx claims X but registry says Y; rebuild after reconciling."

This is the same discipline as our 109 audit gates: collateral is just code, and code that lies about reality fails the build.

---

## Part 3 — The Generation Discipline (the spirit, captured)

These are the rules every generator must obey. They are the campaign discipline applied to documentation.

### 1. No invented numbers

Every number in the magazine, brochure, or whitepaper is either:
- Read from the registry dict (preferred), or
- Cited from an external source with URL + verification date

There are no "industry-standard" numbers without a footnote. There are no "typical bank" benchmarks without a source.

### 2. Roadmap items are clearly marked

Every feature mentioned belongs to one of three buckets, visually distinguished:

| Marker | Meaning | Example |
|---|---|---|
| ✅ **Shipped** | In the codebase, audit-verified, version-stamped | "FLEXCUBE ACL with 5 stocks (v7.10/v7.11)" |
| 🟡 **Designed** | In the charter; engine specified; not yet wired | (none in v8.10 — all engines now wired) |
| ⏳ **Roadmap** | Not yet designed; planned for future | "Multi-process state via Redis (v9.x)" |

The brochure cannot show a 🟡 or ⏳ item without the marker. Section "Honest scope" appears at the end of every spread.

### 3. The Honest Acknowledgements section is mandatory

Every piece of collateral ends with a section titled "What this document does not claim." It enumerates:
- Features mentioned that are roadmap (not shipped)
- Numbers that are projections (not measured)
- Integrations that are designed (not yet integrated)
- Audits that are planned (not yet completed)

This is the same pattern as the 12-item acknowledgements section at the end of each CHANGELOG. Sales collateral inherits the discipline.

### 4. Claims trace to registries; cited sources trace to URLs

| Claim type | Required citation |
|---|---|
| "We have X stocks/loops/gates" | Path in registry dict |
| "We comply with CBK X" | Charter §N + the specific guideline document |
| "Bank Z achieved Y%" | Public URL + verification date + relationship qualifier |
| "Industry average is Z" | Citation: research firm, report year, methodology footnote |

### 5. Canonical references are consistent

Every piece of collateral cites the same five sources we cite in our retrospectives:
- Donella Meadows, *Thinking in Systems* (2008) — for systems-layer claims
- Eric Evans, *Domain-Driven Design* (2003) — for ACL + bounded context claims
- Michael Nygard, *Release It!* (2007) — for circuit breaker + resilience claims
- Sam Newman, *Building Microservices* (2015) — for observability claims
- CBK Operations Resilience Guidelines (2019) — for regulatory alignment

Sales collateral that names patterns matches the technical literature that defines them.

### 6. Build-time honesty over runtime polish

A claim that cannot be traced fails the build. A diagram that cannot be sourced fails the build. A logo of a bank that has not signed a reference agreement does not appear.

This is slower than the alternative. It is what makes the result trustworthy.

---

## Part 4 — The Outputs (Tier 6)

### `A2Z_MIS_360_Brochure.pptx` — Executive (15 slides)

Audience: bank CEO, COO, CIO, head of strategy. Reading time: 12 minutes.

| Slide | Title | Source registry path |
|---|---|---|
| 1 | A2Z MIS 360: Banking Management Intelligence | `platform.version` |
| 2 | The Strategy-Execution Gap | gap_analysis.json |
| 3 | The Architecture (5-tier) | charter §3 |
| 4 | Module Map (visual of 116 standards by domain) | engine_registry |
| 5 | Systems Layer: 6 stocks, 15 loops, 4 composites | `stocks` + `loops` + `composites` |
| 6 | The FLEXCUBE Anti-Corruption Layer | charter §7 |
| 7 | Resilience: retry + circuit + jitter + telemetry | flexcube_adapter constants |
| 8 | Observability Triangle (mode + circuit + latency) | get_circuit_state, get_latency_state |
| 9 | The 6-Gate Audit Perimeter | scripts/audit.py |
| 10 | Compliance: CBK + DPA + IFRS + Basel | charter §11 |
| 11 | Implementation Approach (phased, audit-locked) | A2Z_V7 + V8 retrospectives |
| 12 | Reference Deployments | case_studies.json (cited) |
| 13 | What This Platform Does Not Yet Do (honest) | aggregated honest_acknowledgements |
| 14 | Verification: Run the audit yourself | `platform.audit_command` |
| 15 | Next Steps | pricing_models.json |

**Slide 13 is mandatory and never removed.** It is what makes the deck trustworthy.

### `A2Z_MIS_360_Magazine.pdf` — Comprehensive (~100 pages)

Audience: implementation teams, evaluation committees, regulators. Read time: half-day.

Structure follows the original draft's 17-part outline, with these enrichments:

- **Foreword**: written from the perspective of an engineer honest about both shipped capabilities and current limits — not a CEO testimonial. Models the rest.
- **Every module spread (PART 3)**: includes a "Verification" footnote citing the registry path + the audit gate that locks it. (See Part 5 below for the enriched template.)
- **PART 17 Customer Success**: only includes deployments with signed reference agreements. External case studies (Zanifu, C2FO) appear in a clearly-labelled "Cited industry research" section, not as A2Z customers.
- **PART 18 (NEW) — Honest Scope**: aggregates every "what didn't ship" section from the 32 CHANGELOGs and 2 retrospectives. This is unusual for sales collateral. It is what differentiates A2Z.
- **Appendices**: the 116 engines + 35 KPIs + the audit gate registry + the canonical reference list.

### `A2Z_MIS_360_Security_Whitepaper.pdf` — CISO

Reads from `security_architecture.json`. Distinguishes:
- ✅ Implemented: thread-safe locking, atomic writes, audit-trail dicts, OAuth2 token refresh, CBK Resilience-aligned retry
- 🟡 Designed: HSM integration, SAML/OIDC SSO
- ⏳ Roadmap: SOC 2 Type II, ISO 27001 certification, Redis-backed multi-process state

The CISO sees what is shipped vs planned — they do not need to ask.

### `A2Z_MIS_360_Compliance_Pack.pdf` — Regulator

Maps each shipped engine to its regulatory driver:
- Capital adequacy → Basel III + CBK Prudential
- IFRS 9 staging → IFRS 9 + CBK Loan Classification
- KYC/AML risk scoring → AMLCFT Act + CBK guidelines
- FLEXCUBE resilience → CBK Operations Resilience Guidelines (2019)
- Data Protection Act compliance → DPA 2019

Includes the audit gate references for each (e.g. "Loop round-trip-testability locked by G106 since v7.15").

---

## Part 5 — The Module Spread Template (enriched)

Each module gets a two-page spread. The original template is good; the enrichment adds the **Verification** and **Honest Scope** panels.

### Left page (Pain + Gap + Market Impact) — original template, unchanged

### Right page (Solution + Features + Differentiator + ROI + **Verification** + **Honest Scope**)

```
┌─────────────────────────────────────────────────────────────────┐
│  MODULE: Balanced Scorecard & Performance (continued)           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  THE A2Z SOLUTION                                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Real-time BSC scoring with auto-cascade from MD to teller, ││
│  │  surfaced via 35-KPI library aligned to 4 BSC pillars       ││
│  │  (Financial 40%, Customer 25%, Operational 25%, People 10%)││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  KEY FEATURES (✅ all shipped)                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  • Central BSC engine (utils/profitability_integration.py) ││
│  │  • 35 KPI definitions (data/kpi_library.json)              ││
│  │  • Cascade engine with role-aware weight propagation       ││
│  │  • Auto-target rollup from RM/branch/regional/director     ││
│  │  • CBS-synthetic actuals tier (cbs_synthetic in v7.14+)    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  THE DIFFERENTIATOR                                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  KPIs are not just measured — they are LINKED to system    ││
│  │  stocks via L02 (Customer profitability → Profitability    ││
│  │  integration), so individual performance flows into bank-  ││
│  │  level financial composites.                                ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  VERIFICATION (audit-locked)                                    │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  • Engine registered in invariants registry — locked by    ││
│  │    G105 (strict invariant registry usage)                  ││
│  │  • Loop L02 round-trip-testable — locked by G106            ││
│  │  • Run `python scripts/audit.py` to verify both gates pass ││
│  │    in the version you receive                               ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  HONEST SCOPE                                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  ⏳ Behavioral nudges + AI coaching scripts: planned for    ││
│  │    v9.x; not shipped. The BSC engine + cascade + KPI       ││
│  │    library are shipped.                                     ││
│  │  ⏳ Real-time mobile alerts on KPI drift: not yet wired.    ││
│  │    The polling-based dashboard is the current surface.      ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

The two new panels are non-negotiable. They are what turns sales collateral into a defensible artifact.

---

## Part 6 — The Reconciled Numbers

This is the table the AI prompt MUST use as ground truth. Numbers from the registry, audit-locked.

| Metric | Value as of v8.10 | Source |
|---|---|---|
| Standards delivered | **116** | engine_registry |
| Standards in UI | **62** | page-level audit |
| Audit gates | **109** | scripts/audit.py |
| Defense-in-depth perimeter gates | **6** (G104-G109) | scripts/audit.py |
| System stocks | **6** | utils/system_stocks.py |
| Stocks WIRED | **6 / 6 (100%)** | utils/system_stocks.py |
| Stocks ACL-wired | **5 / 6** | utils/flexcube_aggregator.py |
| Feedback loops | **15** | utils/system_flows.py |
| Loops WIRED | **15 / 15 (100%)** | utils/system_flows.py |
| Learning loops (Meadows' highest-value type) | **3** (L01, L02, L08) | utils/system_flows.py |
| Health composites | **4** | utils/composite_scores.py |
| Engines reading from invariants registry | **6** | utils/system_invariants.py |
| KPI library entries | **35** across 4 BSC pillars | data/kpi_library.json |
| Branches in simulation | **35** | data/staff_register.xlsx |
| Staff in simulation | **487** | data/staff_register.xlsx |
| Customers in CBS sim | **700,000** | cbs_data/customers.json |
| Accounts in CBS sim | **1,197,425** | cbs_data/accounts.json |
| Transactions in CBS sim | **50,000** | cbs_data/transactions.json |
| Live FLEXCUBE handlers | **5** (loans, deposits, NPL, customers, dormant) | utils/flexcube_adapter.py |
| Resilience layers | **4** (retry + jitter + circuit breaker + latency telemetry) | utils/flexcube_adapter.py |
| Observability surfaces | **3** (mode + circuit + latency) | pages/91_systems_view.py |
| Documentation tiers | **3** (CHANGELOGs + charter + 2 retrospectives) | docs/ + CHANGELOG_*.md |
| Per-batch CHANGELOGs | **32** | repository root |
| Consecutive clean-first-try | **36** | scripts/audit.py + commit history |
| Spec deviations (cumulative) | **9** documented | retrospectives |
| Rule 7 applications | **6** | retrospectives |

The 468-standards number from the original draft does NOT reconcile and must not appear in collateral. Where the original wrote "468 standards", the rendered output reads **"116 standards delivered (registered in `utils/`); 32 batches documented; 109 audit gates"**.

---

## Part 7 — Implementation Plan (as campaign batches)

The Living Doc system follows our canonical 2-batch + UI surface pattern. Three batches:

### v8.11 — Build the registry loader + claim validator

**Engine batch.** Closes the foundation.

Deliverables:
- `scripts/docgen/_registry_loader.py` (~300 lines) — produces the unified content dict from tiers 1-5
- `scripts/docgen/_claim_validator.py` (~150 lines) — validates claims against the dict
- 6 new sales-content JSON files in `docs/sales_content/`:
  - `gap_analysis.json`, `security_architecture.json`, `integrations_roadmap.json`, `case_studies.json`, `pricing_models.json`, `competitive_positioning.json`
- Smoke test verifying the loader assembles the dict and the validator catches drifted claims

Audit: 109 gates retained.

### v8.12 — Build the three generators (PPT, Magazine, Whitepaper)

**Engine batch.** Closes the rendering layer.

Deliverables:
- `scripts/docgen/ppt_generator.py` (~400 lines) — python-pptx renderer for the 15-slide brochure
- `scripts/docgen/magazine_generator.py` (~600 lines) — WeasyPrint renderer for the 100-page magazine
- `scripts/docgen/whitepaper_generator.py` (~250 lines) — WeasyPrint for security + compliance variants
- `scripts/docgen/_theme.py`, `_honest_section.py` — shared rendering primitives
- `scripts/generate_all_docs.py` CLI entry point
- Generated artifacts: `A2Z_MIS_360_Brochure.pptx`, `A2Z_MIS_360_Magazine.pdf`, `A2Z_MIS_360_Security_Whitepaper.pdf`, `A2Z_MIS_360_Compliance_Pack.pdf`

Audit: 109 gates retained. `scripts/docgen/` and `scripts/generate_all_docs.py` added to FOUNDATIONAL allowlist (they read JSON files, like `scripts/etl_flexcube.py` and `scripts/generate_cbs_aggregates.py`).

### v8.13 — Surface the docgen on admin/systems-view

**UI batch.** Closes the canonical 2-batch + UI surface sequence.

Deliverables:
- Admin page section: "Living Documentation" with 4 buttons (Generate Brochure / Generate Magazine / Generate Security Whitepaper / Generate Compliance Pack)
- Each button calls the corresponding generator and provides a download link
- Status panel showing last-generated timestamps + which version of the platform produced them
- Audit-claim diff view: if generation aborts due to a claim mismatch, show which claim failed and which registry value it disagreed with

Audit: 109 gates retained.

### v8.14 (proposed) — Add G110 audit gate

**Audit-hardening batch.** Locks the discipline.

Deliverables:
- `gate_collateral_claims_traceable()` — verifies every claim in `docs/sales_content/*.json` has a `source` field that resolves to a real file or registry path
- 109 → **110 audit gates**
- The Living Doc system now refuses to render collateral that contains untraceable claims, AND the audit refuses to pass if any sales-content file declares a claim without a citation

This completes the canonical pattern: build engine (v8.11) + close UI (v8.13) + lock as invariant (v8.14). Three batches plus one optional hardening = 4 in total.

### Why three batches not one

The campaign discipline says: single-purpose batches. v8.11 is "the loader is correct + the validator catches drift." v8.12 is "the three generators render correctly from the loader's output." v8.13 is "operators can trigger generation and see drift errors clearly." Each is independently auditable. Each is a clean-first-try candidate.

If we did all three in one batch and something broke, the post-mortem would be ambiguous about which sub-system failed. Three batches preserve the clean-streak signal.

---

## Part 8 — How this extends the audit perimeter

The 6-gate defense-in-depth perimeter (G104-G109) locks the engineering architecture. v8.14's proposed G110 extends it to documentation:

| Gate | Locks |
|---|---|
| G104 | Engine migration ratchet |
| G105 | Strict invariant registry usage |
| G106 | Loop round-trip-testability |
| G107 | Stock data_source provenance |
| G108 | FLEXCUBE resilience + observability |
| G109 | PUBLISHED_LANGUAGE payload_version |
| **G110** (proposed v8.14) | **Collateral claims traceable to registries** |

After v8.14, the Living Doc system inherits the campaign's quality discipline. Marketing is no longer an honor system; it is an audit gate.

---

## Part 9 — Spirit statements (the philosophical foundation)

These are the principles every contributor to the Living Doc system signs onto. They are the campaign discipline written in plain language.

1. **We do not invent numbers.** Every number traces to a registry or a citation. If it cannot be sourced, it is removed.

2. **We mark what is shipped vs what is planned.** The reader always knows which is which. This is harder to write and easier to trust.

3. **We end every artifact with what it does not claim.** The Honest Scope section is mandatory, never edited out, never minimised.

4. **The same audit script that proves the code works proves the marketing is true.** `python scripts/audit.py` must pass before any collateral is rendered. This is not a wish; it is a build gate.

5. **The 36-batch clean streak is the proof point — not a claim.** Anyone can run the audit. Anyone can read the CHANGELOGs. The discipline is reproducible by inspection. Sales collateral that says "production-grade" hands the buyer the audit script and lets them verify.

6. **Honest acknowledgements compound.** Every CHANGELOG ends with 12 things we did not ship. Every retrospective has a "what didn't ship" section. The Living Doc system inherits this. After fifty deals, prospects will know A2Z by its honest scope statements as much as by its features.

7. **We cite what we built on.** Meadows + Evans + Nygard + Newman + CBK appear in every retrospective and every whitepaper. Sales collateral that does not credit its intellectual lineage is harder to trust.

8. **Reference customers must agree to be referenced.** A bank logo appears only with a signed reference agreement. External case studies (Zanifu, C2FO, etc.) appear only as "cited industry research", not as A2Z deployments.

9. **The platform's truth-source is `scripts/audit.py`.** Not the brochure. Not the magazine. Not anyone's slide deck. If a claim diverges from the audit, the claim is wrong.

10. **Build the thing that fails the build when it lies.** This is the meta-discipline. Every sub-system in A2Z fails its build if it lies about reality. The Living Doc system extends this to documentation.

---

## Part 10 — References

### Internal — the campaign canon

| Document | Lines | Date | Audience |
|---|---|---|---|
| `docs/A2Z_SYSTEMS_CHARTER.md` | 288 | v7.0 | architecture truth |
| `docs/A2Z_V7_RETROSPECTIVE.md` | 282 | v7.16 | v7.x campaign narrative |
| `docs/A2Z_V8_RETROSPECTIVE.md` | 364 | v8.6 | v8.x campaign narrative |
| `CHANGELOG_v5.71.md` through `CHANGELOG_v8.10.md` | varies | per batch | per-batch detail |
| `Master_Prompt_v3.md` | varies | continuously | self-extending campaign log |
| `scripts/audit.py` | ~12,800 | continuously | the truth-source |

### External — the canonical references

- Donella Meadows, *Thinking in Systems: A Primer* (2008) — the systems-layer foundation; "a system is its feedback loops"
- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software* (2003) — Anti-Corruption Layer, Published Language, Bounded Context patterns
- Michael Nygard, *Release It! Design and Deploy Production-Ready Software* (2007) — circuit breaker, bulkhead, retry-with-backoff patterns
- Sam Newman, *Building Microservices: Designing Fine-Grained Systems* (2015, 2nd ed. 2021) — the observability triangle; integration testing
- Central Bank of Kenya, *Operations Resilience Guidelines for Banks* (2019) — the regulatory frame for retry + circuit breaker tunings
- IFRS Foundation, *IFRS 9 Financial Instruments*, *IFRS 7*, *IFRS 16*, *IFRS 15* — accounting compliance
- Basel Committee, *Basel III Final Reform Package* (2017, in force 2023+) — capital adequacy

### What this document deliberately does not cite

- "Industry analyst" research firms (Gartner, Forrester) — without signed access agreements, claims cannot be verified
- Specific benchmark percentages from unsigned reference deployments
- Vendor certifications not yet awarded (SOC 2, ISO 27001 — these go in the roadmap section, not the cover page)
- Numbers from the original sales-pitch draft that did not reconcile to the registry

---

## Closing

The original draft was a generic sales-enablement playbook — competent and useful. This enriched plan transforms it into something more specific: a documentation discipline that mirrors the engineering discipline that built the platform.

Every other banking platform has a documentation problem: the deck describes one product, the codebase implements another, and the drift compounds until trust collapses. We have a chance to ship documentation that cannot drift, because the build fails when it does.

That is the spirit. The 36-batch clean streak is the foundation. The audit script is the proof.

When we proceed to v8.11, we are not building marketing. We are extending the audit perimeter to cover the last unaudited surface in the campaign.

---

*Planning document — to be implemented as v8.11 (registry loader + claim validator) → v8.12 (three generators) → v8.13 (admin/systems-view surface) → v8.14 (G110 audit gate). Companion to `docs/A2Z_SYSTEMS_CHARTER.md`, `docs/A2Z_V7_RETROSPECTIVE.md`, `docs/A2Z_V8_RETROSPECTIVE.md`. References Meadows + Evans + Nygard + Newman + CBK. The campaign that built the platform now builds the discipline that documents it.*
