# Changelog — v10.292 CIMS Batch 3: Compliance & Audit

**Date:** 2026-05-08
**Phase:** 2B
**Audit:** 184/184 gates PASS = 100.0%
**G162 Rebase:** 3967 → 3983 (+16; +12 CBK references and +4 KRA
references introduced by the regulatory/document modules and their
audit/admin/cockpit text). Established_in updated to v10.292.

---

## Summary

Third of 4 CIMS arc batches. Activates 4 standards (#171, #172, #176,
#178) covering the compliance and audit layer of the Customer
Instructions Management System: how regulatory SLAs are tracked
(Reg E / Reg Z / CBK Banking Act), how PAN tokens and document vault
references are catalogued without ever storing raw PAN or raw
document bytes, how every upstream lifecycle event flows into an
append-only audit history with supersede-not-replace corrections,
and how agents pick work off a unified queue with skill-based
routing.

3 active standards remain in the CIMS arc, all in Batch 4:
  • v10.293 Batch 4 (#177 Self-Service Portal, #179 Analytics
    Dashboard, #180 Feedback Loop)

---

## Standards activated

| Standard | Name | Engine |
|----------|------|--------|
| #171 | Regulatory SLA Enforcement Engine | `cims_regulatory_sla` |
| #172 | Secure Document & PAN Management | `cims_secure_pan_documents` |
| #176 | Audit-Ready Instruction History | `cims_audit_ready_history` |
| #178 | Agent Workspace for Instruction Processing | `cims_agent_workspace` |

---

## Files changed

  • utils/cims_regulatory_sla.py — NEW. REGULATORY_FRAMEWORKS (5:
    REG_E/REG_Z/CBK_BANKING_ACT/CBK_PRUDENTIAL/DPA_KENYA_2019) +
    SLA_DEFINITION_STATES (4) Rule 4 + OBLIGATION_STATES (5) Rule 4
    with FULFILLED/BREACHED/CANCELLED terminals + OBLIGATION_EVENT_TYPES
    (5: DEADLINE_REGISTERED/REMINDER_SENT/DEADLINE_APPROACHING/
    DEADLINE_BREACHED/FULFILLED_RECORDED) + SLA_BREACH_SEVERITIES (4) +
    INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS (DISPUTE_INVESTIGATION=240,
    BILLING_ERROR=720, CUSTOMER_COMPLAINT=120, GENERAL_INQUIRY=48,
    REGULATORY_REPORTING=168) + reminder=24h + approaching=4h.
    breach_report identifies both EXPLICITLY_BREACHED state and
    PAST_DEADLINE_NOT_FULFILLED implicit breaches. upcoming_deadlines
    surfaces obligations within the configurable horizon.

  • utils/cims_secure_pan_documents.py — NEW. PAN_TOKEN_STATES (4) Rule 4
    + DOCUMENT_STATES (5) Rule 4 with VERIFIED/REJECTED/ARCHIVED
    terminals + DOCUMENT_TYPES (8: NATIONAL_ID/PASSPORT/
    KRA_PIN_CERTIFICATE/UTILITY_BILL/BANK_STATEMENT/
    BUSINESS_REGISTRATION/PROOF_OF_INCOME/OTHER) + ACCESS_EVENT_TYPES
    (5) + PAN_FIELD_KINDS (3: TOKEN/LAST_FOUR/BIN) + token_ttl=365d +
    retention=7y + PCI_DSS_RAW_PAN_PROHIBITED=True. _looks_like_raw_pan
    helper performs Luhn check on cleaned digit runs PLUS scans for
    embedded PANs in narrative text. LAST_FOUR enforced 4 digits, BIN
    enforced 6 digits. All four register/transition entry points
    reject any field that looks like a raw PAN.

  • utils/cims_audit_ready_history.py — NEW. HISTORY_RECORD_KINDS (8)
    + ALLOWED_CORRECTION_REASONS (5: DATA_QUALITY_CORRECTION/
    IDENTITY_REASSIGNMENT/REGULATORY_DIRECTIVE/AUDIT_FINDING/
    OPERATIONAL_ERROR) + EXAMINER_QUERY_TYPES (5: SAR_TRACE/
    DISPUTE_TRACE/COMPLIANCE_REVIEW/REGULATORY_INSPECTION/
    INTERNAL_AUDIT_REQUEST) + EXAMINER_RESPONSE_OUTCOMES (4: PROVIDED/
    PARTIAL_PROVIDED/REQUEST_DENIED/IN_PROGRESS) +
    COMPLIANCE_REVIEW_OUTCOMES (4: PASSED/OBSERVATIONS/FINDINGS/
    ESCALATED) + retention=7y + IMMUTABILITY_NOTE module-level
    constant. Records are append-only; corrections are themselves
    new records that reference (not replace) the original; corrections
    require supersedes_record_id to point at an existing history
    record.

  • utils/cims_agent_workspace.py — NEW. AGENT_STATES (5) Rule 4 +
    WORK_ITEM_STATES (6) Rule 4 with COMPLETED/CANCELLED terminals +
    WORK_ITEM_PRIORITIES (4: URGENT/HIGH/NORMAL/LOW) +
    WORK_ITEM_SOURCES (5: CAPTURE_HANDOFF/EXCEPTION_RAISED/
    SLA_APPROACHING/DROPOUT_INTERVENTION/MANUAL_ESCALATION) +
    AGENT_ACTION_KINDS (8) + AGENT_SKILL_TAGS (5: KYC_REVIEW/
    COMPLAINT_HANDLING/DISPUTE_RESOLUTION/LOAN_PROCESSING/GENERAL) +
    reassignment=4h + break_limit=60min + queue_depth_threshold=50.

  • pages/107_cims_compliance.py — NEW. 7-tab cockpit at G4 ceiling
    covering all 4 engines: SLA definitions, SLA obligations + breach
    report + upcoming deadlines, PAN tokens + inventory, documents +
    access events, audit history + corrections + per-session query,
    examiner queries + reviews + summary, agent workspace + queue
    summary + workload-by-agent. Uses
    `require_access("operations.cims_compliance")` and `audit_log()`
    after every write.

  • scripts/audit.py — added gate_cims_compliance_audit_registered()
    (G184) locking all 4 engines + every enum tuple + every constant
    + every Rule 4 transition map + Luhn helper round-trip checks.
    Registered G184 in GATES tuple.

  • pages/7_admin.py — added Tier 52 with all 4 engine entries.

  • pages/_manifest.json — added 107_cims_compliance.py entry with
    all 7 required fields (department_primary=operations,
    module_path=operations.cims_compliance, secondary_visibility=
    __all_admins__, title, icon, description, current_module_key).

  • utils/standards_registry.py — flipped #171, #172, #176, #178 to
    status="active", implementation_batch="v10.292".

  • data/audit_baselines.json — G162 rebased: 3967 → 3983
    (+12 CBK, +4 KRA). 44 → 45 scope_history entries.

  • CHANGELOG_v10.292.md — this file.

---

## CIMS arc progress

| Batch | Version | Standards | Status |
|-------|---------|-----------|--------|
| 1 | v10.290 | #166, #167, #168, #173 | shipped |
| 2 | v10.291 | #169, #170, #174, #175 | shipped |
| 3 | v10.292 | #171, #172, #176, #178 | **shipped** |
| 4 | v10.293 | #177, #179, #180 | next |

CIMS arc 12/15 complete after this drop.

---

## Audit gates

| Gate | Status | Notes |
|------|--------|-------|
| G160 (manifest) | PASS | 111 pages, 16 departments, all required fields |
| G162 (tenant) | PASS | rebased 3967 → 3983 (+16 CBK/KRA from CIMS Batch 3) |
| G177 (imports) | PASS | canonical imports verified |
| G182 (CIMS B1) | PASS | locked from v10.290 |
| G183 (CIMS B2) | PASS | locked from v10.291 |
| G184 (CIMS B3) | PASS | NEW — 4 engines registered, all enums + constants byte-for-byte |

---

## Platform state

  • Audit: **184/184 gates = 100.0% PASS**
  • Standards active: **327/330** (4 newly active: #171, #172, #176, #178)
  • Standards remaining: 3 (all CIMS Batch 4: #177, #179, #180)
  • Audit gate count: G1 → G184 (184 total)
  • Engine Hub: 52 tiers
  • Pages: 111 (manifest entries match)

---

## Cluster invariants verified

  ✅ One ZIP per cluster (4 engines + 1 page + audit + admin + manifest + standards + baselines + changelog)
  ✅ All audit_log() calls after write operations
  ✅ All page-level require_access() uses dotted manifest path
  ✅ Canonical imports throughout: `from utils.core_audit import audit_log` and `from pages._access import require_access`
  ✅ ≤7 tabs per page (page 107 uses exactly 7)
  ✅ Standards registry status="active" + batch="v10.292" for all 4
  ✅ G184 added linearly (no gate ID reuse)
  ✅ Tier 52 added in admin (no tier reuse)
  ✅ Manifest entry for page 107 has all 7 required fields
  ✅ G162 rebased with full scope_history entry including rationale and per-token deltas
