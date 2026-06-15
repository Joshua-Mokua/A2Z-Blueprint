# CHANGELOG v10.560 — Batch A2: pipeline config from pipeline_settings.json

## Why (corrects Batch A)
Batch A read get_pipeline_stages() (org_config -> 7-stage fallback). But the
authoritative admin config is data/pipeline_settings.json, which defines 9
deal categories — New Facility, Top Up, Renewal, Restructure, Partnership/MOU,
Customer Referral, Sponsored Event, Beyond Banking, Retailer Finance — each
with its own stage flow (17 distinct stages live in the seeded data, 45 stage
names across all flows), plus sectors, decision_levels, probability maps,
deal_types and product_catalogue. Reading org_config instead would still
reject configured stages (Term Sheet, Due Diligence, Valuation, Vetting,
Credit Committee, Bank Approval, Documentation) — the mismatch.

## Changes
- utils/core.py: get_all_pipeline_stage_names() collects every stage across
  pipeline_settings stages + all deal_categories flows.
- utils/api_pipeline_mutations.py: the advance gate now accepts any of those
  configured stages (45 names) — no hardcoding.
- utils/api.py: GET /api/pipeline/stages now returns the FULL config —
  stages, deal_categories (with per-category flows), sectors, decision_levels,
  probability_map, deal_types, product_catalogue, currency — the single source
  for all frontend pipeline dropdowns.

## Verified
- py_compile x3; 45 configured stage names collected; all previously-rejected
  stages now accepted; 16/17 seeded stages covered (the 17th, "Signed", is a
  data-generation orphan not present in any configured flow — config has
  "Signing").

## Next (Batch A frontend)
Frontend consumes the rich config: category selector -> category-specific
stage dropdown on create + a stage filter on the list, plus sector and
decision-level dropdowns — all from /api/pipeline/stages.
