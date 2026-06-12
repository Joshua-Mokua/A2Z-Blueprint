# CHANGELOG v10.543 — Phase P Batch P3a: Intelligence-display primitives

Closes design-system gaps M9 (modal) and M10 (KPI/RAG/variance tier) from
PARITY_UX_ASSESSMENT_2026_06_12.md — the Tier-0 primitives the CEO
Dashboard (Phase P4) and BSC view depend on. Pure React + Tailwind + the
existing cn/tokens/Card/Button. NO new dependencies.

## New components (frontend/web/src/components/)
- RagChip.tsx        — RAG status chip (on_track/at_risk/off_track/no_data) over Badge.
- VarianceBadge.tsx  — actual-vs-target variance %, polarity-aware (invert for NPL/PAR).
- KpiTile.tsx        — executive KPI tile (Card + VarianceBadge + RagChip); dashboard workhorse.
- EmptyState.tsx     — standardized empty/no-results panel.
- ConfirmDialog.tsx  — accessible modal (portal + Escape + scroll-lock) for destructive
                       banking actions. First modal primitive in the system.

## Modified
- pages/Showcase.tsx — five new demo sections at /components so each primitive is
  inspectable (living design-system documentation; the existing pattern).

## Gate
- Scratch strict `tsc --noEmit` on the 5 new components -> 0 errors.
- Full `pnpm tsc --noEmit` (incl. Showcase in context) -> run by Josh before commit.

## Parity dimension closed
- UX / design-system (exec-grade primitive tier). Pipeline path untouched.

## Deferred
- P3b: <Chart> adapter — needs a charting dependency decision (recharts not
  currently installed). Separate batch.
