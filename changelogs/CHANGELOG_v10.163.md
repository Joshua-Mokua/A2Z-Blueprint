# CHANGELOG v10.163 — ENH-194 SAR/STR Filing Engine

**Status:** Fourth active standard of the AML/Compliance cluster. **First non-orphan-claim engine of the AML cluster** — pre-build inspection found greenfield (no existing code, no orphan to claim). Builds and tracks Suspicious Activity Reports (SARs) and Suspicious Transaction Reports (STRs) for filing with the Kenya Financial Reporting Centre (FRC).

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged — engine-level work). G142 anti-drift floor 78→79. Active standards 180→181. v10.163 tests 30/30 pass.

---

## Regulatory alignment is the headline

| Source | Implementation |
|---|---|
| Kenya POCAMLA §44 | `POCAMLA_FILING_DEADLINE_DAYS = 7` constant; deadline auto-computed |
| FATF Rec 20 | SAR vs STR vocabulary distinction in `ReportType` enum |
| CBK PG/15 | Audit trail via `transition_log` accumulating across lifecycle |
| FRC Reporting Format | Required field shape via `FilingPayload.to_dict()` |

POCAMLA §44 mandates the institution file SAR within 7 days of suspicion forming. Engine auto-computes `filing_deadline_utc = suspicion_formed_at_utc + timedelta(days=7)`. `overdue_filings()` returns DRAFT filings past the deadline — operator-actionable regulatory exposure.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/sar_filing.py` | ~430 | NEW. 3 enums + 4 frozen dataclasses + state machine + SarFilingEngine |
| `utils/standards_registry.py` | 1 line | MODIFIED. ENH-194 'planned'→'active', affected_engines=()→('sar_filing',) |
| `tests/test_sar_filing_v10_163.py` | ~440 | NEW. 30 tests across 9 classes |
| `docs/Master_Prompt_v3.56.md` | ~1100 | Anti-drift sync v3.55 → v3.56 |
| `SCOPE_LEDGER.md` | updated | v10.163 row + status block |
| `CHANGELOG_v10.163.md` | this file | This document |

---

## Engine surface

### 3 enums

```python
class ReportType(str, Enum):
    SAR = "SAR"   # Suspicious Activity — behavioural patterns
    STR = "STR"   # Suspicious Transaction — specific txns cited

class FilingStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATION_OPENED = "INVESTIGATION_OPENED"
    INVESTIGATION_CLOSED = "INVESTIGATION_CLOSED"
    WITHDRAWN = "WITHDRAWN"      # only DRAFT → WITHDRAWN allowed

class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_REPORT_NOT_FOUND = "REJECTED_REPORT_NOT_FOUND"
```

### 4 frozen dataclasses

```python
@dataclass(frozen=True)
class SubjectIdentity:
    subject_id: str
    legal_name: str
    subject_kind: str  # INDIVIDUAL | BUSINESS
    nat_id: str = ""   # KYC: national ID; KYB: BRS cert
    nationality: str = "KE"
    # ... + DOB/incorporation, occupation/industry, address

@dataclass(frozen=True)
class TransactionEvidence:
    txn_id: str
    txn_date: str
    amount_kes: Decimal
    txn_type: str
    counterparty_name: str = ""
    counterparty_country: str = ""
    description: str = ""

@dataclass(frozen=True)
class AlertProvenance:
    monitoring_engine: str  # "ENH-193 AmlMonitoringEngine"
    customer_id: str
    monitored_at_utc: str
    rule_ids: Tuple[str, ...]
    rule_names: Tuple[str, ...]
    severity: str
    escalation_reason: str = ""

@dataclass(frozen=True)
class FilingPayload:
    filing_id: str
    report_type: ReportType
    subject: SubjectIdentity
    transactions: Tuple[TransactionEvidence, ...]
    suspicion_narrative: str
    risk_indicators: Tuple[str, ...]
    suspicion_formed_at_utc: str
    filing_deadline_utc: str            # POCAMLA §44 auto-computed
    filed_at_utc: Optional[str]
    acknowledged_at_utc: Optional[str]
    investigation_opened_at_utc: Optional[str]
    investigation_closed_at_utc: Optional[str]
    investigation_outcome: str
    status: FilingStatus
    provenance: AlertProvenance
    submission_method: str              # honest deferral surface
    filed_by_user: str = ""
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    meta: Mapping[str, Any] = ...
    
    def to_dict() -> Dict[str, Any]: ...   # for FRC export
```

### State machine

`ALLOWED_TRANSITIONS` enforces forward-only lifecycle:

```
DRAFT ─┬─→ SUBMITTED ──→ ACKNOWLEDGED ─┬─→ INVESTIGATION_OPENED ──→ INVESTIGATION_CLOSED
       │                                └─→ INVESTIGATION_CLOSED  (FRC may close at ack)
       └─→ WITHDRAWN  (only from DRAFT, requires reason)
```

POCAMLA enforces: once SUBMITTED, the institution must maintain the filing — cannot revert to DRAFT, cannot WITHDRAW. The state machine codifies this as a hard rule. Backwards transitions return `REJECTED_INVALID_TRANSITION`.

### Engine API

```python
class SarFilingEngine:
    def build_filing(
        self,
        monitoring_result: Any,           # AmlMonitoringResult from ENH-193
        subject: SubjectIdentity,
        transactions: List[TransactionEvidence],
        suspicion_narrative: str,
        report_type: Optional[ReportType] = None,
        suspicion_formed_at_utc: Optional[str] = None,
    ) -> FilingPayload: ...
    
    def transition(
        self,
        filing_id: str,
        new_status: FilingStatus,
        user: str,
        reason: str = "",
        investigation_outcome: str = "",
    ) -> Tuple[TransitionOutcome, Optional[FilingPayload]]: ...
    
    def filing_by_id(filing_id) -> FilingPayload
    def all_filings() -> Tuple[FilingPayload, ...]
    def overdue_filings() -> Tuple[FilingPayload, ...]
    def board_summary() -> Dict[str, Any]
```

---

## Auto-detect SAR vs STR

When `transactions=[]` → `report_type=SAR` (Suspicious Activity Report — behavioural patterns, profile changes, no specific transaction). When non-empty → `report_type=STR` (Suspicious Transaction Report — specific transactions cited). Operator can override with explicit `report_type`.

---

## Provenance threading from ENH-193

`build_filing(monitoring_result=...)` accepts an `AmlMonitoringResult` from ENH-193 and auto-populates `AlertProvenance`:

| Field | Source |
|---|---|
| `monitoring_engine` | `"ENH-193 AmlMonitoringEngine"` (literal) |
| `customer_id` | `monitoring_result.customer_id` |
| `monitored_at_utc` | `monitoring_result.monitored_at_utc` |
| `rule_ids` | tuple of all `tiered_alerts[*].rule_id` |
| `rule_names` | tuple of all `tiered_alerts[*].rule_name` |
| `severity` | max severity across alerts |
| `escalation_reason` | first non-empty `tiered_alerts[*].escalation_reason` |

Risk indicators composite: `rule_ids + ['TIER_<level>'] + ['EDD_ESCALATION' if EDD escalation present]`.

Auditors get a regulator-grade trace of why the filing was produced — from the upstream alert → through the orchestration tier-aware logic → to the filing payload.

---

## POCAMLA §44 deadline auto-computation

```python
POCAMLA_FILING_DEADLINE_DAYS = 7
filing_deadline_utc = suspicion_formed_at_utc + timedelta(days=7)
```

If `suspicion_formed_at_utc` not provided to `build_filing`, defaults to `monitoring_result.monitored_at_utc` — the time ENH-193 first flagged the activity. `overdue_filings()` returns DRAFT filings whose deadline has passed.

---

## Honest deferral — wire-level FRC submission

FRC has no public programmatic submission API. v10.163 ships **build + track + export** capability. The `submission_method` field on every FilingPayload reads:

> *"MANUAL_PORTAL — FRC has no public programmatic submission API. Operator exports the filing via to_dict() and uploads via FRC's secure web portal or encrypted email. v10.163 ships build+track+export capability; wire-level submission is a future increment if/when FRC publishes a submission API."*

Operators reading the API don't assume auto-submit. Same discipline as v10.159 vocabulary endpoint's CBK extension note, v10.162 ml_layer_status DEFERRED, ENH-138 no_product_resolution. Surface gaps explicitly, not via fabricated capability.

---

## End-to-end probe — full lifecycle verified

Realistic Ecobank Kenya structuring case threaded all the way through:

1. **ENH-193 produces `outcome=ESCALATE_TO_SAR`** for EDD customer with 3x sub-1M cash deposits within 7 days, R2 fires CRITICAL
2. **ENH-194 builds DRAFT STR**: `filing_id=SAR-000001`, POCAMLA deadline auto-computed exactly 7 days out, `risk_indicators=['R2', 'TIER_EDD', 'EDD_ESCALATION']`, `provenance.severity=CRITICAL`
3. **Operator transitions to SUBMITTED**: `filed_at_utc` + `filed_by_user='compliance_officer_001'` recorded
4. **Backwards transition to DRAFT correctly `REJECTED_INVALID_TRANSITION`** — state unchanged at SUBMITTED
5. **FRC ACKNOWLEDGED** → **INVESTIGATION_OPENED** → **INVESTIGATION_CLOSED** with `investigation_outcome=CLOSED_REFERRED`
6. **`transition_log`: 5 entries** — DRAFT, SUBMITTED, ACKNOWLEDGED, INVESTIGATION_OPENED, INVESTIGATION_CLOSED — full audit trail preserved with timestamps + user attribution

This is regulator-grade. A POCAMLA examiner pulling this filing's audit trail sees the complete chain of custody.

---

## Tests — 30 across 9 classes

- **TestModuleShape** (5) — exists/parses/imports/enum cardinality/frozen
- **TestRegistryActivation** (1) — ENH-194 active + sar_filing engine claimed
- **TestStateMachine** (5) — DRAFT branches to SUBMITTED+WITHDRAWN / SUBMITTED no backwards / SUBMITTED no withdrawal / terminals empty / ACKNOWLEDGED branches
- **TestBuildFiling** (5) — STR with txns / SAR without / POCAMLA 7-day deadline / empty narrative rejected / provenance from real AmlMonitoringResult
- **TestTransitions** (7) — SUBMITTED records filed_at + filed_by_user / no backwards / no withdrawal / withdraw requires reason / withdraw with reason / 5-entry log on full lifecycle / unknown filing_id rejected
- **TestOverdueDetection** (1) — 30-day-old DRAFT surfaced via `overdue_filings()`
- **TestHonestDeferral** (1) — MANUAL_PORTAL note explicit
- **TestPortfolioSummary** (1)
- **TestNoRegression** (4) — all gates / count unchanged / v10.162 AML still works / v10.160 KYC still works

All 30 pass.

---

## AML/Compliance module progress: 4 of 9

| Standard | Status | Engine(s) | Drop |
|---|---|---|---|
| ENH-191 KYC/KYB Onboarding | **active** | kyc_onboarding | v10.160 |
| ENH-192 PEP & Sanctions Screening | **active** | screening_orchestrator + sanctions_screening | v10.161 (prior session) |
| ENH-193 AML Transaction Monitoring | **active** | aml_monitoring + transaction_monitoring | v10.162 |
| **ENH-194 SAR/STR Filing** | **active** | **sar_filing** | **v10.163** |
| ENH-195 Regulatory Change Mgmt | planned | — | v10.164 (candidate) |
| ENH-196 Policy Management & Attestation | planned | — | future |
| ENH-197 Compliance Training | planned | — | future |
| ENH-198 Compliance Risk Assessment | planned | — | v10.164 (candidate) |
| ENH-199 Examiner-Ready Reporting | planned | — | future |

Module closure gates G152+G153 when all 9 active + module cockpit + module API + admin Tier 4C marker — same pattern as Treasury G150/G151.

---

## Apply order

After v10.162:

```
1. utils/sar_filing.py                    → utils/  (NEW)
2. utils/standards_registry.py            → utils/  (REPLACES — ENH-194 active)
3. tests/test_sar_filing_v10_163.py       → tests/  (NEW)
4. docs/Master_Prompt_v3.56.md            → docs/
5. SCOPE_LEDGER.md                        → root
6. CHANGELOG_v10.163.md                   → root
```

`git add -A && git commit -m "v10.163 ENH-194 SAR/STR Filing Engine — POCAMLA §44 lifecycle"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

**No app.py / scripts/audit.py change.**

---

## v10.164 next-up — two candidates

1. **ENH-195 Regulatory Change Management** — ingests CBK circulars + amendments to POCAMLA / Banking Act / Banking Prudential Guidelines + KRA/FRC notices; tracks impact on internal policies; drives gap analysis; schedules attestation. Reading-side engine complementing the writing-side filings of v10.163.
2. **ENH-198 Compliance Risk Assessment Engine** — rolls up portfolio risk from ENH-191 OnboardingDecision + ENH-193 AmlMonitoringResult + ENH-194 SAR filings into an enterprise-level compliance risk score with executive dashboard. Top-of-pyramid rollup engine.

**Recommendation: ENH-198 next.** It's the rollup that turns 4 individual engines into a compliance-suite story for vendor demo. The compliance risk score becomes the headline number Joshua puts in front of the Ecobank evaluation panel — proof that the modular engines compose into an enterprise view. ENH-195 can come after.

---

## Summary

v10.163 lands ENH-194 SAR/STR Filing Engine — first greenfield (non-orphan-claim) AML standard. ~430 LOC engine: 3 enums, 4 frozen dataclasses, ALLOWED_TRANSITIONS state machine codifying POCAMLA §44 forward-only lifecycle, auto-computed 7-day filing deadline, provenance threading from ENH-193 AmlMonitoringResult, honest deferral on wire-level FRC submission. 30 tests pass. End-to-end probe verified full lifecycle DRAFT → SUBMITTED → ACKNOWLEDGED → INVESTIGATION_OPENED → INVESTIGATION_CLOSED with 5-entry audit trail.

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. v10.163 tests `30/30 pass`.
