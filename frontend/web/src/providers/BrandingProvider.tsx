// v10.495 — BrandingProvider for the React SPA.
//
// CONTRACT AMENDMENT (G46 → G381):
//
// The original App.tsx provider chain (per frontend/web/README.md
// G46) is:
//   QueryClient → Auth → WebSocket → BrowserRouter
//
// v10.495 amends this to:
//   QueryClient → Branding → Auth → WebSocket → BrowserRouter
//
// Branding is placed inside QueryClientProvider (so it could
// migrate to TanStack Query later) but before AuthProvider (so
// the future login page, which is unauthenticated, can still
// read branding to render the bank name and IP notice).
//
// This amendment is documented in CHANGELOG_v10.495.md and
// enforced by G381 (which replaces the phantom G46).

import {
  createContext, useEffect, useState, type ReactNode,
} from 'react';
import { fetchBranding } from '@/lib/api';
import type { Branding } from '@/types/branding';

interface BrandingContextValue {
  branding: Branding | null;
  loading: boolean;
  error: string | null;
}

// Fallback branding used while /api/branding is loading or if
// it fails. Mirrors the Ecobank corporate defaults baked into
// utils/config.py — keeps the UI alive and on-brand even if
// the backend is down.
const FALLBACK_BRANDING: Branding = {
  bank_name: 'Ecobank Kenya',
  app_name: 'EKE Blueprint',
  currency: 'KES',
  currency_symbol: 'KES',
  country: 'Kenya',
  regulator: 'CBK',
  regulator_full: '',
  core_banking_system: '',
  tax_authority: 'KRA',
  brand: {
    primary: '#1797ce',
    secondary: '#0e2440',
    accent: '#ffd200',
  },
  ip_notice:
    'Confidential · Authorised users only · All sessions are logged. ' +
    'This system is protected intellectual property. Unauthorised ' +
    'access or reproduction is strictly prohibited and may be ' +
    'subject to legal action.',
};

export const BrandingContext = createContext<BrandingContextValue>({
  branding: null,
  loading: true,
  error: null,
});

function applyBrandColors(brand: Branding['brand']): void {
  // Inject brand colors as CSS variables so Tailwind tokens like
  // `bg-brand-primary` resolve to the configured hex value.
  const root = document.documentElement;
  root.style.setProperty('--brand-primary', brand.primary);
  root.style.setProperty('--brand-secondary', brand.secondary);
  root.style.setProperty('--brand-accent', brand.accent);
}

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBranding] = useState<Branding | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBranding()
      .then((b) => {
        setBranding(b);
        setError(null);
        applyBrandColors(b.brand);
      })
      .catch((e) => {
        // Honest finding: backend not running, or branding endpoint
        // not yet wired. We log the error but continue with
        // fallback so the UI doesn't crash. Same discipline as
        // utils.config.py's "[Bank Name]" placeholder pattern.
        // eslint-disable-next-line no-console
        console.warn('Branding API unavailable, using fallback:', e);
        setBranding(FALLBACK_BRANDING);
        applyBrandColors(FALLBACK_BRANDING.brand);
        setError(String(e));
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <BrandingContext.Provider value={{ branding, loading, error }}>
      {children}
    </BrandingContext.Provider>
  );
}
