// v10.495 — useBranding hook.
//
// Returns the tenant branding from BrandingContext. Used by any
// React component that needs to display bank name, brand colors,
// or the IP notice.
//
// Usage:
//   const { branding, loading } = useBranding();
//   if (loading) return <Spinner />;
//   return <h1>{branding.app_name}</h1>;

import { useContext } from 'react';
import { BrandingContext } from '@/providers/BrandingProvider';

export function useBranding() {
  return useContext(BrandingContext);
}
