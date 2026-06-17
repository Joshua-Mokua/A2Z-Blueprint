// v10.548 Phase P Batch P3b — shared chart theme.
//
// One visual language for every chart. Brand colors are supplied at
// runtime from /api/branding (see useChartPalette); only the NON-brand
// semantic series + chrome live here, sourced from tokens.ts — never a
// hard-coded brand hex (audit gates G381/G382).

import { semantic } from '@/lib/tokens';

/** Axis / grid / tick-text colors shared by all charts. */
export const chartChrome = {
  grid: semantic.gray[200],
  axis: semantic.gray[400],
  text: semantic.gray[500],
} as const;

/** Non-brand categorical series colors, used after the brand colors. */
export const semanticSeries: string[] = [
  semantic.info[500],
  semantic.success[500],
  semantic.warning[500],
  semantic.danger[500],
  semantic.gray[500],
];

/** RAG → color, for status-coded charts. */
export const ragColor = {
  on_track:  semantic.success[500],
  at_risk:   semantic.warning[500],
  off_track: semantic.danger[500],
  no_data:   semantic.gray[400],
} as const;

interface BrandColors {
  primary?: string;
  secondary?: string;
  accent?: string;
}

/** Full categorical palette: a vivid, semantically-neutral sweep so every
 *  category reads clearly. The brand primary leads (identity anchor); the
 *  vivid categorical series from tokens follow. No hard-coded brand hex here. */
export function buildPalette(brand?: BrandColors | null): string[] {
  const lead = brand?.primary ? [brand.primary] : [];
  return [...lead, ...semantic.categorical.filter((c) => c !== brand?.primary)];
}
