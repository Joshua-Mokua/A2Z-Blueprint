# CHANGELOG v10.548 — Phase P Batch P3b: Enterprise chart library (recharts)

Adds a reusable, brand-themed charting layer for the dashboard and BSC
surfaces. New dependency: recharts ^2.12.7 (requires `pnpm install`).

## New
- lib/chartTheme.ts            — palette builder + axis/grid chrome + RAG colors.
                                  Brand colors come from /api/branding (no hard-coded hex).
- hooks/useChartPalette.ts     — default palette from live branding + tokens.
- components/charts/ChartCard.tsx        — titled card chrome + loading/empty states.
- components/charts/TrendChart.tsx       — line / area time series.
- components/charts/CategoryBarChart.tsx — grouped / stacked categorical bars.
- components/charts/DonutChart.tsx       — composition donut + optional center label.

## Modified
- package.json   — add recharts.
- pages/Showcase.tsx — three chart demos at /components (superset of the P3a sections).

## Design
- Charts accept an optional `palette`; default sources brand primary/secondary/
  accent from branding, then semantic series from tokens. G381/G382 safe.
- ChartCard composes with any chart: <ChartCard title=…><TrendChart …/></ChartCard>.

## Gate
- Scratch strict tsc on all 6 chart files (with recharts) -> 0 errors.
- Full `pnpm install` then `pnpm tsc --noEmit` -> run by Josh before commit.
