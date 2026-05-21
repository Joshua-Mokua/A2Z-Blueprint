# CHANGELOG v10.166 — ENH-195 Regulatory Change Management

**Status:** Seventh active standard of the AML/Compliance cluster. Greenfield engine. Inbound complement to v10.164 outbound enterprise rollup and v10.165 outbound examination package.

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged). G142 anti-drift floor 81→82. Active standards 183→184. v10.166 tests 30/30 pass.

---

## What this drop ships

| Artifact | Purpose |
|---|---|
| `utils/regulatory_change.py` (~430 LOC) | NEW. Inbound regulatory change tracking engine |
| `utils/standards_registry.py` (1 line) | ENH-195 'planned'→'active', engines=('regulatory_change',) |
| `pages/7_admin.py` (Tier 30 extended) | regulatory_change added to AML/Compliance Suite tier |
| `tests/test_regulatory_change_v10_166.py` (~330 LOC, 30 tests) | NEW |
| `docs/Master_Prompt_v3.59.md` | Anti-drift sync v3.58 → v3.59 |
| `SCOPE_LEDGER.md` | v10.166 row |
| `CHANGELOG_v10.166.md` | This document |

---

## Engine surface

**4 enums:**
- `RegulatorySource` (7 values): CBK / POCAMLA / BANKING_ACT / KRA / FRC / DPC / OTHER
- `ChangeStatus` (5 values): DRAFT / OPEN / IN_PROGRESS / CLOSED / WITHDRAWN
- `ImpactSeverity` (4 values): LOW / MEDIUM / HIGH / CRITICAL
- `TransitionOutcome` (4 values): OK / REJECTED_INVALID_TRANSITION / REJECTED_REASON_REQUIRED / REJECTED_NOT_FOUND

**1 frozen dataclass:** `RegulatoryChange` with full to_dict serialization and transition_log accumulation.

**State machine** enforces forward-only lifecycle:

```
DRAFT ─┬─→ OPEN ──→ IN_PROGRESS ──→ CLOSED
       └─→ WITHDRAWN  (only from DRAFT, requires reason)
```

CLOSED requires `closure_evidence` (audit trail mandate). WITHDRAWN requires `reason`.

**Severity-based attestation deadlines:**

| Severity | Deadline (days) |
|---|---:|
| CRITICAL | 7 |
| HIGH | 30 |
| MEDIUM | 60 |
| LOW | 90 |

`overdue_attestations()` surfaces non-CLOSED changes past their deadline as operator-actionable regulatory exposure.

---

## Honest deferrals — 2 surfaces

### automated_feed_status — DEFERRED
> *"CBK / KRA / FRC publish circulars and amendments via PDF, web pages, and email subscriptions. There is no programmatic API. v10.166 accepts manual operator entries via register_change(). Future increment can add per-source PDF parsers + web scrapers; out of scope for this drop."*

This is the operational reality: CBK doesn't expose its circulars via REST/JSON. Operators copy/paste from gazettes and PDFs into the engine. Honest about that gap rather than fabricating a "feed."

### policy_linkage_status — PARTIAL
> *"affected_policies field accepts string IDs but bidirectional linkage to a Policy Management engine requires ENH-196 (Policy Management & Attestation) to be active. v10.166 ships uni-directional reference (change → list of policy_id strings). Full bidirectional linkage in ENH-196+ increment."*

When ENH-196 ships next, the bidirectional join completes and the policy can show all regulatory drivers, the regulatory change can show all affected policies.

---

## End-to-end probe

Realistic Kenya scenarios verified before declaring done:

**C1: CBK PG/15 Amendment (HIGH severity)**
```
citation: CBK PG/15 Amendment 3 of 2026
title:    Enhanced EDD requirements for cash-intensive businesses
summary:  CBK now requires monthly EDD review (was quarterly) for cash-intensive
          businesses; new evidence requirement: source-of-funds documentation per
          transaction > KES 5M.
severity: HIGH → auto-deadline 30 days
affected_policies: ["POL-KYC-001", "POL-EDD-002"]
affected_engines:  ["kyc_onboarding", "aml_monitoring"]
```

**C2: POCAMLA Amendment (CRITICAL — 7-day deadline)**
```
citation: POCAMLA Amendment Act 2026 §44A
title:    SAR filing deadline reduced to 5 days for HIGH-RISK matters
severity: CRITICAL → auto-deadline 7 days
affected_engines: ["sar_filing"]
```

**Lifecycle:**
- DRAFT → OPEN (validated) → IN_PROGRESS (impact analysis) → CLOSED (with closure_evidence="POL-KYC-001 + POL-EDD-002 updated; staff trained 2026-06-30") → 4-entry transition_log
- Backward transition (OPEN → DRAFT) correctly **REJECTED_INVALID_TRANSITION**
- CLOSED without evidence correctly **REJECTED_REASON_REQUIRED**

---

## Tests — 30 across 10 classes

- **TestModuleShape** (5) — exists/parses/imports/4-enum-cardinalities/frozen
- **TestRegistryActivation** (1)
- **TestEngineHubIntegration** (1) — regulatory_change in Tier 30
- **TestStateMachine** (3) — DRAFT branches / OPEN→IN_PROGRESS only / terminals empty
- **TestRegister** (6) — DRAFT default / 7d/30d/90d deadlines per severity / empty citation rejected / empty owner rejected
- **TestTransitions** (6) — DRAFT→OPEN OK / backward rejected / WITHDRAWN-needs-reason / CLOSED-needs-evidence / full lifecycle 4-entry log / unknown id rejected
- **TestOverdueDetection** (1) — past-deadline non-CLOSED surfaced
- **TestHonestDeferrals** (2) — automated_feed DEFERRED + policy_linkage PARTIAL surface
- **TestPortfolioSummary** (1)
- **TestNoRegression** (4) — gates / count / v10.165 / v10.164

All 30 pass.

---

## AML/Compliance module progress: 7 of 9 (78%)

| Standard | Status | Engine | Drop |
|---|---|---|---|
| ENH-191 KYC/KYB Onboarding | active | kyc_onboarding | v10.160 |
| ENH-192 PEP & Sanctions Screening | active | screening_orchestrator + sanctions_screening | v10.161 (prior) |
| ENH-193 AML Transaction Monitoring | active | aml_monitoring + transaction_monitoring | v10.162 |
| ENH-194 SAR/STR Filing | active | sar_filing | v10.163 |
| ENH-198 Compliance Risk Assessment | active | compliance_risk_assessment | v10.164 |
| ENH-199 Examiner-Ready Reporting | active | examiner_reporting | v10.165 |
| **ENH-195 Regulatory Change Mgmt** | **active** | **regulatory_change** | **v10.166** |
| ENH-196 Policy Management & Attestation | planned | — | **v10.167 next** |
| ENH-197 Compliance Training | planned | — | future |

Two standards remaining. Module closure G152+G153 when all 9 active + cockpit + API + admin Tier 4C marker.

---

## Apply order

After v10.165:

```
1. utils/regulatory_change.py                     → utils/  (NEW)
2. utils/standards_registry.py                    → utils/  (REPLACES — ENH-195 active)
3. pages/7_admin.py                               → pages/  (Tier 30 extended)
4. tests/test_regulatory_change_v10_166.py        → tests/  (NEW)
5. docs/Master_Prompt_v3.59.md                    → docs/
6. SCOPE_LEDGER.md                                → root
7. CHANGELOG_v10.166.md                           → root
```

`git add -A && git commit -m "v10.166 ENH-195 Regulatory Change Management"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

---

## v10.167 next-up — ENH-196 Policy Management & Attestation

Natural next step. ENH-195 references policy IDs uni-directionally; ENH-196 makes the linkage bidirectional. Manages internal policy artifacts, attestation cycles, version control, ownership tracking. Sets up the bridge between ENH-195's regulatory drivers and the institution's actual policy implementation.

After ENH-196: ENH-197 Compliance Training Management. Module closure G152+G153 when all 9 active + cockpit + API.

---

## Summary

v10.166 ships ENH-195 Regulatory Change Management — inbound regulatory change tracking with severity-based attestation deadlines, forward-only state machine, audit-trail-mandate closure_evidence requirement, two honest deferrals (no programmatic CBK feed; uni-directional policy linkage pending ENH-196). 30 tests pass. AML cluster reaches 7/9 active.

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. `30/30 tests pass`.
