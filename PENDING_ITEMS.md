# A2Z — Pending Items (living backlog)

Last updated: v10.574 (B10). Newest-first within each group.

## DONE (recent)
- [x] Submit-to-Credit document gate — explicit, config-sourced checklist,
      blocks on missing docs, creates linked loan application.
      Backend B9 (v10.573) + Frontend B10 (v10.574). Silent Compliance
      trigger removed; gated button is the only path to credit.

## PENDING — next up (code, ready when you are)
- [ ] Admin reassignment of a deal's owner (staff departure/handover):
      POST /api/pipeline/deals/{id}/reassign {new_owner_staff_code};
      can_reassign = admin OR admin-configured roles; audit REASSIGNED;
      owner re-sync; frontend control. Interim: admin edits owner directly.
- [ ] Managers: "My deals" vs "My team's deals" filter (managers can already
      create; this is the view split).
- [ ] Unvalidated deals excluded from pipeline VALUE & forecast (full
      anti-ghost effect, not just the validation queue).

## PENDING — needs your input / data
- [ ] Allocate real Area Manager regions from the admin module (all 10 are
      currently Region="Head Office"). Then I extend the scope resolver one
      tier up (region-scoped, bounded to the region's branches), then Head of
      Branches / CRBO, then retire the hardcoded reporting tree.
- [ ] Complete org_config.hierarchy (CEO + ~63 unplaced roles) — admin/data.
- [ ] Sectorization / CVP heads — pipeline views by sector and CVP head;
      orthogonal scope dimension to the reporting hierarchy; needs design
      (how sector/CVP heads are defined, how sector scope composes with
      cascade scope). EDMS exists for existing clients (data/edms_documents.json,
      linked by client_cif, Streamlit-only) — wire later to auto-satisfy the
      checklist for existing clients.

## PENDING — architecture / hygiene
- [ ] Unify pipeline reads on Postgres. The list reads the DB; the validation
      queue reads JSON (PipelineManager) — they can disagree. Durable fix is
      one source of truth.
- [ ] Root-cause what empties pipeline_deals / users.json between sessions
      (the self-heal masks it).
- [ ] Verify CBS fetch for existing clients (CIF lookup -> autopopulate) is
      intact; add a regression check.

## PENDING — surfacing track (config-driven UX)
- [ ] Create-deal form from config (category -> stages + sector + decision level).
- [ ] Credit workflow on LMS detail (swim lanes / mandate matrix / doc checklist).
- [ ] Stage-funnel dashboards.
