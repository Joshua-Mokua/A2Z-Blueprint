# CHANGELOG v10.168 — ENH-197 Compliance Training Management

**Status:** Ninth and final standard of the AML/Compliance cluster. **AML CLUSTER 9/9 ACTIVE — 100% STANDARDS COMPLETE.** Greenfield engine. Last drop before v10.169 module closure ceremony.

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged). G142 anti-drift floor 83→84. Active standards 185→186. v10.168 tests 37/37 pass.

---

## Headline: AML cluster 9/9 active

| Standard | Engine | Drop |
|---|---|---|
| ENH-191 KYC/KYB Onboarding | kyc_onboarding | v10.160 |
| ENH-192 PEP & Sanctions Screening | screening_orchestrator + sanctions_screening | v10.161 |
| ENH-193 AML Transaction Monitoring | aml_monitoring + transaction_monitoring | v10.162 |
| ENH-194 SAR/STR Filing | sar_filing | v10.163 |
| ENH-198 Compliance Risk Assessment | compliance_risk_assessment | v10.164 |
| ENH-199 Examiner-Ready Reporting | examiner_reporting | v10.165 |
| ENH-195 Regulatory Change Mgmt | regulatory_change | v10.166 |
| ENH-196 Policy Management & Attestation | policy_management | v10.167 |
| **ENH-197 Compliance Training Management** | **compliance_training** | **v10.168** |

**v10.169 next: module closure ceremony** with G152 (module_closed) + G153 (ui_integrated) audit gates — same pattern as Treasury G150/G151.

---

## What this drop ships

| Artifact | Purpose |
|---|---|
| `utils/compliance_training.py` (~520 LOC) | NEW. Course catalogue + assignment lifecycle + certifications |
| `utils/standards_registry.py` (1 line) | ENH-197 'planned'→'active' |
| `pages/7_admin.py` (Tier 30 extended) | compliance_training added |
| `tests/test_compliance_training_v10_168.py` (~430 LOC, 37 tests) | NEW |
| `docs/Master_Prompt_v3.61.md` | Anti-drift sync v3.60 → v3.61 |
| `SCOPE_LEDGER.md` | v10.168 row |
| `CHANGELOG_v10.168.md` | This document |

---

## Engine surface

**4 enums:**
- `CourseStatus` (3): DRAFT / PUBLISHED / RETIRED
- `AssignmentStatus` (4): ASSIGNED / COMPLETED / FAILED / WITHDRAWN
- `CourseLifecycleOutcome` (3): OK / REJECTED_INVALID_TRANSITION / REJECTED_NOT_FOUND
- `AssignmentOutcome` (5): OK / REJECTED_COURSE_NOT_PUBLISHED / REJECTED_NOT_FOUND / REJECTED_ALREADY_TERMINAL / REJECTED_REASON_REQUIRED

**3 frozen dataclasses:**
- `CertificationRecord` — issued on COMPLETED assignment (employee_id, course_id, expiry_date, score, evidence)
- `Course` — course definition (course_id, version, mandatory_for_roles, validity_days, pass_score, related_policy_ids, related_regulatory_change_ids)
- `Assignment` — employee × course pairing (status, score, certification reference)

### Two distinct entities

**Course** — the catalogue. `(course_id, version)` is the unique key. Annual refresher logic handled by versioning the course (CBT-AML-101 v1.0 superseded by v2.0 etc.). 

**Assignment** — the per-employee instance. Each assignment has a unique `assignment_id`. Same employee can have multiple assignments to the same course over time (annual cycle).

### Course lifecycle

```
DRAFT → PUBLISHED → RETIRED
```

Cannot assign DRAFT course (engine returns REJECTED_COURSE_NOT_PUBLISHED).

### Assignment lifecycle

```
ASSIGNED ─┬─→ COMPLETED  (score >= pass_score; cert issued)
           ├─→ FAILED     (score < pass_score; no cert)
           └─→ WITHDRAWN  (cancelled before completion; reason required)
```

All three terminal states. Cannot re-complete.

### Certifications auto-issued on COMPLETED

```python
expiry_date = completed_at + timedelta(days=course.validity_days)
```

Default `validity_days=365` (annual cadence per CBK PG/15 §7). Per-course configurable.

`expiring_certifications(window_days=30)` returns certifications expiring within 30 days — drives renewal scheduling.

---

## Pass-score discipline

`complete(assignment_id, score, evidence)` evaluates:

```python
if score >= course.pass_score:   # default pass_score = 70
    status = COMPLETED
    certification = CertificationRecord(...)   # issued
else:
    status = FAILED
    certification = None
```

Evidence is **mandatory** — engine returns REJECTED_REASON_REQUIRED if blank. The evidence captures LMS course completion ID, attempted-via-method label, etc. Actual e-signature/LMS integration deferred (see honest deferrals below).

---

## Bidirectional linkage trio: ENH-195 ↔ ENH-196 ↔ ENH-197

After v10.167 completed ENH-195↔ENH-196 with `policies_for_change()`, v10.168 closes the trio:

| Reverse-lookup | Returns |
|---|---|
| `courses_for_change(change_id)` | All courses linked to that regulatory change |
| `courses_for_policy(policy_id)` | All courses training on that policy |
| `assignments_for_employee(employee_id)` | All assignments for that employee |
| `assignments_for_role(role)` | All assignments for that role |

The full trio:

```
Regulatory Change (ENH-195)
       ↓ change.affected_policies / change.affected_engines (uni)
       ↓ policies_for_change()                              (rev)
       ↓ courses_for_change()                               (rev)
       
Policy (ENH-196)
       ↓ policy.related_change_ids                          (uni back to ENH-195)
       ↓ courses_for_policy()                               (rev to ENH-197)
       
Course (ENH-197)
       ↓ course.related_policy_ids                          (uni back to ENH-196)
       ↓ course.related_regulatory_change_ids               (uni back to ENH-195)
```

A regulator examiner can ask: "this CBK PG/15 amendment came in last quarter — show me all your downstream changes." The answer flows: `policies_for_change('REG-000001')` returns updated policies; `courses_for_change('REG-000001')` returns the AML refresher course updated to cover the new requirement; `assignments_for_role('teller')` returns all tellers who must complete it. **The trio of reverse-lookups makes the regulatory-change → policy-update → staff-training chain auditable end-to-end.**

---

## 2 honest deferrals

### lms_integration_status — DEFERRED
> *"Engine does NOT integrate with Learning Management Systems (Moodle, Cornerstone, Workday Learning, SuccessFactors). Operators record completions via complete() API. Future increment can wire LMS webhooks; out of scope for v10.168."*

### course_content_status — META_ONLY
> *"Engine tracks course metadata (title, description, validity, pass_score) and assignment lifecycle. Actual course content (videos, slides, quiz questions) is operator-side, hosted in an LMS or document repository. v10.168 ships meta-only."*

Same discipline as throughout the AML cluster: engine ships what it can do well, surfaces what it doesn't do explicitly.

---

## End-to-end probe

Realistic Ecobank Kenya scenario:

```
Register: CBT-AML-101 v2.0 — "AML Fundamentals — Annual Refresher"
          owner_role: head_of_compliance
          mandatory_for_roles: ('teller', 'branch_manager', 'compliance_officer')
          validity_days: 365
          pass_score: 80
          related_policy_ids: ('POL-AML-001',)
          related_regulatory_change_ids: ('REG-000001',)

Lifecycle: DRAFT → PUBLISHED (status=PUBLISHED)

Try assign DRAFT course (CBT-FRAUD-101 v1.0)
  → REJECTED_COURSE_NOT_PUBLISHED

Assign EMP-001 (teller) → ASN-000001 status=ASSIGNED, due_date 30d out

Complete without evidence
  → REJECTED_REASON_REQUIRED

Complete (score=85, evidence='LMS course completion ID #12345')
  → status=COMPLETED, certification.expiry_date=2027-05-06 (1 year out)

Re-complete (score=90) → REJECTED_ALREADY_TERMINAL

Assign EMP-002 (teller) → ASN-000002
Complete (score=60)  # below pass_score 80
  → status=FAILED, certification=None

Reverse lookups:
  courses_for_change('REG-000001') → 1 course
  courses_for_policy('POL-AML-001') → 1 course
```

**Final state**: 2 courses (1 PUBLISHED, 1 DRAFT); 2 assignments (1 COMPLETED with cert, 1 FAILED); 1 active certification.

---

## Tests — 37 across 12 classes

- **TestModuleShape** (4) — exists/parses/imports/4-enum-cardinalities/frozen
- **TestRegistryActivation** (1)
- **TestEngineHubIntegration** (2) — compliance_training in hub / **all 9 AML engines in Tier 30**
- **TestCourseLifecycle** (4) — DRAFT default / publish / published→retired / retired terminal
- **TestRegisterCourse** (4) — empty rejected / invalid validity / invalid pass_score / duplicate version
- **TestAssignment** (3) — DRAFT course rejected / published works / unknown rejected
- **TestComplete** (5) — empty evidence rejected / pass→COMPLETED+cert / fail→FAILED+no cert / cert expiry correct / re-complete terminal rejected
- **TestWithdraw** (2) — empty reason / with reason
- **TestQueries** (4) — for_employee / for_role / **courses_for_change** / **courses_for_policy**
- **TestOverdueAndExpiring** (1) — past-due ASSIGNED surfaced
- **TestHonestDeferrals** (2) — LMS DEFERRED + course_content META_ONLY
- **TestPortfolioSummary** (1)
- **TestNoRegression** (4) — gates / count / v10.167 / v10.166

All 37 pass.

---

## v10.169 next-up — AML/Compliance MODULE CLOSURE CEREMONY

After v10.168, all 9 AML cluster standards are active. The closure work mirrors Treasury G150/G151 from v10.155:

1. **`pages/27_compliance_arc_cockpit.py`** (NEW) — module cockpit page with ≤7 sub-tabs covering all 9 engine surfaces (KYC + Sanctions + AML Monitoring + SAR Filing + Risk Assessment + Examiner Reporting + Reg Change + Policy + Training)
2. **`utils/api_compliance.py`** (NEW) — module API exposing endpoints across the 9 engines
3. **`pages/7_admin.py`** — AML/Compliance Tier 4C closure marker (after Treasury Tier 4C from v10.155)
4. **`scripts/audit.py`** — G152 (module_closed) + G153 (ui_integrated) audit gates

After v10.169: AML/Compliance module FULLY CLOSED. Active standards count goes from 186 to 188 (+2 closure standards). G142 anti-drift floor goes 84→86. Audit count goes 151→153.

---

## Summary

v10.168 ships ENH-197 Compliance Training Management — the last greenfield AML engine. Two distinct entities (Course catalogue + Assignment instances), pass-score discipline, auto-issued certifications with expiry, bidirectional reverse-lookups completing the ENH-195↔196↔197 linkage trio, 2 honest deferrals (LMS integration + course content). 37 tests pass. **AML cluster reaches 9/9 active — 100% standards complete. v10.169 module closure ceremony queued.**

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. `37/37 tests pass`. **AML CLUSTER 9/9 ACTIVE.**
