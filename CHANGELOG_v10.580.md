# CHANGELOG v10.580 — Batch B16: fix "Field required" when advancing a deal

## Bug
Advancing a deal failed with a vague "Field required" even with a valid stage
and note. Cause: a field-name mismatch — the React client sends `target_stage`,
but the backend model PipelineDealAdvance required `new_stage`. So `new_stage`
arrived empty -> Pydantic 422 "Field required" (field name not surfaced).

## Fix
utils/api_pipeline_models.py: PipelineDealAdvance.new_stage now accepts both
names via AliasChoices("new_stage", "target_stage") + populate_by_name. The
endpoint still reads payload.new_stage, populated from either key. No frontend
rebuild needed — the existing UI works immediately.

## Note (not this bug)
Lead -> Negotiation skipping intermediate stages is allowed by design —
validate_advance_target permits any stage in ALLOWED_ADVANCE_STAGES, it does not
enforce strict adjacency.

## Test
tests/test_batchB16_advance_alias.py
