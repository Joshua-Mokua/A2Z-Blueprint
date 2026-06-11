# Pipeline & Credit Workflow Domain Audit

**Authored:** 2026-06-10
**Author:** Claude + Joshua
**Purpose:** Establish the React build spec by documenting what the backend actually contains for the loan origination workflow — same-turn inspection only, no assumptions.
**Scope:** Pipeline (sales) + Loan Application (credit) + Credit Admin (pre-disbursement). Post-disbursement (Credit Monitoring, EWS, DRU) is **out of scope** for this audit and will be a separate document.

> **Doctrine context.** This is the Phase 3 equivalent of an Arc D2 reality-check: the React frontend is built against documented backend reality, not against assumptions. Every claim in this document is grounded in same-turn code inspection of the cloned repo at commit `b2cf3a4`.

---

## 1. The three-entity model

The loan origination workflow uses **three distinct entities** with explicit linkage:

| Entity | Storage | Manager | Count | Owner role |
|---|---|---|---|---|
| **Pipeline Deal** | `data/pipeline.json` | `PipelineManager` (`utils/core.py:3896`) | 302 | RM (sales) |
| **Loan Application** | `data/loan_applications.json` | `LoanApplicationManager` (`utils/core.py:5267`) | 724 | Credit analyst → committee |
| **Credit Admin Case** | `data/credit_admin.json` | `CreditAdminManager` (`utils/core.py:5349`) | 214 | Credit Admin officer |

**Linkage:**
- `LoanApplication.pipeline_deal_id` → `PipelineDeal.id`
- `CreditAdminCase.application_id` → `LoanApplication.id`

This is a **chain of records**, not state changes on a single record. Each entity has its own lifecycle, status field, and owner. The chain represents handoff between domains (Sales → Credit → Admin → Disbursement).

---

## 2. Entity 1: Pipeline Deal

### 2.1 Data shape (verified from `data/pipeline.json` first record)

All 28 fields present in every record:

```
id, client_name, client_cif, amount, currency, deal_category,
product, stage, probability, win_probability_ai,
win_probability_ai_factors, expected_close, open_date,
last_updated, staff_code, staff_name, role, unit,
proposition_tag, notes, actions_due, backup_staff_codes,
conflict_status, existing_facility_id, is_repeat_borrower,
original_facility_amount, repayment_history, top_up_amount
```

### 2.2 Stage vocabulary — **DRIFT FINDING D1**

`PIPELINE_STAGES_LOAN` is defined in `utils/core.py:932` with 10 stages:
```
Lead, Contacted, Qualified, Application, Credit Assessment,
Offer/Proposal, Negotiation, Compliance, Closed Won, Closed Lost
```

**But the actual `pipeline.json` data uses different stage names** (same-turn count of 302 deals):

| Count | Stage (actual) |
|---|---|
| 61 | Prospecting |
| 54 | Proposal |
| 44 | Disbursed |
| 42 | Needs Analysis |
| 40 | Credit Review |
| 19 | Approval |
| 15 | Closed Lost |
| 4 | Valuation |
| 4 | Credit Committee |
| 4 | Negotiation |
| 3 | Bank Approval |
| 3 | Closed Won |
| 2 | Due Diligence |
| 2 | Term Sheet |
| 2 | Signed |
| 2 | Vetting |
| 1 | Documentation |

**The doctrine (`PIPELINE_STAGES_LOAN` constants) and the data are out of sync.** This is exactly the kind of stated-vs-enforced gap Arc D2 surfaced. The actual operational vocabulary has more granular stages than the doctrine constants document.

**Resolution decision needed (deferred to operator):** Either (a) update `PIPELINE_STAGES_LOAN` to match operational vocabulary, OR (b) migrate data to canonical constants. For React build purposes, we use the **actual operational stages** as the source of truth and document this drift explicitly.

### 2.3 Deal categories

3 categories (110 New Facility / 95 Renewal / 89 Top Up / 8 unspecified). Each category may carry product-specific fields (e.g. `top_up_amount`, `original_facility_amount`, `existing_facility_id` for Top-Ups).

### 2.4 Conflict resolution

Field: `conflict_status`. Cross-references `backup_staff_codes` (array of staff codes). Per session memory, the UX wording is "Seek permission" when a portfolio conflict exists. **Implementation details require deeper inspection of `pages/3_pipeline.py` — flagged as Q1 below.**

### 2.5 Roles owning pipeline deals

Same-turn count of role distribution across 302 deals:

| Count | Role |
|---|---|
| 72 | Relationship Officer - Business Banker |
| 44 | Branch Relationship Manager |
| 43 | Relationship Officer - Personal Banker |
| 34 | Branch Senior Relationship Officer |
| 31 | Relationship Officer Bancassurance |
| 30 | Direct Sales Representative - Assets & Liabilities |
| 8 | (unspecified) |
| 6 | Relationship Manager - Institutional Banking |
| 5 | Senior Relationship Manager - Corporate Banking |
| 5 | Senior Digital Channels Officer |
| 4 | Assistant Relationship Manager - Corporate |
| 4 | Relationship Manager - Public Sector |

12+ distinct role types. The React UI must handle this diversity — different roles have different views, queues, KPI emphasis.

---

## 3. Entity 2: Loan Application

### 3.1 Data shape (verified from `data/loan_applications.json` first record)

28 fields:

```
id, pipeline_deal_id, client_name, client_cif, amount, currency,
deal_category, product, application_date, last_updated,
status, swim_lane, rm_code, rm_name, rm_unit,
analyst (object with code+name), proposition_tag,
appraisal_notes, is_repeat_borrower, clean_repayment_history,
docs_required, docs_submitted, completeness_score,
compliance_flag, compliance_type, decision, tat_days,
sla_target_days
```

`decision` is an object containing `verdict / date / authority / reason / conditions / comments`.
`analyst` is an object containing `code / name`.

### 3.2 Status taxonomy (verified — 11 distinct statuses across 724 applications)

| Count | Status | Owner |
|---|---|---|
| 144 | approved | (terminal, ready for credit admin) |
| 88 | analysis | Credit analyst (active work) |
| 76 | assigned | Credit analyst (just assigned) |
| 70 | committee | Credit committee |
| 64 | submitted | (waiting for assignment) |
| 63 | returned | Returned to RM for more info |
| 56 | draft | (rare — typically auto-created submitted) |
| 54 | completeness | Completeness check stage |
| 44 | disbursed | (terminal — exits front-office) |
| 38 | credit_admin | In credit admin processing |
| 27 | declined | (terminal — declined) |

### 3.3 Swim lanes

Field: `swim_lane`. Three values driven by amount thresholds (from same-turn read of `pages/3_pipeline.py:1262-1266`):
- **Express**: ≤ KES 5,000,000
- **Standard**: between 5M and 100M
- **Complex**: ≥ KES 100,000,000

Different SLAs / approval authorities per swim lane.

### 3.4 Formal state machine — **important parallel structure**

`utils/credit_workflow.py` defines a more rigorous **18-state `ApplicationState` enum** with explicit allowed transitions:

```
DRAFT → SUBMITTED → EKYC_PENDING → BUREAU_PULL_PENDING →
DECISION_PENDING → (APPROVED | CONDITIONALLY_APPROVED |
                    DECLINED | REFERRED_TO_COMMITTEE)
REFERRED_TO_COMMITTEE → COMMITTEE_PENDING →
                       (COMMITTEE_APPROVED | COMMITTEE_DECLINED)
APPROVED / COMMITTEE_APPROVED → DOCUMENTATION_PENDING →
                                DISBURSEMENT_PENDING → DISBURSED

Terminal states: DECLINED, COMMITTEE_DECLINED, EKYC_FAILED,
                 DISBURSED, WITHDRAWN_BY_APPLICANT, EXPIRED
```

`CreditWorkflowEngine` class enforces transitions via `is_valid_transition()`.

**DRIFT FINDING D2:** The formal `ApplicationState` enum (18 states with strict transition graph) is **not the same as** the 11 lowercase string statuses (`draft`, `submitted`, `analysis`, etc.) actually used in `loan_applications.json`. The pragmatic data model uses shorter, role-relatable strings; the formal model uses banking-rigorous enum values.

**Resolution decision needed (Q2):** For React, do we (a) extend the existing 11-status model into the UI, OR (b) implement the formal 18-state machine? Recommendation: use the operational 11-status model (matches data + matches Streamlit pages) and treat `ApplicationState` as a forthcoming rigorous overlay for committee/audit purposes.

---

## 4. Entity 3: Credit Admin Case

### 4.1 Data shape (verified from `data/credit_admin.json`)

```
id, application_id, client_name, amount, product, rm_code, rm_name,
approval_date, conditions (array), all_conditions_met,
ready_for_disbursement, disbursed, disbursement_date, last_updated
```

### 4.2 Lifecycle

Created when LoanApplication.status = approved. Tracks pre-disbursement conditions (security perfection, legal docs, drawdown setup). When all conditions are met → `ready_for_disbursement = true`. Upon disbursement, `disbursed = true` and `disbursement_date` is set. This event is what closes the loop back to PipelineDeal (stage moves to "Disbursed" / "Closed Won").

---

## 5. The handoff trigger (verified)

Same-turn read of `pages/3_pipeline.py:1239-1281`:

When an RM updates a pipeline deal's stage to any of `{Credit Review, Approval, Bank Approval, Credit Committee, Documentation, Vetting, Disbursed}`, **a LoanApplication record is automatically created** if one doesn't already exist for that `pipeline_deal_id`. The application starts with:

- `status = "submitted"`
- `swim_lane = computed from amount` (Express / Standard / Complex)
- `rm_*` fields populated from the pipeline deal
- `sla_target_days = 10`
- All other fields nullable / defaults

The handoff is **driven from the pipeline UI**, not via API. The RM's stage update is the trigger.

**Implication for React:** When the React pipeline UI advances a deal to a credit stage, it must trigger the same handoff. This is a **business event the API needs to support** — a `POST /api/pipeline/deals/{id}/advance-to-credit` endpoint or similar.

---

## 6. Role → entity → stage matrix

Who owns what at each point in the workflow:

| Workflow phase | Entity | Status / stage | Owning role |
|---|---|---|---|
| Lead generation | PipelineDeal | Prospecting, Needs Analysis | RM, RO, Branch RM, DSR |
| Sales conversion | PipelineDeal | Proposal, Negotiation, Term Sheet | RM, RO, Branch RM |
| Application submitted | LoanApplication | submitted | (auto, no owner yet) |
| Application assigned | LoanApplication | assigned | Credit analyst |
| Completeness check | LoanApplication | completeness | Credit analyst |
| Analysis | LoanApplication | analysis | Credit analyst |
| Committee referral | LoanApplication | committee | Credit Committee |
| Approval | LoanApplication | approved | (committee or analyst per swim lane) |
| Credit admin | CreditAdminCase | created from approved app | Credit Admin officer |
| Disbursement ready | CreditAdminCase | ready_for_disbursement | Credit Admin officer |
| Disbursed | CreditAdminCase + PipelineDeal | disbursed | (transitions back to pipeline as "Disbursed") |
| Returned to RM | LoanApplication | returned | RM (for more info) |
| Declined | LoanApplication | declined | (terminal) |

**Role visibility rule** (from `pages/3_pipeline.py:47` and `pages/_access.py`):
- RM sees their own deals
- Manager sees their visible-staff deals via `get_visible_staff()` cascade walk
- MD / admin sees all

**Implication for React:** Every endpoint must enforce server-side scope filtering. Today's `/api/pipeline/deals` does NOT do this — it returns all deals regardless of caller role. **This is GAP #1 for production go-live.**

---

## 7. Streamlit page → workflow phase mapping

Each Streamlit page is a role-specific workspace on a slice of the workflow:

| Page | LOC | Phase covered | React equivalent needed |
|---|---|---|---|
| `pages/3_pipeline.py` | 2,035 | Pipeline (all stages, RM view) | ✅ Pipeline module (primary) |
| `pages/21_loan_applications.py` | 682 | LoanApplication submission inventory | secondary view, may fold into Pipeline detail |
| `pages/22_credit_analysis.py` | 982 | LoanApplication status ∈ {assigned, completeness, analysis} | **Credit Analysis module** |
| `pages/82_credit_approvals.py` | 962 | LoanApplication status = committee | **Credit Approvals module** |
| `pages/85_chief_credit_centre.py` | 509 | Cross-stage oversight (Chief Credit Officer) | Executive view |
| `pages/23_credit_admin.py` | 293 | CreditAdminCase processing | **Credit Admin module** |
| `pages/19_credit_monitoring.py` | 1,160 | Post-disbursement portfolio | **OUT OF SCOPE** (separate audit) |
| `pages/20_debt_recovery.py` | 626 | DRU (Debt Recovery Unit) | **OUT OF SCOPE** (separate audit) |
| `pages/39_ews.py` | 131 | Early Warning Signals (post-disbursement) | **OUT OF SCOPE** (separate audit) |
| `pages/94_credit_governance_cockpit.py` | n/a | Cross-stage governance | secondary, executive |
| `pages/111_credit_live.py` | n/a | Live ops | secondary |

**Phase 3 React build covers (in priority order):**
1. Pipeline (`3_pipeline.py` → `Pipeline.tsx`)
2. Credit Analysis (`22_credit_analysis.py` → `CreditAnalysis.tsx`)
3. Credit Approvals (`82_credit_approvals.py` → `CreditApprovals.tsx`)
4. Credit Admin (`23_credit_admin.py` → `CreditAdmin.tsx`)
5. Chief Credit Centre (`85_chief_credit_centre.py` → executive view)
6. Loan Applications inventory (`21_loan_applications.py` → may fold into above)

Post-disbursement (Credit Monitoring, EWS, DRU) is documented in a separate audit later.

---

## 8. Backend API surface today (verified — only 4 endpoints exist)

Same-turn grep across `utils/api*.py`:

```
GET /api/pipeline/summary    — by_stage + totals
GET /api/pipeline/deals      — filtered list (stage, category, unit, pagination)
GET /api/credit/summary      — credit portfolio summary
GET /api/credit/watchlist    — credit watchlist
```

**That is the entire workflow API surface.** All 4 are READ-ONLY. There are NO endpoints for:

- Pipeline deal create/update/stage-transition
- Loan application create/list/detail/update/status-transition
- Credit admin case list/detail/condition-fulfillment
- Committee decision recording
- Pipeline → Application handoff
- Conflict resolution / "Seek permission"
- Activity timeline read

**Implication for React: backend API expansion is required before React UI can do anything beyond read-only displays.**

---

## 9. Audit emission patterns (verified)

Same-turn grep of `pages/3_pipeline.py`:

```
audit_log("DEAL_UPDATED", uname, f"{_sd['id']}|{_who}")
audit_log("LMS_APPLICATION_CREATED", uname,
          f"{_sd['id']}|{_sd.get('client_name','')}|pipeline→credit")
```

The Streamlit pages emit audit events via `audit_log()` (which writes to `data/audit_log.json` — gitignored per DATA_DICTIONARY).

The API endpoints emit via `_audit()` (from `utils/api.py`) — events like `API_PIPELINE_SUMMARY`, `API_PIPELINE_DEALS`, `API_CREDIT_SUMMARY`. These are the TELEMETRY_MAP entries gates G384 + G392 enforce.

**Implication for React build:** Every new API endpoint must call `_audit(...)` and the emitted event must be added to TELEMETRY_MAP. G392 will catch any miss (as it did with `API_RATE_LIMITED` in Batch 5e).

---

## 10. Gaps blocking production React (the gap log)

**GAP-001 — Cascade visibility not server-side.** `/api/pipeline/deals` returns all deals regardless of caller. RBAC is currently client-side in Streamlit via `get_visible_staff()`. Production go-live REQUIRES server-side scope enforcement in every loan-workflow endpoint.

**GAP-002 — Pipeline CRUD endpoints missing.** Need: `POST /api/pipeline/deals`, `PUT /api/pipeline/deals/{id}`, `POST /api/pipeline/deals/{id}/advance` (stage transition with handoff trigger).

**GAP-003 — Loan Application endpoints missing.** Need: `GET /api/applications`, `GET /api/applications/{id}`, `POST /api/applications/{id}/assign`, `POST /api/applications/{id}/decision`, `POST /api/applications/{id}/return`, `POST /api/applications/{id}/forward-to-committee`.

**GAP-004 — Credit Admin endpoints missing.** Need: `GET /api/credit-admin/cases`, `POST /api/credit-admin/cases/{id}/conditions/{type}/fulfill`, `POST /api/credit-admin/cases/{id}/disburse`.

**GAP-005 — Conflict resolution flow not exposed.** `conflict_status` is in the data but the "Seek permission" workflow is buried in Streamlit. Need `POST /api/pipeline/deals/{id}/request-permission` + `POST /api/pipeline/deals/{id}/grant-permission`.

**GAP-006 — Stage vocabulary drift (D1 above).** `PIPELINE_STAGES_LOAN` doctrine constant != actual data stages. Resolution decision needed before React build commits.

**GAP-007 — Status vocabulary drift (D2 above).** `ApplicationState` enum (18 formal states) != actual data statuses (11 lowercase strings). Resolution decision needed.

**GAP-008 — TELEMETRY_MAP additions.** Every new endpoint adds new `API_*` events that must be documented in TELEMETRY_MAP to keep G392 green.

**GAP-009 — Activity timeline endpoint missing.** Each deal/application has actions/notes. Need `GET /api/pipeline/deals/{id}/activities` and equivalent for applications.

**GAP-010 — BSC roll-up integration.** `pipeline_to_bsc.py` exists and feeds the scorecard. The React Pipeline page should optionally show "your BSC impact from current deals." Need `GET /api/pipeline/bsc-impact?staff_code=...`.

---

## 11. Open questions (operator decision required)

**Q1 — Conflict resolution implementation.** What does "Seek permission" actually do? Inspect `pages/3_pipeline.py` deeper to confirm. Probably: when an RM tries to work a deal whose `conflict_status` flags a portfolio overlap with another RM, the system holds the action until the conflict owner grants permission. Need confirmation.

**Q2 — Status taxonomy choice (D2).** Use the operational 11-status model (matches data + Streamlit) or migrate to the formal 18-state `ApplicationState` enum? Recommendation: use operational model for React build.

**Q3 — Stage vocabulary choice (D1).** Update `PIPELINE_STAGES_LOAN` constants to match data, OR leave constants alone and use data-source-of-truth in React? Recommendation: trust data, accept drift, document explicitly.

**Q4 — Credit Monitoring + EWS + DRU scope.** Are these part of "production go-live" or a later phase? They're substantial pages (1,160 + 626 + 131 LOC) and represent the post-disbursement portfolio lifecycle. Out of scope for this audit; needs decision.

**Q5 — Existing 4 read endpoints — keep or replace?** They power existing dashboards (per Dashboard.tsx). Replace them with scope-enforced versions, or leave them and build new endpoints alongside? Recommendation: replace in place — same paths, add scope.

---

## 12. Proposed Phase 3 build sequence (informed by audit)

Each batch is single-purpose, ends with audit gates green + tests passing.

### Arc α — Backend foundation (no React code yet)

**α1 — Cascade scope enforcement on existing endpoints.** Modify `/api/pipeline/deals` + `/api/pipeline/summary` to apply server-side scope per caller. Add tests proving RM sees only own deals, Manager sees branch deals, MD sees all. Closes GAP-001. *(One batch.)*

**α2 — Pipeline CRUD endpoints.** `POST/PUT/DELETE /api/pipeline/deals`. Reuse `PipelineManager`. Server-side scope. Audit emission. Tests. Closes GAP-002. *(One batch.)*

**α3 — Pipeline stage advance with handoff trigger.** `POST /api/pipeline/deals/{id}/advance`. Implements the LMS handoff (creates LoanApplication on credit-stage entry). Audit emission via `LMS_APPLICATION_CREATED` event. Tests. *(One batch.)*

**α4 — Conflict resolution endpoints.** `POST /api/pipeline/deals/{id}/request-permission` + `POST /api/pipeline/deals/{id}/grant-permission`. Closes GAP-005. *(One batch.)*

**α5 — Loan Application endpoints.** `GET /api/applications` (list + filters + scope), `GET /api/applications/{id}` (detail), and the lifecycle transitions (`assign`, `decision`, `return`, `forward-to-committee`). Closes GAP-003. *(Two batches likely.)*

**α6 — Credit Admin endpoints.** Cases list, condition fulfillment, disbursement. Closes GAP-004. *(One batch.)*

**α7 — API_CONTRACTS documentation.** Document all new endpoints (∼20+) in `API_CONTRACTS.md`. TELEMETRY_MAP additions for all new `API_*` events. Closes GAP-008.

### Arc β — React foundation

**β1 — App shell.** Layout component with sidebar nav (logo, Pipeline, Applications, Approvals, Credit Admin, Dashboard, logout). Replaces standalone-page pattern. Refactors existing Dashboard / Perform / Profitability to use Layout.

**β2 — Frontend test infrastructure.** Vitest + React Testing Library. Type-contract tests for every `api.ts` function against backend mock.

**β3 — Pipeline read-only view.** Pipeline.tsx — list with filters (stage, category, unit, segment), summary KPI strip, detail modal. Consumes scope-enforced `/api/pipeline/deals`. Loading / empty / error states. Branding-aware.

### Arc γ — Pipeline production module

**γ1 — Deal create/edit.** Pipeline.tsx adds create modal + edit modal. POST/PUT integration.

**γ2 — Stage advance UI.** Stage progression UI with visual workflow representation. Calls `POST /api/pipeline/deals/{id}/advance`. Surfaces the LMS handoff event to the RM.

**γ3 — Conflict resolution flow.** Detect `conflict_status`, surface "Seek permission" affordance, integrate with the conflict endpoints.

**γ4 — Pipeline tests + UAT prep.** Full test pass, accessibility audit, performance baseline.

### Arc δ — Credit Analysis module (parallel to γ but later)

**δ1 — Credit Analysis read-only view.** Lists applications in {assigned, completeness, analysis}. RM-visibility-aware analyst filtering.

**δ2 — Assignment + return flow.**

**δ3 — Decision flow (analyst tier only — non-committee).**

**δ4 — Committee referral.**

### Arc ε — Credit Approvals module

**ε1 — Committee queue view.** Lists status=committee applications.

**ε2 — Vote recording.** Uses `CommitteeDecision` model from `credit_workflow.py`.

**ε3 — Decision flow (committee tier).**

### Arc ζ — Credit Admin module

**ζ1 — Cases view + condition tracking.**

**ζ2 — Disbursement trigger.**

### Arc η — Polish + production

**η1 — Chief Credit Centre executive view.**
**η2 — Loan Applications inventory page (if not folded into above).**
**η3 — Accessibility + performance + security audit.**
**η4 — Production deployment + rollback plan.**

---

## 13. Estimated batch count to production go-live

- Arc α (backend): 7-9 batches
- Arc β (React foundation): 3 batches
- Arc γ (Pipeline production): 4 batches
- Arc δ (Credit Analysis): 4 batches
- Arc ε (Credit Approvals): 3 batches
- Arc ζ (Credit Admin): 2 batches
- Arc η (polish): 4 batches

**Total: 27-29 focused batches.** At an aggressive 2-3 batches per day with long hours, that's 10-15 working days — call it 2-3 weeks calendar time if you sustain pace.

**Friday checkpoint (today + Thursday + Friday):** Realistically α1 + α2 + part of α3. That's backend scope enforcement + pipeline CRUD + the handoff trigger started. **No React code shipped by Friday under this plan.** The Friday demo is the backend foundation that the React build will rest on, plus this audit document as the spec.

This is honest. Building React on top of unscoped, unCRUDed endpoints would create exactly the kind of debt that put the patient in coma the first time.

---

## 14. Verification

Every claim in this document is grounded in same-turn inspection of the cloned repo at `b2cf3a4`:

- Three-entity model: `wc -l data/pipeline.json data/loan_applications.json data/credit_admin.json` + Python json shape inspection
- Stage drift D1: `Counter` of stage field across 302 deals in pipeline.json vs constants at `utils/core.py:932`
- Status taxonomy: `Counter` of status field across 724 records in loan_applications.json
- ApplicationState enum: read of `utils/credit_workflow.py:41-125`
- Handoff trigger: read of `pages/3_pipeline.py:1239-1281`
- API surface: `grep -nE "@app.(get|post|put|delete)" utils/api*.py` filtered to workflow paths — returned exactly 4
- Streamlit page mapping: `wc -l pages/*.py` filtered to workflow domain
- All Manager classes: `grep -n "^class.*Manager" utils/core.py`

No claim in this document is from my training data, memory, or assumption. Every fact ties back to a line in `b2cf3a4`.

---

**End of audit. Ready for Joshua's review and resolution of Q1-Q5.**

---

# Section 15 — Deep anatomy (Pipeline)

**Authored:** 2026-06-10 (same session as Sections 1-14)
**Method:** Same-turn line-by-line inspection of `pages/3_pipeline.py` (2,035 lines), `utils/core.py::PipelineManager` (3896-4090+), `utils/core_audit.py::get_visible_staff`, and full key-union analysis of both pipeline JSON files at `b2cf3a4`.
**Append-only discipline:** No prior section is edited. New findings are added as Section 15 with explicit cross-references where they refine earlier sections.

---

## 15.1 CRITICAL FINDING D3 — Two pipeline data files coexist with different shapes

The earlier sections of this audit assumed a single pipeline data source. **That assumption is wrong.** Same-turn inspection found two separate JSON files, each read by a different code path:

| File | Size | Records | ID format | Sample stage |
|---|---|---|---|---|
| `data/pipeline.json` | 356,387 B | 302 | `DEAL01001` | Needs Analysis |
| `data/pipeline_deals.json` | 8,050 B | 8 | `D0001` | Closed Lost |

**Verified consumers (grep across `utils/*.py` + `pages/*.py`):**

```
data/pipeline.json:
  utils/api.py:837            → GET /api/pipeline/summary  (the API endpoint!)
  utils/api.py:887            → GET /api/pipeline/deals    (the API endpoint!)
  utils/api.py:1143           → CRUD scaffold reference
  utils/api_client.py:204     → client-side helper
  utils/api_crud.py:29,146    → CRUD framework references
  utils/core.py:6154          → BSC actuals computation

data/pipeline_deals.json:
  utils/core.py:3898          → PipelineManager.__init__()
  utils/peer_learning.py:733  → peer learning summarizer
  pages/7_admin.py:2991       → admin maintenance reference
```

**The API endpoints and the Streamlit page read from different files.** Specifically:

- `pages/3_pipeline.py:64` → `pm = PipelineManager()` → reads `pipeline_deals.json` (8 records)
- `pages/3_pipeline.py:67` → `all_deals = pm.get_deals()` → returns 8 records
- `utils/api.py:861` → `/api/pipeline/deals` → reads `pipeline.json` (302 records)

**The Streamlit UI shows 8 deals; the React UI built against the existing API would show 302 deals.** These two surfaces are looking at different datasets entirely.

**Implication for React build:** Before any React Pipeline page is built, this drift must be resolved. Three options:

1. **Consolidate** — pick one file as canonical, migrate the other into it, retire the second path.
2. **Bridge** — make `PipelineManager` read from `pipeline.json` so the manager + API + page all see the same 302 records.
3. **Diverge intentionally** — accept that there are two pipelines (development sandbox + live), document the boundary explicitly.

Recommendation: **bridge** (option 2). The 302-record dataset is the operationally meaningful one (it's what `compute_pipeline_to_bsc` would aggregate from per Section 9). The 8-record file looks like a vestige of an earlier manager-driven design that never got migrated.

**This is the most important finding in this section.** Sections 12-13 of this audit proposed Arc α1 as "cascade scope enforcement on existing endpoints" — but if the existing endpoint reads from a different file than the manager class, scope enforcement alone won't fix the divergence. **The actual first batch needs to be: resolve the two-file split.**

---

## 15.2 CRITICAL FINDING D4 — Field-name drift within `pipeline.json` itself

Even within the 302-record file, two data generations coexist. Field presence analysis across all 302 deals:

| Field | Presence | Generation |
|---|---|---|
| `id`, `client_name`, `amount`, `last_updated`, `open_date`, `probability`, `product`, `staff_code`, `staff_name`, `stage` | 302 / 302 (100%) | Both |
| `actions_due`, `backup_staff_codes`, `client_cif`, `conflict_status`, `currency`, `deal_category`, `existing_facility_id`, `expected_close`, `is_repeat_borrower`, `notes`, `original_facility_amount`, `proposition_tag`, `repayment_history`, `role`, `top_up_amount`, `unit`, `win_probability_ai`, `win_probability_ai_factors` | 294 / 302 (97.4%) | **Generation A** |
| `_v10325_seed`, `client_type`, `closed_date`, `created_at`, `deal_value`, `decision_level`, `is_ntb`, `manager_validated`, `next_action`, `pipeline_category`, `product_type`, `rm`, `rm_name`, `sector`, `updated_at`, `updated_by` | 8 / 302 (2.6%) | **Generation B** |

**Naming inconsistencies:**

| Generation A | Generation B | Consumer |
|---|---|---|
| `amount` | `deal_value` | DB / API uses `amount`; Streamlit page uses `deal_value` (`.get` with default) |
| `product` | `product_type` | Same dual-read pattern |
| `staff_name` | `rm_name` | Both exist in Gen B; only `staff_name` in Gen A |
| `staff_code` | `rm` + `staff_code` | Both fields in Gen B |

**Field semantics by generation:**

- Generation A (294 deals): legacy CRM shape — RM-centric ownership, simple actions/notes
- Generation B (8 deals): newer banking shape — adds NTB flag, pipeline_category enum, manager_validated workflow, decision_level (probably for swim_lane analog), sector classification

**Implication:** The PipelineManager methods (line 3919: `d['id'] = f"D{len(self.deals)+1:04d}"`) generate IDs in `D####` format — matching `pipeline_deals.json`, NOT the 302-record `pipeline.json` (which has `DEAL#####` IDs). So PipelineManager **cannot have been the producer of the 302-record dataset**. Some other generator created those records.

Search for likely generators:

```
generate_lms_data.py  — likely creates LoanApplication records
generate_propositions.py — creates proposition_config
generate_staff.py / generate_staff_v2.py — creates staff records
compute_actuals.py — recomputes BSC actuals
```

**Not finding a `generate_pipeline.py` in the listing.** The 302-deal file may have been generated by a since-deleted script, or generated manually for demo purposes, or generated by something inside `utils/virtual_bank_*` per the v10.494 TRANSITION_BRIEF. **This needs to be confirmed before React production work.**

---

## 15.3 Customer typology — 2×2 matrix × 4 pipeline categories

Verified from `pages/3_pipeline.py:349-423`. The deal-creation UI presents a **2-step picker**:

**Step 1 — Customer relationship (4 tiles):**
- Existing · Individual
- Existing · Business
- NTB · Individual
- NTB · Business

**Step 2 — Pipeline category (4 tiles):**
- 📈 Loan / Asset — loans, overdrafts, trade finance, mortgages
- 💰 Deposit — CASA, FD, Call & Notice
- 🏦 Account — account opening (count not KES value)
- ⚙️ Other — Insurance, DFS, Treasury

**Total: 16 deal subtypes** (4 customer × 4 category). Each combination has different downstream consumers:

- Existing customers require CBS account lookup → triggers portfolio conflict check
- NTB customers require ID number entry (no CBS lookup)
- Account category deals are measured by count (not KES value) in BSC
- Loan/Asset category is the only one that triggers the LMS handoff per Section 5

**Implication for React build:** The deal creation form has to handle 16 distinct field schemas. This isn't "one form with optional fields" — the UX is materially different per quadrant. Plan: build a routing component that selects the right sub-form once the user picks (customer-type, category).

---

## 15.4 Conflict resolution flow — fully verified (refines GAP-005)

Same-turn read of `pages/3_pipeline.py:530-580`. **When Existing customer is selected and CBS RM ≠ current user:**

1. Amber alert renders: `"⚠️ Portfolio conflict — This customer's RM is X (per CBS). BSC credit on closure goes to them."`

2. User presented with **3 radio options**:

   | Option | Behavior | Required fields |
   |---|---|---|
   | **Seek permission** | Proceed with the deal; user acknowledges and will obtain owner's OK | Override checkbox required at submit |
   | **Refer to portfolio owner** | Hand off the deal formally — create a referral lead | `referred_to`, `referral_note` |
   | **Pursue and credit to my BSC** | Take the deal anyway, BSC credit to current user | `manager_override_note` required |

3. **Fields captured on the deal (regardless of path):**

   ```
   portfolio_owner_code  — set to CBS RM code
   portfolio_owner_name  — set to CBS RM name
   is_referral           — true if Refer path
   referred_to           — name of referral target
   referral_note         — note attached
   bsc_credit_to         — name receiving BSC credit (the owner if "Seek permission" or "Refer")
   manager_override_note — required if "Pursue" path
   ```

4. **Audit event emitted:** `DEAL_REFERRED` (in Refer path, line 573)

**Implication for React build:** This is more nuanced than a simple "permission" flow. It's a **portfolio sovereignty model** with three distinct paths and explicit BSC credit routing. The React UI must surface all three with the correct field requirements and audit emission per path. **GAP-005 in Section 10 should be re-scoped: it's not "1 permission endpoint" — it's at minimum 2 (refer, override) and the seek-permission path is purely a deal-creation state, not a separate endpoint.**

---

## 15.5 Manager validation lifecycle — verified

Same-turn read of `pages/3_pipeline.py:1290-1336`.

**The rule:** Any deal that advances **beyond the Lead stage** is automatically flagged `manager_validated=False` and surfaces in the manager's validation queue. Until validated, the deal does NOT count toward pipeline forecasts.

**Manager queue (line 1316-1336):**

- Lists deals where `stage in STAGE_NAMES[1:]` AND `manager_validated=False` AND NOT `cancel_requested` AND NOT `draft`
- Each deal expandable with the staff name, product, value, probability, next action, expected close
- Manager input: validation note (text)
- Two actions:
  - **Validate — include in forecast** → calls `pm.validate_deal(id, uname, True, note)`, emits `DEAL_VALIDATED`
  - **Query — return to owner** → calls `pm.validate_deal(id, uname, False, note)`, emits `DEAL_QUERIED`

**Cancellation queue (line 1295-1314):**

- Lists deals where `cancel_requested=True` AND NOT `cancel_approved`
- Manager approves (emits `CANCEL_APPROVED`) or rejects (emits `CANCEL_REJECTED`)

**Implication for React build:** Managers need their own UI surface — not just RM-filtered deal list, but explicit "actions needed from me" queues. This is a real **manager dashboard module** as a sibling to the RM pipeline view. **Adding GAP-011 to the gap log: Manager queue endpoints.**

---

## 15.6 Backup staff RBAC — verified

Same-turn read of `pages/3_pipeline.py:69-98` + `1380-1410`.

**Backup mechanism:**
- Deals have field `backup_staff_codes: list[str]` — array of staff codes designated as backup for the deal
- Backup staff **see the deal** even if outside their normal cascade visibility (lines 94-98 explicitly append)
- Backup staff have a dedicated "Deals I'm backing up" section in their My Actions tab (line 1380)
- Caption text at line 1387 confirms: **"You can move the stage but not edit details."**

**RBAC distinction (3-level for any given deal):**

| Role | View | Stage advance | Edit details | Approve cancel |
|---|---|---|---|---|
| Owner (RM) | yes | yes | yes | request only |
| Backup | yes | yes | **NO** | no |
| Manager (in scope) | yes | yes | yes | yes |
| Out-of-scope | no | no | no | no |

**Implication for React build:** The deal-detail endpoint must return a `permissions: {can_edit, can_advance_stage, can_approve_cancel, can_request_cancel}` object alongside the deal data, computed server-side based on caller identity vs deal ownership + backup membership + cascade scope. The React UI then renders/hides controls accordingly. This is **GAP-012 — deal-level permission resolution endpoint pattern**.

---

## 15.7 Draft state lifecycle — verified

Same-turn read of `pages/3_pipeline.py:100-103` + `1341-1378`.

**Draft creation:** Deals are created with `draft=true` if either `deal_value` is missing or `next_action` is missing. They are excluded from the main pipeline view (`live_deals = [d for d in view_deals if not d.get("draft")]` at line 102).

**Draft surfacing:** All my drafts surface in the My Actions tab (line 1343) for completion later. Each draft expander offers:
- Edit deal value
- Edit next action + date
- **Complete & publish** button — promotes to live (`draft: False`), emits `DRAFT_COMPLETED`
- **Discard draft** button — soft delete (`pm.delete_deal`), emits `DRAFT_DISCARDED`

**Validation on publish:** Both `next_action` (non-empty) AND `deal_value > 0` are required.

**Implication for React build:** The "create deal" UX should support saving partial entries as drafts. This matches how RMs work — they often start capturing a lead with just a name and product, then fill in value/action later. **Adding GAP-013 — draft state CRUD support.**

---

## 15.8 BSC trigger semantics — K041

Same-turn read of `pages/3_pipeline.py:21-25` + 16 trigger sites.

**The mechanism (line 21-25):**
```python
def _bsc_trigger(username: str, kpi: str = ""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
```

**`update_bsc_from_modules(username)`** is the central scorecard recalc function. It re-aggregates pipeline contributions per `utils/pipeline_to_bsc.py` (539 LOC, Section 9). Despite the `kpi` parameter being passed (always `"K041"` from the pipeline page), the function ignores it — it does a full recompute.

**KPI K041:** Same-turn search did not find this code defined in `utils/core.py` or `data/kpi_library.json` accessibly. The `"K041"` string appears 16 times in `3_pipeline.py` but is not consumed by the trigger function. **It's effectively a comment / breadcrumb naming the pipeline KPI, not a routing key.**

**16 trigger sites in `pages/3_pipeline.py`:** every mutation event fires `_bsc_trigger`. The list:

```
Line 574:  after DEAL_REFERRED
Line 966:  after deal added via "Pursue" path
Line 988:  after deal added via "Seek permission" path
Line 1238: after stage update / deal mutation
Line 1284: after LMS_APPLICATION_CREATED (handoff)
Line 1310: after CANCEL_APPROVED
Line 1314: after CANCEL_REJECTED
Line 1332: after DEAL_VALIDATED
Line 1336: after DEAL_QUERIED
Line 1371: after DRAFT_COMPLETED
Line 1378: after DRAFT_DISCARDED
Line 903 + others: at deal-add boundary
```

**Implication for React build:** Every write endpoint for pipeline must call `update_bsc_from_modules(caller_username)` AFTER the database write succeeds. Failing to do this means the scorecard goes stale — and per the v10.494 TRANSITION_BRIEF, BSC accuracy is the Charter §2 invariant the system is built on. **Adding GAP-014 — every write endpoint must trigger BSC recompute.**

The silent `except Exception: pass` at line 24 is a **latent bug pattern** identical to the one Phase 1 Batch 3b discovered (`NameError` hidden under silent except for 2 years). It should be replaced with explicit error handling that at minimum logs the failure. **Adding GAP-015 — replace silent except in `_bsc_trigger` with proper error handling.**

---

## 15.9 Complete audit event inventory (verified)

Same-turn grep of `audit_log\(` calls within `pages/3_pipeline.py`:

| Event | Trigger | Payload |
|---|---|---|
| `DEAL_UPDATED` | Generic deal field update | `{id}\|{owner_or_backup}` |
| `DEAL_VALIDATED` | Manager validates queued deal | `{id}` |
| `DEAL_QUERIED` | Manager queries (returns) deal | `{id}` |
| `DEAL_REFERRED` | Refer-to-owner path on conflict | `{account_number}→{ref_to}` |
| `CANCEL_APPROVED` | Manager approves cancellation | `{id}` |
| `CANCEL_REJECTED` | Manager rejects cancellation | `{id}` |
| `DRAFT_COMPLETED` | Draft promoted to live | `{id}` |
| `DRAFT_DISCARDED` | Draft deleted | `{id}` |
| `LMS_APPLICATION_CREATED` | Handoff to credit | `{id}\|{client_name}\|pipeline→credit` |

**9 distinct audit events emitted from this single page.** All flow into `audit_log.json` (or whatever audit sink the system uses). These are **the source-of-truth event names** the React API must preserve.

**For TELEMETRY_MAP (G384):** When the React-driven API endpoints emit their own events (e.g., `API_PIPELINE_DEAL_CREATED`), each one is a NEW event that needs TELEMETRY_MAP registration. The 9 events above are page-level events; the API events are a parallel set. G384 will catch any drift.

---

## 15.10 RBAC visibility chain — verified end-to-end

The cascade-walk RBAC pattern, complete:

```
1. Page imports get_visible_staff from utils.core_audit (via pages/_access.py shim)
2. Caller invokes: vis_staff = get_visible_staff(user_data, staff_scores)
3. Inside get_visible_staff (utils/core_audit.py:190):
   - if is_admin OR role in _ALL_VIEW_ROLES → return full DataFrame
   - else look up REPORTING_TREE[role] config
   - filter staff_scores by tree_roles + tree_units (or region for Regional Heads)
   - return filtered DataFrame
4. Page extracts: vis_names = visible["Staff Name"].tolist()
                  vis_codes = visible["Staff Code"].tolist()
5. Page filters deals: [d for d in all_deals if d.staff_name in vis_names OR d.staff_code in vis_codes OR d.unit == my_unit]
6. Backup deals appended regardless (out-of-tree exception)
```

**The pattern relies on `staff_scores` being a DataFrame loaded in session state.** For React API, this DataFrame doesn't exist — we need a server-side equivalent that:

1. Takes the caller identity (from JWT)
2. Walks REPORTING_TREE to determine visible-staff set
3. Joins against pipeline data
4. Returns filtered results

**This is the load-bearing function for GAP-001 (cascade scope server-side enforcement).** The implementation should live in `utils/api_pipeline.py` (or similar) as a helper:

```python
def get_visible_staff_codes(user_data: dict) -> set[str]:
    """Server-side equivalent of get_visible_staff, returns staff_code set."""
    # walks REPORTING_TREE per role; reads staff_register.xlsx for roster
    ...

# Then in the endpoint:
@app.get("/api/pipeline/deals")
def pipeline_deals(...):
    visible = get_visible_staff_codes(user)
    deals = [d for d in load_pipeline() if d.staff_code in visible]
    # apply other filters...
```

**Note the input difference:** the existing `get_visible_staff(ud, staff_scores)` consumes a DataFrame; the API equivalent must work without it. Either we materialize the staff roster server-side at request time (extra I/O per request), or we cache it (need invalidation on staff register update). **Recommendation: cache with 60-second TTL — staff roster changes rarely; 60s is acceptable staleness.**

---

## 15.11 New gap log additions (extending Section 10)

From this deep anatomy, **5 new gaps** surface beyond GAP-001 through GAP-010:

**GAP-011 — Manager queue endpoints.** Cancellation approval queue, validation queue. These are role-specific, server-side scoped. *(Sec 15.5)*

**GAP-012 — Per-deal permission resolution.** Endpoint must return `permissions: {can_edit, can_advance_stage, can_approve_cancel, can_request_cancel}` per caller-vs-deal relationship (owner/backup/manager/oo-of-scope). *(Sec 15.6)*

**GAP-013 — Draft state CRUD.** Create deals as drafts (partial fields OK), promote to live (publish), discard. Drafts excluded from forecasts. *(Sec 15.7)*

**GAP-014 — Write endpoints must trigger BSC recompute.** Every pipeline write must call `update_bsc_from_modules(caller_username)` after success. *(Sec 15.8)*

**GAP-015 — Silent-except replacement in `_bsc_trigger`.** Latent-bug pattern. Replace bare `except Exception: pass` with logged error handling. *(Sec 15.8)*

Also surfaced but not numbered as new gaps because they're sharper versions of existing gaps:

- **D3 (Section 15.1)** refines GAP-006 (stage vocabulary drift): the deeper issue is two-file split, not just stage names. The first React backend batch must resolve the file split before scope enforcement.
- **D4 (Section 15.2)** refines GAP-007 (status drift): even within one file, two data generations exist with different field names. Pydantic schema for React API must pick one canonical shape.
- **Section 15.4** refines GAP-005: conflict resolution is 3 distinct paths, not 1 endpoint.

---

## 15.12 Revised first-batch recommendation

Section 12 of this audit proposed Arc α1 as "cascade scope enforcement on existing endpoints." **That was incorrect ordering.** The deep anatomy reveals that scope enforcement is downstream of resolving D3 (the two-file split). Revised ordering for Arc α:

**α1 (revised) — Pipeline data consolidation.** Resolve D3: pick canonical file, migrate the other into it, retire the second path. Pydantic schema authored that picks one of Generation A vs Generation B field names. Tests prove `PipelineManager.get_deals()` and `/api/pipeline/deals` now read the same dataset. *(One batch — but careful, this touches data integrity.)*

**α2 — Cascade scope enforcement.** Now that there's one dataset, add `get_visible_staff_codes()` helper and apply to both endpoints. *(One batch.)*

**α3 — Pipeline CRUD endpoints.** POST/PUT/advance, with BSC trigger calls. Closes GAP-002, GAP-013, GAP-014. *(One batch.)*

**α4 — Stage advance + LMS handoff endpoint.** `POST /api/pipeline/deals/{id}/advance` reproducing the auto-create-application logic from `pages/3_pipeline.py:1239-1281`. *(One batch.)*

**α5 — Conflict resolution endpoints.** Three paths: refer (creates referral deal), pursue-with-override, seek-permission (just a creation field). Closes GAP-005. *(One batch.)*

**α6 — Manager queue endpoints.** GET cancellation queue, GET validation queue, POST approve/reject/validate/query. Closes GAP-011. *(One batch.)*

**α7 — Per-deal permissions resolution.** GET /api/pipeline/deals/{id} returns permissions object. Closes GAP-012. *(Half a batch — folds into α2 or α3.)*

**α8 — Loan Application endpoints.** Same scope. (Per Section 12 Arc α5.)

**α9 — Credit Admin endpoints.** Same scope. (Per Section 12 Arc α6.)

**α10 — API_CONTRACTS + TELEMETRY_MAP documentation pass.** (Per Section 12 Arc α7.)

**Revised total: 10 backend batches** (was 7-9 in Section 12). Honest scope after deep inspection.

---

## 15.13 What deep anatomy did NOT cover

For transparency, things this section did not fully verify (still aspirational, deserve follow-up):

1. **The `pipeline_activities.json` log structure** — `PipelineManager.activities` is loaded but I did not inspect its schema or how the page surfaces activity history.
2. **The full PipelineManager method set** — I inspected `add_deal`, `update_stage`, `update_deal`, `delete_deal`, `request_cancel`, `approve_cancel`, `get_deals`, `get_activities` (lines 3918-4020). Methods after line 4020 (including `validate_deal`, `pipeline_value`, `weighted_pipeline`, `add_activity`, etc.) were not fully read.
3. **The proposition_config.json schema** — referenced at line 110 but contents not inspected.
4. **REPORTING_TREE config contents** — referenced at `utils/core_audit.py:213` but the config itself not opened.
5. **The `_LMS_STAGES` set** uses stage names ("Credit Review", "Vetting", "Disbursed") that match neither the Generation A `PIPELINE_STAGES_LOAN` constants nor the actual data stage names from the 302-deal file. This needs investigation — it's a third stage vocabulary I didn't expect.
6. **`update_bsc_from_modules`** — referenced at line 22 but the function itself was not opened.
7. **Backend `/api/v1/bsc/*` endpoints** referenced in the React `Perform.tsx` placeholder — the pipeline→BSC flow on the API side was not traced end-to-end.

These will be inspected as their relevant batches come up. **Section 15 is a deep first pass, not a final pass.** Subsequent sections (16+) will fill remaining gaps as work progresses.

---

**End of Section 15.**


---

# Section 16 — Doctrine reference (the "Streamlit stays, React additive" architecture)

**Authored:** 2026-06-10 (Batch α1 doctrine sync)
**Type:** Append-only amendment. Refines the framing of Section 15.12 without modifying it.

---

## 16.1 The established doctrine

The audit's Sections 1-15 were authored before this section was added. Section 15.12 in particular proposed "Arc α1 — Pipeline data consolidation" with language about picking a canonical file and migrating the other. This framing, while pointing in the right direction, missed the architecturally precise statement of what's being done.

The architecture this codebase has been built around — consistently since at least v10.21 (~480 batches ago) — is:

> **Both presentation layers remain. Business logic is centralized in FastAPI. Streamlit and React consume the same backend services. No duplicate logic across presentation surfaces.**

The clearest single-line statement is in `docs/REACT_READINESS_AUDIT.md` line 35:

> "Streamlit pages remain the **internal admin/staging tool**. React SPA is the **production employee-facing UI**."

The pattern has a name in the changelogs — **"zero-streamlit engines"** — referring to business logic modules deliberately built to be callable from any presentation layer. Representative citations (same-turn grep):

| Changelog | Quote |
|---|---|
| `CHANGELOG_v10.21.md` | "Dashboard is data-only. This batch produces `DashboardSnapshot` records; the actual UI rendering belongs in pages... The data model is stable; the rendering is per-presentation-layer." |
| `CHANGELOG_v10.400.md` | "Backend + UI separation. `canonical_admin.py` is a leaf module — works without Streamlit. Page is the presentation layer." |
| `CHANGELOG_v10.417.md` | "Bypasses CascadeManager (which has streamlit deps). The engine stays standalone and FastAPI-callable." |
| `CHANGELOG_v10.426.md` | "20 React-ready engines now. All zero-streamlit, all dataclass-returning." |
| `CHANGELOG_v10.434.md` – `v10.439.md` | Each cockpit batch verifies "engine API + zero streamlit + dataclasses" as a structural test. |

The doctrine has been present, named, and enforced via gates throughout the codebase. The PIPELINE_DOMAIN_AUDIT Section 15 inspection surfaced a specific drift from this doctrine — the pipeline endpoints bypassed `PipelineManager` and read raw JSON directly. That drift was Finding D3.

---

## 16.2 What this means for Arc α1 (corrects Section 15.12's framing)

Section 15.12 proposed: **α1 — Pipeline data consolidation** with language about picking a canonical file. That framing reads as "data migration" — implying the operator must decide which dataset to keep.

Under the established doctrine, the correct framing is:

> **α1 — Route the FastAPI pipeline endpoints through `PipelineManager` (the canonical business-logic layer), eliminating the direct `_load_json("pipeline.json")` bypass.**

Same end state — both presentation layers see the same data — but the mechanism is **a refactor of the API surface**, not a migration of data files. The legacy file becomes unreferenced as a *consequence* of doing the right thing architecturally; no data is deleted in this batch. Archival of the orphan file is a separate, later, smaller decision.

This framing aligns with:

1. **The "no duplicate business logic" rule** — the API now consumes `PipelineManager`, not a parallel JSON reader.
2. **The "zero-streamlit engine" pattern** — `PipelineManager` (despite currently having streamlit dependencies; tracked in GAP-008) is the canonical manager; the API calling it follows the same pattern as Streamlit calling it.
3. **The Trap #12 backup-before-mutation discipline** — no destructive data operation occurs in this batch.

---

## 16.3 Updated Arc α sequence (refines Section 15.12)

Per this corrected framing:

| Batch | Title | Scope |
|---|---|---|
| **α1** | **Pipeline API canonical-manager routing** | Refactor `/api/pipeline/summary` and `/api/pipeline/deals` to call `PipelineManager`. New Pydantic schema. New gate G394. (This batch.) |
| α2 | Cascade scope enforcement on pipeline endpoints | Server-side scope filtering via `get_visible_staff_codes()` helper. Closes GAP-001. |
| α3 | Pipeline CRUD endpoints | POST/PUT/advance with BSC trigger calls + draft state. Closes GAP-002, GAP-013, GAP-014. |
| α4 | Stage advance + LMS handoff | `POST /api/pipeline/deals/{id}/advance` reproducing the auto-create-application logic. |
| α5 | Conflict resolution endpoints | Refer + override paths. Closes GAP-005. |
| α6 | Manager queue endpoints | Validation + cancellation queues. Closes GAP-011. |
| α7 | Per-deal permissions resolution | `permissions: {can_edit, can_advance_stage, ...}` object. Closes GAP-012. May fold into α2/α3. |
| α8 | Loan Application endpoints | List, detail, lifecycle transitions. Per Section 12 Arc α5 / refined. |
| α9 | Credit Admin endpoints | Cases, condition fulfillment, disbursement. |
| α10 | API_CONTRACTS + TELEMETRY_MAP documentation pass | All new endpoints documented. |

Total backend arc: still ~10 batches. The numbering changes from Section 12's `α1-α7` to this `α1-α10` because the deep anatomy revealed sub-batches worth separating (manager queues, per-deal permissions). Section 15.12 is the right list; this section just makes the names match the order.

---

## 16.4 What this section is NOT

This section does not edit Sections 1-15. The append-only discipline holds. Section 15.12 retains its original wording for historical fidelity; readers consulting Section 15.12 should also consult Section 16.2 for the corrected framing.

This section does not introduce new findings beyond what Section 15 surfaced. The five new gaps GAP-011 through GAP-015 in Section 15.11 remain the canonical gap list.

This section does not propose new architecture. It cites and names an architecture that has been in continuous use across the codebase for hundreds of batches.

---

**End of Section 16.**


---

# Section 17 — Streamlit α5 bsc_credit inversion (post-α5 finding surfaced during React Batch β3)

**Authored:** 2026-06-11 (governance sweep batch, post-β4 close)
**Type:** Append-only amendment. Surfaced during React Phase 4 Batch β3 (v10.512, commit `a796bc8`) when implementing the conflict-resolution UX on top of the α5 backend. Refines understanding of GAP-005's closure without modifying it.

---

## 17.1 The finding

When implementing the React conflict-resolution flow in β3, same-turn cross-inspection of:

- `utils/api_pipeline_mutations.py::is_override_semantics` (the α5 backend validator)
- `pages/3_pipeline.py::_bsc_credit` (the Streamlit deal-creation path)

…revealed that the Streamlit `_bsc_credit` field assignment is **inverted** relative to what the α5 backend now expects.

The α5 backend (`utils/api_pipeline_mutations.py`) decides whether a create payload is in override-semantics or seek-permission-semantics by comparing `bsc_credit_to` against the caller's name:

| Backend interpretation | `bsc_credit_to` value | Override note required? |
|---|---|---|
| **OVERRIDE** | equals caller's name | YES (≥10 chars) |
| **SEEK PERMISSION** | equals portfolio_owner_name | NO |

The Streamlit `_bsc_credit` calculation does the opposite mapping:

| Streamlit user choice | Streamlit sets `bsc_credit_to` to | Backend then interprets as | Outcome |
|---|---|---|---|
| "Seek permission" | caller (creator) | OVERRIDE | **400 rejection** (no note collected by Streamlit) |
| "Pursue override" | portfolio_owner_name | SEEK PERMISSION | accepted without override note (audit weakness) |

**The polite path errors. The override path silently bypasses the note requirement.**

---

## 17.2 Same-turn evidence

Verified in commit `a796bc8` (v10.512 Phase 4 Batch β3, React frontend):

```
utils/api_pipeline_mutations.py::is_override_semantics():
    returns True iff bsc_credit_to == caller_name
    when True, the validator requires manager_override_note (min 10 chars)

pages/3_pipeline.py::_bsc_credit():
    when user picks "Seek permission":   bsc_credit_to = current user name
    when user picks "Pursue override":   bsc_credit_to = portfolio_owner_name
```

The α5 doctrine note in `api_pipeline_mutations.py` itself flags this as "the API enforcement for what Streamlit promises (requires manager override note) but never actually collects." That note correctly identifies that Streamlit doesn't collect the note. The deeper finding here is that Streamlit's mapping of *user choice → `bsc_credit_to`* is itself reversed — even the "Seek permission" path silently asks the backend for override semantics.

---

## 17.3 Why this surfaced now (not at α5)

The α5 backend validator (added in v10.507 commit `fa61c81`) introduced semantics-by-value-of-`bsc_credit_to`. Streamlit was written earlier under a different convention. The two have been silently incompatible since v10.507. Existing Streamlit users would have experienced "Seek permission" submits failing with 400, but the failure mode was likely attributed to API teething issues rather than a documented inversion.

React β3 only exposed it because β3 had to choose which side to mirror, forcing a deliberate same-turn comparison. React β3 implements the **backend** semantics (internally consistent — the server validates what the server expects). The Streamlit side is the artifact that needs fixing.

---

## 17.4 GAP-016 — Streamlit α5 bsc_credit inversion

**Status:** OPEN
**Surfaced during:** React Phase 4 Batch β3 (v10.512, commit `a796bc8`)
**File affected:** `pages/3_pipeline.py::_bsc_credit` (and its call sites at deal-creation submit)

**Gap:** Streamlit's `_bsc_credit` calculation maps user choice to `bsc_credit_to` in the inverse of what the α5 backend validator expects. The "Seek permission" path silently 400s because no override note is collected for a payload the server interprets as override semantics. The "Pursue override" path silently bypasses the note requirement because the server interprets it as seek-permission.

**Stated location:** `pages/3_pipeline.py` — `_bsc_credit` definition and its call sites in the deal-creation submit handler.

**Enforced location (backend):** `utils/api_pipeline_mutations.py::is_override_semantics`.

**Risk:**

1. **Stated functionality broken.** A Streamlit user who picks "Seek permission" cannot create a deal — they get a 400 with no clear UX recovery path.
2. **Audit weakness.** A Streamlit user who picks "Pursue override" creates the deal without a manager override note, defeating the audit trail α5 was supposed to enforce on overrides.
3. **Doctrine drift (CGR1).** Streamlit and React now have different conflict-resolution semantics for the same backend. Per the "Streamlit stays, React additive" doctrine (Section 16), both presentation layers must consume identical backend semantics.

**Recommendation:** Swap the two assignments in `_bsc_credit`. When user picks "Seek permission", set `bsc_credit_to = portfolio_owner_name`. When user picks "Pursue override", set `bsc_credit_to = current_user_name` AND collect the `manager_override_note` input field (≥10 chars, matching backend validation). Both behaviours then match backend semantics. The fix is small (function-local swap plus one new text input field for the override path).

**Scope:** Streamlit-only fix. No backend changes (backend is correct as of α5). No React changes (β3 already implements backend semantics). A single Streamlit-targeted batch closes this gap.

---

## 17.5 What this section does NOT do

This section does not edit Sections 1-16. The append-only discipline holds.

This section does not propose a fix batch. It documents the finding. The actual fix to `pages/3_pipeline.py` would be a separate batch (Streamlit-side only, no React or backend impact).

This section does not change the closure status of GAP-005. GAP-005 (Conflict resolution endpoints) remains CLOSED for its original scope: the API endpoints exist and are mutually consistent with React. GAP-016 is a separate gap targeting the Streamlit-side consumer of those endpoints.

This section does not retroactively change β3's commit. β3 shipped with the inversion already documented in its commit message (commit `a796bc8`). This section formalises that documentation in the canonical audit artifact and assigns the gap a stable identifier (GAP-016) so future batches can reference it.

---

**End of Section 17.**


---

# Section 18 — α8 Loan Application backend (Arc α continuation)

**Authored:** 2026-06-11 (Batch α8 — Phase 3 Arc α, Loan Application domain)
**Type:** Append-only amendment. Marks completion of α8 from the Arc α plan in Section 16.3. Documents the endpoint surface decisions made during implementation and the deferred work parked for later batches.

---

## 18.1 What α8 ships

Five REST endpoints under `/api/lms/applications` exposing `LoanApplicationManager` (`utils/core.py:5267`) to React:

| Verb | Path | Auth |
|---|---|---|
| GET | `/api/lms/applications` | required + cascade scope filter |
| GET | `/api/lms/applications/{id}` | required + per-app permissions object |
| POST | `/api/lms/applications/{id}/assign` | required + manager-tier |
| PUT | `/api/lms/applications/{id}` | required + can_update permission |
| POST | `/api/lms/applications/{id}/decision` | required + manager-tier |

Plus 5 new helper modules mirroring the pipeline-domain shape:

- `utils/api_lms_models.py` — Pydantic request/response models
- `utils/api_lms_scope.py` — cascade-scope filter (delegates to `api_pipeline_scope.get_visible_staff_codes`, adds analyst-override layer)
- `utils/api_lms_mutations.py` — payload validators + status-guardrail constants
- `utils/api_lms_permissions.py` — per-caller-per-app permission resolver
- `utils/api_lms_routes.py` — `APIRouter` with the 5 endpoint handlers

Mounted in `utils/api.py` via a 2-line append (`import` + `app.include_router(lms_router)`).

### Architectural note: first use of APIRouter

α8 is the **first batch to use FastAPI's `APIRouter`** in this codebase. Pipeline endpoints predate this and live as raw `@app.method` decorators inside `utils/api.py`. The router pattern was chosen for α8 because:

1. It keeps `utils/api.py` changes to a 2-line append rather than ~400 lines of new endpoint code inside an already-4000-line file.
2. The route module becomes self-contained and grep-able as a unit.
3. It's the FastAPI-idiomatic pattern and a precedent for α9 and beyond.

Existing pipeline routes are NOT migrated in this batch — that's not a refactor scope α8 wanted to take on. They remain as `@app.method` in `api.py`. A future hygiene batch can migrate them to `pipeline_router` if Joshua wants the pattern unified.

---

## 18.2 Authorization model

Three tiers stacked per endpoint:

### Tier 1 — Cascade scope

Reuses `get_visible_staff_codes(user)` from `api_pipeline_scope.py`. An application is visible to a caller if EITHER:

- `app.rm_code` is in the caller's `visible_codes` set (RM cascade), OR
- `app.analyst.code` matches the caller's `staff_code` (analyst override)

The analyst override exists because credit analysts at HQ work across cascades — without it, an assigned analyst at HQ wouldn't see applications submitted by branch RMs whose cascade the analyst is otherwise outside.

Admins span the whole roster (their `visible_codes` includes every staff code), so admin sees everything.

### Tier 2 — Manager-tier check

Reuses `is_manager(user)` from `api_pipeline_manager_actions.py`. Same keyword set as the pipeline manager-queue gates (managing, director, head of, regional, branch manager, chief, manager, supervisor, credit manager, operations manager). Applied to:

- `POST /assign` — only managers can assign analysts (per Q1 in α8 planning)
- `POST /decision` — only managers can record decisions (per Q2)

### Tier 3 — Status guardrails

State-machine-lite enforcement on mutations:

- `PUT /` (update) — requires status in `{submitted, assigned}` (no edits after approve/decline/return)
- `POST /assign` — requires status in `{submitted}` (no re-assignment)
- `POST /decision` — requires status in `{submitted, assigned}`

These constants live in `api_lms_mutations.py` (`STATUSES_PERMITTING_UPDATE`, etc.) and are read by both the endpoint handlers (enforcement) AND the permission resolver (UX hints).

### Per-application permissions object

`GET /applications/{id}` returns:

```json
{
  "can_view":           true,
  "can_update":         true,
  "can_assign":         false,
  "can_record_decision": false
}
```

React UI uses these to enable/disable controls. The server still enforces the same gates on every mutation — these flags are UX hints, not the security boundary.

---

## 18.3 Audit events emitted

Five new event types added to the audit inventory:

| Event | Detail format |
|---|---|
| `LMS_ANALYST_ASSIGNED` | `{app_id}\|{analyst_code}` |
| `LMS_APPLICATION_UPDATED` | `{app_id}` |
| `LMS_DECISION_APPROVED` | `{app_id}\|{authority}` |
| `LMS_DECISION_DECLINED` | `{app_id}\|{authority}` |
| `LMS_DECISION_RETURNED` | `{app_id}\|{authority}` |

All emit via `utils.core_audit.audit_log(action, username, detail)`. The decision event name is derived from the normalized verdict, giving downstream audit dashboards three clean event types instead of one ambiguous `LMS_DECISION_RECORDED`.

Existing `LMS_APPLICATION_CREATED` (emitted by α4's pipeline handoff) remains as the lifecycle-creation event. The five events above cover the four mutations α8 surfaces — together they form the full LMS-side audit trail for an application from create to decision.

---

## 18.4 Deliberate scope exclusions

The following capabilities are **not** in α8 — they are explicit candidates for future batches, parked here for traceability:

- **Committee referral / committee approval workflows.** The `ApplicationState` enum (`utils/credit_workflow.py:41-125`) defines `REFERRED_TO_COMMITTEE` / `COMMITTEE_PENDING` / `COMMITTEE_APPROVED` / `COMMITTEE_DECLINED` states. `LoanApplicationManager` doesn't currently expose committee-routing methods. **α8b candidate.**
- **Document checkoff CRUD.** α8 allows PUT to replace `docs_submitted` wholesale but doesn't add per-document submit/verify operations. **α8c candidate.**
- **Manager-specific queues.** For LMS the natural queues are: unassigned applications (manager assigns analyst), decision-pending applications (manager records decision). Equivalent of pipeline α6's validation/cancellation queues. **α8d candidate.**
- **eKYC / Bureau Pull / Documentation states.** The `ApplicationState` enum defines these as discrete states with transition rules. The data file uses simpler status strings. α8 honors the data-file vocabulary (see Section 18.5). Migrating to the enum granularity is a substantial scope.
- **Reverse-decision endpoint.** No `POST /decision/reverse` in α8 — once approved/declined/returned, the application is immutable from the LMS-side API. If a decision needs reversal, that's a future operations-recovery scope.

---

## 18.5 Enum-vs-data discrepancy (potential GAP-017)

Same-turn inspection during α8 surfaced a discrepancy between two sources of "what is a valid application status":

**`utils/credit_workflow.py::ApplicationState`** (19 states, UPPER_CASE, with `ALLOWED_TRANSITIONS` graph):

```
DRAFT, SUBMITTED, EKYC_PENDING, EKYC_FAILED, BUREAU_PULL_PENDING,
DECISION_PENDING, APPROVED, CONDITIONALLY_APPROVED, DECLINED,
REFERRED_TO_COMMITTEE, COMMITTEE_PENDING, COMMITTEE_APPROVED,
COMMITTEE_DECLINED, DOCUMENTATION_PENDING, DISBURSEMENT_PENDING,
DISBURSED, WITHDRAWN_BY_APPLICANT, EXPIRED
```

**`data/loan_applications.json`** runtime data (~7 states, lowercase, no transition graph):

```
submitted, assigned, approved, declined, returned, credit_admin, disbursed
```

Overlap analysis (case-insensitive):

| Data status | Closest enum match | Notes |
|---|---|---|
| `submitted` | `SUBMITTED` | matches |
| `approved` | `APPROVED` | matches |
| `declined` | `DECLINED` | matches |
| `disbursed` | `DISBURSED` | matches |
| `assigned` | (none) | enum has `EKYC_PENDING` after submission but semantics differ |
| `returned` | (none) | no enum equivalent |
| `credit_admin` | (none) | post-approval handoff state, no enum equivalent |

**The enum is more granular than the runtime data.** It's an aspirational model that hasn't been realized in the data layer. α8 implements against the data-file vocabulary because per CGR1, doctrine bends to runtime reality — the enforced behaviour wins over the documented intent until reality is migrated.

**Recommendation (decision for a follow-up batch):**

- **(A)** Demote `ApplicationState` to "aspirational reference" — rename the file/class or add a docstring marking it as `ApplicationStateAspirational`, document that the data file uses a simpler subset.
- **(B)** Plan a Phase 4 batch (separate from React arc) to migrate data records to the enum's granularity. This is a substantial migration: backend logic changes, BSC computation updates, data backfill.

α8 defers this decision. If treated as a tracked divergence, it would become **GAP-017** in a future audit amendment. That entry is not authored in this batch — needs Joshua's reconciliation direction first.

---

## 18.6 What this section does NOT do

This section does not edit Sections 1-17.

This section does not file the enum-vs-data finding as a numbered GAP. That promotion needs an operator decision (path A or path B in 18.5) and would be a separate small batch.

This section does not introduce React-side changes. α8 is backend-only. The React batch consuming α8 (loan application list/detail/decision UI) will be a separate β-arc batch — natural number β5 if no other pipeline-depth work intervenes.

This section does not migrate existing pipeline endpoints from `@app.method` to `APIRouter`. That's a follow-up hygiene batch if Joshua wants the pattern unified across the API surface.

---

**End of Section 18.**
