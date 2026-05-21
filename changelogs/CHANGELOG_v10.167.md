# CHANGELOG v10.167 — ENH-196 Policy Management & Attestation

**Status:** Eighth active standard of the AML/Compliance cluster. Greenfield engine. **AML cluster reaches 8/9 — one drop from module closure.**

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged). G142 anti-drift floor 82→83. Active standards 184→185. v10.167 tests 37/37 pass.

---

## What this drop ships

| Artifact | Purpose |
|---|---|
| `utils/policy_management.py` (~520 LOC) | NEW. Versioned policy repository + attestation tracking |
| `utils/standards_registry.py` (1 line) | ENH-196 'planned'→'active' |
| `pages/7_admin.py` (Tier 30 extended) | policy_management added |
| `tests/test_policy_management_v10_167.py` (~440 LOC, 37 tests) | NEW |
| `docs/Master_Prompt_v3.60.md` | Anti-drift sync v3.59 → v3.60 |
| `SCOPE_LEDGER.md` | v10.167 row |
| `CHANGELOG_v10.167.md` | This document |

---

## Engine surface

**3 enums:**
- `PolicyStatus` (5): DRAFT / IN_REVIEW / ACTIVE / SUPERSEDED / RETIRED
- `TransitionOutcome` (4): OK / REJECTED_INVALID_TRANSITION / REJECTED_REASON_REQUIRED / REJECTED_NOT_FOUND
- `AttestationOutcome` (4): OK / REJECTED_POLICY_NOT_ACTIVE / REJECTED_EVIDENCE_REQUIRED / REJECTED_POLICY_NOT_FOUND

**2 frozen dataclasses:**
- `AttestationRecord` — single attestation event (attestor_id, attested_at_utc, evidence, next_attestation_due_utc)
- `Policy` — full metadata + transition_log + attestations tuple + bidirectional linkage via related_change_ids

### Unique key — (policy_id, version_id)

Same logical policy can have multiple versions. v3.0 supersedes v2.0 via the `supersedes_version_id` field. Engine maintains the version chain.

### State machine

```
DRAFT ─┬─→ IN_REVIEW ─┬─→ ACTIVE ─┬─→ SUPERSEDED
       │              ├─→ DRAFT     └─→ RETIRED
       │              │  (revisions
       │              │   from review)
       │              └─→ RETIRED
       └─→ RETIRED
```

**IN_REVIEW → DRAFT loopback is intentional**: committees frequently surface revisions that need re-drafting before approval. Cleaner than forcing a brand-new version_id for every revision pass.

### Engine API

```python
class PolicyManagementEngine:
    def register_policy(policy_id, version_id, title, summary,
                          owner_role, content_hash, effective_date,
                          attestor_ids, attestation_cycle_days=365,
                          related_change_ids=(), supersedes_version_id="")
    def transition(policy_id, version_id, new_status, user, reason="")
    def record_attestation(policy_id, version_id, attestor_id, evidence)
    def policy_by_version(policy_id, version_id) → Policy
    def all_policies() → Tuple
    def active_policies() → Tuple
    def overdue_attestations() → Tuple
    def policies_for_change(change_id) → Tuple   # ENH-195 reverse-lookup
    def board_summary() → Dict
```

---

## Bidirectional linkage with ENH-195 completed

ENH-195 references policies via `affected_policies` tuple of strings (uni-directional). v10.167's `policies_for_change(change_id)` returns all policy versions whose `related_change_ids` contains that change_id — completing the **regulatory_change ↔ policy** symmetry.

```python
# ENH-195: "Which policies does this regulatory change affect?"
change.affected_policies                          # ['POL-KYC-001', 'POL-EDD-002']

# ENH-196: "Which policies link back to this regulatory change?"
policy_engine.policies_for_change('REG-000001')   # (POL-KYC-001 v3.0, POL-EDD-002 v2.1)
```

The two engines stay independent (no hard import dependency) but operators can wire the linkage at registration time + query both directions.

---

## Attestation cycles

- **Default 365 days** (annual cadence per CBK PG/01 §3 corporate governance expectations)
- **Per-policy configurable** via `attestation_cycle_days` parameter
- Each attestation produces an `AttestationRecord` with `next_attestation_due_utc` auto-computed = `attested_at_utc + cycle_days`
- `overdue_attestations()` returns ACTIVE policies where any attestor's latest attestation is past `next_attestation_due_utc` (or never attested + activated_at + cycle_days ago)
- Per-attestor independent cadence: if a policy has 2 attestors and one is overdue, the policy surfaces in the overdue list

---

## 2 honest deferrals

### document_storage_status — META_ONLY
> *"Engine tracks policy metadata (title, version, owner, content_hash for tamper detection). Actual policy PDF/document storage is operator-side via existing `utils/document_management.py` engine. v10.167 ships meta-only; wiring document_management bidirectional is future work."*

The `content_hash` field provides tamper detection without storage — operators verify the hash against their document repository.

### esignature_verification_status — DEFERRED
> *"Attestation evidence field accepts free-text (signature method label, signed-by-method). Actual digital signature verification (DocuSign API, X.509 certificate validation, ZetaWord) is operator-side. v10.167 ships evidence capture; signature verification is future work."*

The `evidence` field captures the signature method as text (e.g., "DocuSign envelope #ABC-2026-001"). Real verification — calling DocuSign's API to confirm the envelope is signed and not tampered with — is operator-side integration.

---

## End-to-end probe

Realistic Kenya scenario:

```
Register: POL-KYC-001 v3.0 — "Customer Due Diligence — Cash-Intensive Businesses"
          owner: head_of_compliance
          attestors: head_of_compliance + head_of_risk
          related_change_ids: ('REG-000001',)  # links to ENH-195

Lifecycle: DRAFT → IN_REVIEW (committee circulation)
                 → ACTIVE  (board approved; activated_at_utc recorded)

Attestation w/o evidence → REJECTED_EVIDENCE_REQUIRED
Attestation with evidence "DocuSign envelope #ABC-2026-001 signed 2026-07-15"
  → OK; next_due = today + 365 days = 2027-05-06

Reverse lookup: policies_for_change('REG-000001') → 1 policy (POL-KYC-001)
```

Bidirectional linkage works. Lifecycle works. Attestation works.

---

## Tests — 37 across 11 classes

- **TestModuleShape** (5)
- **TestRegistryActivation** (1)
- **TestEngineHubIntegration** (1)
- **TestStateMachine** (4) — DRAFT branches / IN_REVIEW loopback to DRAFT / ACTIVE branches / terminals empty
- **TestRegister** (8) — DRAFT default / 365d default / custom cycle / empty-policy-id rejected / empty-attestors rejected / zero-cycle rejected / duplicate version rejected / **two versions of same policy_id allowed**
- **TestTransitions** (5) — DRAFT→IN_REVIEW / DRAFT→ACTIVE rejected (no skip) / IN_REVIEW→DRAFT loopback / ACTIVE records activated_at / RETIRED requires reason
- **TestAttestation** (4) — non-active rejected / requires evidence / records next_due / unknown policy rejected
- **TestBidirectionalLinkage** (1) — policies_for_change returns linked, unknown returns empty
- **TestOverdueAttestations** (1) — backdated activation surfaces overdue
- **TestHonestDeferrals** (2) — document_storage META_ONLY + esignature DEFERRED
- **TestPortfolioSummary** (1)
- **TestNoRegression** (4) — gates / count / v10.166 / v10.165

All 37 pass.

---

## AML/Compliance module progress: 8 of 9 (89%)

| Standard | Status | Engine | Drop |
|---|---|---|---|
| ENH-191 KYC/KYB Onboarding | active | kyc_onboarding | v10.160 |
| ENH-192 PEP & Sanctions Screening | active | screening_orchestrator + sanctions_screening | v10.161 |
| ENH-193 AML Transaction Monitoring | active | aml_monitoring + transaction_monitoring | v10.162 |
| ENH-194 SAR/STR Filing | active | sar_filing | v10.163 |
| ENH-198 Compliance Risk Assessment | active | compliance_risk_assessment | v10.164 |
| ENH-199 Examiner-Ready Reporting | active | examiner_reporting | v10.165 |
| ENH-195 Regulatory Change Mgmt | active | regulatory_change | v10.166 |
| **ENH-196 Policy Management & Attestation** | **active** | **policy_management** | **v10.167** |
| ENH-197 Compliance Training Management | planned | — | **v10.168 next (LAST)** |

**One standard remaining.** After v10.168 (ENH-197): module closure with G152+G153 gates — module cockpit + module API + admin Tier 4C marker. Same pattern as Treasury G150/G151.

---

## Apply order

After v10.166:

```
1. utils/policy_management.py                     → utils/  (NEW)
2. utils/standards_registry.py                    → utils/  (REPLACES — ENH-196 active)
3. pages/7_admin.py                               → pages/  (Tier 30 extended)
4. tests/test_policy_management_v10_167.py        → tests/  (NEW)
5. docs/Master_Prompt_v3.60.md                    → docs/
6. SCOPE_LEDGER.md                                → root
7. CHANGELOG_v10.167.md                           → root
```

`git add -A && git commit -m "v10.167 ENH-196 Policy Management & Attestation"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

---

## v10.168 next-up — ENH-197 Compliance Training Management (LAST AML STANDARD)

The final standard before module closure. Tracks compliance training assignments per role/employee, course catalogues, completion records, expiry dates, certifications. Wires into FFIEC examination Training module (currently DEFERRED in ENH-199's ExaminerReportingEngine).

After v10.168: **v10.169 module closure** with G152 (module_closed) + G153 (ui_integrated) gates — module cockpit + module API + admin Tier 4C marker. Same closure pattern as Treasury G150/G151.

---

## Summary

v10.167 ships ENH-196 Policy Management & Attestation — versioned policy repository with attestation cycles. Greenfield engine: 3 enums, 2 frozen dataclasses, (policy_id, version_id) unique key supporting multi-version chains, state machine with IN_REVIEW→DRAFT loopback for committee revisions, attestation cycles (365d default, per-policy configurable), bidirectional linkage with ENH-195 via `policies_for_change()` reverse-lookup, 2 honest deferrals (document storage META_ONLY, e-signature verification DEFERRED). 37 tests pass. AML cluster 8/9 active.

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. `37/37 tests pass`.
