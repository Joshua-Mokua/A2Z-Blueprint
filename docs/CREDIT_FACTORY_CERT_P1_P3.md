# Credit Factory Hardening — Phases 1–3 Certification

Date: 2026-06-16 · Baseline: MIS-V1.1 (simulation-green, 43/43)
Method: verified from code; runtime claims backed by scripts/simulate_credit_chain.py.

## Phase 1 — Create Deal: CLOSED (no defect)

| Step | Evidence |
|---|---|
| Reproduce | Drove POST /api/pipeline/deals via harness + React contract |
| Payload | Required fields: client_name, deal_value, product_type, stage (staff_code/staff_name optional, server-authoritative) |
| Response | 201 Created, body = PipelineDeal; 120/120 in stress, 201 every time |
| Root cause | The only failure ever seen was the *harness* sending amount/product instead of deal_value/product_type. The React CreateDealRequest sends the correct names — backend model and form are aligned. |
| Fix | Harness corrected (B25). React form unchanged — never defective. |
| Regression | simulate_credit_chain.py create steps PASS both routes; --volume 120 = 120/120 |

Verdict: **Create Deal works reliably.** Phase 1 gate satisfied.

## Phase 2 — Parity Certification Matrix

| Capability | Backend | React | Status |
|---|---|---|---|
| Create / advance deal | ✓ | PipelineCreate / DealDetail | Certified |
| Doc-gated submit + stage lock | ✓ | CreditSubmissionPanel + AdvancePanel | Certified |
| Assign analyst | ✓ | LmsApplicationDetail | Certified |
| Info-request loop | ✓ | WfRequestInfo/WfSimple | Certified |
| Decision (approve/decline) | ✓ | LmsApplicationDetail | Certified |
| Committee refer/vote/resolve | ✓ | WfCommittee | Certified (free-text member id — see D-C) |
| Offer sign/validate/confirm | ✓ | Wf* + Timeline | Certified |
| CALMS conditions fulfil | ✓ | CreditAdminCaseDetail | Certified |
| Two-layer authorize/disburse | ✓ | CaAuthPanel/DisbursePanel | Certified |
| Structured security perfection | ✗ (checklist only) | ✗ | Missing (Phase 4) |
| Executive drill-down | ✗ | ✗ | Missing (Phase 5) |

All certified rows are runtime-verified (43/43). No assumptions.

## Phase 3 — BSC Wiring Completion: DONE

Prior state (corrected from earlier audit): BSC was wired on pipeline
create/advance/refer, LMS decision, and CA disburse — but (a) submit-to-credit,
committee-resolve were unwired, and (b) every trigger credited the CALLER, so an
RM whose loan was approved/disbursed by a manager never got BSC credit.

Changes:
- New `emit_bsc_for(usernames)` in api_bsc_bridge.py — dedupes, skips blanks,
  recomputes each via update_bsc_from_modules, best-effort.
- submit-to-credit (api.py): fires for owner (caller == owner here).
- LMS decision (api_lms_routes.py): now credits app.created_by (owner) + caller.
- LMS committee resolve (api_lms_routes.py): credits owner + resolving manager.
- CA disburse (api_credit_admin_routes.py): resolves owner via linked
  application's created_by, credits owner + clearer.

Result: Pipeline → LMS → Credit Admin → BSC is now one uninterrupted chain, with
loan-book growth attributed to the originating RM's scorecard.

Regression: tests/test_phase3_bsc_owner_attribution.py (2 pass) — owner+caller
attribution, dedup, blank-safety, best-effort-on-error.

## Remaining (sequenced)
- Phase 4 Security Perfection (largest build, backend-first) — structured legal
  review / perfection / insurance / collateral / CP-vs-CS as first-class objects.
- Phase 5 Executive drill-down (pairs with hierarchy rework).
- Phase 6 UX polish. Phase 7 final certification + verdict.
