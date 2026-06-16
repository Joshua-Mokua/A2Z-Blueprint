# CHANGELOG v10.581 — Batch B17: per-product-class stage flows (admin config)

## What
Loan leads and deposit leads now follow DISTINCT stage flows, defined in admin
config (the single source of truth) — not a flat shared list. Backend + config
this batch; the advance dropdown wiring is the next (frontend) batch.

## Config (run the script — idempotent, backs up, non-destructive)
scripts/add_stage_flows.py adds `stage_flows` to pipeline_settings.json:
  asset:     Lead -> Contacted -> Qualified -> Application -> Credit Assessment
             -> Offer / Proposal -> Negotiation -> Compliance -> Closed Won/Lost
  liability: Lead -> Contacted -> Proposal -> Negotiation -> Documentation -> Closed
  insurance: Lead -> Contacted -> Proposal -> Negotiation -> Documentation -> Closed
  other:     Lead -> Contacted -> Qualified -> Proposal -> Negotiation -> Closed
(asset/liability seeded from your existing core.py Loan/Deposit flows; the bank
edits any of these in config — no code change.)

## Backend
- utils/core.py get_all_pipeline_stage_names(): now also unions stage_flows
  stages, so the advance gate accepts loan-only stages (Application, Credit
  Assessment, Offer / Proposal) the bank configures.
- utils/api.py _stage_flow_for(product_type): classifies the product
  (asset/liability/insurance/other) and returns that class's flow from config;
  falls back to the core per-category flow if stage_flows isn't set.
- GET /api/pipeline/deals/{id}  -> now includes `stage_flow` (this deal's flow).
- GET /api/pipeline/stages      -> now includes `stage_flows` (all class flows).
- Advance endpoint ENFORCES the deal's flow: a deposit deal cannot advance to a
  loan-only stage (HTTP 400 with the allowed stages). Server-side, so it holds
  even before the dropdown is wired.

## Verify (/api/docs)
- GET /api/pipeline/deals/D0001 -> stage_flow is the asset (loan) flow.
- GET /api/pipeline/deals/D0002 -> stage_flow is the liability (deposit) flow.
- POST advance D0002 -> "Credit Assessment" -> 400 (loan-only).
- POST advance D0001 -> "Credit Assessment" -> allowed.

## Next
Frontend: advance dropdown reads the deal's stage_flow (loan vs deposit) instead
of the flat ADVANCE_TARGET_STAGES.

## Tests
tests/test_batchB17_stage_flows.py  (run scripts/add_stage_flows.py first)
