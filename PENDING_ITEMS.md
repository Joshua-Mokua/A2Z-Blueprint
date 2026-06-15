# A2Z Blueprint — Pending Items Tracker
_Living backlog so nothing gets lost. Updated 2026-06-15 (post v10.569)._

## Pipeline → Credit submission (NEXT BATCH — approved approach)
- [ ] **Explicit "Submit to Credit Analysis" button** on the loan deal detail,
      replacing the silent stage-trigger. Calls a new
      `POST /api/pipeline/deals/{id}/submit-to-credit`.
- [ ] **Document-checklist gate**: validate provided ⊇ required (required from
      config — category `docs_required` / swim-lane `document_checklist`).
      Missing → 400 listing the missing documents; complete → create the credit
      application (`create_from_pipeline_deal`) and link it.
- [ ] **Capture "document provided"** via tick-the-checklist on the deal now
      (simulation), EDMS-backed later (decision: checklist now, EDMS wiring later).
- [ ] **Remove the silent Compliance auto-trigger** (v10.568 stopgap) once the
      explicit gated button exists, so credit submission happens ONLY through it.

## EDMS (backend exists — wire to the flow)
- [ ] For **existing clients**, link EDMS documents (data/edms_documents.json,
      linked by client_cif / linked_id) so on-file docs auto-satisfy checklist
      items. Note: current synthetic EDMS rows have blank linked_id.
- [ ] Add an EDMS API endpoint + a documents panel on deal / LMS detail
      (currently Streamlit-only: pages/31_edms.py).

## CBS fetch for existing clients (verify still tight)
- [ ] Confirm the CIF lookup → autopopulate path is intact after recent changes
      (Josh flagged hoping it's still tight). Add a regression check.

## Scope (data-driven cascade)
- [x] Branch-head sees own branch (B2, v10.565).
- [x] CEO/register-root all-view from data (B1, v10.562).
- [ ] **Area Manager → their region's branches** — BLOCKED on register data:
      Area Managers are tagged Region="Head Office". Josh to allocate real
      regions from the admin module; then extend the resolver one tier up.
- [ ] Reconcile "Branch Manager" vs "Senior Branch Manager" (same level — Josh
      confirmed; both already branch heads in B2).
- [ ] After area scope proven: extend to Head of Branches / CRBO; then retire
      hardcoded REPORTING_TREE / _ALL_VIEW_ROLES.

## Validation / anti-ghost-deal
- [x] Validate at creation (Lead) — deal surfaces for line-manager validation
      (B5, v10.569).
- [ ] Confirm/implement that **unvalidated deals are excluded from pipeline
      value & forecast** (the full anti-inflation effect, not just the queue).

## Surfacing track (config-driven UI)
- [ ] Create form from config (category → category-specific stages + sector +
      decision-level).
- [ ] Surface credit workflow on LMS detail (swim lanes / mandate matrix /
      document checklist from lms_config).
- [ ] Stage-funnel dashboards for Pipeline + Credit/LMS (config-driven).

## Data / housekeeping
- [ ] Re-run `reset_test_data.py --confirm` for a clean slate (clears stale
      JSON deals like D0007 that predate the run).
- [ ] Complete org_config.hierarchy (place CEO at top + 63 unplaced roles) —
      admin-module/data task; makes more roles config-driven with no code change.

## Recently closed (context)
- v10.562 B1 data-driven all-view · v10.565 B2 branch-head scope ·
  v10.567 B3 validation queue excludes terminal · v10.568 B4 Compliance handoff
  (stopgap) + login diagnostic · v10.569 B5 validate-at-creation.
