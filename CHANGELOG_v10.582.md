# CHANGELOG v10.582 — Frontend capstone: assured tiles + funnel + aging + per-class advance dropdown

Wires the React pipeline page to the B14/B15/B17 backend. Every tile is now
backend-driven (no more local sums), the advance dropdown follows each deal's
product-class flow, and the page gains a validated funnel + deal aging.

## Backend (utils/api.py)
- GET /api/pipeline/analytics now also returns scope-aware
  totals.pending_validation + totals.pending_cancel (managers: real queue
  counts over visible staff; non-managers: 0). One analytics call now feeds
  every tile.

## Frontend
types/pipeline.ts
- PipelineDealDetailResponse gains `stage_flow?: string[]` (B17).
- PipelineDeal gains `open_date?` (DB-sourced deals, for aging).
- New analytics types: FunnelStage, PipelineBucket, PipelineAnalyticsTotals,
  PipelineAnalyticsResponse, Other* drill-down.

lib/api.ts
- fetchPipelineAnalytics() -> GET /api/pipeline/analytics.

components/PipelineFunnel.tsx (NEW)
- Dependency-free horizontal-bar funnel (no chart library). Renders the
  validated-only funnel from analytics.

pages/Pipeline.tsx
- Replaced the 3 locally-computed tiles with backend-driven ones:
  * 4 assured tiles by product class — Asset / Liability / Insurance / Other —
    each showing VALIDATED value, with "<x> pending assurance" beneath.
  * Scope row: Deals Visible · Pending Validation (scope-aware, accent when >0)
    · Total Assured (with pending-assurance subfigure).
- Added the Validated pipeline funnel card.
- Added an "Age" column (days open; >14d shown red · stale).
- Version badge -> "v10.582 capstone" (use it to confirm the new build loaded;
  hard-refresh if you still see the old badge).

pages/PipelineDealDetail.tsx
- Advance dropdown now follows the deal's stage_flow from the detail response
  (loan vs deposit vs insurance), falling back to the flat list only if config
  didn't load. This is the fix for "stages have not changed" — B17 was
  backend-only; this wires the UI.

## Verify (browser, after `pnpm tsc --noEmit` passes)
As Immaculate (manager):
- Tiles: Asset ~6.00M, Liability ~50.00M, Insurance pending-assurance ~230K
  (unvalidated), Pending Validation reflects her queue.
- Funnel shows validated deals by stage.
- Open D0001 (Business Loan) -> advance dropdown shows the LOAN flow
  (Application, Credit Assessment, ...). Open D0002 (Fixed Deposit) -> the
  DEPOSIT flow (no Credit Assessment).
- Deal rows show an Age column.

## TypeScript gate
pushd frontend\web && pnpm tsc --noEmit && popd   (must be clean before commit)
