# A2Z Blueprint — Pending Items Tracker
_Living backlog so nothing gets lost. Updated 2026-06-15 (post v10.572)._

## NEXT: Pipeline → Credit submission (you chose to finalize credit)
- [ ] Explicit "Submit to Credit Analysis" button (replaces silent stage trigger).
      `POST /api/pipeline/deals/{id}/submit-to-credit`.
- [ ] Document-checklist gate: required from config (category `docs_required` /
      swim-lane `document_checklist`); missing -> 400 listing missing docs;
      complete -> create the credit application and link it.
- [ ] Capture "document provided" via tick-the-checklist now (sim), EDMS later.
- [ ] Remove the silent Compliance auto-trigger (v10.568) once the gated button exists.

## Deal store / data integrity
- [x] Postgres list enforces scope + permissions (B8) — was a leak + empty YOU CAN.
- [ ] **Unify reads on one store.** List reads Postgres; validation queue +
      get_pending_validations read JSON (PipelineManager). They diverge (a deal
      visible in the queue but not the list). Durable fix: read all pipeline
      views from Postgres (the architectural aim). Interim: clean reset so both
      stores align, then create fresh (H5 syncs both).
- [ ] Root-cause what empties pipeline_deals / users.json between sessions.

## Deal ownership & continuity
- [x] Manager oversees, owner operates (B7).
- [ ] Admin reassignment of a deal's owner (staff departure), with the set of
      authorized-to-reassign roles defined by admin in config. Interim: admin edits owner.

## Manager pipeline view (you raised)
- [ ] Managers can create their OWN deals (the +New Deal button is already
      present) — confirm create works for managers and that their own deals show.
- [ ] "My deals" vs "My team's deals" filter so a manager can switch between
      their own pipeline and their cascade.

## Sectorization / CVP (you raised — untouched)
- [ ] Pipeline views by SECTOR and by CVP head. pipeline_settings has sectors[13];
      deals carry a sector. A sector/CVP head should see deals in their sector
      (a scope dimension orthogonal to the reporting hierarchy). Design needed:
      how sector/CVP heads are defined and how sector scope composes with cascade scope.

## Scope (data-driven cascade)
- [x] B1 all-view (root) · [x] B2 branch-head sees own branch.
- [ ] Area Manager -> region's branches — BLOCKED on register data (Area Managers
      tagged Region="Head Office"); Josh allocating real regions from admin.
- [ ] Then Head of Branches / CRBO; then retire hardcoded REPORTING_TREE.

## Validation / anti-ghost-deal
- [x] Validate at creation (B5) · [x] Terminal excluded from queue (B3).
- [ ] Unvalidated deals excluded from pipeline value & forecast.

## Surfacing / housekeeping
- [ ] Create form from config (category -> stages + sector + decision-level).
- [ ] Credit workflow on LMS detail (swim lanes / mandate matrix / doc checklist).
- [ ] Stage-funnel dashboards (Pipeline + Credit/LMS).
- [x] Branch test logins self-heal (B6).
- [ ] EDMS API + panel; complete org_config.hierarchy (CEO + 63 unplaced roles).

## Recently closed
- B1 all-view · B2 branch scope · B3 terminal-queue fix · B4 Compliance handoff +
  diagnostic · B5 validate-at-creation · B6 login self-heal · B7 manager-no-operate ·
  B8 DB list scope+permissions.
