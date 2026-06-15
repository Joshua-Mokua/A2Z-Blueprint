# CHANGELOG v10.567 — Batch B3: validation queue excludes terminal deals

## Problem
Closed Lost / Closed Won deals appeared in the Manager Queues > Validation tab.
A closed deal never needs validation.

## Cause
PipelineManager.get_pending_validations() filtered on STAGE_NAMES[idx:], a
slice from the validate stage ("Contacted") to the END of the stage list — which
includes the terminal stages "Closed Won" and "Closed Lost". So every closed
deal in scope leaked into the validation queue.

## Fix
utils/core.py — intersect the filter with ACTIVE_STAGES (= STAGE_NAMES minus
"Closed Won"/"Closed Lost"). One added predicate; no behaviour change for
active deals.

  result = [d for d in self.deals
            if d['stage'] in STAGE_NAMES[idx:]
            and d['stage'] in ACTIVE_STAGES        # NEW: drop terminal deals
            and not d.get('manager_validated')
            and not d.get('cancel_requested')]

## Verified
- Closed Lost / Closed Won -> excluded.
- Qualified / Compliance (active) -> retained.
- manager_validated / cancel_requested -> still excluded (unchanged).

## Test
tests/test_batchB3_validation_queue_terminal.py (run in the project venv).

## Note
The queue still keys off the hardcoded STAGE_NAMES (8-stage legacy), not the
45-stage pipeline_settings config. Aligning the queue to config stages is a
separate, already-tracked item; this fix is scoped to the terminal-leak bug.
