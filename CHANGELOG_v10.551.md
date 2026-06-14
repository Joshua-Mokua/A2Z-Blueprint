# CHANGELOG v10.551 — Phase P Batch P5: Dashboard Credit Risk panel

Wires P3b's chart library into the live CEO dashboard, consuming the
existing /api/cockpit/credit/open-work endpoint (no new backend).

## New
- types/cockpit.ts          — CreditOpenWork (mirrors credit_open_work()).
- hooks/useCreditOpenWork.ts — fetch-wrap hook.

## Modified
- lib/api.ts          — fetchCreditOpenWork() (GET /api/cockpit/credit/open-work).
- pages/Dashboard.tsx — "Credit Risk" section:
    * DonutChart — IFRS9 stage distribution (Stage 1/2/3), green/amber/red
      from chartTheme.ragColor (token-sourced, no hard-coded hex).
    * CategoryBarChart — loan applications by swim-lane.
    * Stat tiles — NPL %, watchlist entries, open applications.
  Own loading/empty states via the credit hook (independent of the MD hook).

## Notes
- Colors come from chartTheme.ragColor (semantic tokens). G381/G382 safe.
- npl_pct may be null (no IFRS9 records) -> rendered as "n/a".
- BSC trend line still deferred until a /trends endpoint exists (point-in-
  time data can't draw a trend).

## Gate
- Scratch strict tsc (cockpit type + hook + Dashboard, with recharts) -> 0 errors.
- Full pnpm tsc --noEmit -> run by Josh before commit.
