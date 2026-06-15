# CHANGELOG v10.559 — Batch A (backend): pipeline stages from config

## Context
Confirmed end-to-end: pipeline stages are admin-configurable via
org_config.json (get_pipeline_stages), currently using the fallback set
(Prospecting/Needs Analysis/Proposal/Credit Review/Approval/Disbursed/
Closed Lost). But the advance gate (ALLOWED_ADVANCE_STAGES) was hardcoded and
did NOT include those configured stages, so advancing a configured-stage deal
(e.g. "Needs Analysis") would be rejected. Created deals also had no open_date
(list orders by open_date DESC), so they sorted unpredictably.

## Changes
- utils/api_pipeline_mutations.py: _configured_stage_names() reads
  get_pipeline_stages(); validate_advance_target now permits any configured
  stage (union with the hardcoded set — backward compatible). LMS handoff
  still fires on LMS_DEFERRED_STAGES (incl. "Credit Review"), which is the
  "submit to credit analysis" trigger.
- utils/api.py: NEW GET /api/pipeline/stages returns the configured stages
  (names/colors/probabilities) — the single source for the frontend's stage
  dropdowns + filters (Batch A frontend, next).
- utils/core.py: add_deal stamps open_date = today (setdefault) so new deals
  have a real date for list ordering.

## Verified
- py_compile across all three files; gate accepts configured stages
  ("Needs Analysis","Prospecting") that were previously rejected; "Credit
  Review" still triggers handoff; unknown stages still rejected.

## Next (Batch A frontend)
Stage filter dropdown on the deals table + create form stage dropdown, both
fed by /api/pipeline/stages. This closes "proper dropdowns not a flat list"
and makes a created deal findable by filtering to its stage.
