// v10.495 — Perform page placeholder.
// Real BSC scorecard view lands in a later batch consuming
// /api/v1/bsc/* and /api/bsc/summary endpoints.

import { useBranding } from '@/hooks/useBranding';

export function Perform() {
  const { branding } = useBranding();
  return (
    <div style={{ padding: 32 }}>
      <h1 style={{
        fontSize: 24, fontWeight: 700,
        color: branding?.brand.secondary ?? '#0e2440',
      }}>
        Perform — BSC Scorecard
      </h1>
      <p style={{ color: '#6b7280', marginTop: 8 }}>
        Placeholder. Wires to /api/v1/bsc in a later batch.
      </p>
    </div>
  );
}
