# A2Z Blueprint — Pending Items Tracker
_Living backlog so nothing gets lost. Updated 2026-06-15 (post v10.571)._

## Deal ownership & continuity
- [x] Manager oversees but does NOT operate a subordinate's deal — view +
      validate + query + approve-cancel only; owner drives edit/advance; admin
      retains full operate (B7, v10.571).
- [ ] **Admin reassignment** (NEXT, you requested): a sanctioned action to
      change a deal's owner when a staff member leaves without handover.
      - Endpoint `POST /api/pipeline/deals/{id}/reassign {new_owner_staff_code}`.
      - `can_reassign` = admin OR a role the **admin has authorized** to reassign.
      - **Admin-defined authorized roles** in config (e.g. org_config key
        `reassign_authorized_roles`, default Admin only; admin can add e.g.
        Regional Head / Head of Branches).
      - Audit REASSIGNED; re-sync owner to DB (H5).
      - Frontend: reassign action gated by `can_reassign`, new owner picked from
        scoped staff.
      - Interim: admin can already reassign by editing the deal owner.

## Pipeline → Credit submission (approved approach)
- [ ] Explicit "Submit to Credit Analysis" button (replaces the silent stage
      trigger). `POST /api/pipeline/deals/{id}/submit-to-credit`.
- [ ] Document-checklist gate: required from config (category `docs_required` /
      swim-lane `document_checklist`); missing → 400 listing missing docs;
      complete → create the credit application and link it.
- [ ] Capture "document provided" via tick-the-checklist now (sim), EDMS later.
- [ ] Remove the silent Compliance auto-trigger (v10.568) once the gated button exists.

## EDMS (backend exists — wire to the flow)
- [ ] Link EDMS docs (edms_documents.json, by client_cif / linked_id) so an
      existing client's on-file docs auto-satisfy checklist items.
- [ ] EDMS API endpoint + documents panel on deal / LMS detail (Streamlit-only today).

## CBS fetch for existing clients
- [ ] Verify the CIF lookup → autopopulate path is still tight; add a regression check.

## Scope (data-driven cascade)
- [x] B1 data-driven all-view (root) · [x] B2 branch-head sees own branch.
- [ ] Area Manager → region's branches — BLOCKED on register data (Area Managers
      tagged Region="Head Office"). Josh allocating real regions from admin;
      then extend resolver one tier up.
- [ ] After area proven: Head of Branches / CRBO; then retire hardcoded
      REPORTING_TREE / _ALL_VIEW_ROLES.

## Validation / anti-ghost-deal
- [x] Validate at creation (Lead) — B5. [x] Terminal deals excluded from queue — B3.
- [ ] Confirm/implement: unvalidated deals excluded from pipeline value & forecast.

## Surfacing track (config-driven UI)
- [ ] Create form from config (category → stages + sector + decision-level).
- [ ] Credit workflow on LMS detail (swim lanes / mandate matrix / doc checklist).
- [ ] Stage-funnel dashboards for Pipeline + Credit/LMS.

## Login / data housekeeping
- [x] Branch test logins self-heal across users.json resets (B6, v10.570).
- [ ] Root-cause what empties users.json between sessions (self-heal masks it now).
- [ ] Re-run reset_test_data.py --confirm for a clean slate (clears stale JSON
      deals like D0006/D0007 that predate the run).
- [ ] Complete org_config.hierarchy (CEO + 63 unplaced roles) — admin/data task.

## Recently closed
- B1 all-view · B2 branch-head scope · B3 validation-queue terminal fix ·
  B4 Compliance handoff (stopgap) + login diagnostic · B5 validate-at-creation +
  tracker · B6 branch-login self-heal · B7 manager can't operate subordinate deal.
