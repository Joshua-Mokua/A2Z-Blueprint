# CHANGELOG v10.578 — Batch B14: split pipeline by asset / liability / insurance / other

## Why
The B11 headline summed loans (assets) and deposits (liabilities) into one
"pipeline value" — meaningless in banking terms. Now split into four buckets,
mirroring the Streamlit asset_pip / liab_pip split.

## Classification = admin config (not hardcoded)
New helpers in utils/api.py:
- _product_class(product_type): returns the product_catalogue class from
  data/pipeline_settings.json (Assets / Liabilities / Transactional / Insurance
  / Investments), exact match then normalized containment (handles naming drift
  like "Mortgage / Home Loan" vs catalogue "Mortgage").
- _classify_product(product_type): maps that class to a headline bucket
  asset / liability / insurance / other; keyword fallback only if the product
  isn't in the catalogue at all.
So when the bank re-maps a product in pipeline_settings.json, the tiles follow —
no code change. (A product_catalogue admin editor UI is a clean follow-up.)

## Analytics response (GET /api/pipeline/analytics) — additive
New `pipelines` object alongside the existing totals/funnel/by_category:
  pipelines.asset      {label:"Asset Pipeline",     value, weighted, active_count, won_value, funnel[]}
  pipelines.liability  {label:"Liability Pipeline", ...}
  pipelines.insurance  {label:"Insurance",          ...}
  pipelines.other      {label:"Other", ..., breakdown:[{subclass, value, count, products:[{product,value,count}]}]}
Each bucket carries its OWN funnel; "other" carries a drill-down by sub-class
(Transactional / Investments) then product. `totals` is kept (grand totals) but
the headline tiles should now use `pipelines`, not the combined total_value.

## Verify (your D0001 loan + D0002 deposit)
GET http://localhost:8502/api/pipeline/analytics  ->
  pipelines.asset.value     == 6,000,000   (D0001)
  pipelines.liability.value == 50,000,000  (D0002)
  pipelines.insurance.value == 0
  pipelines.other.value     == 0

## Next
Frontend: four headline tiles + per-bucket funnel + expandable "Other".

## Tests
tests/test_batchB14_pipeline_buckets.py
