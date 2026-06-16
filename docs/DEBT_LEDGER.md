# DEBT_LEDGER.md

Tracked technical-debt inventory, grounded in same-turn code inspection (CGR1).
Distinguishes real debt (carried-forward risk) from future features. Updated per
batch. Established at the MIS-V1 boundary (2026-06-16).

## CLEARED in B23 (v10.589)

### D1 — Dashboard pipeline alignment  [CLEARED]
`pipeline_summary` already computed `validated_value`/`pending_value`, but the MD
dashboard and `Dashboard.tsx` surfaced only the consolidated `pipeline_value`
(raw sum), contradicting the funnel/tiles which anchor on validated.
**Fix:** md_dashboard now exposes validated_value/pending_value/pending_validation;
Dashboard.tsx headline is "Assured Pipeline Value" (validated) with pending as a
sub. Evidence: api.py md_dashboard pipeline block; Dashboard.tsx Pipeline stats.

### D2 — Pipeline→credit lifecycle divergence  [CLEARED]
`submit-to-credit` set `submitted_to_credit` + `lms_application_id` but never
advanced the deal's pipeline stage, so a submitted deal sat frozen at "Credit
Assessment" while its loan progressed; the funnel counted it there indefinitely.
**Decision (Joshua, 2026-06-16):** on successful submit, auto-advance the deal one
stage in its configured product-class flow (asset: Credit Assessment → Offer /
Proposal), never into a Closed stage. Config-driven via `stage_flows`; best-effort
(never fails a valid submission). Pairs with the B22b Credit-Assessment lock.

## OPEN (do not distort numbers; safe to defer past hierarchy work)

### D3 — `credit_workflow.py` consolidation  [OPEN, deferred]
Two parallel models coexist: the live string-status `LMS_WORKFLOW_TRANSITIONS`
(wired) and `credit_workflow.py`'s `ApplicationState` enum + `ALLOWED_TRANSITIONS`
+ its own committee model (both unwired). Deliberate trade-off in B19 (extend the
live flow rather than refactor onto the enum). Cleanup, not a functional break.
**When to do:** a dedicated consolidation batch, ideally before any new state is
added to the LMS machine.

### D4 — Committee charter not exposed to frontend  [OPEN, minor UX]
`committee_member_ids()` exists server-side but there is no GET endpoint, so the
vote UI uses a free-text member-id box instead of a dropdown. For simulation, the
default charter members are m1..m5.
**When to do:** small endpoint (GET committee charter) + dropdown; any time.

## NOT DEBT — future features (track separately, sequence on demand)
- Manager "my deals" vs "my team's deals" filter
- Admin deal-owner reassignment endpoint (interim: admin has operate rights)
- EDMS auto-satisfy of the credit checklist (data/edms_documents.json)
- Sectorization / CVP head pipeline views
- List auto-refresh after mutation (minor UX)
- "Other"-bucket drill-down

## HIERARCHY PHASE (the next phase itself — not pre-clearable debt)
- Area managers all resolve to "Head Office" → real regions + region scope tier
- `org_config.hierarchy` completion (CEO + ~63 unplaced roles)
- Retire the hardcoded reporting tree

## SECURITY/GOVERNANCE (mostly closed)
- GAP-007 (`_APP_VERSION` stamp informational only) — OPEN
- GAP-003 / GAP-004 — DEFERRED (triggers not yet materialised)
- OI-64/65/66 — AI-engine registry governance items
