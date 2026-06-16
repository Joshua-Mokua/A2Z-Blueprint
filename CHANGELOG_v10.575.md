# CHANGELOG v10.575 — Batch B11: Pipeline analytics endpoint

## What
Backend aggregation for the pipeline funnel + headline metrics — the data
behind tomorrow's funnel view. Numbers mirror the Streamlit page exactly.

utils/api.py:
- GET /api/pipeline/analytics  -> {totals, funnel, by_category}
    totals:      total_value (active pipeline), weighted_value (probability-
                 weighted, same stage weights as PipelineManager), won_value,
                 active_count, won_count, lost_count, live_count, win_rate (%).
    funnel:      active stages in canonical order, non-empty only,
                 each {stage, count, value}.
    by_category: per pipeline category {category, count, active_count, value,
                 weighted, funnel[]}, sorted by value desc.
- Reads deals from the SAME source the list endpoint uses (Postgres-first,
  JSON fallback) and applies the SAME cascade scope filter — so the funnel
  agrees with the list a user sees. MD sees the whole-bank funnel; a branch
  manager sees only their branch's funnel (same endpoint, scope-aware).
- Helpers: _acquire_scoped_deals(user), _compute_pipeline_analytics(deals)
  (pure), _deal_value(), _STAGE_WEIGHTS.

## Verify now (before the chart lands in B12)
GET http://localhost:8502/api/pipeline/analytics  (as william0001 = whole bank,
as immaculate0716 = Thika only). Confirm totals + funnel look right against
what you see in the pipeline list.

## Mirrors
pages/3_pipeline.py: pip_val / wt_val / won_val / conv_r (headline) and the
per-category funnels (Conversion view). Stage weights from
core.PipelineManager.weighted_pipeline.

## Next (B12)
Frontend Pipeline Analytics page — funnel chart (recharts v2) + category
breakdown bars + headline tiles, scope-aware.

## Test
tests/test_batchB11_analytics.py
