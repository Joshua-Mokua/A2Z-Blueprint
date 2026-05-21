# CHANGELOG v10.161 — ENH-192 PEP & Sanctions Screening Orchestrator

**Status:** Second standard of the AML/Compliance cluster (ENH-190..199, 9 total). Per the standing rule, one standard per ZIP. AML/Compliance progress: 2/9 standards active.

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged — engine-level work, no new gates). G142 anti-drift floor 77→78. Active standards 179→180. v10.161 tests 22/22 pass.

---

## Honest scoping — third time the inspect-first discipline pays off

Pre-build inspection found that BOTH components ENH-192 calls for already exist as live, active code:

1. **`utils/sanctions_screening.py`** for Standard #58 (Sanctions Screening Engine) — OFAC/UN/EU/UK/CBK lists, Levenshtein fuzzy matching with thresholds (60/75/90/100), NEW_HIT/UNDER_REVIEW/CLEARED_FALSE/CONFIRMED_TRUE workflow with Rule 4 honesty (NEW_HIT cannot be auto-cleared)
2. **`utils/kyc_aml_risk.py`** has PEP handling — PEP_FOREIGN +20 pts, PEP_DOMESTIC +15 pts in the customer-type bucket of the risk scorecard

Initial framing might have been "build a PEP/sanctions engine" — that would be **duplicating active capability**. Same lesson the v10.160 ENH-191 inspection caught. Same lesson the v10.159 vocabulary endpoint caught. The pattern is now established: **inspect existing engines first; build orchestration around them, not duplicates of them.**

**The honest scope: ENH-192 is the orchestration layer.** It:

1. Composes Standard #58's sanctions screening + kyc_aml_risk's PEP logic
2. Wires ENH-191's `CustomerApplicant` / `BusinessApplicant` types into screening
3. Adds list freshness tracking that Standard #58 doesn't expose (per-source last refresh + window + status)
4. Returns a single `UnifiedScreeningResult` that downstream AML standards (ENH-193 transaction monitoring, ENH-194 SAR/STR filing) consume

Same compose-don't-duplicate pattern as ENH-191's relationship to ENH-121 + Standard #57.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/screening_orchestrator.py` | ~520 | NEW. Orchestration engine + 4 enums + 4 dataclasses |
| `utils/standards_registry.py` | 1 line | MODIFIED. ENH-192 status='planned'→'active', affected_engines=('screening_orchestrator',) |
| `tests/test_screening_orchestrator_v10_161.py` | ~340 | NEW. 22 tests across 9 classes |
| `docs/Master_Prompt_v3.54.md` | ~1100 | Anti-drift sync v3.53 → v3.54 |
| `SCOPE_LEDGER.md` | updated | v10.161 row + status block |
| `CHANGELOG_v10.161.md` | this file | This document |

---

## Engine surface

### 4 controlled-vocabulary enums

| Enum | Values | Notes |
|---|---|---|
| `SanctionsListSource` | OFAC_SDN, UN_CONSOLIDATED, EU_CONSOLIDATED, UK_HMT, CBK_DOMESTIC | Maps to Standard #58's SUPPORTED_SANCTIONS_LISTS but as proper enum |
| `ListFreshnessStatus` | FRESH, STALE, MISSING, MANUAL_LOAD | Operator sees which lists are usable BEFORE regulatory exam |
| `PepCategory` | NOT_PEP, DOMESTIC_PEP, FOREIGN_PEP, INTERNATIONAL_ORGANIZATION_PEP | FATF Rec 12 verbatim |
| `ScreeningOutcome` | CLEAR, PEP_REVIEW_REQUIRED, SANCTIONS_HIT_REQUIRES_REVIEW, SANCTIONS_CONFIRMED_BLOCK, SCREENING_DEFERRED_LISTS_STALE | Final disposition for screen() |

### 4 frozen dataclasses

```python
@dataclass(frozen=True)
class ListFreshnessRecord:
    source: SanctionsListSource
    last_refreshed_utc: Optional[str]
    n_records_loaded: int
    load_method: str           # "manual" | "automated_feed" | "api_pull"
    status: ListFreshnessStatus
    notes: str = ""

@dataclass(frozen=True)
class PepScreeningResult:
    is_pep: bool
    category: PepCategory
    reason: str = ""

@dataclass(frozen=True)
class SanctionsHitSummary:    # Compact view; full hit stays in Std #58
    source: SanctionsListSource
    matched_entity_name: str
    matched_record_id: str
    match_score: int
    hit_status: str           # NEW_HIT, UNDER_REVIEW, CLEARED_FALSE, CONFIRMED_TRUE
    screening_id: int

@dataclass(frozen=True)
class UnifiedScreeningResult:
    subject_id: str
    subject_name: str
    subject_kind: str         # "INDIVIDUAL" | "BUSINESS" | "BENEFICIAL_OWNER"
    pep_result: PepScreeningResult
    sanctions_hits: Tuple[SanctionsHitSummary, ...]
    outcome: ScreeningOutcome
    lists_screened: Tuple[SanctionsListSource, ...]
    lists_skipped_due_to_staleness: Tuple[SanctionsListSource, ...]
    screened_at_utc: str
    blockers: Tuple[str, ...]
    edd_triggers: Tuple[str, ...]
    meta: Mapping[str, Any]
    
    def to_dict(self) -> Dict[str, Any]: ...     # API serialization
```

### Engine methods

```python
class ScreeningOrchestrator:
    def __init__(sanctions_engine=None,
                  freshness_window_days=30,
                  block_when_lists_stale=False)
    
    # Freshness management
    def register_list_load(source, n_records,
                            load_method="manual", notes="")
    def freshness_summary() -> Dict[str, Any]
    
    # Screening
    def screen(subject_id, subject_name, *, is_pep_self_declared,
               nationality, residence_country, occupation,
               subject_kind="INDIVIDUAL") -> UnifiedScreeningResult
    def screen_applicant(applicant) -> Tuple[UnifiedScreeningResult, ...]
        # Accepts ENH-191 CustomerApplicant or BusinessApplicant;
        # for KYB returns (business, *all_BOs) tuple
    
    # Retrieval
    def all_screenings() -> Tuple[UnifiedScreeningResult, ...]
    def board_summary() -> Dict[str, Any]
```

---

## What ENH-192 adds beyond Standard #58

Standard #58 tracks individual sanctions records and screening events. It does **not** track source-level freshness — operators don't know that OFAC was last refreshed 47 days ago, or that the EU list has never been loaded.

ENH-192 adds:

1. **Per-source freshness windows** — defensible defaults from FATF guidance + source publication frequency:
   - OFAC SDN: 7 days (daily updates)
   - UN/EU/UK: 14 days (weekly)
   - CBK domestic: 30 days (less frequent)
2. **Lazy STALE recomputation** on every `freshness_summary()` and `screen()` call — operators don't need to remember to re-evaluate
3. **`SCREENING_DEFERRED_LISTS_STALE` outcome** — operator can configure `block_when_lists_stale=True` to refuse screenings against fully-stale infrastructure
4. **Initial state honesty**: all 5 sources start as `MISSING` — no auto-fake-readiness. Operator must explicitly call `register_list_load()` for each source. `freshness_summary()` shows the gap.

---

## FATF Rec 12 verbatim — foreign vs domestic PEP

PEP classification distinguishes foreign from domestic, which matters for EDD policy:

- **Foreign PEP** (nationality != residence_country, self-declared): `PepCategory.FOREIGN_PEP`, EDD trigger `foreign_pep_mandatory_edd_fatf_rec12` (FATF Rec 12 mandates EDD, **no exceptions**)
- **Domestic PEP** (post-2012 FATF revision, nationality == residence_country, self-declared): `PepCategory.DOMESTIC_PEP`, EDD trigger `pep_DOMESTIC_PEP`. Requires CDD + periodic review.
- **Occupation heuristic**: applicant didn't self-declare but occupation contains MEMBER OF PARLIAMENT / MINISTER / GOVERNOR / AMBASSADOR / JUDGE / MILITARY → flag with `REQUIRES_HUMAN_VERIFICATION` reason. Engine flags for review, **NOT** auto-confirms — Rule 4 honesty (the human compliance officer makes the final PEP determination).

---

## End-to-end probe — 5 realistic scenarios

Verified before declaring done (round-trip discipline carried forward from v10.156/v10.157):

| # | Scenario | Outcome | Notes |
|---|---|---|---|
| 1 | Clean KE teacher (NOT_PEP) | CLEAR | No PEP, no sanctions hits |
| 2 | Self-declared KE Minister (residence==nationality) | PEP_REVIEW_REQUIRED | DOMESTIC_PEP, edd=['pep_DOMESTIC_PEP'] |
| 3 | Self-declared NG Ambassador resident in KE | PEP_REVIEW_REQUIRED | FOREIGN_PEP, edd=['pep_FOREIGN_PEP', **'foreign_pep_mandatory_edd_fatf_rec12'**] |
| 4 | Undeclared MP (occupation='MEMBER OF PARLIAMENT', is_pep=False) | PEP_REVIEW_REQUIRED | DOMESTIC_PEP via heuristic, reason includes 'REQUIRES_HUMAN_VERIFICATION' |
| 5 | ENH-191 BusinessApplicant with 2 BOs (1 PEP) via `screen_applicant()` | 3 results | 1 business + 2 BOs; PEP BO flagged, clean BO clear |

**List freshness lifecycle** also verified — 5 sources start MISSING; operator loads 3 (OFAC, UN, CBK); 2 remain MISSING (EU, UK); operator sees the gap explicitly via `freshness_summary()`. No silent fake-readiness.

---

## Tests — `tests/test_screening_orchestrator_v10_161.py`

22 tests across 9 classes:

- **TestModuleShape** (3) — exists / parses / imports / all 4 enums present
- **TestRegistryActivation** (1) — ENH-192 status='active' + affected_engines=('screening_orchestrator',)
- **TestInitialState** (3) — all 5 sources MISSING at init / register_load updates freshness / negative records rejected
- **TestPepClassification** (4) — clean→CLEAR / domestic PEP / **foreign PEP triggers FATF Rec 12 mandatory EDD** / occupation heuristic catches undeclared MP with REQUIRES_HUMAN_VERIFICATION
- **TestApplicantIntegration** (3) — CustomerApplicant from ENH-191 / BusinessApplicant with BOs producing N+1 results / unrecognized type raises ValueError
- **TestNoIntegrationBreakage** (2) — Standard #58 still works standalone / ENH-191 engine still works standalone
- **TestDeterminism** (1) — same input → same UnifiedScreeningResult (critical for SAR audit reconstructions)
- **TestOutputSerialization** (1) — `to_dict()` returns JSON-serializable
- **TestNoRegression** (4) — all 151 gates pass / gate count unchanged / ENH-191 engine intact / Treasury endpoints intact

All 22 pass.

---

## Honest deferrals — explicit reasons, not bandwidth

1. **Real OFAC SDN XML feed ingestion** — requires network + parsing of MB-scale XML; separate fetcher work. Engine ships `load_method='manual'/'automated_feed'/'api_pull'` fields so a real fetcher can wire in without engine changes.
2. **Real UN/EU/UK list ingestion** — same reason.
3. **ML-based false-positive reduction** — Standard #58 already does deterministic Levenshtein matching with alias handling. Adding ML on top requires actual ML models, not synthesizable from a spec. The orchestrator surfaces the deterministic match and lets operators run the existing `transition_hit()` workflow for review.
4. **Transliteration tables** (Arabic↔Latin, Cyrillic↔Latin) — real transliteration needs verified lookup tables. Not synthesizing.

**Each gap has a real reason that's not "I ran out of time."** Same discipline as v10.158 NSFR ASF/RSF reasoning, v10.159 CBK-specific category note, v10.160 ENH-191 deferral surfaces.

---

## Apply order

After v10.160:

```
1. utils/screening_orchestrator.py                  → utils/  (NEW)
2. utils/standards_registry.py                      → utils/  (REPLACES — ENH-192 active)
3. tests/test_screening_orchestrator_v10_161.py     → tests/  (NEW)
4. docs/Master_Prompt_v3.54.md                      → docs/
5. SCOPE_LEDGER.md                                  → root
6. CHANGELOG_v10.161.md                             → root
```

`git add -A && git commit -m "v10.161 ENH-192 PEP & Sanctions Screening Orchestrator"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

**No app.py / scripts/audit.py change.** Engine-level + registry update only. Doesn't modify Standard #58 (`sanctions_screening.py`), `kyc_aml_risk.py`, or ENH-191's `kyc_onboarding.py`.

---

## Strategic value for the Ecobank Kenya MIS bid

ENH-192's most demonstrable feature is the **list freshness honesty**. Most vendor sanctions screening modules quietly assume the lists are fresh — they don't surface to operators that "OFAC was last refreshed 47 days ago" until the regulator finds out during examination. The 3 incumbent vendors typically don't show this in demos.

A2Z MIS 360's screening orchestrator forces the operator to confront list freshness at every screening call. The `lists_skipped_due_to_staleness` field in every `UnifiedScreeningResult` is an audit trail showing what wasn't checked and why. This is the kind of operational realism that wins competitive bids — not "we have sanctions screening" but "watch — when I deliberately stale the OFAC list, the screening result tells me exactly which list got skipped."

The FATF Rec 12 distinction (foreign PEP mandatory EDD vs domestic PEP CDD+review) is also a regulator-grade differentiator. Many implementations treat all PEPs identically; ENH-192 enforces the FATF distinction the regulator expects to see.

---

## v10.162 next-up — ENH-193 AML Transaction Monitoring Engine

Natural follow-on. ENH-193 consumes:

- `OnboardingDecision.tier` from ENH-191 (SDD/CDD/EDD/PROHIBITED) to calibrate transaction monitoring thresholds — PEP/EDD customers need lower thresholds for the same activity to be considered suspicious
- `UnifiedScreeningResult.outcome` from ENH-192 to determine if a transaction party is sanctioned (block) or PEP (review)

ENH-193 itself adds:
- Behavioural pattern detection (structuring, smurfing, sudden velocity changes)
- Threshold-based alerts with risk-band-specific calibration
- Alert lifecycle (NEW → REVIEW → ESCALATED → CLOSED)
- Audit trail
- Integration hook for ENH-194 SAR/STR filing

After ENH-193: ENH-194 SAR/STR Filing (consumes ENH-193 alerts → regulatory submission workflow) → ENH-195 Regulatory Change Management → ENH-196 Policy Management → ENH-197 Compliance Training → ENH-198 Compliance Risk Assessment. AML/Compliance module closure (G152+G153) when all 9 standards active + cockpit + API + admin marker.

---

## Summary

v10.161 ships ENH-192 PEP & Sanctions Screening Orchestrator as a ~520 LOC orchestration engine that composes Standard #58 sanctions + kyc_aml_risk PEP into unified `UnifiedScreeningResult` outputs. Adds source-level list freshness tracking that Standard #58 lacks. Enforces FATF Rec 12 verbatim (foreign PEP mandatory EDD, distinct from domestic PEP CDD+review). 5 realistic Ecobank Kenya scenarios verified end-to-end. 22/22 tests pass. AML/Compliance module: 2/9 standards active.

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. v10.161 tests `22/22 pass`.
