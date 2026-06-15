# CHANGELOG v10.569 — Batch B5: validate at creation + pending-items tracker

## Validate at creation (anti-ghost-deal first defense)
A newly created deal (stage "Lead") did not appear in the manager validation
queue — validation began at "Contacted" — so the line manager couldn't confirm
a new deal is real before it counts. Two thresholds both excluded "Lead":

- utils/core.py: PIPELINE_VALIDATE_STAGE "Contacted" -> "Lead"
  (feeds PipelineManager.get_pending_validations).
- utils/api_pipeline_permissions.py: add "Lead" to VALIDATION_STAGES
  (feeds can_validate, so the Validate button appears for a Lead deal).

Verified: a Lead deal now appears in the queue and is validatable; terminal and
already-validated deals stay excluded.

## PENDING_ITEMS.md (new)
Living backlog of everything outstanding (credit-submission gate + checklist,
EDMS wiring, CBS verification, area-level scope, forecast exclusion of
unvalidated deals, surfacing track, housekeeping) so we don't lose sight.

## Test
tests/test_batchB5_validate_at_creation.py (run in the project venv).
