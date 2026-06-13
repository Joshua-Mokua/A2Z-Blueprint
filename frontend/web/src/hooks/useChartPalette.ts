// v10.548 Phase P Batch P3b — useChartPalette.
//
// Builds the chart palette from the live brand colors (/api/branding)
// plus the semantic series from tokens. Charts call this by default so
// brand identity flows through without any hard-coded hex.

import { useBranding } from '@/hooks/useBranding';
import { buildPalette, chartChrome } from '@/lib/chartTheme';

export function useChartPalette() {
  const { branding } = useBranding();
  return { palette: buildPalette(branding?.brand), chrome: chartChrome };
}
