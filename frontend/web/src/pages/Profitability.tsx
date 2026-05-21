// v10.495 — Profitability page placeholder.
// Real PnL view lands in a later batch consuming
// /api/v1/profitability/* — backed by Volume Three engines.

import { useBranding } from '@/hooks/useBranding';

export function Profitability() {
  const { branding } = useBranding();
  return (
    <div style={{ padding: 32 }}>
      <h1 style={{
        fontSize: 24, fontWeight: 700,
        color: branding?.brand.secondary ?? '#0e2440',
      }}>
        Profitability — Customer + RM PnL
      </h1>
      <p style={{ color: '#6b7280', marginTop: 8 }}>
        Placeholder. Wires to /api/v1/profitability in a later batch.
      </p>
    </div>
  );
}
