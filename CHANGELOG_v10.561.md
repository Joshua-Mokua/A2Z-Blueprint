# CHANGELOG v10.561 — Batch A (frontend): category + stage filter dropdowns

## What
The deals list now has two admin-config-driven filter dropdowns in the header,
fed by GET /api/pipeline/stages (Batch A2):
- **Category** — the 9 configured deal categories (New Facility, Top Up,
  Renewal, Restructure, Partnership/MOU, Customer Referral, Sponsored Event,
  Beyond Banking, Retailer Finance).
- **Stage** — narrows to the selected category's own stage flow; shows all
  configured stages when no category is chosen.

Selecting a filter calls refetch({category, stage}) — the list endpoint filters
server-side (deal_category / stage columns). "All categories" / "All stages"
clear each filter. This is what makes a created deal findable (filter to its
category/stage) and replaces the flat "list of all" with the configured
workflow.

## Files
- types/pipeline.ts: PipelineConfig / DealCategoryConfig / PipelineStageConfig.
- lib/api.ts: fetchPipelineConfig() -> /pipeline/stages.
- pages/Pipeline.tsx: config load on mount, catFilter/stageFilter state,
  category-aware stageOptions, two <select> dropdowns in the header.

## Verified
- Scratch tsc: config types + the Pipeline filter logic (stageOptions,
  buildQuery, config shape) type-check cleanly under strict mode.
- Braces balanced; imports resolve.
- Canonical gate in your env: pushd frontend\web && pnpm tsc --noEmit && popd

## Next
Create-form dropdowns from the same config (category -> category-specific
stages + sector + decision-level), then sectors elsewhere; EDMS surfacing.
