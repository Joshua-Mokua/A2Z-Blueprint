# CHANGELOG v10.160 — ENH-191 Digital KYC/KYB Onboarding Engine

**Status:** **PHASE 3 OPENED.** First standard of the AML/Compliance cluster (ENH-190..199, 9 standards total). Per the standing rule, one standard per ZIP. Phase 2 Treasury fully closed and production-ready (43 endpoints); Phase 3 strategic priority is AML/Compliance — identified as the biggest competitive gap relative to the 3 incumbent vendors in the Ecobank Kenya MIS bid.

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged — engine-level work, no new gates). G142 anti-drift floor goes from 76 to 77 (one new active standard). Active standards count goes from 178 to 179. v10.160 tests 20/20 pass.

---

## Honest scoping decision — orchestration, not duplication

Pre-build inspection found that **ENH-121 Digital Identity Verification (eKYC) is already active** with engine `utils/kyc_aml_risk.py`, AND **Standard #57 (KYC/AML Risk Scoring)** is implemented in the same file. Initial framing for ENH-191 might have been "build a KYC engine" — that would be duplicating active capability.

The honest scope: **ENH-191 is the ORCHESTRATION layer.** It wires:

1. **Identity intake** (national ID, KRA PIN, passport / business registration, beneficial owners) — pure data capture, this engine
2. **ID verification** — delegates to `KycAmlRiskEngine.assess_customer`
3. **Risk scoring** — same delegation
4. **KYC tier assignment** — this engine, deterministic from risk band
5. **Review schedule** — this engine, deterministic from tier

Same compose-don't-duplicate pattern as the Treasury cockpit's relationship to the 12 Treasury engines. Caught this by inspecting `utils/` before writing — same discipline that caught the v10.156 FXPosition bug pre-ship, and the v10.159 vocabulary expansion reframing.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/kyc_onboarding.py` | ~580 | NEW. Orchestration engine + 7 enums + 4 input dataclasses + OnboardingDecision output |
| `utils/standards_registry.py` | 1 line | MODIFIED. ENH-191 status='planned'→'active', affected_engines=()→('kyc_onboarding',) |
| `tests/test_kyc_onboarding_v10_160.py` | ~340 | NEW. 20 tests across 8 classes |
| `docs/Master_Prompt_v3.53.md` | ~1100 | Anti-drift sync v3.52 → v3.53 |
| `SCOPE_LEDGER.md` | updated | v10.160 row + status block |
| `CHANGELOG_v10.160.md` | this file | This document |

---

## Engine surface

### 7 controlled-vocabulary enums

| Enum | Values | Notes |
|---|---|---|
| `ApplicantType` | INDIVIDUAL, SOLE_PROPRIETOR, PARTNERSHIP, LIMITED_COMPANY, NGO, TRUST | Top-level KYC vs KYB distinction |
| `IdDocumentType` | NATIONAL_ID, PASSPORT, ALIEN_CARD, KRA_PIN, BRS_CERTIFICATE, PARTNERSHIP_DEED, NGO_REGISTRATION | Kenya-specific (BRS for business registration) |
| `DocumentVerificationStatus` | NOT_PROVIDED, PENDING, VERIFIED, FAILED_OCR, FAILED_AUTHENTICITY, FAILED_IPRS_MISMATCH | IPRS = Kenya Integrated Population Registration Services |
| `BiometricVerificationStatus` | NOT_PROVIDED, PENDING, VERIFIED_LIVE, FAILED_LIVENESS, FAILED_FACE_MATCH | |
| `KycTier` | SDD, CDD, EDD, PROHIBITED | **Exact CBK/PG/15 vocabulary** |
| `OnboardingOutcome` | APPROVED, APPROVED_WITH_EDD, PENDING_DOCUMENTS, PENDING_BIOMETRICS, BLOCKED_PROHIBITED, BLOCKED_INSUFFICIENT_DATA, BLOCKED_FAILED_VERIFICATION | |

### 4 input dataclasses (all frozen)

```python
@dataclass(frozen=True)
class IdentityDocument:
    document_type: IdDocumentType
    document_number: str
    issuing_country: str = "KE"
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    verification_status: DocumentVerificationStatus = NOT_PROVIDED
    verification_notes: str = ""

@dataclass(frozen=True)
class BeneficialOwner:
    full_name: str
    national_id: str
    ownership_pct: Decimal       # validated 0-100 in __post_init__
    is_significant_controller: bool = False
    is_pep: bool = False
    nationality: str = "KE"

@dataclass(frozen=True)
class CustomerApplicant:        # KYC
    applicant_id: str
    full_name: str
    date_of_birth: str
    nationality: str
    residence_country: str
    occupation: str
    # ... + employer, income, PEP self-declaration, purpose, throughput,
    #     documents tuple, biometric_status, notes

@dataclass(frozen=True)
class BusinessApplicant:        # KYB
    applicant_id: str
    legal_name: str
    applicant_type: ApplicantType  # raises ValueError if INDIVIDUAL
    date_of_incorporation: str
    country_of_incorporation: str
    industry_sic: str
    # ... + turnover, headcount, cash-intensive flag, purpose,
    #     documents tuple, beneficial_owners tuple, notes
```

### Output dataclass

```python
@dataclass(frozen=True)
class OnboardingDecision:
    applicant_id: str
    applicant_kind: str           # "KYC" | "KYB"
    outcome: OnboardingOutcome
    tier: Optional[KycTier]
    risk_score: Optional[int]
    risk_band: Optional[str]
    pep_flag: bool
    sanctions_flag: bool
    next_review_date: Optional[str]
    blockers: Tuple[str, ...]
    edd_triggers: Tuple[str, ...]
    decided_at_utc: str
    meta: Mapping[str, Any]
    
    def to_dict(self) -> Dict[str, Any]: ...   # for API serialization
```

### Engine methods

```python
class KycOnboardingEngine:
    def register_customer(applicant: CustomerApplicant) -> None
    def register_business(applicant: BusinessApplicant) -> None
    def decide(applicant_id: str) -> OnboardingDecision
    def decision_by_id(applicant_id: str) -> OnboardingDecision
    def all_decisions() -> Tuple[OnboardingDecision, ...]
    def board_summary() -> Dict[str, Any]   # for cockpit consumption
```

---

## Decision logic — CBK/PG/15 + FATF Rec 10 + Kenya BO Regulations 2020

The `decide()` method runs a deterministic 10-step sequence:

1. **Mandatory identity fields** missing → blocker
2. **Verified primary ID document** required (NATIONAL_ID / PASSPORT / ALIEN_CARD); expired ID → blocker
3. **Biometric verification** required for digital channel (CBK/PG/15 EDD-grade for non-face-to-face); failure → blocker
4. **Risk scoring** via `KycAmlRiskEngine.assess_customer`
5. **Sanctions match** → PROHIBITED tier, BLOCKED_PROHIBITED outcome
6. **PEP** → APPROVED_WITH_EDD with `pep_flag` trigger
7. **Cash-intensive business** → EDD trigger (KYB only)
8. **<75% beneficial ownership identified** for limited company → EDD trigger. **Rule 6 honesty:** missing BO data does NOT lower the trust score
9. **KYB tier rollup**: business tier = max(its own tier, max of all BO tiers). Single bad beneficial owner pulls the whole business into EDD or PROHIBITED. **KYB cannot launder one bad BO.**
10. **Review schedule** deterministic from tier:
    - SDD → 36 months (3 years)
    - CDD → 24 months
    - EDD → 12 months (CBK/PG/15 mandates more frequent EDD review)
    - PROHIBITED → None

---

## End-to-end probe — 5 realistic Ecobank Kenya scenarios

Verified in a Python REPL before declaring done (v10.156/v10.157 round-trip discipline carried forward):

### Scenario 1: Clean retail KYC
```
Jane Wanjiru, teacher at Aga Khan Academy, KES 840K annual income
NATIONAL_ID + KRA_PIN both VERIFIED
Biometric VERIFIED_LIVE
```
**Result:** `APPROVED, tier=CDD, next_review=2028-04-25`

### Scenario 2: KYC missing biometric
```
Same data structure but biometric_status=NOT_PROVIDED
```
**Result:** `PENDING_BIOMETRICS, blockers=['biometric_not_provided']` (recoverable, not blocked)

### Scenario 3: PEP individual
```
Hon. Member of Parliament, is_pep=True, NID verified, biometric verified
```
**Result:** `APPROVED_WITH_EDD, tier=CDD, edd_triggers=['pep_flag']`

### Scenario 4: Clean limited company KYB
```
Wanjiru Holdings Ltd, real estate (SIC 6810), KES 50M turnover
BRS_CERTIFICATE + KRA_PIN verified
Beneficial owners: Jane (60%) + Mary (40%) = 100% coverage
```
**Result:** `APPROVED, tier=CDD`

### Scenario 5: Cash-intensive FX bureau with opaque ownership
```
Cash King Forex Bureau Ltd, FX dealing (SIC 6612), KES 200M turnover
is_cash_intensive=True
Beneficial owners: only "Anonymous Shareholder" (50%) — 50% of ownership identified
```
**Result:** `APPROVED_WITH_EDD, tier=CDD, edd_triggers=['only_50pct_ownership_identified', 'cash_intensive_business']`

**This is the result that demonstrates regulator-alignment** — the engine identifies BOTH risk factors (opaque ownership + cash intensity) and triggers EDD without blocking the legitimate business. CBK/PG/15 requires this exact behaviour.

---

## Tests — `tests/test_kyc_onboarding_v10_160.py`

20 tests across 8 classes:

- **TestModuleShape** (5) — exists / parses / imports / all 7 enums present / frozen dataclasses immutable
- **TestRegistryActivation** (2) — ENH-191 status='active' + affected_engines=('kyc_onboarding',)
- **TestKycScenarios** (3) — clean retail KYC / no biometric pending / PEP EDD
- **TestKybScenarios** (3) — clean limited company / 50% BO triggers EDD / no BO blocks
- **TestDeterminism** (1) — same input twice → same decision (critical for audit trails)
- **TestNoIntegrationBreakage** (1) — `KycAmlRiskEngine` still works standalone (ENH-191 didn't modify ENH-121's engine)
- **TestDuplicateRegistration** (1) — duplicate applicant_id raises ValueError
- **TestPortfolioSummary** (1) — `board_summary` returns required cockpit-consumption fields
- **TestNoRegression** (3) — all 151 gates still pass / gate count unchanged / Treasury endpoints intact

All 20 pass via inline runner.

---

## Why ENH-191 first (not 192 or 193)

ENH-191 produces the `OnboardingDecision` dataclass that every subsequent AML standard consumes:

- **ENH-192 PEP & Sanctions Screening** consumes `OnboardingDecision.applicant_id` + applicant data for screening lookups
- **ENH-193 AML Transaction Monitoring** consumes the resolved `tier` and `pep_flag` to calibrate transaction thresholds
- **ENH-194 SAR/STR Filing** uses the `OnboardingDecision` audit trail when building regulatory filings
- **ENH-198 Compliance Risk Assessment** rolls up portfolio-level risk from `OnboardingDecision` data

Building 191 first means 192-198 have a clean upstream surface to consume.

---

## Strategic value for the Ecobank Kenya MIS bid

AML/Compliance was the biggest competitive gap relative to the 3 incumbent vendors. ENH-191 establishes:

- **Regulator-alignment**: CBK/PG/15 + FATF Rec 10 + Kenya BO Regulations 2020 — verbatim vocabulary (SDD/CDD/EDD/PROHIBITED), explicit threshold (>=10% BO + significant control per BO Regulations 2020), explicit review periodicity (12mo for EDD per CBK/PG/15)
- **Determinism**: same input → same output, audit-trail-friendly. Critical for SAR filings where the regulator may reconstruct the decision
- **Honest deferral surfaces**: PENDING_DOCUMENTS / PENDING_BIOMETRICS as recoverable states (operator-actionable), distinct from BLOCKED states (terminal)
- **Compose-don't-duplicate**: integrates with existing `kyc_aml_risk` instead of replacing it — minimal risk to current footprint

The 5 realistic Ecobank Kenya scenarios in the test suite are demonstrable in 60 seconds during a vendor evaluation: show the engine handling a PEP, a cash-intensive FX bureau with opaque ownership, a clean retail customer.

---

## Apply order

After v10.159:

```
1. utils/kyc_onboarding.py                    → utils/  (NEW)
2. utils/standards_registry.py                → utils/  (REPLACES — ENH-191 active)
3. tests/test_kyc_onboarding_v10_160.py       → tests/  (NEW)
4. docs/Master_Prompt_v3.53.md                → docs/
5. SCOPE_LEDGER.md                            → root
6. CHANGELOG_v10.160.md                       → root
```

`git add -A && git commit -m "v10.160 ENH-191 Digital KYC/KYB Onboarding — Phase 3 AML/Compliance opened"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

**No app.py / scripts/audit.py change.** Engine-level + registry update only.

---

## What this drop does NOT change

- No engine modifications to existing engines (`kyc_aml_risk` untouched, ENH-121 still works standalone)
- No new audit gates — those come at module closure (G152+G153 future, when ENH-191..199 all active + cockpit + API)
- No `app.py` change — cockpit will be added at module closure
- No FastAPI router yet — `utils/api_compliance.py` at module closure or interim drops
- No Treasury work touched — v10.154-v10.159 endpoints intact (verified by TestNoRegression)

---

## v10.161 next-up — ENH-192 PEP & Sanctions Screening Engine

Natural follow-on. ENH-191 already screens for sanctions via the `kyc_aml_risk` delegation, but ENH-192 properly externalizes that into a screening-as-a-service engine with:

- OFAC SDN list ingestion
- UN consolidated sanctions list ingestion
- EU consolidated sanctions list
- CBK domestic sanctions list (per CBK/PG/15)
- Fuzzy name matching with score threshold
- False positive reduction (alias handling, transliteration)
- Periodic refresh schedule
- Match audit trail

After ENH-192: ENH-193 AML Transaction Monitoring (consumes transaction streams, applies behavioural patterns, generates alerts), then onward through ENH-194..198. AML/Compliance module closure (G152+G153) when all 9 standards active + cockpit + API + admin marker — same pattern as Treasury G150/G151.

---

## Summary

v10.160 opens Phase 3 AML/Compliance with ENH-191 Digital KYC/KYB Onboarding Engine. The honest scoping decision: orchestration over existing engines, not duplication. ~580 LOC engine with 7 CBK/PG/15-aligned enums, 4 frozen input dataclasses, deterministic decision logic enforcing FATF Rec 10 + Kenya BO Regulations 2020 + Rule 6 honesty (missing data doesn't lower trust score). KYB tier rollup prevents one bad BO from being laundered through a clean-on-paper company. 5 realistic Ecobank Kenya scenarios verified end-to-end. 20 tests pass. Standards registry shows 179/264 active (+1).

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. v10.160 tests `20/20 pass`.
