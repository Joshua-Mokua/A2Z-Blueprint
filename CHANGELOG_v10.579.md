# CHANGELOG v10.579 — Batch B15: validated/pending split + pending-validation tile fix + Bancassurance

## Three things
1. PENDING VALIDATION tile was wrong (showed 0 / "No cancel requests").
   pipeline_summary never returned a validation count — the tile fell back to
   the cancel count. Now returns scope-aware counts:
     totals.pending_validation  — managers: count of subordinate deals awaiting
                                   their sign-off (same source as Manager Queues
                                   -> Validation). Non-managers: 0 (they don't
                                   validate). So Frank=0, Immaculate=1 (D0003).
     totals.pending_cancel      — scope-aware cancel-request count.

2. Validated (assured) vs pending-assurance split, everywhere value is shown.
   Management anchors on VALIDATED deals. pipeline_summary + analytics now split:
     totals.total_value / pipelines.<bucket>.value   = VALIDATED active (headline)
     totals.pending_value / pipelines.<bucket>.pending_value = unvalidated active
   The funnel (overall + per bucket) is VALIDATED-ONLY, matching the headline.
   pipeline_summary also adds totals.validated_value + totals.pending_value.

3. Bancassurance -> Insurance by CONFIG (not keyword fallback).
   scripts/add_bancassurance.py adds it to product_catalogue.Insurance in
   pipeline_settings.json (idempotent, backs up first, preserves other config).

## Your live state after applying
With D0001 + D0002 validated and D0003 (Bancassurance) pending, Immaculate sees:
  Asset Pipeline      6,000,000 assured
  Liability Pipeline 50,000,000 assured
  Insurance                   0 assured · 230,000 pending assurance
  PENDING VALIDATION  1   (D0003 awaiting her sign-off)

## Tests
tests/test_batchB15_validation_split.py (new)
tests/test_batchB11_analytics.py, tests/test_batchB14_pipeline_buckets.py
  (fixtures updated — value is now validated-only, so active deals are marked
   manager_validated=True)

## Next
Frontend: four assured tiles (+ pending-assurance subfigure), validated-only
funnel, expandable Other, and the corrected PENDING VALIDATION tile.
