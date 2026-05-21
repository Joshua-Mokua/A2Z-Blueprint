# Changelog — v10.290 CIMS Batch 1: Capture & Classification

**Date:** 2026-05-08
**Phase:** 2B
**Audit:** 182/182 gates PASS = 100.0%
**G162 Rebase:** 3959 → 3967 (+8 KES; rationale: STP engine defines KES amount limits as Kenya-currency defaults)

---

## Summary

First of 4 CIMS arc batches. Activates 4 standards (#166, #167, #168,
#173) covering the entry layer of the Customer Instructions Management
System: how an instruction enters the bank, how its intent is
classified, how it's routed for STP vs manual processing, and how the
customer's identity is unified across systems.

11 active standards remain planned — all in CIMS arc:
v10.291 Batch 2 (#169, #170, #174, #175 — Process Intelligence & Prediction),
v10.292 Batch 3 (#171, #172, #176, #178 — Compliance & Audit),
v10.293 Batch 4 (#177, #179, #180 — Closure).

---

## Standards activated

| ID      | Name                                              | Subcategory | Risk |
|---------|---------------------------------------------------|-------------|------|
| ENH-166 | Omnichannel Instruction Capture Engine            | cims        | Cat C |
| ENH-167 | NLP Instruction Classification Engine             | cims        | Cat C |
| ENH-168 | Straight-Through Processing (STP) Engine          | cims        | Cat C |
| ENH-173 | Unified Customer Identity (Contact as Consumer)   | cims        | Cat C |

All four flipped status="active", implementation_batch="v10.290".

---

## Engine modules

### `utils/cims_omnichannel_capture.py` (#166)

`OmnichannelCaptureEngine` — cross-channel instruction capture session registry. Records originating channel, channel touches, handoffs between channels, and the overall capture lifecycle.

Byte-for-byte invariants:
- `CHANNELS` (8: BRANCH, MOBILE_APP, USSD, INTERNET_BANKING, CONTACT_CENTRE, EMAIL, RM_PORTAL, ATM)
- `CAPTURE_STATES` (5: INITIATED, IN_PROGRESS, HANDED_OFF, COMPLETED, ABANDONED) — Rule 4 (COMPLETED + ABANDONED terminal)
- `INSTRUCTION_TYPES` (8: ACCOUNT_OPENING, FUNDS_TRANSFER, CARD_REQUEST, LOAN_INQUIRY, COMPLAINT, STATEMENT_REQUEST, PROFILE_UPDATE, GENERAL_INQUIRY)
- `DEFAULT_CAPTURE_TIMEOUT_MINUTES = 30`
- `DEFAULT_ABANDONMENT_THRESHOLD_MINUTES = 60`

`capture_summary(session_id)` returns `is_omnichannel` flag — true when more than one channel has touched the session. This is the core CIMS metric for cross-channel continuity.

### `utils/cims_nlp_classification.py` (#167)

`NLPClassificationEngine` — NL request → intent classification → human override → confirmation registry. Diagnostic only (Rule 7) — never auto-acts on classified intent. The model itself is an external service; this engine owns the request lifecycle and the human-in-the-loop override flow.

Byte-for-byte invariants:
- `INTENT_CATEGORIES` (8: INFORMATION_REQUEST, ACCOUNT_OPERATION, COMPLAINT, APPLICATION_NEW, AMENDMENT_EXISTING, COMPLEX_INQUIRY, OUT_OF_SCOPE, AMBIGUOUS)
- `CONFIDENCE_TIERS` (4: HIGH, MEDIUM, LOW, UNKNOWN)
- `CLASSIFICATION_STATES` (5: SUBMITTED, CLASSIFIED, OVERRIDDEN, CONFIRMED, REJECTED) — Rule 4 (CONFIRMED + REJECTED terminal)
- `MODEL_VERSION_STATES` (4: CANDIDATE, ACTIVE, DEPRECATED, ARCHIVED) — Rule 4 (DEPRECATED → ARCHIVED only)
- `DEFAULT_CONFIDENCE_HIGH_THRESHOLD = 0.85`
- `DEFAULT_CONFIDENCE_MEDIUM_THRESHOLD = 0.65`
- `DEFAULT_CLASSIFICATION_TIMEOUT_SECONDS = 5`

`requests_below_confidence(threshold)` routes low-confidence classifications to manual review (consumed by #178 Agent Workspace in v10.292).

### `utils/cims_stp_engine.py` (#168)

`StraightThroughProcessingEngine` — STP routing decision registry. Read-side only — never auto-executes the instruction itself. The STP decision is a routing recommendation; actual execution flows through the relevant downstream banking engine.

Byte-for-byte invariants:
- `STP_DECISION_STATES` (5: EVALUATING, APPROVED_FOR_STP, REJECTED_FOR_STP, MANUAL_REVIEW, EXECUTED) — Rule 4 (EXECUTED terminal)
- `RISK_TIERS` (4: LOW, MEDIUM, HIGH, ENHANCED_DUE_DILIGENCE)
- `ELIGIBILITY_CRITERIA` (6: AMOUNT_THRESHOLD, CHANNEL_TRUST, CUSTOMER_RISK_TIER, INSTRUCTION_TYPE, KYC_FRESHNESS, BLACKLIST_CHECK)
- `REJECTION_REASONS` (5: EXCEEDS_AMOUNT_LIMIT, RISK_TIER_TOO_HIGH, KYC_STALE, BLACKLIST_HIT, ELIGIBILITY_RULE_FAILED)
- `DEFAULT_STP_AMOUNT_LIMIT_LOW_RISK = 100000` (KES)
- `DEFAULT_STP_AMOUNT_LIMIT_MEDIUM_RISK = 25000` (KES)
- `DEFAULT_KYC_FRESHNESS_DAYS = 365`

### `utils/cims_unified_identity.py` (#173)

`UnifiedIdentityEngine` — ServiceNow FSO-inspired unified identity model. Catalogues identity links across systems and tracks proposed merges through an explicit approval workflow. Never auto-merges.

Byte-for-byte invariants:
- `IDENTITY_LINK_TYPES` (8: CORE_BANKING_CUST_ID, MOBILE_APP_USER_ID, BIOMETRIC_ID, CONTACT_CENTRE_ID, SANCTIONS_SCREENING_ID, NATIONAL_ID, PASSPORT_NUMBER, CRM_LEAD_ID)
- `IDENTITY_STATES` (5: PROVISIONAL, VERIFIED, MERGED, ARCHIVED, FLAGGED) — Rule 4 (MERGED + ARCHIVED terminal)
- `MERGE_OUTCOMES` (4: PROPOSED, APPROVED, REJECTED, REVERSED) — Rule 4 (REJECTED + REVERSED terminal)
- `DEFAULT_MERGE_REVIEW_HOURS = 24`
- `DEFAULT_FLAGGED_REVIEW_HOURS = 4`

`pending_merges()` surfaces unresolved proposals for data steward review.

---

## Page

### `pages/105_cims_capture.py`

7 tabs (G4 ceiling, planned upfront):
1. Capture sessions — register + lifecycle + handoffs
2. Channel touches — record + sessions-by-channel listing
3. NLP classification — request, result, override, state transitions, below-confidence list
4. STP decisions — request + decision + transition + pending manual review
5. STP eligibility rules — register
6. Unified identity — identity + links + propose/approve/reject merge + pending merges
7. Metrics — NLP and STP side-by-side dashboard

Canonical imports throughout (G177):
```python
from utils.core_audit import audit_log
from pages._access import require_access
require_access("cims.cims_capture")
```

`audit_log()` calls use canonical signature `(action, username, module)` on every write surface — 16 distinct audit actions across the page.

---

## Audit gate

### G182 — `gate_cims_capture_classification_registered`

Locks 4 engines + 17 enum tuples + 9 default constants byte-for-byte across all four CIMS Batch 1 standards.

Checks:
1. All 4 modules import and expose their named engine classes.
2. 17 enum tuples byte-for-byte against the spec.
3. Rule 4 terminals across all four engines (CAPTURE_STATES, CLASSIFICATION_STATES, MODEL_VERSION_STATES, STP_DECISION_STATES, IDENTITY_STATES, MERGE_OUTCOMES).
4. All 9 default spec constants match.
5. ENH-166, ENH-167, ENH-168, ENH-173 are active and tagged v10.290.
6. Page 105 exists on disk.

---

## G162 ratchet

```
Before:    3959 (established_in v10.289)
After:     3967 (established_in v10.290)
Delta:     +8 (all KES)
Scope history entries: 44
```

The 8 new KES tokens come from the STP engine's two amount-limit constants (LOW_RISK=100000 KES, MEDIUM_RISK=25000 KES) being defined in the engine, echoed in the audit gate summary, the cockpit caption, the Tier 50 admin entry description, and the changelog. KES is the bank's default currency for retail STP decisions in Kenya.

---

## Tier registration

`Tier 50 — CIMS Batch 1: Capture & Classification (v10.290, Phase 2B)` added to `pages/7_admin.py` with all four engines documented.

---

## Manifest entry

`105_cims_capture.py` registered with all 7 required fields:
- `department_primary`: "cims"
- `module_path`: "cims.cims_capture"
- `current_module_key`: "cims_capture"
- `icon`: "📥"

G160 enforces; G177 confirms `require_access("cims.cims_capture")` resolves.

---

## Files in this release

```
utils/cims_omnichannel_capture.py             NEW (#166, ~340 lines)
utils/cims_nlp_classification.py              NEW (#167, ~410 lines)
utils/cims_stp_engine.py                      NEW (#168, ~370 lines)
utils/cims_unified_identity.py                NEW (#173, ~430 lines)
utils/standards_registry.py                   flipped #166/#167/#168/#173 active
scripts/audit.py                              +G182 gate_cims_capture_classification_registered
pages/7_admin.py                              +Tier 50
pages/105_cims_capture.py                     NEW (7-tab cockpit, 16 audit_log surfaces)
pages/_manifest.json                          +105 entry
data/audit_baselines.json                     g162 rebase to 3967
CHANGELOG_v10.290.md                          NEW (this document)
```

---

## Audit summary

```
  Score: 182/182 gates = 100.0% — PASS
```

319 of 330 standards active. CIMS arc 4/15 complete. 11 standards remain planned — all in CIMS.

Next batch: **v10.291 — CIMS Batch 2: Process Intelligence & Prediction (#169, #170, #174, #175)**.
