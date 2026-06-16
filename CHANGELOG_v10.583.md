# CHANGELOG v10.583 — Batch B18: create form segment/sector cascade + product-class initial stages

Wires the new-deal form to admin config for two things you flagged:
1. Initial-stage dropdown now follows the product's class flow (loan vs deposit
   vs …) from stage_flows — no longer the old hardcoded category list.
2. Segment + Sector now exist on the form, cascading from client type, sourced
   from admin config.

## Backend
- utils/api_pipeline_models.py: PipelineDealCreate gains `segment` + `sector`
  (Optional). The create endpoint already does model_dump -> add_deal, so both
  auto-persist on the deal — no endpoint change needed.
- utils/api.py: GET /api/pipeline/stages now also returns `customer_segments`
  (from core.CUSTOMER_SEGMENTS: Individual -> Affluent / Core Middle /
  Mass-Retail; Business -> Large Corporate / Corporate / SME / Micro).
- utils/api_pipeline_mutations.py: validate_create_payload now accepts any
  configured stage (stage_flows / deal_categories), not just the narrow
  ALLOWED_ADVANCE_STAGES — so creating at a per-class stage (e.g. the loan-flow
  'Application') is allowed. LMS-handoff stages still rejected at create.

## Frontend
types/pipeline.ts
- PipelineConfig gains stage_flows + customer_segments.
- CreateDealRequest gains segment + sector.

pages/PipelineCreate.tsx
- classifyProduct(productType, product_catalogue) mirrors the backend
  classifier (exact then containment) -> asset/liability/insurance/other.
- Initial-stage options now come from config.stage_flows[class] (terminal
  stages removed), falling back to the legacy category map only before config
  loads or when the product isn't classifiable yet.
- New Segment dropdown (cascades off Customer type, from customer_segments) and
  Sector dropdown (from config.sectors). Both sent on create.

## Verify
- New Deal form: pick "Business Loan" -> Initial stage shows the LOAN flow
  (Lead, Contacted, Qualified, Application, Credit Assessment, ...). Pick a
  deposit product -> the DEPOSIT flow (no Credit Assessment).
- Customer type Individual -> Segment offers Affluent / Core Middle /
  Mass-Retail; Business -> Large Corporate / Corporate / SME / Micro.
- Sector dropdown lists the 13 configured sectors.
- Create a deal with a segment + sector -> GET /api/pipeline/deals/{id} shows
  both persisted.

## Tests
tests/test_batchB18_segment_sector_stage.py (run scripts/add_stage_flows.py first)

## TypeScript gate
pushd frontend\web && pnpm tsc --noEmit && popd
