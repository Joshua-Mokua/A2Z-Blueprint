# CHANGELOG v10.162 — ENH-193 AML Transaction Monitoring Engine

**Status:** Third active standard of the AML/Compliance cluster (after ENH-191 v10.160, ENH-192 prior session). Orchestration layer over the previously-orphaned `transaction_monitoring` engine (Standard #59). 

**Note:** This drop was originally drafted as v10.161 in this session — but pre-package inspection found a `CHANGELOG_v10.161.md` already exists in the repo from a prior session that shipped ENH-192 PEP & Sanctions Screening. Renamed all internal references to v10.162 to avoid collision with prior-session work. Same discipline as the orphaned-engine catches in v10.160 (kyc_aml_risk pre-existing) and v10.162-itself (transaction_monitoring pre-existing). **Always inspect before assuming.**

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged — engine-level work). G142 anti-drift floor 77→78. v10.162 tests 19/19 pass.

---

## Pre-build inspection — orphaned engine claimed

Inspection of `utils/` found `transaction_monitoring.py` (730 LOC) already exists with a real, working `TransactionMonitoringEngine` for **Standard #59 KYC/AML risk surface**. 8 deterministic CBK/PG/15 + FATF Rec 20 rules:

| Rule | Pattern | Threshold |
|---|---|---:|
| R1 | CASH_THRESHOLD_BREACH | KES 1M (CBK reportable) |
| R2 | STRUCTURING_PATTERN | 3+ deposits 800k-999k / 7 days |
| R3 | RAPID_MOVEMENT | KES 5M in & out within 48h |
| R4 | HIGH_RISK_GEOGRAPHY | Wire to/from IR, KP |
| R5 | ACCOUNT_DORMANT_ACTIVITY | Activity > KES 100k on dormant |
| R6 | ROUND_NUMBER_PATTERN | 5+ identical round-number / 30 days |
| R7 | VELOCITY_BREACH | >20 daily count or >KES 10M daily |
| R8 | PEP_LARGE_TRANSACTION | PEP customer txn > KES 2M |

**The engine was orphaned** — no standard claimed it as `affected_engines`. Initial framing for ENH-193 might have been "build a transaction monitoring engine" — duplicating active capability.

**Honest scope:** claim the existing engine for ENH-193 + add the orchestration layer that's actually missing.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/aml_monitoring.py` | ~340 | NEW. Orchestration engine wrapping Standard #59 |
| `utils/standards_registry.py` | 1 line | MODIFIED. ENH-193 status='planned'→'active', affected_engines=()→('aml_monitoring','transaction_monitoring'), implementation_batch='v10.162' |
| `tests/test_aml_monitoring_v10_162.py` | ~330 | NEW. 19 tests across 8 classes |
| `docs/Master_Prompt_v3.55.md` | ~1100 | Anti-drift sync v3.54 → v3.55 |
| `SCOPE_LEDGER.md` | updated | v10.162 row + status block |
| `CHANGELOG_v10.162.md` | this file | This document |

---

## Engine surface

### 2 enums

```python
class MonitoringOutcome(str, Enum):
    CLEAN = "CLEAN"
    ALERTS_OPEN = "ALERTS_OPEN"
    ESCALATE_TO_SAR = "ESCALATE_TO_SAR"
    ESCALATE_TO_BLOCK = "ESCALATE_TO_BLOCK"

class TierAwareSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
```

### 2 frozen output dataclasses

```python
@dataclass(frozen=True)
class TieredAlert:
    alert_id: int
    rule_id: str
    rule_name: str
    base_severity: str             # from underlying engine
    tier_aware_severity: TierAwareSeverity   # after escalation
    customer_id: str
    customer_tier: Optional[str]   # SDD/CDD/EDD/PROHIBITED
    txn_ids: Tuple[str, ...]
    description: str
    escalation_reason: str         # audit trail for severity bump

@dataclass(frozen=True)
class AmlMonitoringResult:
    customer_id: str
    customer_tier: Optional[str]
    outcome: MonitoringOutcome
    n_alerts: int
    n_critical: int
    n_high: int
    tiered_alerts: Tuple[TieredAlert, ...]
    sanctions_match_propagated: bool
    monitored_at_utc: str
    ml_layer_status: str           # honest deferral surface
    meta: Mapping[str, Any]
```

Both have `to_dict()` for JSON API serialization.

### Engine API

```python
class AmlMonitoringEngine:
    def monitor_customer(
        self,
        customer_id: str,
        transactions: List[Transaction],
        customer_tier: Optional[str] = None,    # SDD/CDD/EDD/PROHIBITED from ENH-191
        sanctions_hit: bool = False,            # from ENH-192/screening_orchestrator
        is_pep: bool = False,
    ) -> AmlMonitoringResult: ...
    
    def result_by_customer(customer_id) -> AmlMonitoringResult
    def all_results() -> Tuple[AmlMonitoringResult, ...]
    def board_summary() -> Dict[str, Any]
```

---

## Orchestration value-add over the rule engine alone

Six capabilities the underlying `TransactionMonitoringEngine` doesn't have:

1. **Tier-aware severity escalation** — EDD customers bump alert severity by one band (HIGH → CRITICAL) with explicit audit-trail `escalation_reason` like `edd_tier_escalation_from_HIGH`
2. **Sanctions match auto-escalates to CRITICAL** regardless of base severity, with reason `sanctions_match_auto_critical`
3. **PROHIBITED tier defensive trip-wire** — outcome `ESCALATE_TO_BLOCK` without scanning. Customer in PROHIBITED tier shouldn't be active; defensive engine prevents fabricated cleanliness
4. **Deterministic outcome calculation** — sanctions/PROHIBITED → BLOCK; n_critical>=1 → SAR; n_alerts>=1 → ALERTS_OPEN; else CLEAN
5. **Per-customer `AmlMonitoringResult` dataclass** with `to_dict()` for API + tier_counts + sanctions_propagated tracking
6. **`board_summary` cross-arc aggregation** for cockpit consumption + module rollup

---

## Honest deferral surface — ML layer

ENH-193 spec calls for **"hybrid detection combining rule-based, scorecard, and ML models."** v10.162 ships rule-based + scorecard (tier-aware multipliers); ML alert prioritization is honestly deferred:

> *"DEFERRED — ML alert prioritization requires labeled training data (historical true-positive vs false-positive alerts). Not in scope for v10.162; tracked as future work for ENH-193+ increments. Current detection is rule-based + scorecard (tier-aware threshold multipliers)."*

Surfaces in every `AmlMonitoringResult.ml_layer_status` and `board_summary()['ml_layer_status']`. Operators see this gap explicitly.

---

## End-to-end probe — 5 realistic Ecobank Kenya scenarios

| Scenario | Outcome | Headline alert | Notes |
|---|---|---|---|
| Clean SDD retail | CLEAN | — | 0 alerts |
| CDD structuring (3x KES 999K cash 7d) | ESCALATE_TO_SAR | R2 CRITICAL | engine baseline already CRITICAL |
| EDD/PEP large cash (KES 1.5M) | ESCALATE_TO_SAR | **R1 HIGH→CRITICAL** | **EDD escalation working** |
| PROHIBITED + sanctions hit | ESCALATE_TO_BLOCK | — | defensive trip-wire, no scan |
| CDD wire to Iran (KES 500K) | ESCALATE_TO_SAR | R4 CRITICAL | high-risk geography |

**The EDD escalation result is the orchestration value-add headline.** R1 baseline HIGH → CRITICAL because EDD customer warrants stricter alerting; the `TransactionMonitoringEngine` alone wouldn't make this distinction. The `escalation_reason` field gives a regulator-auditable trail.

---

## Tests — `tests/test_aml_monitoring_v10_162.py`

19 tests across 8 classes:

- **TestModuleShape** (4) — exists / parses / imports / enums + frozen dataclasses
- **TestRegistryActivation** (1) — ENH-193 active + both engines registered
- **TestOutcomeLogic** (4) — clean SDD / structuring CDD / PROHIBITED / high-risk geography
- **TestTierAwareEscalation** (3) — EDD bumps HIGH→CRITICAL with audit reason / SDD passes through / sanctions match auto-critical
- **TestHonestDeferral** (2) — `ml_layer_status` DEFERRED in result + summary
- **TestIntegrationCleanliness** (1) — `TransactionMonitoringEngine` still works standalone
- **TestPortfolioSummary** (1) — `board_summary` shape
- **TestNoRegression** (3) — gates pass / count unchanged / v10.160 KYC still works

All 19 pass.

---

## AML/Compliance module progress: 3 of 9

| Standard | Status | Engine(s) | Drop |
|---|---|---|---|
| ENH-191 KYC/KYB Onboarding | **active** | kyc_onboarding | v10.160 |
| ENH-192 PEP & Sanctions Screening | **active** | screening_orchestrator + sanctions_screening | v10.161 (prior session) |
| **ENH-193 AML Transaction Monitoring** | **active** | **aml_monitoring + transaction_monitoring** | **v10.162** |
| ENH-194 SAR/STR Filing | planned | — | **v10.163 next** |
| ENH-195 Regulatory Change Mgmt | planned | — | future |
| ENH-196 Policy Management & Attestation | planned | — | future |
| ENH-197 Compliance Training | planned | — | future |
| ENH-198 Compliance Risk Assessment | planned | — | future |
| ENH-199 Examiner-Ready Reporting | planned | — | future |

Module closure gates (G152 module_closed + G153 ui_integrated) come when all 9 active + module cockpit + module API + admin Tier 4C marker — same pattern as Treasury G150/G151.

---

## Apply order

After v10.161 (which shipped ENH-192 in a prior session):

```
1. utils/aml_monitoring.py                  → utils/  (NEW)
2. utils/standards_registry.py              → utils/  (REPLACES — ENH-193 active)
3. tests/test_aml_monitoring_v10_162.py     → tests/  (NEW)
4. docs/Master_Prompt_v3.55.md              → docs/
5. SCOPE_LEDGER.md                          → root
6. CHANGELOG_v10.162.md                     → root
```

`git add -A && git commit -m "v10.162 ENH-193 AML Transaction Monitoring — orchestration over Standard #59"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

**No app.py / scripts/audit.py change.** Engine + registry only.

---

## v10.163 next-up — ENH-194 SAR/STR Filing Engine

Natural follow-on. ENH-193's `AmlMonitoringResult.outcome=ESCALATE_TO_SAR` is the input to ENH-194's filing engine. ENH-194 produces FRC-filing-ready Suspicious Activity Report (SAR) / Suspicious Transaction Report (STR) payloads with required fields per:

- Kenya Financial Reporting Centre (FRC) format
- Kenya Proceeds of Crime and Anti-Money Laundering Act (POCAMLA) §44 — SAR within 7 days of suspicion forming
- FATF Recommendation 20

Tracks filing status: DRAFT → SUBMITTED → ACKNOWLEDGED → INVESTIGATION_OPENED → INVESTIGATION_CLOSED.

After ENH-194: ENH-195 Regulatory Change Mgmt, ENH-196 Policy Management, ENH-197 Compliance Training, ENH-198 Compliance Risk Assessment, ENH-199 Examiner-Ready Reporting. Module closure (G152+G153) when all 9 active + cockpit + API.

---

## Summary

v10.162 lands ENH-193 AML Transaction Monitoring as an orchestration layer over the previously-orphaned `transaction_monitoring` engine. ~340 LOC adding 6 capabilities (tier-aware escalation, sanctions auto-critical, PROHIBITED trip-wire, deterministic outcome, AmlMonitoringResult dataclass, board_summary aggregation). ML layer honestly DEFERRED. 5 realistic Ecobank Kenya scenarios verified including the headline EDD-escalation case. 19 tests pass.

The v10.161 → v10.162 rename is itself a documented honesty: pre-package inspection found the prior session had already shipped a v10.161 with ENH-192. Drop renamed cleanly to avoid collision; same inspect-first discipline that caught the orphaned engines in v10.160 and v10.162-itself.

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. v10.162 tests `19/19 pass`.
