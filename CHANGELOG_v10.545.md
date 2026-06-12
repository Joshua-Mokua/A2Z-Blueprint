# CHANGELOG v10.545 — Phase P Batch P4: CEO/MD Command Centre (live)

Replaces the Dashboard shell with a live executive cockpit consuming the
already-built /api/dashboard/md endpoint. Closes M3 (dashboard wiring)
from PARITY_UX_ASSESSMENT_2026_06_12.md — the Brain milestone.

## New
- types/dashboard.ts      — MdDashboardResponse (mirrors md_dashboard payload).
- hooks/useMdDashboard.ts  — fetch-wrap hook (matches usePortfolioSummary pattern).

## Modified
- lib/api.ts        — fetchMdDashboard() (GET /api/dashboard/md).
- pages/Dashboard.tsx — live cockpit: BSC score + NPL as RAG KpiTiles
  (P3a primitives), pipeline/credit/AML/org as Stats, loading skeletons,
  error+retry, snapshot timestamp, manual refresh. Null-safe throughout.

## Notes
- RAG bands on BSC score / NPL are PRESENTATION HEURISTICS (commented as
  such); authoritative RAG should come from Target Cascade bank targets
  once wired into the payload.
- Endpoint is any-authenticated + bank-wide (not cascade-scoped), so all
  test roles can view it. william001 (CEO) is the intended consumer.

## Gate
- Scratch strict tsc on dashboard.ts + useMdDashboard.ts + Dashboard.tsx -> 0 errors.
- Full pnpm tsc --noEmit (in context) -> run by Josh before commit.
